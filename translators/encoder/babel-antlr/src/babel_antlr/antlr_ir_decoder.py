from functools import reduce

from babel_antlr.model.antlr_ir import (
    AntlrIr,
    ActedAntlrLexerBlock,
    AntlrAtom,
    AntlrBlock,
    AntlrBlockList,
    AntlrCharRange,
    AntlrLexerProduction,
    AntlrLexerWildcard,
    AntlrNonterminal,
    AntlrNot,
    AntlrNumRange,
    AntlrOptional,
    AntlrParserProduction,
    AntlrParserWildcard,
    AntlrPlus,
    AntlrProduction,
    AntlrRawRegex,
    AntlrStar,
    AntlrSymbol,
)
from babel_ir.model import (
    BabelAtom,
    BabelBlock,
    BabelBlockList,
    BabelCharRange,
    BabelIr,
    BabelNonterminal,
    BabelNumRange,
    BabelOptional,
    BabelPlus,
    BabelProduction,
    BabelRawRegex,
    BabelStar,
    BabelSymbol,
)
from babel_shared.name_generator import stateful_name_generator


# https://stackoverflow.com/questions/5920643/add-an-item-between-each-item-already-in-the-list
def _tween(seq, sep):
    return reduce(lambda r, v: r + [sep, v], seq[1:], seq[:1])


def _escape_char_class_char(char: str) -> str:
    return "\\" + char if char in "\\[]^-" else char


def _char_class_body(atom: AntlrAtom) -> str:
    match atom:
        case AntlrSymbol(terminal):
            return "".join(_escape_char_class_char(c) for c in terminal)
        case AntlrCharRange(beginning, end):
            return (
                f"{_escape_char_class_char(beginning)}-{_escape_char_class_char(end)}"
            )
        case AntlrNumRange(beginning, end):
            return f"{beginning}-{end}"
        case AntlrRawRegex(raw) if raw.startswith("[") and raw.endswith("]"):
            return raw[1:-1]
        case _:
            raise NotImplementedError(
                f"Cannot negate a {type(atom).__name__}; ~ is only supported over characters, ranges and char sets"
            )


def _decode_not(atom: AntlrNot) -> BabelAtom:
    inner = atom.atom
    elements = inner.atoms if isinstance(inner, AntlrBlock) else [inner]
    body = "".join(_char_class_body(element) for element in elements)
    return BabelRawRegex(f"[^{body}]")


class _Scope:
    """What differs between decoding a lexer rule and a parser rule."""

    def __init__(
        self,
        wildcard: BabelAtom,
        separator: BabelAtom | None = None,
        negation: bool = True,
    ):
        self.wildcard = wildcard
        self.separator = separator
        self.negation = negation


def _decode_block(block: AntlrBlock, scope: _Scope) -> BabelBlock:
    atoms = [_decode_atom(atom, scope) for atom in block.atoms]
    if scope.separator is not None:
        atoms = _tween(atoms, scope.separator)
    return BabelBlock(atoms)


def _decode_block_list(block_list: AntlrBlockList, scope: _Scope) -> BabelBlockList:
    return BabelBlockList([_decode_block(block, scope) for block in block_list.opts])


def _decode_atom(atom: AntlrAtom, scope: _Scope) -> BabelAtom:
    match atom:
        case AntlrSymbol(symbol):
            return BabelSymbol(symbol)
        case AntlrCharRange(beginning, end):
            return BabelCharRange(beginning, end)
        case AntlrNumRange(beginning, end):
            return BabelNumRange(beginning, end)
        case AntlrRawRegex(raw):
            return BabelRawRegex(raw)
        case AntlrNonterminal(nonterminal):
            return BabelNonterminal(nonterminal)
        case AntlrOptional(inner):
            return BabelOptional(_decode_atom(inner, scope))
        case AntlrStar(inner):
            return BabelStar(_decode_atom(inner, scope))
        case AntlrPlus(inner):
            return BabelPlus(_decode_atom(inner, scope))
        case AntlrLexerWildcard() | AntlrParserWildcard():
            return scope.wildcard
        case AntlrNot():
            if not scope.negation:
                raise NotImplementedError("~ is not supported in parser rules")
            return _decode_not(atom)
        case AntlrBlockList():
            return _decode_block_list(atom, scope)
        case AntlrBlock():
            return _decode_block(atom, scope)
        case _:
            raise NotImplementedError(f"Cannot decode {type(atom).__name__}")


