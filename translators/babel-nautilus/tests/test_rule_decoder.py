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


def test_pure_terminal_and_nonterminal_block_generates_no_rules():
    expr = _single_block_expr("foo", NautilusTerminal("a"), NautilusNonterminal("BAR"))

    assert decode_to_rules([expr]) == []


def test_pure_regex_block_is_merged_without_generating_a_rule():
    expr = _single_block_expr("foo", NautilusRegex("[a-z]"), NautilusRegex("[0-9]"))

    assert decode_to_rules([expr]) == []


def test_expression_itself_never_becomes_a_rule():
    # Known gap in the current rewrite (see git log: "Will rework due to DS not
    # working so well"): _decode_expression only returns the *child* rules it
    # collects, never a Rule for the NautilusExpr being decoded. So even a
    # non-trivial top-level expression produces nothing on its own.
    expr = _single_block_expr("foo", NautilusTerminal("a"), NautilusNonterminal("BAR"))

    assert decode_to_rules([expr]) == []


def test_regex_atom_in_a_mixed_block_is_extracted_into_its_own_rule():
    # A block only collapses to a single RegexBlock if *every* atom is regex.
    # Once it's mixed with a terminal/nonterminal, each regex atom is pulled
    # out into its own generated Rule. This only surfaces through
    # decode_to_rules when the mixed block lives inside a nested expression,
    # since a top-level expression's own rule is otherwise discarded.
    inner = _single_block_expr("inner", NautilusTerminal("a"), NautilusRegex("[0-9]"))
    outer = _single_block_expr("outer", NautilusTerminal("x"), inner)

    assert decode_to_rules([outer]) == [
        Rule("inner_0__GENERATED", [RegexBlock("[0-9]")]),
    ]


def test_each_regex_atom_in_a_mixed_block_gets_its_own_sequential_rule():
    inner = _single_block_expr(
        "inner", NautilusTerminal("a"), NautilusRegex("[0-9]"), NautilusRegex("[a-z]")
    )
    outer = _single_block_expr("outer", inner)

    assert decode_to_rules([outer]) == [
        Rule("inner_0__GENERATED", [RegexBlock("[0-9]")]),
        Rule("inner_1__GENERATED", [RegexBlock("[a-z]")]),
    ]


def test_generated_names_are_scoped_per_parent_expression_name():
    inner_foo = _single_block_expr("foo", NautilusTerminal("a"), NautilusRegex("[0-9]"))
    inner_bar = _single_block_expr("bar", NautilusTerminal("b"), NautilusRegex("[a-z]"))
    outer_foo = _single_block_expr("outer_foo", inner_foo)
    outer_bar = _single_block_expr("outer_bar", inner_bar)

    result = decode_to_rules([outer_foo, outer_bar])

    assert result == [
        Rule("foo_0__GENERATED", [RegexBlock("[0-9]")]),
        Rule("bar_0__GENERATED", [RegexBlock("[a-z]")]),
    ]


def test_rules_from_every_option_are_flattened_in_order():
    inner_a = _single_block_expr("a_opt", NautilusTerminal("a"), NautilusRegex("[0-9]"))
    inner_b = _single_block_expr("b_opt", NautilusTerminal("b"), NautilusRegex("[a-z]"))
    outer = NautilusExpr(
        "outer",
        options=[
            NautilusBlock([inner_a]),
            NautilusBlock([inner_b]),
        ],
    )

    result = decode_to_rules([outer])

    assert result == [
        Rule("a_opt_0__GENERATED", [RegexBlock("[0-9]")]),
        Rule("b_opt_0__GENERATED", [RegexBlock("[a-z]")]),
    ]


def test_rules_from_deeply_nested_expressions_are_all_collected():
    innermost = _single_block_expr(
        "innermost", NautilusTerminal("a"), NautilusRegex("[0-9]")
    )
    middle = _single_block_expr("middle", NautilusTerminal("b"), innermost)
    outer = _single_block_expr("outer", middle)

    assert decode_to_rules([outer]) == [
        Rule("innermost_0__GENERATED", [RegexBlock("[0-9]")]),
    ]


# --- _decode_atom (per-atom translation) ---------------------------------


def test_decode_atom_terminal():
    assert _decode_atom(NautilusTerminal("hi")) == (TerminalAtom("hi"), [])


def test_decode_atom_nonterminal_wraps_name_in_angle_brackets():
    assert _decode_atom(NautilusNonterminal("BAR")) == (NonterminalAtom("<BAR>"), [])


def test_decode_atom_regex():
    assert _decode_atom(NautilusRegex("[a-z]")) == (RegexAtom("[a-z]"), [])


def test_decode_atom_nested_expression_does_not_wrap_name_in_brackets():
    # Unlike a real NautilusNonterminal, a nested NautilusExpr atom decodes to
    # a bare-name NonterminalAtom with no surrounding "<...>" — an asymmetry
    # in the current implementation worth locking down.
    expr = _single_block_expr("inner", NautilusTerminal("a"))

    assert _decode_atom(expr) == (NonterminalAtom("inner"), [])


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
    atoms = [TerminalAtom("a"), RegexAtom("[0-9]"), NonterminalAtom("<BAR>")]

    block, rules = _construct_block(atoms, "foo")

    assert block == RuleBlock("a<foo_0__GENERATED><BAR>")
    assert rules == [Rule("foo_0__GENERATED", [RegexBlock("[0-9]")])]
