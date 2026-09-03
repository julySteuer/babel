import pytest

from babel_ir.model import (
    BabelIr,
    BabelProduction,
    BabelBlockList,
    BabelBlock,
    BabelAtom,
    BabelSymbol,
    BabelNonterminal,
    BabelOptional,
    BabelStar,
    BabelPlus,
    BabelNot,
    BabelCharRange,
    BabelNumRange,
)

from babel_nautilus.ir_decoder import decode_ir
from babel_nautilus.model.nautilus_ir import (
    NautilusExpr,
    NautilusBlock,
    NautilusTerminal,
    NautilusNonterminal,
    NautilusRegex,
)
from babel_nautilus.name_generator import stateful_name_generator


@pytest.fixture(autouse=True)
def reset_name_generator():
    # The name generator is a process-wide singleton; give every test a clean slate
    # so generated names ("foo_0__GENERATED", "foo_1__GENERATED", ...) don't depend
    # on test execution order.
    stateful_name_generator.counter.clear()


def _single_rule_ir(name: str, *atoms: BabelAtom) -> BabelIr:
    return BabelIr(
        production_rules={
            name: BabelProduction(
                BabelBlockList(opts=[BabelBlock(atoms=list(atoms))])
            )
        }
    )


def test_plain_terminals_and_nonterminal():
    ir = _single_rule_ir("foo", BabelNonterminal("BAR"), BabelSymbol("test"))

    result = decode_ir(ir)

    assert result == [
        NautilusExpr(
            "foo",
            options=[
                NautilusBlock([NautilusNonterminal("BAR"), NautilusTerminal("test")]),
            ],
        )
    ]


def test_char_range_terminal():
    ir = _single_rule_ir("foo", BabelCharRange("a", "z"))

    result = decode_ir(ir)

    assert result == [
        NautilusExpr("foo", options=[NautilusBlock([NautilusRegex("[a-z]")])])
    ]


def test_num_range_terminal():
    ir = _single_rule_ir("foo", BabelNumRange(0, 9))

    result = decode_ir(ir)

    assert result == [
        NautilusExpr("foo", options=[NautilusBlock([NautilusRegex("[0-9]")])])
    ]


def test_optional_desugars_to_epsilon_alternative():
    ir = _single_rule_ir("foo", BabelSymbol("a"), BabelOptional(BabelSymbol("b")))

    result = decode_ir(ir)

    assert result == [
        NautilusExpr(
            "foo",
            options=[
                NautilusBlock(
                    [
                        NautilusTerminal("a"),
                        NautilusExpr(
                            "foo_0__GENERATED",
                            options=[
                                NautilusBlock([NautilusTerminal("b")]),
                                NautilusBlock([]),
                            ],
                        ),
                    ]
                ),
            ],
        )
    ]


def test_star_desugars_to_right_recursive_rule():
    ir = _single_rule_ir("foo", BabelStar(BabelSymbol("a")))

    result = decode_ir(ir)

    assert result == [
        NautilusExpr(
            "foo",
            options=[
                NautilusBlock(
                    [
                        NautilusExpr(
                            "foo_0__GENERATED",
                            options=[
                                NautilusBlock(
                                    [NautilusTerminal("a"), NautilusNonterminal("foo_0__GENERATED")]
                                ),
                                NautilusBlock([]),
                            ],
                        ),
                    ]
                ),
            ],
        )
    ]


def test_plus_desugars_to_recursive_rule_with_non_empty_base_case():
    ir = _single_rule_ir("foo", BabelPlus(BabelSymbol("a")))

    result = decode_ir(ir)

    assert result == [
        NautilusExpr(
            "foo",
            options=[
                NautilusBlock(
                    [
                        NautilusExpr(
                            "foo_0__GENERATED",
                            options=[
                                NautilusBlock(
                                    [NautilusTerminal("a"), NautilusNonterminal("foo_0__GENERATED")]
                                ),
                                NautilusBlock([NautilusTerminal("a")]),
                            ],
                        ),
                    ]
                ),
            ],
        )
    ]


def test_not_over_char_range_negates_the_char_class():
    ir = _single_rule_ir("foo", BabelNot(BabelCharRange("a", "z")))

    result = decode_ir(ir)

    assert result == [
        NautilusExpr(
            "foo",
            options=[
                NautilusBlock(
                    [NautilusExpr("foo_0__GENERATED", options=[NautilusBlock([NautilusRegex("[^a-z]")])])]
                ),
            ],
        )
    ]


def test_not_over_symbol_negates_the_char_class():
    ir = _single_rule_ir("foo", BabelNot(BabelSymbol("a")))

    result = decode_ir(ir)

    assert result == [
        NautilusExpr(
            "foo",
            options=[
                NautilusBlock(
                    [NautilusExpr("foo_0__GENERATED", options=[NautilusBlock([NautilusRegex("[^a]")])])]
                ),
            ],
        )
    ]


def test_not_over_nonterminal_is_unsupported():
    ir = _single_rule_ir("foo", BabelNot(BabelNonterminal("BAR")))

    with pytest.raises(NotImplementedError):
        decode_ir(ir)


def test_nested_star_inside_optional_derives_names_from_parent_scope():
    ir = _single_rule_ir("foo", BabelOptional(BabelStar(BabelSymbol("a"))))

    result = decode_ir(ir)

    assert result == [
        NautilusExpr(
            "foo",
            options=[
                NautilusBlock(
                    [
                        NautilusExpr(
                            "foo_0__GENERATED",
                            options=[
                                NautilusBlock(
                                    [
                                        NautilusExpr(
                                            "foo_0__GENERATED_0__GENERATED",
                                            options=[
                                                NautilusBlock(
                                                    [
                                                        NautilusTerminal("a"),
                                                        NautilusNonterminal("foo_0__GENERATED_0__GENERATED"),
                                                    ]
                                                ),
                                                NautilusBlock([]),
                                            ],
                                        ),
                                    ]
                                ),
                                NautilusBlock([]),
                            ],
                        ),
                    ]
                ),
            ],
        )
    ]


def test_multiple_rules_are_each_decoded_independently():
    ir = BabelIr(
        production_rules={
            "foo": BabelProduction(
                BabelBlockList(opts=[BabelBlock(atoms=[BabelOptional(BabelSymbol("a"))])])
            ),
            "bar": BabelProduction(
                BabelBlockList(opts=[BabelBlock(atoms=[BabelStar(BabelSymbol("b"))])])
            ),
        }
    )

    result = decode_ir(ir)

    assert [expr.name for expr in result] == ["foo", "bar"]
    # Synthetic names are scoped per parent rule name, so "foo" and "bar" each start at 0.
    assert result[0].options[0].children[0].name == "foo_0__GENERATED"
    assert result[1].options[0].children[0].name == "bar_0__GENERATED"
