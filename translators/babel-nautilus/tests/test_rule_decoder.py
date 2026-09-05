import pytest

from babel_nautilus.model.nautilus_ir import (
    NautilusExpr,
    NautilusBlock,
    NautilusTerminal,
    NautilusNonterminal,
    NautilusRegex,
)
from babel_nautilus.model.rule import (
    Rule,
    RegexBlock,
    RuleBlock,
    TerminalAtom,
    NonterminalAtom,
    RegexAtom,
)
from babel_nautilus.rule_decoder import decode_to_rules, _decode_atom, _construct_block
from babel_nautilus.name_generator import stateful_name_generator


@pytest.fixture(autouse=True)
def reset_name_generator():
    # The name generator is a process-wide singleton; give every test a clean slate
    # so generated names ("foo_0__GENERATED", ...) don't depend on test execution order.
    stateful_name_generator.counter.clear()


def _single_block_expr(name: str, *atoms) -> NautilusExpr:
    return NautilusExpr(name, options=[NautilusBlock(list(atoms))])


# --- decode_to_rules (public API) ---------------------------------------


def test_terminal_and_nonterminal_block_becomes_a_single_rule_block():
    expr = _single_block_expr("foo", NautilusTerminal("a"), NautilusNonterminal("BAR"))

    assert decode_to_rules([expr]) == [Rule("foo", [RuleBlock("a{BAR}")])]


def test_pure_regex_block_becomes_a_regex_rule():
    expr = _single_block_expr("foo", NautilusRegex("[a-z]"), NautilusRegex("[0-9]"))

    assert decode_to_rules([expr]) == [Rule("foo", [RegexBlock("[a-z][0-9]")])]


def test_empty_block_becomes_an_empty_regex_rule():
    # all(...) over an empty iterable is vacuously True, so an epsilon block
    # (e.g. the base case of an optional/star desugaring) is classified as a
    # "pure regex" block with empty content.
    expr = _single_block_expr("foo")

    assert decode_to_rules([expr]) == [Rule("foo", [RegexBlock("")])]


def test_multiple_options_produce_one_rule_with_one_block_per_option():
    expr = NautilusExpr(
        "outer",
        options=[
            NautilusBlock([NautilusTerminal("a")]),
            NautilusBlock([NautilusTerminal("b")]),
        ],
    )

    assert decode_to_rules([expr]) == [
        Rule("outer", [RuleBlock("a"), RuleBlock("b")])
    ]


def test_regex_atom_in_a_mixed_block_is_extracted_into_a_rule_before_its_parent():
    # A block only collapses to a single RegexBlock if *every* atom is regex.
    # Once it's mixed with a terminal/nonterminal, each regex atom is pulled
    # out into its own generated Rule, which is emitted before the rule that
    # references it.
    expr = _single_block_expr("foo", NautilusTerminal("a"), NautilusRegex("[a-z]"))

    assert decode_to_rules([expr]) == [
        Rule("foo_0__GENERATED", [RegexBlock("[a-z]")]),
        Rule("foo", [RuleBlock("a{foo_0__GENERATED}")]),
    ]


def test_each_regex_atom_in_a_mixed_block_gets_its_own_sequential_rule():
    expr = _single_block_expr(
        "foo", NautilusTerminal("a"), NautilusRegex("[0-9]"), NautilusRegex("[a-z]")
    )

    assert decode_to_rules([expr]) == [
        Rule("foo_0__GENERATED", [RegexBlock("[0-9]")]),
        Rule("foo_1__GENERATED", [RegexBlock("[a-z]")]),
        Rule("foo", [RuleBlock("a{foo_0__GENERATED}{foo_1__GENERATED}")]),
    ]


