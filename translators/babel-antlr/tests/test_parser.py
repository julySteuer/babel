"""Tests for the ANTLR4 *parser* grammar encoder (babel_antlr.parser / babel_antlr.encoder).

Two notes on how the encoder's output maps onto the IR model:

- TOKEN_REF terminals (e.g. ``INT``) encode as BabelNonterminal, not BabelSymbol —
  only STRING_LITERAL terminals (e.g. ``'+'``) encode as BabelSymbol. This mirrors
  the fact that an uppercase token name is itself a reference to another
  (lexer) rule, same as a lowercase RULE_REF is a reference to a parser rule.
- encode() still returns raw antlr4 TerminalNode objects wherever the IR model
  declares a plain ``str`` (BabelNonterminal.nonterminal, BabelCharRange.beginning/end,
  and the BabelIr.production_rules keys) rather than calling .getText() on them.
  _helpers.normalize() walks the returned tree and replaces every such node with
  node.getText(), so tests can compare against BabelIr/BabelBlock/... built with
  plain string literals instead of depending on antlr4 object identity.

Lexer rules are out of scope here (see test_lexer.py); every grammar below
only defines parser rules and references undeclared token names, which the
ANTLR4 meta-grammar happily parses.
"""

import pytest
from babel_ir.model import (
    BabelBlock,
    BabelBlockList,
    BabelCharRange,
    BabelNonterminal,
    BabelNot,
    BabelOptional,
    BabelPlus,
    BabelProduction,
    BabelStar,
    BabelSymbol,
    BabelWildcard,
)

from ._helpers import encode_rule as _encode_rule


# ---------------------------------------------------------------------------
# Terminals & nonterminals
# ---------------------------------------------------------------------------


def test_token_ref_is_a_nonterminal_reference():
    production = _encode_rule("r: INT ;")
    assert production == BabelProduction(BabelBlockList([BabelBlock([BabelNonterminal("INT")])]))


def test_string_literal_is_a_symbol():
    production = _encode_rule("r: '+' ;")
    assert production == BabelProduction(BabelBlockList([BabelBlock([BabelSymbol("'+'")])]))


def test_eof_token_ref_is_a_nonterminal_reference():
    production = _encode_rule("r: EOF ;")
    assert production == BabelProduction(BabelBlockList([BabelBlock([BabelNonterminal("EOF")])]))


def test_rule_reference_nonterminal():
    production = _encode_rule("r: other ;")
    assert production == BabelProduction(BabelBlockList([BabelBlock([BabelNonterminal("other")])]))


# ---------------------------------------------------------------------------
# Sequences & alternatives
# ---------------------------------------------------------------------------


def test_sequence_of_elements_in_one_alternative():
    production = _encode_rule("r: expr EOF ;")
    assert production == BabelProduction(
        BabelBlockList([BabelBlock([BabelNonterminal("expr"), BabelNonterminal("EOF")])])
    )


def test_longer_sequence_of_elements():
    production = _encode_rule("r: expr PLUS expr ;")
    assert production == BabelProduction(
        BabelBlockList(
            [
                BabelBlock(
                    [BabelNonterminal("expr"), BabelNonterminal("PLUS"), BabelNonterminal("expr")]
                )
            ]
        )
    )


def test_multiple_alternatives_become_multiple_blocks():
    production = _encode_rule("r: INT | ID ;")
    assert production == BabelProduction(
        BabelBlockList([BabelBlock([BabelNonterminal("INT")]), BabelBlock([BabelNonterminal("ID")])])
    )


def test_labeled_alternatives_are_still_separate_blocks():
    production = _encode_rule(
        """
        r: INT # First
         | ID   # Second
         ;
        """
    )
    assert production == BabelProduction(
        BabelBlockList([BabelBlock([BabelNonterminal("INT")]), BabelBlock([BabelNonterminal("ID")])])
    )


# ---------------------------------------------------------------------------
# Wildcard / not-set / character range
# ---------------------------------------------------------------------------


def test_wildcard():
    production = _encode_rule("r: . ;")
    assert production == BabelProduction(BabelBlockList([BabelBlock([BabelWildcard()])]))


def test_not_set_single_terminal():
    production = _encode_rule("r: ~INT ;")
    assert production == BabelProduction(
        BabelBlockList([BabelBlock([BabelNot(BabelNonterminal("INT"))])])
    )


def test_not_set_block_of_alternatives():
    production = _encode_rule("r: ~(INT | ID) ;")
    assert production == BabelProduction(
        BabelBlockList(
            [BabelBlock([BabelNot(BabelBlock([BabelNonterminal("INT"), BabelNonterminal("ID")]))])]
        )
    )


def test_character_range_inside_not_set():
    production = _encode_rule("r: ~('a'..'z') ;")
    assert production == BabelProduction(
        BabelBlockList([BabelBlock([BabelNot(BabelBlock([BabelCharRange("'a'", "'z'")]))])])
    )


# ---------------------------------------------------------------------------
# Parenthesized groups — every alternative inside `( ... )` becomes its own
# BabelBlock (a sequence), and the group itself becomes a BabelBlockList
# (the set of alternatives), nested inside the outer BabelBlock as one atom.
# ---------------------------------------------------------------------------


def test_parenthesized_group_of_single_element_alternatives():
    production = _encode_rule("r: (INT | ID) ;")
    assert production == BabelProduction(
        BabelBlockList(
            [
                BabelBlock(
                    [
                        BabelBlockList(
                            [BabelBlock([BabelNonterminal("INT")]), BabelBlock([BabelNonterminal("ID")])]
                        )
                    ]
                )
            ]
        )
    )


def test_parenthesized_group_keeps_every_element_of_an_alternative():
    production = _encode_rule("r: (INT ID) ;")
    assert production == BabelProduction(
        BabelBlockList(
            [BabelBlock([BabelBlockList([BabelBlock([BabelNonterminal("INT"), BabelNonterminal("ID")])])])]
        )
    )


# ---------------------------------------------------------------------------
# EBNF suffixes
# ---------------------------------------------------------------------------


def test_optional_suffix():
    production = _encode_rule("r: INT? ;")
    assert production == BabelProduction(
        BabelBlockList([BabelBlock([BabelOptional(BabelNonterminal("INT"))])])
    )


def test_star_suffix():
    production = _encode_rule("r: INT* ;")
    assert production == BabelProduction(
        BabelBlockList([BabelBlock([BabelStar(BabelNonterminal("INT"))])])
    )


def test_plus_suffix():
    production = _encode_rule("r: INT+ ;")
    assert production == BabelProduction(
        BabelBlockList([BabelBlock([BabelPlus(BabelNonterminal("INT"))])])
    )


def test_labeled_element_is_encoded():
    production = _encode_rule("r: x=INT ;")
    assert production == BabelProduction(BabelBlockList([BabelBlock([BabelNonterminal("INT")])]))
