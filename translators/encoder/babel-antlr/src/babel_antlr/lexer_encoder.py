from typing import Optional

from antlr4.tree.Tree import TerminalNode

from babel_antlr._generated.ANTLRv4Parser import ANTLRv4Parser
from babel_antlr.model.antlr_ir import (
    AntlrLexerProduction,
    AntlrBlockList,
    AntlrRawRegex,
    AntlrLexerWildcard,
    AntlrAtom,
    AntlrBlock,
    AntlrLexerNonterminal,
    AntlrAction,
    AntlrSkip,
    AntlrChannel,
    RegularAntlrLexerBlock,
    ActedAntlrLexerBlock,
)
from babel_antlr.shared_encoder import (
    encode_ebnf_suffix_with_inner,
    encode_terminal_def,
    encode_character_range,
    encode_not_set,
    process_symbol_str,
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
        (
            not_set,
            lambda elem: encode_not_set(
                elem, AntlrLexerNonterminal, RegularAntlrLexerBlock
            ),
        ),
        (lexer_char_set, _parse_lexer_char_set),
        (wildcard, lambda _: AntlrLexerWildcard()),
    )


def _encode_lexer_element(
    lexer_element: ANTLRv4Parser.LexerElementContext,
) -> AntlrAtom | None:
    lexer_atom = lexer_element.lexerAtom()
    lexer_block = lexer_element.lexerBlock()
    ebnf_suffix = lexer_element.ebnfSuffix()
    # Ignore actionBlock

    inner = exec_first_valid(
        (lexer_atom, _encode_lexer_atom), (lexer_block, _encode_lexer_block)
    )

    if inner is None:  # lone action / predicate, emits no text
        return None
    return encode_ebnf_suffix_with_inner(ebnf_suffix, inner)


def _get_channel(
    lexer_command: ANTLRv4Parser.LexerCommandContext,
) -> Optional[AntlrAction]:
    name = lexer_command.lexerCommandName().getText()
    match name:
        case "skip":
            return AntlrSkip()
        case "channel":
            return AntlrChannel()
        case _:
            return None


def _encode_lexer_alt(lexer_alt: ANTLRv4Parser.LexerAltContext) -> AntlrBlock:
    lexer_elements = lexer_alt.lexerElements().lexerElement()
    lexer_commands = lexer_alt.lexerCommands()
    elements = [
        encoded
        for encoded in map(_encode_lexer_element, lexer_elements)
        if encoded is not None
    ]
    if lexer_commands is None:
        return RegularAntlrLexerBlock(elements)
    lexer_commands = lexer_commands.lexerCommand()
    channel = [
        lexer_command
        for lexer_command in [_get_channel(c) for c in lexer_commands]
        if lexer_command is not None
    ]
    if not channel:
        return RegularAntlrLexerBlock(elements)
    return ActedAntlrLexerBlock(elements, channel[0])  # TODO: Make this clean


def _encode_lexer_alt_list(
    lexer_alt_list: ANTLRv4Parser.LexerAltListContext,
) -> AntlrBlockList:
    lexer_alts = lexer_alt_list.lexerAlt()
    return AntlrBlockList([_encode_lexer_alt(alt) for alt in lexer_alts])


def encode_lexer_rule(
    lexer_rule: ANTLRv4Parser.LexerRuleSpecContext,
) -> tuple[str, AntlrLexerProduction]:
    name = lexer_rule.TOKEN_REF().getText()
    lexer_alt_list = lexer_rule.lexerRuleBlock().lexerAltList()
    babel_block_list = _encode_lexer_alt_list(lexer_alt_list)
    return name, AntlrLexerProduction(babel_block_list)


__all__ = ["encode_lexer_rule"]
