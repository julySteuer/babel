from typing import Type

from antlr4.tree.Tree import TerminalNodeImpl

from babel_antlr._generated.ANTLRv4Parser import ANTLRv4Parser
from babel_antlr.model.antlr_ir import (
    AntlrAtom,
    AntlrPlus,
    AntlrStar,
    AntlrOptional,
    AntlrNot,
    AntlrBlock,
    AntlrSymbol,
    AntlrCharRange,
    AntlrNonterminal,
    AntlrLexerNonterminal,
    AntlrRawRegex,
)
from babel_antlr.util import exec_first_valid

context_type = Type[AntlrNonterminal]

def encode_ebnf_suffix_with_inner(
    ebnf_suffix: ANTLRv4Parser.EbnfSuffixContext | None, inner: AntlrAtom
) -> AntlrAtom:
    if ebnf_suffix is None:
        return inner
    return exec_first_valid(
        (ebnf_suffix.PLUS(), lambda _: AntlrPlus(inner)),
        (ebnf_suffix.STAR(), lambda _: AntlrStar(inner)),
        (ebnf_suffix.QUESTION(0), lambda _: AntlrOptional(inner)), # Only if all fail check if one question mark was set (weird way to check i know)
    )

def make_symbol(terminal_node: TerminalNodeImpl) -> AntlrSymbol:
    return AntlrSymbol(process_symbol_str(terminal_node.getText()))

def process_symbol_str(symbol_str: str) -> str:
    return symbol_str[1:len(symbol_str) - 1]

def encode_terminal_def(terminal_def: ANTLRv4Parser.TerminalDefContext, context: context_type) -> AntlrAtom:
    return ( # TODO: Deal with the change and make caller decide the type
        context(terminal_def.TOKEN_REF().getText())
        if terminal_def.TOKEN_REF() is not None
        else make_symbol(terminal_def.STRING_LITERAL()) # Get text needs to be one layer firther down
    )

def encode_character_range(character_range: ANTLRv4Parser.CharacterRangeContext) -> AntlrCharRange:
    beginning = process_symbol_str(character_range.STRING_LITERAL(0).getText())
    end = process_symbol_str(character_range.STRING_LITERAL(1).getText())

    return AntlrCharRange(beginning, end)

def encode_set_element(set_element: ANTLRv4Parser.SetElementContext, context: context_type) -> AntlrAtom:
    token_ref = set_element.TOKEN_REF()
    string_literal = set_element.STRING_LITERAL()
    char_range = set_element.characterRange()
    lexer_char_set = set_element.LEXER_CHAR_SET()

    return exec_first_valid( # Use context to give the wrapping type of the nonterminal (AntlrLExerNonterminal or AntlrParserNonterminal)
        (token_ref, lambda ref: context(ref.getText())), # TODO: Rename Symbol to something that suggests one or more characters
        (string_literal, lambda lit: make_symbol(lit)),
        (char_range, encode_character_range),
        (lexer_char_set, lambda lcs: AntlrRawRegex(lcs.getText()))
    )

def _encode_block_set(block_set: ANTLRv4Parser.BlockSetContext, context: context_type) -> AntlrBlock:
    set_elements = block_set.setElement()

    encoded_block_sets = list(map(lambda elem: encode_set_element(elem, context), set_elements)) # TODO: Add BabelBlockSet as atom
    return AntlrBlock(encoded_block_sets)

def encode_not_set(not_set: ANTLRv4Parser.NotSetContext, context: context_type) -> AntlrNot:
    set_element = not_set.setElement()
    block_set = not_set.blockSet()

    return AntlrNot(
        exec_first_valid(
            (set_element, lambda elem: encode_set_element(elem, context)), (block_set, lambda elem: _encode_block_set(elem, context))
        )
    )