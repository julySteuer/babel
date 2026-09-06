import pytest

from babel_ir.model import (
    BabelIr,
    BabelProduction,
    BabelBlockList,
    BabelBlock,
    BabelAtom,
    BabelSymbol,
    BabelNonterminal,
    BabelCharRange,
    BabelNumRange,
    BabelOptional,
)

from babel_nautilus.decoder import decode
from babel_nautilus.name_generator import stateful_name_generator


@pytest.fixture(autouse=True)
def reset_name_generator():
    # The name generator is a process-wide singleton; give every test a clean slate
    # so generated names ("foo_0__GENERATED", ...) don't depend on test execution order.
    stateful_name_generator.counter.clear()


def _single_rule_ir(name: str, *atoms: BabelAtom) -> BabelIr:
    return BabelIr(
        production_rules={
            name: BabelProduction(
                BabelBlockList(opts=[BabelBlock(atoms=list(atoms))])
            )
        }
    )


def test_plain_terminal_and_nonterminal_input_compiles_to_a_ctx_rule_call():
    ir = _single_rule_ir("foo", BabelSymbol("a"), BabelNonterminal("BAR"))

    assert decode(ir, "foo") == (
        'ctx.rule("foo", "a{BAR}")\n'
        'ctx.rule("START", "{foo}")'
    )


def test_pure_char_range_input_compiles_to_a_ctx_regex_call():
    # A block made up entirely of regex atoms collapses into a single
    # RegexBlock and is emitted under the rule's own name.
    ir = _single_rule_ir("foo", BabelCharRange("a", "z"))

    assert decode(ir, "foo") == (
        'ctx.regex("foo", "[a-z]")\n'
        'ctx.rule("START", "{foo}")'
    )


def test_char_range_mixed_with_symbol_compiles_regex_before_referencing_rule():
    ir = _single_rule_ir("foo", BabelSymbol("a"), BabelCharRange("a", "z"))

    assert decode(ir, "foo") == (
        'ctx.regex("foo_0__GENERATED", "[a-z]")\n'
        'ctx.rule("foo", "a{foo_0__GENERATED}")\n'
        'ctx.rule("START", "{foo}")'
    )


def test_num_range_mixed_with_symbol_compiles_regex_before_referencing_rule():
    ir = _single_rule_ir("foo", BabelSymbol("a"), BabelNumRange(0, 9))

    assert decode(ir, "foo") == (
        'ctx.regex("foo_0__GENERATED", "[0-9]")\n'
        'ctx.rule("foo", "a{foo_0__GENERATED}")\n'
        'ctx.rule("START", "{foo}")'
    )


def test_multiple_production_rules_compile_to_newline_joined_calls():
    ir = BabelIr(
        production_rules={
            "foo": BabelProduction(
                BabelBlockList(
                    opts=[BabelBlock(atoms=[BabelSymbol("a"), BabelCharRange("a", "z")])]
                )
            ),
            "bar": BabelProduction(
                BabelBlockList(
                    opts=[BabelBlock(atoms=[BabelSymbol("b"), BabelNumRange(0, 9)])]
                )
            ),
        }
    )

    assert decode(ir, "foo") == (
        'ctx.regex("foo_0__GENERATED", "[a-z]")\n'
        'ctx.rule("foo", "a{foo_0__GENERATED}")\n'
        'ctx.regex("bar_0__GENERATED", "[0-9]")\n'
        'ctx.rule("bar", "b{bar_0__GENERATED}")\n'
        'ctx.rule("START", "{foo}")'
    )


def test_optional_desugaring_compiles_the_synthetic_rule_and_the_referencing_rule():
    # BabelOptional desugars into a nested NautilusExpr named "foo_0__GENERATED"
    # with two options - [Symbol("b")] and [] - which become the two blocks of
    # a single generated Rule, each emitted as its own ctx.* call under that
    # rule's name, followed by the outer "foo" rule that references it.
    ir = _single_rule_ir("foo", BabelOptional(BabelSymbol("b")))

    assert decode(ir, "foo") == (
        'ctx.rule("foo_0__GENERATED", "b")\n'
        'ctx.rule("foo_0__GENERATED", "")\n'
        'ctx.rule("foo", "{foo_0__GENERATED}")\n'
        'ctx.rule("START", "{foo}")'
    )


def test_add_start_rule_appends_a_start_rule_referencing_the_given_symbol():
    # decode() runs preprocess.add_start_rule before decoding, which injects a
    # "START" production rule referencing the given start symbol. It is added
    # last (dict insertion order), after all of the IR's own rules.
    ir = _single_rule_ir("foo", BabelSymbol("a"))

    assert decode(ir, "foo") == (
        'ctx.rule("foo", "a")\n'
        'ctx.rule("START", "{foo}")'
    )
