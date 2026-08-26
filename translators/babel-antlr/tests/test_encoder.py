"""Tests for babel_antlr.encoder.encode() on full, combined grammars.

Where test_parser.py and test_lexer.py each check one rule at a time in
isolation, this file runs whole grammars — parser rules and lexer rules
together, in the same file — through encode() and asserts on the full
resulting BabelIr. This exercises the parts individual-rule tests can't:
that _encode_rules dispatches each RuleSpecContext to the right encoder
(encode_lexer_rule vs encode_parser_rule), that every rule shows up exactly
once under its own name, and that rules referencing each other by name
(a parser rule using a token, a lexer rule using a fragment) come out as
plain BabelNonterminal(name) references rather than being resolved/inlined.

See _helpers.py for normalize(), needed because encode() still embeds raw
antlr4 TerminalNode objects in fields the IR model types as ``str``.
"""

from babel_ir.model import (
    BabelBlock,
    BabelBlockList,
    BabelCharRange,
    BabelIr,
    BabelNonterminal,
    BabelNot,
    BabelOptional,
    BabelPlus,
    BabelProduction,
    BabelStar,
    BabelSymbol,
)

from ._helpers import encode_grammar

ARITH_GRAMMAR = """
grammar Arith;

prog: expr EOF ;

expr: expr (PLUS | MINUS) term  # AddSub
    | term                      # ToTerm
    ;

term: term (STAR | SLASH) factor # MulDiv
    | factor                     # ToFactor
    ;

factor: INT
      | LPAREN expr RPAREN
      ;

INT: DIGIT+ ;
fragment DIGIT: '0'..'9' ;

PLUS: '+' ;
MINUS: '-' ;
STAR: '*' ;
SLASH: '/' ;
LPAREN: '(' ;
RPAREN: ')' ;

WS: (' ' | '\\t' | '\\r' | '\\n')+ -> skip ;
"""


def test_arith_grammar_produces_every_rule_exactly_once():
    ir = encode_grammar(ARITH_GRAMMAR)
    assert sorted(ir.production_rules) == sorted(
        [
            "prog",
            "expr",
            "term",
            "factor",
            "INT",
            "DIGIT",
            "PLUS",
            "MINUS",
            "STAR",
            "SLASH",
            "LPAREN",
            "RPAREN",
            "WS",
        ]
    )


def test_arith_grammar_full_ir():
    ir = encode_grammar(ARITH_GRAMMAR)

    plus_or_minus = BabelBlockList(
        [BabelBlock([BabelNonterminal("PLUS")]), BabelBlock([BabelNonterminal("MINUS")])]
    )
    star_or_slash = BabelBlockList(
        [BabelBlock([BabelNonterminal("STAR")]), BabelBlock([BabelNonterminal("SLASH")])]
    )

    expected = BabelIr(
        {
            "prog": BabelProduction(
                BabelBlockList([BabelBlock([BabelNonterminal("expr"), BabelNonterminal("EOF")])])
            ),
            # Alt labels (# AddSub / # ToTerm) carry no information in the IR today —
            # both alternatives just become separate BabelBlocks, same as unlabeled alts.
            "expr": BabelProduction(
                BabelBlockList(
                    [
                        BabelBlock(
                            [BabelNonterminal("expr"), plus_or_minus, BabelNonterminal("term")]
                        ),
                        BabelBlock([BabelNonterminal("term")]),
                    ]
                )
            ),
            "term": BabelProduction(
                BabelBlockList(
                    [
                        BabelBlock(
                            [BabelNonterminal("term"), star_or_slash, BabelNonterminal("factor")]
                        ),
                        BabelBlock([BabelNonterminal("factor")]),
                    ]
                )
            ),
            "factor": BabelProduction(
                BabelBlockList(
                    [
                        BabelBlock([BabelNonterminal("INT")]),
                        BabelBlock(
                            [
                                BabelNonterminal("LPAREN"),
                                BabelNonterminal("expr"),
                                BabelNonterminal("RPAREN"),
                            ]
                        ),
                    ]
                )
            ),
            # INT references the fragment DIGIT by name only — it is not inlined.
            "INT": BabelProduction(
                BabelBlockList([BabelBlock([BabelPlus(BabelNonterminal("DIGIT"))])])
            ),
            # fragment rules encode exactly like any other lexer rule.
            "DIGIT": BabelProduction(
                BabelBlockList([BabelBlock([BabelCharRange("'0'", "'9'")])])
            ),
            "PLUS": BabelProduction(BabelBlockList([BabelBlock([BabelSymbol("'+'")])])),
            "MINUS": BabelProduction(BabelBlockList([BabelBlock([BabelSymbol("'-'")])])),
            "STAR": BabelProduction(BabelBlockList([BabelBlock([BabelSymbol("'*'")])])),
            "SLASH": BabelProduction(BabelBlockList([BabelBlock([BabelSymbol("'/'")])])),
            "LPAREN": BabelProduction(BabelBlockList([BabelBlock([BabelSymbol("'('")])])),
            "RPAREN": BabelProduction(BabelBlockList([BabelBlock([BabelSymbol("')'")])])),
            # The `-> skip` lexer command is silently dropped, not encoded.
            "WS": BabelProduction(
                BabelBlockList(
                    [
                        BabelBlock(
                            [
                                BabelPlus(
                                    BabelBlockList(
                                        [
                                            BabelBlock([BabelSymbol("' '")]),
                                            BabelBlock([BabelSymbol("'\\t'")]),
                                            BabelBlock([BabelSymbol("'\\r'")]),
                                            BabelBlock([BabelSymbol("'\\n'")]),
                                        ]
                                    )
                                )
                            ]
                        )
                    ]
                )
            ),
        }
    )

    assert ir == expected


