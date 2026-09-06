"""Integration tests for babel_core.domain.generate_nautilus().

Unlike the per-package unit tests (babel_antlr's encode(), babel_ir's merge(),
babel_nautilus's decode()), these exercise the whole pipeline end to end from
real ANTLR grammar source text down to the final nautilus ctx.rule/ctx.regex
script, the way a real caller would use it.

The test grammars deliberately avoid parenthesized alternation groups (e.g.
`(A | B)` or `(A | B)*`) inside a rule body: babel_nautilus.ir_decoder does
not yet handle a BabelBlockList as the inner atom of a suffix/not-set (see
its "TODO: Add Block List" marker), so such groups have to be factored out
into their own named rule instead (as TAIL is below) to stay on supported
ground.
"""

import pytest

from babel_core.domain import generate_nautilus
from babel_nautilus.name_generator import stateful_name_generator


@pytest.fixture(autouse=True)
def reset_name_generator():
    # The name generator is a process-wide singleton; give every test a clean slate
    # so generated names ("foo_0__GENERATED", ...) don't depend on test execution order.
    stateful_name_generator.counter.clear()


# A small statically-typed-looking expression language: statements, left-recursive
# arithmetic expressions/terms with two operators each, parenthesized sub-expressions,
# identifiers, integers, string literals, and a skipped whitespace token. Exercises
# BabelPlus (INT, WS), BabelStar (ID's tail, STRING's body), BabelOptional (the
# statement's trailing SEMI), BabelNot (STRING's body), BabelCharRange (LETTER,
# DIGIT), multi-alternative rules, and fragment rules, all wired through a real
# start symbol.
CALC_GRAMMAR = """
grammar Calc;

prog: stmt* EOF ;

stmt: ID ASSIGN expr SEMI? ;

expr: expr PLUS term
    | expr MINUS term
    | term
    ;

term: term STAR factor
    | term SLASH factor
    | factor
    ;

factor: INT
      | ID
      | STRING
      | LPAREN expr RPAREN
      ;

ID: LETTER TAIL* ;
fragment TAIL: LETTER
             | DIGIT
             ;
fragment LETTER: 'a'..'z' ;

INT: DIGIT+ ;
fragment DIGIT: '0'..'9' ;

STRING: QUOTE INNERCHAR* QUOTE ;
fragment QUOTE: '"' ;
fragment INNERCHAR: ~'"' ;

ASSIGN: '=' ;
SEMI: ';' ;
PLUS: '+' ;
MINUS: '-' ;
STAR: '*' ;
SLASH: '/' ;
LPAREN: '(' ;
RPAREN: ')' ;

WS: SPACE+ -> skip ;
fragment SPACE: ' ' ;
"""


def test_generate_nautilus_compiles_a_larger_grammar_end_to_end():
    result = generate_nautilus([CALC_GRAMMAR], "prog")

    assert result == "\n".join(
        [
            'ctx.rule("prog_0__GENERATED", "{stmt}{prog_0__GENERATED}")',
            'ctx.rule("prog_0__GENERATED", "")',
            'ctx.rule("prog", "{prog_0__GENERATED}{EOF}")',
            'ctx.rule("stmt_0__GENERATED", "{SEMI}")',
            'ctx.rule("stmt_0__GENERATED", "")',
            'ctx.rule("stmt", "{ID}{ASSIGN}{expr}{stmt_0__GENERATED}")',
            'ctx.rule("expr", "{expr}{PLUS}{term}")',
            'ctx.rule("expr", "{expr}{MINUS}{term}")',
            'ctx.rule("expr", "{term}")',
            'ctx.rule("term", "{term}{STAR}{factor}")',
            'ctx.rule("term", "{term}{SLASH}{factor}")',
            'ctx.rule("term", "{factor}")',
            'ctx.rule("factor", "{INT}")',
            'ctx.rule("factor", "{ID}")',
            'ctx.rule("factor", "{STRING}")',
            'ctx.rule("factor", "{LPAREN}{expr}{RPAREN}")',
            'ctx.rule("ID_0__GENERATED", "{TAIL}{ID_0__GENERATED}")',
            'ctx.rule("ID_0__GENERATED", "")',
            'ctx.rule("ID", "{LETTER}{ID_0__GENERATED}")',
            'ctx.rule("TAIL", "{LETTER}")',
            'ctx.rule("TAIL", "{DIGIT}")',
            'ctx.regex("LETTER", "[\'a\'-\'z\']")',
            'ctx.rule("INT_0__GENERATED", "{DIGIT}{INT_0__GENERATED}")',
            'ctx.rule("INT_0__GENERATED", "{DIGIT}")',
            'ctx.rule("INT", "{INT_0__GENERATED}")',
            'ctx.regex("DIGIT", "[\'0\'-\'9\']")',
            'ctx.rule("STRING_0__GENERATED", "{INNERCHAR}{STRING_0__GENERATED}")',
            'ctx.rule("STRING_0__GENERATED", "")',
            'ctx.rule("STRING", "{QUOTE}{STRING_0__GENERATED}{QUOTE}")',
            'ctx.rule("QUOTE", "\'"\'")',
            'ctx.regex("INNERCHAR_0__GENERATED", "[^\'"\']")',
            'ctx.rule("INNERCHAR", "{INNERCHAR_0__GENERATED}")',
            'ctx.rule("ASSIGN", "\'=\'")',
            'ctx.rule("SEMI", "\';\'")',
            'ctx.rule("PLUS", "\'+\'")',
            'ctx.rule("MINUS", "\'-\'")',
            'ctx.rule("STAR", "\'*\'")',
            'ctx.rule("SLASH", "\'/\'")',
            'ctx.rule("LPAREN", "\'(\'")',
            'ctx.rule("RPAREN", "\')\'")',
            'ctx.rule("WS_0__GENERATED", "{SPACE}{WS_0__GENERATED}")',
            'ctx.rule("WS_0__GENERATED", "{SPACE}")',
            'ctx.rule("WS", "{WS_0__GENERATED}")',
            'ctx.rule("SPACE", "\' \'")',
            'ctx.rule("START", "{prog}")',
        ]
    )


# A second, differently-shaped grammar (operator precedence via prog/expr/term/atom
# layering, a prefix unary operator, keyword literals) used for a structural check
# rather than another full-text snapshot, so the suite isn't only ever validating
# one exact string.
BOOL_GRAMMAR = """
grammar Bool;

prog: expr EOF ;

expr: expr AND term
    | expr OR term
    | term
    ;

term: NOT term
    | atom
    ;

atom: TRUE
    | FALSE
    | LPAREN expr RPAREN
    ;

TRUE: 'true' ;
FALSE: 'false' ;
AND: '&' ;
OR: '|' ;
NOT: '!' ;
LPAREN: '(' ;
RPAREN: ')' ;

WS: SPACE+ -> skip ;
fragment SPACE: ' ' ;
"""


def test_generate_nautilus_wires_every_rule_and_the_given_start_symbol():
    result = generate_nautilus([BOOL_GRAMMAR], "prog")

    for rule_name in [
        "prog",
        "expr",
        "term",
        "atom",
        "TRUE",
        "FALSE",
        "AND",
        "OR",
        "NOT",
        "LPAREN",
        "RPAREN",
        "WS",
        "SPACE",
    ]:
        assert f'"{rule_name}"' in result, f"missing rule {rule_name!r} in:\n{result}"

    # add_start_rule() always appends the synthetic START rule last, referencing
    # whatever start symbol the caller passed in.
    assert result.splitlines()[-1] == 'ctx.rule("START", "{prog}")'
