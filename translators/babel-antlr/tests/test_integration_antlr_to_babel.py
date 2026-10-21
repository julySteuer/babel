"""Integration: ANTLR grammar source -> AntlrIr -> BabelIr, using the real parser and both translation steps."""

import pytest

from babel_antlr.antlr_ir_decoder import decode_antlr_ir_to_babel_ir
from babel_ir.model import (
    BabelBlock,
    BabelBlockList,
    BabelCharRange,
    BabelIr,
    BabelNonterminal,
    BabelOptional,
    BabelPlus,
    BabelProduction,
    BabelRawRegex,
    BabelStar,
    BabelSymbol,
)
from babel_shared.name_generator import stateful_name_generator

from ._helpers import to_antlr_ir

GRAMMAR = """grammar Calc;

prog: stmt+ EOF ;
stmt: ID '=' expr ';' | expr ';' ;
expr: term (('+' | '-') term)* ;
term: INT | ID | '(' expr ')' | . ;

ID: [a-z]+ ;
INT: '0'..'9'+ ;
STRING: '"' ~["\\\\]* '"' ;
WS: ' ' -> skip | '\\t' ;
COMMENT: '#' ~[\\n]* -> skip ;
"""


@pytest.fixture(autouse=True)
def reset_name_generator():
    stateful_name_generator.counter.clear()


def prod(*alts: list) -> BabelProduction:
    return BabelProduction(BabelBlockList([BabelBlock(a) for a in alts]))


def nt(name: str) -> BabelNonterminal:
    return BabelNonterminal(name)


def test_antlr_grammar_translates_to_babel_ir():
    babel_ir = decode_antlr_ir_to_babel_ir(to_antlr_ir(GRAMMAR))

    skip = BabelStar(nt("ALL_ACTED_RULES_0__GENERATED"))
    plus_minus = BabelBlockList([BabelBlock([BabelSymbol("+")]), BabelBlock([BabelSymbol("-")])])
    tail = BabelBlockList([BabelBlock([plus_minus, skip, nt("term")])])

    assert babel_ir == BabelIr(
        {
            # parser rules, with skipped tokens allowed between every two elements
            "prog": prod([BabelPlus(nt("stmt")), skip, nt("EOF")]),
            "stmt": prod(
                [nt("ID"), skip, BabelSymbol("="), skip, nt("expr"), skip, BabelSymbol(";")],
                [nt("expr"), skip, BabelSymbol(";")],
            ),
            "expr": prod([nt("term"), skip, BabelStar(tail)]),
            "term": prod(
                [nt("INT")],
                [nt("ID")],
                [BabelSymbol("("), skip, nt("expr"), skip, BabelSymbol(")")],
                [nt("ALL_LEXER_RULES_0__GENERATED")],
            ),
            # `.` in the parser: every token the lexer hands over (no skipped ones)
            "ALL_LEXER_RULES_0__GENERATED": prod(
                [nt("ID")], [nt("INT")], [nt("STRING")], [BabelSymbol("\t")]
            ),
            # skipped alternatives, one rule each
            "ALL_ACTED_RULES_0__GENERATED": prod([nt("WS_0__GENERATED")], [nt("COMMENT_0__GENERATED")]),
            # lexer rules: complete, so references to e.g. WS still match ' '
            "ID": prod([BabelPlus(BabelRawRegex("[a-z]"))]),
            "INT": prod([BabelPlus(BabelCharRange("0", "9"))]),
            "STRING": prod(
                [BabelSymbol('"'), BabelStar(BabelRawRegex('[^"\\\\]')), BabelSymbol('"')]
            ),
            "WS": prod([BabelSymbol(" ")], [BabelSymbol("\t")]),
            "COMMENT": prod([BabelSymbol("#"), BabelStar(BabelRawRegex("[^\\n]"))]),
            "WS_0__GENERATED": prod([BabelSymbol(" ")]),
            "COMMENT_0__GENERATED": prod([BabelSymbol("#"), BabelStar(BabelRawRegex("[^\\n]"))]),
        }
    )