CSV_GRAMMAR = r"""
grammar Csv;

file: header row* EOF ;
header: row ;
row: field (COMMA field)* NEWLINE ;
field: STRING | TEXT | ;

STRING: '"' (~'"')* '"' ;
COMMA: ',' ;
NEWLINE: '\r'? '\n' ;
TEXT: (~[,\r\n])+ ;
"""


def test_csv_grammar_produces_every_rule_exactly_once():
    ir = encode_grammar(CSV_GRAMMAR)
    assert sorted(ir.production_rules) == sorted(
        ["file", "header", "row", "field", "STRING", "COMMA", "NEWLINE", "TEXT"]
    )


def test_csv_grammar_full_ir():
    ir = encode_grammar(CSV_GRAMMAR)

    expected = BabelIr(
        {
            "file": BabelProduction(
                BabelBlockList(
                    [
                        BabelBlock(
                            [
                                BabelNonterminal("header"),
                                BabelStar(BabelNonterminal("row")),
                                BabelNonterminal("EOF"),
                            ]
                        )
                    ]
                )
            ),
            "header": BabelProduction(BabelBlockList([BabelBlock([BabelNonterminal("row")])])),
            "row": BabelProduction(
                BabelBlockList(
                    [
                        BabelBlock(
                            [
                                BabelNonterminal("field"),
                                BabelStar(
                                    BabelBlockList(
                                        [
                                            BabelBlock(
                                                [BabelNonterminal("COMMA"), BabelNonterminal("field")]
                                            )
                                        ]
                                    )
                                ),
                                BabelNonterminal("NEWLINE"),
                            ]
                        )
                    ]
                )
            ),
            # A trailing empty alternative (`| ;`) becomes an empty BabelBlock.
            "field": BabelProduction(
                BabelBlockList(
                    [
                        BabelBlock([BabelNonterminal("STRING")]),
                        BabelBlock([BabelNonterminal("TEXT")]),
                        BabelBlock([]),
                    ]
                )
            ),
            "STRING": BabelProduction(
                BabelBlockList(
                    [
                        BabelBlock(
                            [
                                BabelSymbol("'\"'"),
                                BabelStar(
                                    BabelBlockList(
                                        [BabelBlock([BabelNot(BabelSymbol("'\"'"))])]
                                    )
                                ),
                                BabelSymbol("'\"'"),
                            ]
                        )
                    ]
                )
            ),
            "COMMA": BabelProduction(BabelBlockList([BabelBlock([BabelSymbol("','")])])),
            "NEWLINE": BabelProduction(
                BabelBlockList(
                    [BabelBlock([BabelOptional(BabelSymbol("'\\r'")), BabelSymbol("'\\n'")])]
                )
            ),
            # ~[,\r\n] is a not-set over a lexer char set, wrapped in a plus suffix.
            "TEXT": BabelProduction(
                BabelBlockList(
                    [
                        BabelBlock(
                            [
                                BabelPlus(
                                    BabelBlockList(
                                        [BabelBlock([BabelNot(BabelSymbol("[,\\r\\n]"))])]
                                    )
                                )
                            ]
                        )
                    ]
                )
            ),
        }
    )

    assert ir == expected
