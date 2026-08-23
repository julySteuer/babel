from babel_antlr._generated.ANTLRv4Parser import ANTLRv4Parser
from babel_antlr.util import exec_first_valid
from babel_ir.model import (
    BabelAtom,
    BabelBlock,
    BabelNonterminal,
    BabelNot,
    BabelOptional,
    BabelPlus,
    BabelProduction,
    BabelStar,
    BabelSymbol,
    BabelCharRange,
    BabelWildcard,
    BabelBlockList,
    BabelTerminal,
)


def _encode_labeled_element(
    labeled_element: ANTLRv4Parser.LabeledElementContext,
    ebnf_suffix: ANTLRv4Parser.EbnfSuffixContext | None,
) -> BabelAtom:
    print("No luck")
    pass

def _encode_ebnf(ebnf: ANTLRv4Parser.EbnfContext) -> BabelAtom:
    block = ebnf.block()

    inner = BabelBlockList(list(map(_encode_alternative, block.altList().alternative()))) # Parse this to a BabelBlockSet so inline Options
    if ebnf.blockSuffix() is not None:
        suffix = ebnf.blockSuffix().ebnfSuffix()
        return _encode_ebnf_suffix_with_inner(suffix, inner)
    return inner

def _encode_terminal_def(terminal_def: ANTLRv4Parser.TerminalDefContext) -> BabelAtom:
    return (
        BabelNonterminal(terminal_def.TOKEN_REF().getText())
        if terminal_def.TOKEN_REF() is not None
        else BabelSymbol(terminal_def.STRING_LITERAL().getText())
    )


def _encode_ruleref(ruleref: ANTLRv4Parser.RulerefContext) -> BabelNonterminal:
    content = (
        ruleref.RULE_REF()
    )  # I suppose non terminal here but who knows. Testing this is absolutly horrible
    # Ignore Action block and elementOptions for now
    return BabelNonterminal(content)

def _encode_character_range(character_range: ANTLRv4Parser.CharacterRangeContext) -> BabelCharRange:
    beginning = character_range.STRING_LITERAL(0)
    end = character_range.STRING_LITERAL(1)

    return BabelCharRange(beginning, end)

def _encode_set_element(set_element: ANTLRv4Parser.SetElementContext) -> BabelAtom:
    token_ref = set_element.TOKEN_REF()
    string_literal = set_element.STRING_LITERAL()
    char_range = set_element.characterRange()
    lexer_char_set = set_element.LEXER_CHAR_SET()

    return exec_first_valid(
        (token_ref, lambda ref: BabelNonterminal(ref)), # TODO: Rename Symbol to something that suggests one or more characters
        (string_literal, lambda lit: BabelSymbol(lit)),
        (char_range, _encode_character_range),
        (lexer_char_set, lambda lcs: BabelSymbol(lexer_char_set))
    )

def _encode_block_set(block_set: ANTLRv4Parser.BlockSetContext) -> BabelBlock:
    set_elements = block_set.setElement()

    encoded_block_sets = list(map(_encode_set_element, set_elements)) # TODO: Add BabelBlockSet as atom
    return BabelBlock(encoded_block_sets)


def _encode_not_set(not_set: ANTLRv4Parser.NotSetContext) -> BabelAtom:
    set_element = not_set.setElement()
    block_set = not_set.blockSet()

    return BabelNot(
        exec_first_valid(
            (set_element, _encode_set_element), (block_set, _encode_block_set)
        )
    )


def _encode_wildcard() -> BabelWildcard:
    # Again ignore options in the beginning
    return BabelWildcard()


def _encode_ebnf_suffix_with_inner(
    ebnf_suffix: ANTLRv4Parser.EbnfSuffixContext, inner: BabelAtom
) -> BabelAtom:
    return exec_first_valid(
        (ebnf_suffix.PLUS(), lambda _: BabelPlus(inner)),
        (ebnf_suffix.STAR(), lambda _: BabelStar(inner)),
        (ebnf_suffix.QUESTION(0), lambda _: BabelOptional(inner)), # Only if all fail check if one question mark was set (weird way to check i know)
    )


def _encode_atom(
    atom: ANTLRv4Parser.AtomContext, ebnf_suffix: ANTLRv4Parser.EbnfSuffixContext | None
) -> BabelAtom:
    terminal_def = atom.terminalDef()
    ruleref = atom.ruleref()
    not_set = atom.notSet()
    wildcard = atom.wildcard()

    inner = exec_first_valid(
        (terminal_def, _encode_terminal_def),
        (ruleref, _encode_ruleref),
        (not_set, _encode_not_set),
        (wildcard, lambda _: _encode_wildcard()),
    )

    if ebnf_suffix is not None:
        return _encode_ebnf_suffix_with_inner(ebnf_suffix, inner)
    return inner


def _encode_element(element: ANTLRv4Parser.ElementContext) -> BabelAtom: # Have to rethink if this is a good idea to return a Atom at this stage
    labeled_element = element.labeledElement()
    atom = element.atom()
    ebnf = element.ebnf()

    ebnf_suffix_opt = element.ebnfSuffix()
    # Ignore actionBlock bcs currently not needed

    return exec_first_valid(
        (atom, lambda at: _encode_atom(at, ebnf_suffix_opt)),
        (labeled_element, lambda le: _encode_labeled_element(le, ebnf_suffix_opt)),
        (ebnf, _encode_ebnf),
    )

def _encode_alternative(alternative: ANTLRv4Parser.AlternativeContext) -> BabelBlock:
    return BabelBlock(list(map(lambda elem: _encode_element(elem), alternative.element())))

def _encode_labeled_alt(alt: ANTLRv4Parser.LabeledAltContext) -> BabelBlock:
    return _encode_alternative(alt.alternative())

def _encode_alt_list(alt_list: ANTLRv4Parser.RuleAltListContext) -> list[BabelBlock]:
    return list(
        map(lambda alt: _encode_labeled_alt(alt), alt_list.labeledAlt())
    )  # Gets all alts even first one


def encode_parser_rule(
    parser_rule: ANTLRv4Parser.ParserRuleSpecContext,
) -> tuple[str, BabelProduction]:
    name = parser_rule.RULE_REF()  # Lets hope this casts to a string
    return name, BabelProduction(BabelBlockList(_encode_alt_list(parser_rule.ruleBlock().ruleAltList())))
