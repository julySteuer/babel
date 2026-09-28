from babel_antlr.model.antlr_ir import (
    AntlrBlock,
    AntlrBlockList,
    AntlrCharRange,
    AntlrIr,
    AntlrLexerNonterminal,
    AntlrLexerProduction,
    AntlrLexerWildcard,
    AntlrNot,
    AntlrOptional,
    AntlrParserNonterminal,
    AntlrParserProduction,
    AntlrParserWildcard,
    AntlrPlus,
    AntlrRawRegex,
    AntlrStar,
    AntlrSymbol,
    RegularAntlrProduction,
)

from ._helpers import rule, to_antlr_ir


def lexer(*alts: list) -> AntlrLexerProduction:
    return AntlrLexerProduction(RegularAntlrProduction(AntlrBlockList([AntlrBlock(a) for a in alts])))


def parser(*alts: list) -> AntlrParserProduction:
    return AntlrParserProduction(RegularAntlrProduction(AntlrBlockList([AntlrBlock(a) for a in alts])))


# --- grammar level -----------------------------------------------------------


def test_empty_grammar():
    assert to_antlr_ir("grammar Empty;") == AntlrIr({}, [])


def test_rules_are_keyed_by_name_and_typed():
    ir = to_antlr_ir("grammar T;\nprog: expr ;\nexpr: INT ;\nINT: 'a' ;\n")
    assert list(ir.production_rules) == ["prog", "expr", "INT"]
    assert isinstance(ir.production_rules["prog"], AntlrParserProduction)
    assert isinstance(ir.production_rules["expr"], AntlrParserProduction)
    assert isinstance(ir.production_rules["INT"], AntlrLexerProduction)


def test_plain_rules_are_not_action_rules():
    assert to_antlr_ir("grammar T;\na: B ;\nB: 'b' ;\n").action_rules == []


# --- lexer rules -------------------------------------------------------------


def test_lexer_string_literal_strips_quotes():
    assert rule("A: 'abc' ;", "A") == lexer([AntlrSymbol("abc")])


def test_lexer_alternatives():
    assert rule("A: 'a' | 'b' ;", "A") == lexer([AntlrSymbol("a")], [AntlrSymbol("b")])


def test_lexer_sequence():
    assert rule("A: 'a' 'b' ;", "A") == lexer([AntlrSymbol("a"), AntlrSymbol("b")])


def test_lexer_token_reference():
    assert rule("A: B ;\nB: 'b' ;", "A") == lexer([AntlrLexerNonterminal("B")])


def test_lexer_char_range():
    assert rule("A: 'a'..'z' ;", "A") == lexer([AntlrCharRange("a", "z")])


def test_lexer_char_set():
    assert rule("A: [a-z] ;", "A") == lexer([AntlrRawRegex("[a-z]")])


def test_lexer_wildcard():
    assert rule("A: . ;", "A") == lexer([AntlrLexerWildcard()])


def test_lexer_suffixes():
    assert rule("A: 'a'* ;", "A") == lexer([AntlrStar(AntlrSymbol("a"))])
    assert rule("A: 'a'+ ;", "A") == lexer([AntlrPlus(AntlrSymbol("a"))])
    assert rule("A: 'a'? ;", "A") == lexer([AntlrOptional(AntlrSymbol("a"))])


def test_lexer_block_with_suffix():
    assert rule("A: ('a' | 'b')+ ;", "A") == lexer(
        [AntlrPlus(AntlrBlockList([AntlrBlock([AntlrSymbol("a")]), AntlrBlock([AntlrSymbol("b")])]))]
    )


def test_lexer_not_set_char_set():
    assert rule("A: ~[a] ;", "A") == lexer([AntlrNot(AntlrRawRegex("[a]"))])


def test_lexer_not_string_literal():
    assert rule("A: ~'a' ;", "A") == lexer([AntlrNot(AntlrSymbol("a"))])


def test_lexer_not_block_set():
    assert rule("A: ~('a' | 'b') ;", "A") == lexer(
        [AntlrNot(AntlrBlock([AntlrSymbol("a"), AntlrSymbol("b")]))]
    )


# --- parser rules ------------------------------------------------------------


def test_parser_rule_reference():
    assert rule("r: other ;\nother: X ;", "r") == parser([AntlrParserNonterminal("other")])


def test_parser_token_reference():
    assert rule("r: X ;", "r") == parser([AntlrParserNonterminal("X")])


def test_parser_string_literal():
    assert rule("r: 'x' ;", "r") == parser([AntlrSymbol("x")])


def test_parser_alternatives_and_sequences():
    assert rule("r: a b | c ;", "r") == parser(
        [AntlrParserNonterminal("a"), AntlrParserNonterminal("b")],
        [AntlrParserNonterminal("c")],
    )


def test_parser_labels_are_ignored():
    assert rule("r: a # One\n | b # Two\n ;", "r") == parser(
        [AntlrParserNonterminal("a")], [AntlrParserNonterminal("b")]
    )


def test_parser_suffixes():
    a = AntlrParserNonterminal("a")
    assert rule("r: a* ;", "r") == parser([AntlrStar(a)])
    assert rule("r: a+ ;", "r") == parser([AntlrPlus(a)])
    assert rule("r: a? ;", "r") == parser([AntlrOptional(a)])


def test_parser_block_without_suffix():
    assert rule("r: (a | b) ;", "r") == parser(
        [AntlrBlockList([AntlrBlock([AntlrParserNonterminal("a")]), AntlrBlock([AntlrParserNonterminal("b")])])]
    )


def test_parser_block_with_suffix():
    assert rule("r: (a b)* ;", "r") == parser(
        [AntlrStar(AntlrBlockList([AntlrBlock([AntlrParserNonterminal("a"), AntlrParserNonterminal("b")])]))]
    )


def test_parser_wildcard():
    assert rule("r: . ;", "r") == parser([AntlrParserWildcard()])


def test_parser_not_set():
    assert rule("r: ~X ;", "r") == parser([AntlrNot(AntlrParserNonterminal("X"))])


def test_parser_labeled_element():
    assert rule("r: l=a ;", "r") == parser([AntlrParserNonterminal("a")])


def test_parser_labeled_element_with_suffix():
    assert rule("r: l=a+ ;", "r") == parser([AntlrPlus(AntlrParserNonterminal("a"))])


def test_parser_labeled_block():
    assert rule("r: l=(a | b) ;", "r") == parser(
        [AntlrBlockList([AntlrBlock([AntlrParserNonterminal("a")]), AntlrBlock([AntlrParserNonterminal("b")])])]
    )


# --- larger grammar ----------------------------------------------------------


def test_expression_grammar():
    ir = to_antlr_ir(
        """grammar Expr;
prog: expr EOF ;
expr: expr ('*'|'/') expr   # MulDiv
    | INT                   # Int
    | '(' expr ')'          # Parens
    ;
INT: [0-9]+ ;
"""
    )
    assert list(ir.production_rules) == ["prog", "expr", "INT"]
    assert ir.production_rules["prog"] == parser(
        [AntlrParserNonterminal("expr"), AntlrParserNonterminal("EOF")]
    )
    assert ir.production_rules["INT"] == lexer([AntlrPlus(AntlrRawRegex("[0-9]"))])
    assert len(ir.production_rules["expr"].production.production.opts) == 3
