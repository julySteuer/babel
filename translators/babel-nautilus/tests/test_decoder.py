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
    BabelRawRegex,
    BabelNumRange,
    BabelOptional,
)

from babel_nautilus.decoder import decode
from babel_shared.name_generator import stateful_name_generator


@pytest.fixture(autouse=True)
def reset_name_generator():
    # The name generator is a process-wide singleton; give every test a clean slate
    # so generated names ("Foo_0__GENERATED", ...) don't depend on test execution order.
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
    ir = _single_rule_ir("Foo", BabelSymbol("a"), BabelNonterminal("BAR"))

    assert decode(ir, "Foo") == (
        'ctx.rule("Foo", "a{BAR}")\n'
        'ctx.rule("START", "{Foo}")\n'
        'ctx.rule("EOF", "")'
    )


def test_pure_char_range_input_compiles_to_a_ctx_regex_call():
    # A block made up entirely of regex atoms collapses into a single
    # RegexBlock and is emitted under the rule's own name.
    ir = _single_rule_ir("Foo", BabelCharRange("a", "z"))

    assert decode(ir, "Foo") == (
        'ctx.regex("Foo", "[a-z]")\n'
        'ctx.rule("START", "{Foo}")\n'
        'ctx.rule("EOF", "")'
    )


def test_char_range_mixed_with_symbol_compiles_regex_before_referencing_rule():
    ir = _single_rule_ir("Foo", BabelSymbol("a"), BabelCharRange("a", "z"))

    assert decode(ir, "Foo") == (
        'ctx.regex("Foo_0__GENERATED", "[a-z]")\n'
        'ctx.rule("Foo", "a{Foo_0__GENERATED}")\n'
        'ctx.rule("START", "{Foo}")\n'
        'ctx.rule("EOF", "")'
    )


def test_num_range_mixed_with_symbol_compiles_regex_before_referencing_rule():
    ir = _single_rule_ir("Foo", BabelSymbol("a"), BabelNumRange(0, 9))

    assert decode(ir, "Foo") == (
        'ctx.regex("Foo_0__GENERATED", "[0-9]")\n'
        'ctx.rule("Foo", "a{Foo_0__GENERATED}")\n'
        'ctx.rule("START", "{Foo}")\n'
        'ctx.rule("EOF", "")'
    )


def test_multiple_production_rules_compile_to_newline_joined_calls():
    ir = BabelIr(
        production_rules={
            "Foo": BabelProduction(
                BabelBlockList(
                    opts=[BabelBlock(atoms=[BabelSymbol("a"), BabelCharRange("a", "z")])]
                )
            ),
            "Bar": BabelProduction(
                BabelBlockList(
                    opts=[BabelBlock(atoms=[BabelSymbol("b"), BabelNumRange(0, 9)])]
                )
            ),
        }
    )

    assert decode(ir, "Foo") == (
        'ctx.regex("Foo_0__GENERATED", "[a-z]")\n'
        'ctx.rule("Foo", "a{Foo_0__GENERATED}")\n'
        'ctx.regex("Bar_0__GENERATED", "[0-9]")\n'
        'ctx.rule("Bar", "b{Bar_0__GENERATED}")\n'
        'ctx.rule("START", "{Foo}")\n'
        'ctx.rule("EOF", "")'
    )


def test_optional_desugaring_compiles_the_synthetic_rule_and_the_referencing_rule():
    # BabelOptional desugars into a nested NautilusExpr named "Foo_0__GENERATED"
    # with two options - [Symbol("b")] and [] - which become the two blocks of
    # a single generated Rule, each emitted as its own ctx.* call under that
    # rule's name, followed by the outer "Foo" rule that references it.
    ir = _single_rule_ir("Foo", BabelOptional(BabelSymbol("b")))

    assert decode(ir, "Foo") == (
        'ctx.rule("Foo_0__GENERATED", "b")\n'
        'ctx.rule("Foo_0__GENERATED", "")\n'
        'ctx.rule("Foo", "{Foo_0__GENERATED}")\n'
        'ctx.rule("START", "{Foo}")\n'
        'ctx.rule("EOF", "")'
    )


def test_add_start_rule_appends_a_start_rule_referencing_the_given_symbol():
    # decode() runs preprocess.add_start_rule before decoding, which injects a
    # "START" production rule referencing the given start symbol, followed by an
    # empty "EOF" rule (add_eof_rule). Both are added
    # last (dict insertion order), after all of the IR's own rules.
    ir = _single_rule_ir("Foo", BabelSymbol("a"))

    assert decode(ir, "Foo") == (
        'ctx.rule("Foo", "a")\n'
        'ctx.rule("START", "{Foo}")\n'
        'ctx.rule("EOF", "")'
    )


# --- escaping in the generated python grammar ----------------------------------


def _execute(grammar: str) -> list[tuple[str, str, str]]:
    calls = []

    class Ctx:
        def rule(self, name, content):
            calls.append(("rule", name, content))

        def regex(self, name, content):
            calls.append(("regex", name, content))

    exec(compile(grammar, "<grammar>", "exec"), {"ctx": Ctx()})
    return calls


def test_generated_grammar_reads_back_the_original_terminal():
    for terminal in ['"', "\\", "\n", "\r", "\t", "\x0c", "'", "\\\"", "a\\nb"]:
        ir = _single_rule_ir("Foo", BabelSymbol(terminal))
        assert _execute(decode(ir, "Foo"))[0] == ("rule", "Foo", terminal)


def test_braces_in_terminals_are_escaped_for_nautilus_once():
    ir = _single_rule_ir("Foo", BabelSymbol("{}"))
    assert _execute(decode(ir, "Foo"))[0] == ("rule", "Foo", "\\{\\}")


def test_generated_grammar_reads_back_regexes():
    ir = _single_rule_ir("Foo", BabelRawRegex('["\\\\a-z]'))
    assert _execute(decode(ir, "Foo"))[0] == ("regex", "Foo", '["\\\\a-z]')


def test_char_range_ends_are_escaped_in_the_class():
    ir = _single_rule_ir("Foo", BabelCharRange("\\", "]"))
    assert _execute(decode(ir, "Foo"))[0] == ("regex", "Foo", "[\\\\-\\]]")


def test_backslash_before_a_nonterminal_gets_its_own_rule():
    # `\{BAR}` would be read by nautilus as an escaped brace followed by `BAR}`
    ir = _single_rule_ir("Foo", BabelSymbol("\\"), BabelNonterminal("BAR"))
    assert decode(ir, "Foo").splitlines()[:2] == [
        'ctx.rule("Foo_0__GENERATED", "\\\\")',
        'ctx.rule("Foo", "{Foo_0__GENERATED}{BAR}")',
    ]


def test_trailing_backslash_needs_no_extra_rule():
    ir = _single_rule_ir("Foo", BabelNonterminal("BAR"), BabelSymbol("\\"))
    assert decode(ir, "Foo").splitlines()[0] == 'ctx.rule("Foo", "{BAR}\\\\")'
