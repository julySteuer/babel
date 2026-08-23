from babel_antlr.encoder import encode


def test_basic():
    test_str = """grammar Expr;

prog: expr EOF ;
expr: expr ('*'|'/') expr   # MulDiv
    | expr ('+'|'-') expr   # AddSub
    | INT                   # Int
    | '(' expr ')'          # Parens
    ;

ruleAltList
    : labeledAlt (OR labeledAlt)*
    ;
    """

    encode(test_str)