from antlr4.tree.Tree import TerminalNode

from babel_antlr._generated.ANTLRv4Parser import ANTLRv4Parser
from babel_antlr.model.antlr_ir import (
    AntlrLexerProduction,
    AntlrBlockList,
    AntlrRawRegex,
    AntlrLexerWildcard,
    RegularAntlrProduction,
    AntlrAtom,
    AntlrBlock,
    AntlrLexerNonterminal,
)
from babel_antlr.shared_encoder import (
    encode_ebnf_suffix_with_inner,
    encode_terminal_def,
    encode_character_range,
    encode_not_set,
)
from babel_antlr.util import exec_first_valid


def _encode_lexer_block(lexer_block: ANTLRv4Parser.LexerBlockContext) -> AntlrAtom:
    return _encode_lexer_alt_list(lexer_block.lexerAltList())

def _parse_lexer_char_set(lexer_char_set: TerminalNode) -> AntlrAtom:
    text = lexer_char_set.getText()
    return AntlrRawRegex(text)

def _encode_lexer_atom(lexer_atom: ANTLRv4Parser.LexerAtomContext) -> AntlrAtom:
    terminal_def = lexer_atom.terminalDef()
    character_range = lexer_atom.characterRange()
    not_set = lexer_atom.notSet()
    lexer_char_set = lexer_atom.LEXER_CHAR_SET()
    wildcard = lexer_atom.wildcard()

    return exec_first_valid(
        (terminal_def, lambda elem: encode_terminal_def(elem, AntlrLexerNonterminal)),
        (character_range, encode_character_range),
        (not_set, lambda elem: encode_not_set(elem, AntlrLexerNonterminal)),
        (lexer_char_set, _parse_lexer_char_set),
        (wildcard, lambda _: AntlrLexerWildcard())
    )

def _encode_lexer_element(lexer_element: ANTLRv4Parser.LexerElementContext) -> AntlrAtom:
    lexer_atom = lexer_element.lexerAtom()
    lexer_block = lexer_element.lexerBlock()
    ebnf_suffix = lexer_element.ebnfSuffix()
    # Ignore actionBlock

    inner = exec_first_valid(
        (lexer_atom, _encode_lexer_atom),
        (lexer_block, _encode_lexer_block)
    )

    return encode_ebnf_suffix_with_inner(ebnf_suffix, inner)

def _encode_lexer_alt(lexer_alt: ANTLRv4Parser.LexerAltContext) -> AntlrBlock:
    lexer_elements = lexer_alt.lexerElements().lexerElement()
    return AntlrBlock([_encode_lexer_element(element) for element in lexer_elements])

def _encode_lexer_alt_list(lexer_alt_list: ANTLRv4Parser.LexerAltListContext) -> AntlrBlockList:
    lexer_alts = lexer_alt_list.lexerAlt()
    return AntlrBlockList([_encode_lexer_alt(alt) for alt in lexer_alts])

def encode_lexer_rule(lexer_rule: ANTLRv4Parser.LexerRuleSpecContext) -> tuple[str, AntlrLexerProduction]:
    name = lexer_rule.TOKEN_REF().getText()
    lexer_alt_list = lexer_rule.lexerRuleBlock().lexerAltList()
    babel_block_list = _encode_lexer_alt_list(lexer_alt_list)
    return name, AntlrLexerProduction(RegularAntlrProduction(babel_block_list)) # If it is regular or acted upon shall be added next

__all__ = ['encode_lexer_rule']