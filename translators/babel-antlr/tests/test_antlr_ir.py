from babel_antlr.model.antlr_ir import (
    ActedAntlrLexerBlock,
    AntlrChannel,
    AntlrParserBlock,
    AntlrSkip,
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
    RegularAntlrLexerBlock,
)

import pytest

from ._helpers import rule, to_antlr_ir


def lexer(*alts: list) -> AntlrLexerProduction:
    return AntlrLexerProduction(AntlrBlockList([RegularAntlrLexerBlock(a) for a in alts]))


def parser(*alts: list) -> AntlrParserProduction:
    return AntlrParserProduction(AntlrBlockList([AntlrParserBlock(a) for a in alts]))


def _atoms(atoms: tuple) -> list:
    return list(atoms[0]) if len(atoms) == 1 and isinstance(atoms[0], list) else list(atoms)


def lblock(*atoms) -> RegularAntlrLexerBlock:
    return RegularAntlrLexerBlock(_atoms(atoms))


def pblock(*atoms) -> AntlrParserBlock:
    return AntlrParserBlock(_atoms(atoms))


# --- grammar level -----------------------------------------------------------


def test_empty_grammar():
    assert to_antlr_ir("grammar Empty;") == AntlrIr({}, [])


def test_rules_are_keyed_by_name_and_typed():
    ir = to_antlr_ir("grammar T;\nprog: expr ;\nexpr: INT ;\nINT: 'a' ;\n")
    assert list(ir.production_rules) == ["prog", "expr", "INT"]
    assert isinstance(ir.production_rules["prog"], AntlrParserProduction)
    assert isinstance(ir.production_rules["expr"], AntlrParserProduction)
    assert isinstance(ir.production_rules["INT"], AntlrLexerProduction)


def test_production_type_hierarchy():
    ir = to_antlr_ir("grammar T;\np: A ;\nA: 'a' ;\n")
    lexer_rule, parser_rule = ir.production_rules["A"], ir.production_rules["p"]
    assert isinstance(lexer_rule, AntlrLexerProduction)
    assert not isinstance(lexer_rule, AntlrParserProduction)
    assert isinstance(parser_rule, AntlrParserProduction)
    assert not isinstance(parser_rule, AntlrLexerProduction)


def test_production_holds_block_list_directly():
    assert isinstance(rule("r: a ;", "r").production, AntlrBlockList)


def test_block_types_follow_rule_kind():
    ir = to_antlr_ir("grammar T;\np: a | b ;\nA: 'a' | 'b' ;\n")
    assert all(type(b) is AntlrParserBlock for b in ir.production_rules["p"].production.opts)
    assert all(type(b) is RegularAntlrLexerBlock for b in ir.production_rules["A"].production.opts)


def test_plain_rules_have_no_action_blocks():
    ir = to_antlr_ir("grammar T;\na: B ;\nB: 'b' ;\n")
    assert ir.action_blocks == []


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
        [AntlrPlus(AntlrBlockList([lblock([AntlrSymbol("a")]), lblock([AntlrSymbol("b")])]))]
    )


def test_lexer_not_set_char_set():
    assert rule("A: ~[a] ;", "A") == lexer([AntlrNot(AntlrRawRegex("[a]"))])


def test_lexer_not_string_literal():
    assert rule("A: ~'a' ;", "A") == lexer([AntlrNot(AntlrSymbol("a"))])


def test_lexer_not_block_set():
    assert rule("A: ~('a' | 'b') ;", "A") == lexer(
        [AntlrNot(lblock(AntlrSymbol("a"), AntlrSymbol("b")))]
    )


def test_lexer_not_block_set_is_a_lexer_block():
    (block,) = rule("A: ~('a' | 'b') ;", "A").production.opts
    assert type(block.atoms[0].atom) is RegularAntlrLexerBlock


def test_lexer_not_block_set_with_token_reference_and_range():
    assert rule("A: ~(B | 'a'..'z') ;\nB: 'b' ;", "A") == lexer(
        [AntlrNot(lblock(AntlrLexerNonterminal("B"), AntlrCharRange("a", "z")))]
    )


def test_parser_not_block_set_is_a_parser_block():
    assert rule("r: ~(X | Y) ;", "r") == parser(
        [AntlrNot(pblock(AntlrParserNonterminal("X"), AntlrParserNonterminal("Y")))]
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
        [AntlrBlockList([pblock([AntlrParserNonterminal("a")]), pblock([AntlrParserNonterminal("b")])])]
    )


