import re
from functools import reduce
from typing import Callable

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


def _alternatives_body(
    opts: list[AntlrBlock], productions: dict, seen: frozenset
) -> str:
    """The body of a char class matching what any alternative matches. Every alternative must be a single character matcher."""
    bodies = []
    for opt in opts:
        if isinstance(opt, ActedAntlrLexerBlock) or len(opt.atoms) != 1:
            raise NotImplementedError(
                "Cannot negate a rule that does not match a single character"
            )
        bodies.append(_char_class_body(opt.atoms[0], productions, seen))
    return "".join(bodies)


def _char_class_body(
    atom: AntlrAtom, productions: dict, seen: frozenset = frozenset()
) -> str:
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
        case AntlrNonterminal(name) if name in productions and name not in seen:
            # A lexer rule (usually a fragment) that stands for a set of single characters
            return _alternatives_body(
                productions[name].production.opts, productions, seen | {name}
            )
        case AntlrBlockList(opts):
            return _alternatives_body(opts, productions, seen)
        case _:
            raise NotImplementedError(
                f"Cannot negate a {type(atom).__name__}; ~ is only supported over characters, ranges, char sets and lexer rules matching a single character"
            )


def _negated_elements(atom: AntlrNot) -> list[AntlrAtom]:
    inner = atom.atom
    return inner.atoms if isinstance(inner, AntlrBlock) else [inner]


def _decode_lexer_not(atom: AntlrNot, productions: dict) -> BabelAtom:
    body = "".join(
        _char_class_body(element, productions) for element in _negated_elements(atom)
    )
    return BabelRawRegex(f"[^{body}]")


def _literal_tokens(productions: dict[str, AntlrProduction]) -> dict[str, str]:
    """Maps a literal to the lexer rule that is defined as exactly that literal (`SEMI: ';' ;`)."""
    literals: dict[str, str] = {}
    for name, production in productions.items():
        opts = production.production.opts
        if len(opts) != 1 or isinstance(opts[0], ActedAntlrLexerBlock):
            continue
        if len(opts[0].atoms) == 1 and isinstance(opts[0].atoms[0], AntlrSymbol):
            literals.setdefault(opts[0].atoms[0].terminal, name)
    return literals


def _parser_literals(atom: AntlrAtom) -> set[str]:
    match atom:
        case AntlrSymbol(literal):
            return {literal}
        case AntlrBlockList(opts):
            return set().union(*(_parser_literals(opt) for opt in opts))
        case AntlrBlock(atoms):
            return set().union(*(_parser_literals(a) for a in atoms))
        case AntlrOptional(inner) | AntlrStar(inner) | AntlrPlus(inner):
            return _parser_literals(inner)
        case _:
            return set()


class _TokenComplements:
    """Decodes `~` in parser rules: any token except the negated ones.

    Every distinct set of negated tokens gets one generated choice rule over the remaining tokens.
    Tokens are the lexer rules plus the literals used in parser rules that no lexer rule is defined as (ANTLR's implicit tokens).
    """

    def __init__(
        self, lexer_productions: dict[str, AntlrProduction], parser_literals: set[str]
    ):
        self.lexer_productions = lexer_productions
        self.literals = _literal_tokens(lexer_productions)
        self.implicit_literals = parser_literals - self.literals.keys()
        self.generated_rules: dict[str, BabelProduction] = {}
        self._rule_by_excluded: dict[tuple[frozenset, frozenset], BabelAtom] = {}

    def _excluded(self, element: AntlrAtom) -> tuple[str | None, str | None]:
        """The (lexer rule name, implicit literal) a negated element stands for; one of the two is None."""
        match element:
            case AntlrNonterminal(name):
                if name not in self.lexer_productions:
                    raise NotImplementedError(
                        f"Cannot negate {name}; it is not a lexer rule of the given grammars"
                    )
                return name, None
            case AntlrSymbol(literal):
                return self.literals.get(literal), literal
            case _:
                raise NotImplementedError(
                    f"Cannot negate a {type(element).__name__} in a parser rule; ~ is only supported over tokens and literals"
                )

    def __call__(self, atom: AntlrNot) -> BabelAtom:
        excluded = [self._excluded(e) for e in _negated_elements(atom)]
        tokens = frozenset(token for token, _ in excluded if token is not None)
        literals = frozenset(literal for token, literal in excluded if token is None)
        if (tokens, literals) not in self._rule_by_excluded:
            options = _all_lexer_rule_options(self.lexer_productions, tokens)
            options += [
                BabelBlock([BabelSymbol(literal)])
                for literal in sorted(self.implicit_literals - literals)
            ]
            if not options:
                raise NotImplementedError("~ excludes every token of the grammars")
            name, production = _generate_choice_rule("NOT_LEXER_RULES", options)
            self.generated_rules[name] = production
            self._rule_by_excluded[(tokens, literals)] = BabelNonterminal(name)
        return self._rule_by_excluded[(tokens, literals)]


