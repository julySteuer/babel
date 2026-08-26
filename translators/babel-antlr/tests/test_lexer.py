"""Tests for the ANTLR4 *lexer* grammar encoder (babel_antlr.lexer / babel_antlr.encoder).

Lexer rules share terminalDef/characterRange/notSet/ebnfSuffix encoding with
the parser encoder via babel_antlr.shared_encoder — see test_parser.py for
what those produce in general (TOKEN_REF -> BabelNonterminal, STRING_LITERAL
-> BabelSymbol, etc). This file exercises what's specific to *lexer* rules:

- a characterRange ('a'..'z') can appear directly as a lexer atom (in a
  parser rule it's only reachable inside a not-set, e.g. ~('a'..'z')).
- TOKEN_REF inside a lexer rule refers to another *lexer* rule.
- FRAGMENT rules encode the same way as regular lexer rules; the IR model
  carries no concept of "fragment" (a known simplification, not a bug).
- lexerCommands (e.g. `-> skip`) are silently dropped, not encoded at all.

See _helpers.py for normalize(), needed because encode() still embeds raw
antlr4 TerminalNode objects in fields the IR model types as ``str``.

Parser rules are out of scope here; every grammar below only defines lexer
rules (uppercase names).
"""

import pytest
from babel_ir.model import (
    BabelBlock,
    BabelBlockList,
    BabelCharRange,
    BabelNot,
    BabelOptional,
    BabelPlus,
    BabelProduction,
    BabelStar,
    BabelSymbol,
    BabelNonterminal,
    BabelWildcard,
)

from ._helpers import encode_rule


# ---------------------------------------------------------------------------
# Terminals & nonterminals
# ---------------------------------------------------------------------------


def test_string_literal_is_a_symbol():
    production = encode_rule("A: 'a' ;", rule_name="A")
    assert production == BabelProduction(BabelBlockList([BabelBlock([BabelSymbol("'a'")])]))


def test_token_ref_is_a_nonterminal_reference_to_another_lexer_rule():
    production = encode_rule("B: A ;", rule_name="B")
    assert production == BabelProduction(BabelBlockList([BabelBlock([BabelNonterminal("A")])]))


def test_character_range_is_usable_directly_as_a_lexer_atom():
    production = encode_rule("R: 'a'..'z' ;", rule_name="R")
    assert production == BabelProduction(BabelBlockList([BabelBlock([BabelCharRange("'a'", "'z'")])]))


def test_fragment_rule_encodes_like_a_normal_rule():
    production = encode_rule("fragment DIGIT: 'a'..'z' ;", rule_name="DIGIT")
    assert production == BabelProduction(BabelBlockList([BabelBlock([BabelCharRange("'a'", "'z'")])]))


# ---------------------------------------------------------------------------
# Sequences & alternatives
# ---------------------------------------------------------------------------


def test_sequence_of_elements():
    production = encode_rule("AB: 'a' 'b' ;", rule_name="AB")
    assert production == BabelProduction(
        BabelBlockList([BabelBlock([BabelSymbol("'a'"), BabelSymbol("'b'")])])
    )


def test_multiple_alternatives_become_multiple_blocks():
    production = encode_rule("BOOL: 'true' | 'false' ;", rule_name="BOOL")
    assert production == BabelProduction(
        BabelBlockList([BabelBlock([BabelSymbol("'true'")]), BabelBlock([BabelSymbol("'false'")])])
    )


# ---------------------------------------------------------------------------
# Not-set / grouped blocks / EBNF suffixes
# ---------------------------------------------------------------------------


def test_not_set_on_a_lexer_char_set():
    production = encode_rule("NOTD: ~[0-9] ;", rule_name="NOTD")
    assert production == BabelProduction(
        BabelBlockList([BabelBlock([BabelNot(BabelSymbol("[0-9]"))])])
    )


def test_not_set_on_character_range():
    production = encode_rule("NOTR: ~('a'..'z') ;", rule_name="NOTR")
    assert production == BabelProduction(
        BabelBlockList([BabelBlock([BabelNot(BabelBlock([BabelCharRange("'a'", "'z'")]))])])
    )


def test_parenthesized_lexer_block_with_plus_suffix():
    production = encode_rule("A: ('a' | 'b')+ ;", rule_name="A")
    assert production == BabelProduction(
        BabelBlockList(
            [
                BabelBlock(
                    [
                        BabelPlus(
                            BabelBlockList(
                                [BabelBlock([BabelSymbol("'a'")]), BabelBlock([BabelSymbol("'b'")])]
                            )
                        )
                    ]
                )
            ]
        )
    )


def test_optional_suffix():
    production = encode_rule("A: 'a'? ;", rule_name="A")
    assert production == BabelProduction(
        BabelBlockList([BabelBlock([BabelOptional(BabelSymbol("'a'"))])])
    )


def test_plus_suffix_on_character_range():
    production = encode_rule("NUM: 'a'..'z'+ ;", rule_name="NUM")
    assert production == BabelProduction(
        BabelBlockList([BabelBlock([BabelPlus(BabelCharRange("'a'", "'z'"))])])
    )


# ---------------------------------------------------------------------------
# lexerCommands (`-> skip`, `-> channel(HIDDEN)`, ...) are simply dropped
# ---------------------------------------------------------------------------


def test_lexer_command_is_ignored_not_encoded():
    production = encode_rule("WS: 'a'+ -> skip ;", rule_name="WS")
    assert production == BabelProduction(BabelBlockList([BabelBlock([BabelPlus(BabelSymbol("'a'"))])]))


def test_lexer_char_set_is_wrapped_in_a_symbol():
    production = encode_rule("WS: [ \\t\\r\\n] ;", rule_name="WS")
    assert production == BabelProduction(BabelBlockList([BabelBlock([BabelSymbol("[ \\t\\r\\n]")])]))


def test_wildcard():
    production = encode_rule("ANY: . ;", rule_name="ANY")
    assert production == BabelProduction(BabelBlockList([BabelBlock([BabelWildcard()])]))