def test_parser_block_with_suffix():
    assert rule("r: (a b)* ;", "r") == parser(
        [AntlrStar(AntlrBlockList([pblock([AntlrParserNonterminal("a"), AntlrParserNonterminal("b")])]))]
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
        [AntlrBlockList([pblock([AntlrParserNonterminal("a")]), pblock([AntlrParserNonterminal("b")])])]
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
    assert len(ir.production_rules["expr"].production.opts) == 3


# --- lexer commands ------------------------------------------------------------


def acted(cmd, *atoms) -> ActedAntlrLexerBlock:
    return ActedAntlrLexerBlock(list(atoms), cmd)


def test_skip_command():
    prod = rule("WS: ' '+ -> skip ;", "WS")
    assert prod == AntlrLexerProduction(
        AntlrBlockList([acted(AntlrSkip(), AntlrPlus(AntlrSymbol(" ")))])
    )


def test_channel_command():
    prod = rule("C: 'c' -> channel(HIDDEN) ;", "C")
    assert prod == AntlrLexerProduction(
        AntlrBlockList([acted(AntlrChannel(), AntlrSymbol("c"))])
    )


def test_commands_apply_per_outermost_alternative():
    prod = rule("A: 'a' -> skip | 'b' ;", "A")
    assert prod == AntlrLexerProduction(
        AntlrBlockList([acted(AntlrSkip(), AntlrSymbol("a")), lblock(AntlrSymbol("b"))])
    )


def test_command_after_block_applies_to_whole_alternative():
    prod = rule("A: ('a' | 'b') -> skip ;", "A")
    inner = AntlrBlockList([lblock(AntlrSymbol("a")), lblock(AntlrSymbol("b"))])
    assert prod == AntlrLexerProduction(AntlrBlockList([acted(AntlrSkip(), inner)]))


def test_other_commands_are_regular_blocks():
    assert rule("A: 'a' -> mode(M) ;", "A") == lexer([AntlrSymbol("a")])


def test_action_blocks_are_collected_as_name_block_pairs():
    ir = to_antlr_ir("grammar T;\nWS: ' ' -> skip | '\\t' ;\nA: 'a' ;\n")
    assert ir.action_blocks == [("WS", acted(AntlrSkip(), AntlrSymbol(" ")))]


def test_action_blocks_are_the_same_objects_as_in_the_production():
    ir = to_antlr_ir("grammar T;\nWS: ' ' -> skip ;\n")
    ((_, block),) = ir.action_blocks
    assert block is ir.production_rules["WS"].production.opts[0]


def test_every_acted_alternative_of_a_rule_is_listed():
    ir = to_antlr_ir("grammar T;\nA: 'a' -> skip | 'b' | 'c' -> channel(HIDDEN) ;\n")
    assert ir.action_blocks == [
        ("A", acted(AntlrSkip(), AntlrSymbol("a"))),
        ("A", acted(AntlrChannel(), AntlrSymbol("c"))),
    ]


def test_action_blocks_keep_grammar_order_across_rules():
    ir = to_antlr_ir("grammar T;\nA: 'a' -> skip ;\nB: 'b' ;\nC: 'c' -> channel(HIDDEN) ;\n")
    assert [name for name, _ in ir.action_blocks] == ["A", "C"]


def test_unrecognised_commands_are_not_action_blocks():
    ir = to_antlr_ir("grammar T;\nA: 'a' -> mode(M) ;\n")
    assert ir.action_blocks == []


def test_parser_rules_never_produce_action_blocks():
    ir = to_antlr_ir("grammar T;\nr: a | b ;\n")
    assert ir.action_blocks == []


# --- escape sequences in literals ----------------------------------------------


@pytest.mark.parametrize(
    "literal, expected",
    [
        (r"'\''", "'"),
        (r"'\\'", "\\"),
        (r"'\"'", '"'),
        (r"'\n'", "\n"),
        (r"'\r'", "\r"),
        (r"'\t'", "\t"),
        (r"'\u000C'", "\x0c"),
        (r"'\u{1F600}'", "\U0001F600"),
        (r"'a\'b'", "a'b"),
        (r"'\\n'", "\\n"),  # escaped backslash followed by a plain n
    ],
)
def test_string_literal_escapes_are_resolved(literal, expected):
    assert rule(f"A: {literal} ;", "A") == lexer([AntlrSymbol(expected)])


def test_char_range_escapes_are_resolved():
    assert rule(r"A: '\u0000'..'\u001F' ;", "A") == lexer([AntlrCharRange("\x00", "\x1f")])


def test_char_sets_stay_raw_regex():
    assert rule(r"A: [\n\\] ;", "A") == lexer([AntlrRawRegex(r"[\n\\]")])
