import pytest

from babel_antlr.antlr_ir_decoder import decode_antlr_ir_to_babel_ir
from babel_ir.model import (
    BabelBlock,
    BabelBlockList,
    BabelCharRange,
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


@pytest.fixture(autouse=True)
def reset_name_generator():
    stateful_name_generator.counter.clear()


def decode(source: str) -> dict[str, BabelProduction]:
    return decode_antlr_ir_to_babel_ir(to_antlr_ir(source)).production_rules


def prod(*alts: list) -> BabelProduction:
    return BabelProduction(BabelBlockList([BabelBlock(a) for a in alts]))


def nt(name: str) -> BabelNonterminal:
    return BabelNonterminal(name)


ALL_LEXER = "ALL_LEXER_RULES_0__GENERATED"
ALL_ACTED = "ALL_ACTED_RULES_0__GENERATED"


# --- lexer rules ---------------------------------------------------------------


def test_empty_grammar_decodes_to_no_rules():
    assert decode("grammar E;") == {}


def test_lexer_atoms():
    rules = decode("grammar T;\nA: 'a' 'b'..'c' [x-z] B ;\nB: 'b' ;\n")
    assert rules["A"] == prod(
        [BabelSymbol("a"), BabelCharRange("b", "c"), BabelRawRegex("[x-z]"), nt("B")]
    )


def test_lexer_suffixes():
    rules = decode("grammar T;\nA: 'a'* 'b'+ 'c'? ;\n")
    assert rules["A"] == prod(
        [
            BabelStar(BabelSymbol("a")),
            BabelPlus(BabelSymbol("b")),
            BabelOptional(BabelSymbol("c")),
        ]
    )


def test_lexer_alternatives():
    assert decode("grammar T;\nA: 'a' | 'b' ;\n")["A"] == prod(
        [BabelSymbol("a")], [BabelSymbol("b")]
    )


def test_lexer_inline_block_becomes_block_list():
    rules = decode("grammar T;\nA: ('a' | 'b')+ ;\n")
    inner = BabelBlockList(
        [BabelBlock([BabelSymbol("a")]), BabelBlock([BabelSymbol("b")])]
    )
    assert rules["A"] == prod([BabelPlus(inner)])


def test_lexer_wildcard_is_a_single_character():
    assert decode("grammar T;\nA: . ;\n")["A"] == prod([BabelRawRegex(".")])


def test_lexer_not_char_set():
    assert decode("grammar T;\nA: ~[a-c] ;\n")["A"] == prod([BabelRawRegex("[^a-c]")])


def test_lexer_not_string_literal():
    assert decode("grammar T;\nA: ~'a' ;\n")["A"] == prod([BabelRawRegex("[^a]")])


def test_lexer_not_block_set_merges_into_one_class():
    assert decode("grammar T;\nA: ~('x' | 'y' | 'a'..'c' | [0-9]) ;\n")["A"] == prod(
        [BabelRawRegex("[^xya-c0-9]")]
    )


def test_not_escapes_class_metacharacters():
    assert decode("grammar T;\nA: ~'-' ;\n")["A"] == prod([BabelRawRegex("[^\\-]")])


def test_not_over_token_reference_is_unsupported():
    with pytest.raises(NotImplementedError):
        decode("grammar T;\nA: ~B ;\nB: 'b' ;\n")


# --- parser rules --------------------------------------------------------------


def test_parser_rule_without_lexer_rules_is_decoded_plainly():
    rules = decode("grammar T;\nr: a b | 'x' ;\na: 'a' ;\nb: 'b' ;\n")
    assert rules["r"] == prod([nt("a"), nt("b")], [BabelSymbol("x")])
    assert rules["a"] == prod([BabelSymbol("a")])
    assert set(rules) == {"r", "a", "b"}


def test_parser_suffixes_and_blocks():
    rules = decode("grammar T;\nr: a* (a | b)+ b? ;\na: 'a' ;\nb: 'b' ;\n")
    alts = BabelBlockList([BabelBlock([nt("a")]), BabelBlock([nt("b")])])
    assert rules["r"] == prod(
        [BabelStar(nt("a")), BabelPlus(alts), BabelOptional(nt("b"))]
    )


def test_parser_not_is_unsupported():
    with pytest.raises(NotImplementedError):
        decode("grammar T;\nr: ~X ;\nX: 'x' ;\n")


def test_lexer_rules_are_not_decoded_as_parser_rules():
    rules = decode("grammar T;\nr: A ;\nA: 'a' ;\n")
    assert rules["r"] == prod([nt("A")])
    assert rules["A"] == prod([BabelSymbol("a")])


def test_parser_wildcard_references_a_rule_with_all_lexer_rules():
    rules = decode("grammar T;\nr: . ;\nA: 'a' ;\nB: 'b' ;\n")
    assert rules["r"] == prod([nt(ALL_LEXER)])
    assert rules[ALL_LEXER] == prod([nt("A")], [nt("B")])


def test_no_all_lexer_rules_rule_without_lexer_rules():
    assert not any(
        name.startswith("ALL_LEXER_RULES")
        for name in decode("grammar T;\nr: a ;\na: 'a' ;\n")
    )


# --- lexer commands ------------------------------------------------------------


def test_acted_alternative_becomes_its_own_rule():
    rules = decode("grammar T;\nWS: ' ' -> skip ;\n")
    assert rules["WS_0__GENERATED"] == prod([BabelSymbol(" ")])
    assert rules[ALL_ACTED] == prod([nt("WS_0__GENERATED")])


def test_original_rule_keeps_its_acted_alternatives_so_references_still_match():
    rules = decode("grammar T;\nA: 'a' WS 'b' ;\nWS: ' ' -> skip | '\\t' ;\n")
    assert rules["WS"] == prod([BabelSymbol(" ")], [BabelSymbol("\t")])
    assert rules["A"] == prod([BabelSymbol("a"), nt("WS"), BabelSymbol("b")])


def test_rule_consisting_only_of_acted_alternatives_is_kept():
    assert decode("grammar T;\nWS: ' ' -> skip ;\n")["WS"] == prod([BabelSymbol(" ")])


def test_all_acted_rules_lists_every_acted_alternative_as_an_option():
    rules = decode(
        "grammar T;\nA: 'a' -> skip | 'b' -> skip ;\nC: 'c' -> channel(HIDDEN) ;\n"
    )
    assert rules[ALL_ACTED] == prod(
        [nt("A_0__GENERATED")], [nt("A_1__GENERATED")], [nt("C_0__GENERATED")]
    )


def test_acted_rules_are_not_part_of_all_lexer_rules():
    rules = decode("grammar T;\nr: . ;\nA: 'a' ;\nWS: ' ' -> skip ;\n")
    assert rules[ALL_LEXER] == prod([nt("A")])


def test_all_lexer_rules_inlines_only_the_regular_alternatives_of_mixed_rules():
    rules = decode("grammar T;\nr: . ;\nA: 'a' ;\nWS: ' ' -> skip | '\\t' ;\n")
    assert rules[ALL_LEXER] == prod([nt("A")], [BabelSymbol("\t")])


def test_acted_rules_are_tweened_between_parser_atoms():
    rules = decode(
        "grammar T;\nr: A B C ;\nA: 'a' ;\nB: 'b' ;\nC: 'c' ;\nWS: ' ' -> skip ;\n"
    )
    skip = BabelStar(nt(ALL_ACTED))
    assert rules["r"] == prod([nt("A"), skip, nt("B"), skip, nt("C")])


def test_single_atom_parser_block_has_nothing_to_tween():
    rules = decode("grammar T;\nr: A ;\nA: 'a' ;\nWS: ' ' -> skip ;\n")
    assert rules["r"] == prod([nt("A")])


def test_acted_rules_are_tweened_inside_nested_blocks():
    rules = decode("grammar T;\nr: (A B)* ;\nA: 'a' ;\nB: 'b' ;\nWS: ' ' -> skip ;\n")
    inner = BabelBlockList([BabelBlock([nt("A"), BabelStar(nt(ALL_ACTED)), nt("B")])])
    assert rules["r"] == prod([BabelStar(inner)])


def test_lexer_rules_are_not_tweened():
    rules = decode("grammar T;\nA: 'a' 'b' ;\nWS: ' ' -> skip ;\n")
    assert rules["A"] == prod([BabelSymbol("a"), BabelSymbol("b")])


def test_unrecognised_commands_do_not_generate_action_rules():
    rules = decode("grammar T;\nr: A B ;\nA: 'a' ;\nB: 'b' -> mode(M) ;\n")
    assert rules["r"] == prod([nt("A"), nt("B")])
    assert not any(name.startswith("ALL_ACTED_RULES") for name in rules)