def _lexer_scope() -> _Scope:
    return _Scope(BabelRawRegex("."))


def _generate_acted_productions(
    action_blocks: list[tuple[str, ActedAntlrLexerBlock]],
) -> dict[str, AntlrLexerProduction]:
    return {
        stateful_name_generator.generate_for(name): AntlrLexerProduction(
            AntlrBlockList([block])
        )
        for name, block in action_blocks
    }


def _lexer_productions(
    production_rules: dict[str, AntlrProduction],
) -> dict[str, AntlrProduction]:
    return {
        name: production
        for name, production in production_rules.items()
        if isinstance(production, AntlrLexerProduction)
    }


def _all_lexer_rule_options(
    lexer_productions: dict[str, AntlrProduction],
) -> list[BabelBlock]:
    scope = _lexer_scope()
    options: list[BabelBlock] = []
    for name, production in lexer_productions.items():
        opts = production.production.opts
        regular = [
            block for block in opts if not isinstance(block, ActedAntlrLexerBlock)
        ]
        if len(regular) == len(opts):
            options.append(BabelBlock([BabelNonterminal(name)]))
        else:
            options.extend(_decode_block(block, scope) for block in regular)
    return options


def _decode_lexer_rules(
    productions: dict[str, AntlrProduction],
) -> dict[str, BabelProduction]:
    scope = _lexer_scope()
    return {
        name: BabelProduction(_decode_block_list(production.production, scope))
        for name, production in productions.items()
    }


def _generate_choice_rule(
    base_name: str, options: list[BabelBlock]
) -> tuple[str, BabelProduction]:
    # TODO: Stateful name generator needs to be aware of all the names that exist to generate collision free names
    name = stateful_name_generator.generate_for(base_name)
    return name, BabelProduction(BabelBlockList(options))


def _decode_parser_rules(
    production_rules: dict[str, AntlrProduction], scope: _Scope
) -> dict[str, BabelProduction]:
    return {
        name: BabelProduction(_decode_block_list(production.production, scope))
        for name, production in production_rules.items()
        if isinstance(production, AntlrParserProduction)
    }


def decode_antlr_ir_to_babel_ir(antlr_ir: AntlrIr) -> BabelIr:
    production_rules = antlr_ir.production_rules

    acted_productions = _generate_acted_productions(antlr_ir.action_blocks)
    lexer_productions = _lexer_productions(production_rules)

    generated_rules: dict[str, BabelProduction] = {}

    # `.` in a parser rule matches any (non skipped) token. Skipped tokens may appear between any two elements
    wildcard: BabelAtom = BabelRawRegex(".")
    all_lexer_options = _all_lexer_rule_options(lexer_productions)
    if all_lexer_options:
        name, production = _generate_choice_rule("ALL_LEXER_RULES", all_lexer_options)
        generated_rules[name] = production
        wildcard = BabelNonterminal(name)

    separator = None
    if acted_productions:
        name, production = _generate_choice_rule(
            "ALL_ACTED_RULES",
            [BabelBlock([BabelNonterminal(rule)]) for rule in acted_productions],
        )
        generated_rules[name] = production
        separator = BabelStar(BabelNonterminal(name))

    parser_rules = _decode_parser_rules(
        production_rules, _Scope(wildcard, separator, negation=False)
    )
    lexer_rules = _decode_lexer_rules(lexer_productions | acted_productions)

    return BabelIr(parser_rules | generated_rules | lexer_rules)


__all__ = ["decode_antlr_ir_to_babel_ir"]