def test_nested_expression_produces_its_own_rule_referenced_like_any_nonterminal():
    # A nested NautilusExpr atom decodes to a "{name}"-wrapped reference, same
    # as a real NautilusNonterminal - every nonterminal reference gets wrapped.
    inner = _single_block_expr("inner", NautilusTerminal("a"))
    outer = _single_block_expr("outer", NautilusTerminal("x"), inner)

    assert decode_to_rules([outer]) == [
        Rule("inner", [RuleBlock("a")]),
        Rule("outer", [RuleBlock("x{inner}")]),
    ]


def test_rules_from_deeply_nested_expressions_are_collected_innermost_first():
    innermost = _single_block_expr(
        "innermost", NautilusTerminal("a"), NautilusRegex("[0-9]")
    )
    middle = _single_block_expr("middle", NautilusTerminal("b"), innermost)
    outer = _single_block_expr("outer", middle)

    assert decode_to_rules([outer]) == [
        Rule("innermost_0__GENERATED", [RegexBlock("[0-9]")]),
        Rule("innermost", [RuleBlock("a{innermost_0__GENERATED}")]),
        Rule("middle", [RuleBlock("b{innermost}")]),
        Rule("outer", [RuleBlock("{middle}")]),
    ]


def test_generated_names_are_scoped_per_parent_expression_name():
    foo = _single_block_expr("foo", NautilusTerminal("a"), NautilusRegex("[0-9]"))
    bar = _single_block_expr("bar", NautilusTerminal("b"), NautilusRegex("[a-z]"))

    assert decode_to_rules([foo, bar]) == [
        Rule("foo_0__GENERATED", [RegexBlock("[0-9]")]),
        Rule("foo", [RuleBlock("a{foo_0__GENERATED}")]),
        Rule("bar_0__GENERATED", [RegexBlock("[a-z]")]),
        Rule("bar", [RuleBlock("b{bar_0__GENERATED}")]),
    ]


def test_multiple_top_level_expressions_are_decoded_independently():
    foo = _single_block_expr("foo", NautilusTerminal("a"))
    bar = _single_block_expr("bar", NautilusTerminal("b"))

    assert decode_to_rules([foo, bar]) == [
        Rule("foo", [RuleBlock("a")]),
        Rule("bar", [RuleBlock("b")]),
    ]


# --- _decode_atom (per-atom translation) ---------------------------------


def test_decode_atom_terminal():
    assert _decode_atom(NautilusTerminal("hi")) == (TerminalAtom("hi"), [])


def test_decode_atom_nonterminal_wraps_name_in_curly_braces():
    assert _decode_atom(NautilusNonterminal("BAR")) == (NonterminalAtom("{BAR}"), [])


def test_decode_atom_regex():
    assert _decode_atom(NautilusRegex("[a-z]")) == (RegexAtom("[a-z]"), [])


def test_decode_atom_nested_expression_returns_its_generated_rule():
    expr = _single_block_expr("inner", NautilusTerminal("a"))

    assert _decode_atom(expr) == (
        NonterminalAtom("{inner}"),
        [Rule("inner", [RuleBlock("a")])],
    )


# --- _construct_block -----------------------------------------------------


def test_construct_block_merges_all_regex_atoms_into_one_block():
    block, rules = _construct_block([RegexAtom("[a-z]"), RegexAtom("[0-9]")], "foo")

    assert block == RegexBlock("[a-z][0-9]")
    assert rules == []


def test_construct_block_with_no_atoms_is_an_empty_regex_block():
    # all(...) over an empty iterable is vacuously True, so an epsilon block
    # (e.g. the base case of an optional/star desugaring) is currently
    # classified as a "pure regex" block with empty content.
    block, rules = _construct_block([], "foo")

    assert block == RegexBlock("")
    assert rules == []


def test_construct_block_extracts_regex_atoms_when_mixed_with_other_atoms():
    atoms = [TerminalAtom("a"), RegexAtom("[0-9]"), NonterminalAtom("{BAR}")]

    block, rules = _construct_block(atoms, "foo")

    assert block == RuleBlock("a{foo_0__GENERATED}{BAR}")
    assert rules == [Rule("foo_0__GENERATED", [RegexBlock("[0-9]")])]