class _Scope:
    """What differs between decoding a lexer rule and a parser rule."""

    def __init__(
        self,
        wildcard: BabelAtom,
        negate: Callable[[AntlrNot], BabelAtom],
        separator: BabelAtom | None = None,
    ):
        self.wildcard = wildcard
        self.negate = negate
        self.separator = separator


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
            return scope.negate(atom)
        case AntlrBlockList():
            return _decode_block_list(atom, scope)
        case AntlrBlock():
            return BabelBlockList([_decode_block(atom, scope)])
        case _:
            raise NotImplementedError(f"Cannot decode {type(atom).__name__}")


def _lexer_scope(lexer_productions: dict[str, AntlrProduction]) -> _Scope:
    return _Scope(
        BabelRawRegex("."), lambda atom: _decode_lexer_not(atom, lexer_productions)
    )


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
    excluded: frozenset[str] = frozenset(),
) -> list[BabelBlock]:
    scope = _lexer_scope(lexer_productions)
    options: list[BabelBlock] = []
    for name, production in lexer_productions.items():
        if name in excluded:
            continue
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
    all_lexer_productions: dict[str, AntlrProduction],
) -> dict[str, BabelProduction]:
    scope = _lexer_scope(all_lexer_productions)
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


WHITESPACE_MODES = ("auto", "space", "none", "skipped")


def _skips_character(
    acted_productions: dict[str, AntlrProduction],
    lexer_productions: dict,
    character: str,
) -> bool:
    """Whether a skipped / hidden lexer rule can match exactly `character`, e.g. `WS: [ \\t\\r\\n]+ -> skip`."""
    for production in acted_productions.values():
        for block in production.production.opts:
            atoms = block.atoms
            while len(atoms) == 1:
                inner = atoms[0]
                if isinstance(inner, (AntlrPlus, AntlrStar, AntlrOptional)):
                    atoms = [inner.atom]
                elif isinstance(inner, AntlrBlock):
                    atoms = inner.atoms
                else:
                    break
            if len(atoms) != 1:
                continue
            try:
                body = _char_class_body(atoms[0], lexer_productions)
                if re.fullmatch(f"[{body}]", character):
                    return True
            except (NotImplementedError, re.error):
                continue  # not a single character matcher
    return False


def _lexer_regex(atom: AntlrAtom, productions: dict, seen: frozenset = frozenset()) -> str:
    """A regular expression for what a lexer atom matches. Raises NotImplementedError for what it cannot express
    (recursive rules, numeric ranges, ...)."""
    match atom:
        case AntlrSymbol(terminal):
            return re.escape(terminal)
        case AntlrCharRange(beginning, end):
            return f"[{_escape_char_class_char(beginning)}-{_escape_char_class_char(end)}]"
        case AntlrRawRegex(raw):
            return f"(?:{raw})"
        case AntlrLexerWildcard():
            return "[\\s\\S]"
        case AntlrNot():
            body = "".join(
                _char_class_body(element, productions) for element in _negated_elements(atom)
            )
            return f"[^{body}]"
        case AntlrNonterminal(name) if name in productions and name not in seen:
            return _lexer_regex(productions[name].production, productions, seen | {name})
        case AntlrOptional(inner):
            return f"(?:{_lexer_regex(inner, productions, seen)})?"
        case AntlrStar(inner):
            return f"(?:{_lexer_regex(inner, productions, seen)})*"
        case AntlrPlus(inner):
            return f"(?:{_lexer_regex(inner, productions, seen)})+"
        case AntlrBlockList(opts):
            return "(?:" + "|".join(_lexer_regex(opt, productions, seen) for opt in opts) + ")"
        case AntlrBlock(atoms):
            return "".join(_lexer_regex(a, productions, seen) for a in atoms)
        case _:
            raise NotImplementedError(type(atom).__name__)


def _referenced_names(atom: AntlrAtom) -> set[str]:
    match atom:
        case AntlrNonterminal(name):
            return {name}
        case AntlrOptional(inner) | AntlrStar(inner) | AntlrPlus(inner):
            return _referenced_names(inner)
        case AntlrBlockList(opts):
            return set().union(*(_referenced_names(opt) for opt in opts))
        case AntlrBlock(atoms):
            return set().union(*(_referenced_names(a) for a in atoms))
        case AntlrNot(inner):
            return _referenced_names(inner)
        case _:
            return set()


