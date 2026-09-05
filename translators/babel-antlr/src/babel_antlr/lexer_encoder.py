from babel_antlr._generated.ANTLRv4Parser import ANTLRv4Parser
from babel_antlr.shared_encoder import (
    encode_ebnf_suffix_with_inner,
    encode_terminal_def,
    encode_character_range,
    encode_not_set,
    encode_wildcard,
    ENCODE_WILDCARD_IN_EXEC_FIRST_VALID,
)
from babel_antlr.util import exec_first_valid
from babel_ir.model import BabelAtom, BabelBlock, BabelBlockList, BabelProduction, BabelSymbol


def _encode_lexer_block(lexer_block: ANTLRv4Parser.LexerBlockContext) -> BabelAtom:
    return _encode_lexer_alt_list(lexer_block.lexerAltList())

def _encode_lexer_atom(lexer_atom: ANTLRv4Parser.LexerAtomContext) -> BabelAtom:
    terminal_def = lexer_atom.terminalDef()
    character_range = lexer_atom.characterRange()
    not_set = lexer_atom.notSet()
    lexer_char_set = lexer_atom.LEXER_CHAR_SET()
    wildcard = lexer_atom.wildcard()

    return exec_first_valid(
        (terminal_def, encode_terminal_def),
        (character_range, encode_character_range),
        (not_set, encode_not_set),
        (lexer_char_set, lambda lcs: BabelSymbol(lcs.getText())),
        (wildcard, ENCODE_WILDCARD_IN_EXEC_FIRST_VALID)
    )

def _encode_lexer_element(lexer_element: ANTLRv4Parser.LexerElementContext) -> BabelAtom:
    lexer_atom = lexer_element.lexerAtom()
    lexer_block = lexer_element.lexerBlock()
    ebnf_suffix = lexer_element.ebnfSuffix()
    # Ignore actionBlock

    inner = exec_first_valid(
        (lexer_atom, _encode_lexer_atom),
        (lexer_block, _encode_lexer_block)
    )

    return encode_ebnf_suffix_with_inner(ebnf_suffix, inner)

def _encode_lexer_alt(lexer_alt: ANTLRv4Parser.LexerAltContext) -> BabelBlock:
    lexer_elements = lexer_alt.lexerElements().lexerElement()
    return BabelBlock([_encode_lexer_element(element) for element in lexer_elements])

def _encode_lexer_alt_list(lexer_alt_list: ANTLRv4Parser.LexerAltListContext) -> BabelBlockList:
    lexer_alts = lexer_alt_list.lexerAlt()
    return BabelBlockList([_encode_lexer_alt(alt) for alt in lexer_alts])

def encode_lexer_rule(lexer_rule: ANTLRv4Parser.LexerRuleSpecContext) -> tuple[str, BabelProduction]:
    name = lexer_rule.TOKEN_REF().getText()
    lexer_alt_list = lexer_rule.lexerRuleBlock().lexerAltList()
    babel_block_list = _encode_lexer_alt_list(lexer_alt_list)
    return name, BabelProduction(babel_block_list)

__all__ = ['encode_lexer_rule']