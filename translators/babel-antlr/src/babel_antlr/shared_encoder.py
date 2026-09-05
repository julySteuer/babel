from babel_antlr._generated.ANTLRv4Parser import ANTLRv4Parser
from babel_antlr.util import exec_first_valid
from babel_ir.model import (
    BabelAtom,
    BabelPlus,
    BabelStar,
    BabelOptional,
    BabelNonterminal,
    BabelSymbol,
    BabelNot,
    BabelCharRange,
    BabelBlock,
    BabelWildcard,
)


def encode_ebnf_suffix_with_inner(
    ebnf_suffix: ANTLRv4Parser.EbnfSuffixContext | None, inner: BabelAtom
) -> BabelAtom:
    if ebnf_suffix is None:
        return inner
    return exec_first_valid(
        (ebnf_suffix.PLUS(), lambda _: BabelPlus(inner)),
        (ebnf_suffix.STAR(), lambda _: BabelStar(inner)),
        (ebnf_suffix.QUESTION(0), lambda _: BabelOptional(inner)), # Only if all fail check if one question mark was set (weird way to check i know)
    )

def encode_terminal_def(terminal_def: ANTLRv4Parser.TerminalDefContext) -> BabelAtom:
    return (
        BabelNonterminal(terminal_def.TOKEN_REF().getText())
        if terminal_def.TOKEN_REF() is not None
        else BabelSymbol(terminal_def.STRING_LITERAL().getText())
    )

def encode_character_range(character_range: ANTLRv4Parser.CharacterRangeContext) -> BabelCharRange:
    beginning = character_range.STRING_LITERAL(0)
    end = character_range.STRING_LITERAL(1)

    return BabelCharRange(beginning.getText(), end.getText())

def encode_set_element(set_element: ANTLRv4Parser.SetElementContext) -> BabelAtom:
    token_ref = set_element.TOKEN_REF()
    string_literal = set_element.STRING_LITERAL()
    char_range = set_element.characterRange()
    lexer_char_set = set_element.LEXER_CHAR_SET()

    return exec_first_valid(
        (token_ref, lambda ref: BabelNonterminal(ref.getText())), # TODO: Rename Symbol to something that suggests one or more characters
        (string_literal, lambda lit: BabelSymbol(lit.getText())),
        (char_range, encode_character_range),
        (lexer_char_set, lambda lcs: BabelSymbol(lcs.getText()))
    )

def _encode_block_set(block_set: ANTLRv4Parser.BlockSetContext) -> BabelBlock:
    set_elements = block_set.setElement()

    encoded_block_sets = list(map(encode_set_element, set_elements)) # TODO: Add BabelBlockSet as atom
    return BabelBlock(encoded_block_sets)

def encode_not_set(not_set: ANTLRv4Parser.NotSetContext) -> BabelAtom:
    set_element = not_set.setElement()
    block_set = not_set.blockSet()

    return BabelNot(
        exec_first_valid(
            (set_element, encode_set_element), (block_set, _encode_block_set)
        )
    )

def encode_wildcard() -> BabelWildcard:
    # Again ignore options in the beginning
    return BabelWildcard()

ENCODE_WILDCARD_IN_EXEC_FIRST_VALID = lambda _: encode_wildcard()