def _token_can_match(lexer_productions: dict, character: str) -> bool:
    """Whether a lexer rule that is not skipped can match just `character` (or a CRLF), so that the character
    is a token of its own and not skipped. Anything that cannot be analysed counts as a match.

    Only rules no other lexer rule refers to are looked at: the IR does not say which rules are fragments, and
    a fragment matters through the tokens that use it."""
    referenced = set().union(
        *(
            _referenced_names(p.production) - {name}
            for name, p in lexer_productions.items()
        )
    )
    for name, production in lexer_productions.items():
        if name in referenced:
            continue
        for block in production.production.opts:
            if isinstance(block, ActedAntlrLexerBlock):
                continue
            try:
                pattern = _lexer_regex(block, lexer_productions)
                if any(re.fullmatch(pattern, text) for text in (character, "\r" + character)):
                    return True
            except (NotImplementedError, re.error, RecursionError):
                return True
    return False


def _plain_separator(
    whitespace: str,
    acted_productions: dict[str, AntlrProduction],
    lexer_productions: dict,
) -> BabelAtom | None:
    """The atom put between two parser elements for every mode but "skipped", None if there is none."""
    if not acted_productions or whitespace in ("none", "skipped"):
        return None
    if whitespace == "space":
        return BabelSymbol(" ")
    if whitespace == "auto":
        # a newline ends tokens that run to the end of the line, but only if it really is skipped:
        # `EOL: '\\n'` before `WS: [ \\n] -> skip` or `Text: ~[<]+` make it a token (or part of one)
        if _skips_character(
            acted_productions, lexer_productions, "\n"
        ) and not _token_can_match(lexer_productions, "\n"):
            return BabelSymbol("\n")
        if _skips_character(acted_productions, lexer_productions, " "):
            return BabelSymbol(" ")
        return None
    return None


def decode_antlr_irs_to_babel_irs(
    antlr_irs: list[AntlrIr], whitespace: str = "auto"
) -> BabelIr:
    """Decodes grammars that belong together, e.g. a parser and its lexer in separate files, into one BabelIr.

    What a parser rule needs from the lexer (the `.` wildcard, the skipped tokens between elements and the
    tokens `~` ranges over) is taken from all the grammars, not just the one the rule is in.
    If several grammars define a rule of the same name, the last one wins.

    `whitespace` decides what goes between two parser elements when the grammars skip some tokens
    (`-> skip`, `-> channel(HIDDEN)`); without skipped tokens nothing is added:
      - "auto" (default): a newline if some skipped rule can match one, else a space if one can match that, else
        nothing. A newline ends tokens that run to the end of the line (`XFIELD: 'X:' ~[\\r\\n]*`), which a space
        does not
      - "space": always one space, so tokens never merge and no comment can swallow the next token
      - "none": nothing, the elements are concatenated
      - "skipped": any number of skipped tokens (whitespace, comments), which is how ANTLR lexes the input but
        generates unseparated keywords and line comments without their newline
    """
    acted_productions: dict[str, AntlrProduction] = {}
    lexer_productions: dict[str, AntlrProduction] = {}
    parser_literals: set[str] = set()
    for antlr_ir in antlr_irs:
        acted = _generate_acted_productions(antlr_ir.action_blocks)
        acted_productions |= acted
        lexer_productions |= _lexer_productions(antlr_ir.production_rules)
        for production in antlr_ir.production_rules.values():
            if isinstance(production, AntlrParserProduction):
                parser_literals |= _parser_literals(production.production)

    generated_rules: dict[str, BabelProduction] = {}

    # `.` in a parser rule matches any (non skipped) token. Skipped tokens may appear between any two elements
    wildcard: BabelAtom = BabelRawRegex(".")
    all_lexer_options = _all_lexer_rule_options(lexer_productions)
    if all_lexer_options:
        name, production = _generate_choice_rule("ALL_LEXER_RULES", all_lexer_options)
        generated_rules[name] = production
        wildcard = BabelNonterminal(name)

    if whitespace not in WHITESPACE_MODES:
        raise ValueError(f"whitespace must be one of {WHITESPACE_MODES}, got {whitespace!r}")
    separator = _plain_separator(whitespace, acted_productions, lexer_productions)
    if acted_productions and whitespace == "skipped":
        name, production = _generate_choice_rule(
            "ALL_ACTED_RULES",
            [BabelBlock([BabelNonterminal(rule)]) for rule in acted_productions],
        )
        generated_rules[name] = production
        separator = BabelStar(BabelNonterminal(name))

    token_complements = _TokenComplements(lexer_productions, parser_literals)
    scope = _Scope(wildcard, token_complements, separator)

    rules: dict[str, BabelProduction] = {}
    for antlr_ir in antlr_irs:
        rules |= _decode_parser_rules(antlr_ir.production_rules, scope)
    rules |= _decode_lexer_rules(
        lexer_productions | acted_productions, lexer_productions
    )

    return BabelIr(rules | generated_rules | token_complements.generated_rules)


def decode_antlr_ir_to_babel_ir(
    antlr_ir: AntlrIr, whitespace: str = "auto"
) -> BabelIr:
    return decode_antlr_irs_to_babel_irs([antlr_ir], whitespace)


__all__ = ["decode_antlr_ir_to_babel_ir", "decode_antlr_irs_to_babel_irs"]
