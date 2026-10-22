import pytest

from babel_ir.model import (
    BabelIr,
    BabelRawRegex,
    BabelProduction,
    BabelBlockList,
    BabelBlock,
    BabelAtom,
    BabelSymbol,
    BabelNonterminal,
    BabelOptional,
    BabelStar,
    BabelPlus,
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
from babel_shared.name_generator import stateful_name_generator


@pytest.fixture(autouse=True)
def reset_name_generator():
    # The name generator is a process-wide singleton; give every test a clean slate
    # so generated names ("Foo_0__GENERATED", "Foo_1__GENERATED", ...) don't depend
    # on test execution order.
    stateful_name_generator.counter.clear()


def _single_rule_ir(name: str, *atoms: BabelAtom) -> BabelIr:
    return BabelIr(
        production_rules={
            name: BabelProduction(BabelBlockList(opts=[BabelBlock(atoms=list(atoms))]))
        }
    )


def test_plain_terminals_and_nonterminal():
    ir = _single_rule_ir("Foo", BabelNonterminal("BAR"), BabelSymbol("test"))

    result = decode_ir(ir)

    assert result == [
        NautilusExpr(
            "Foo",
            options=[
                NautilusBlock([NautilusNonterminal("BAR"), NautilusTerminal("test")]),
            ],
        )
    ]


def test_char_range_terminal():
    ir = _single_rule_ir("Foo", BabelCharRange("a", "z"))

    result = decode_ir(ir)

    assert result == [
        NautilusExpr("Foo", options=[NautilusBlock([NautilusRegex("[a-z]")])])
    ]


def test_num_range_terminal():
    ir = _single_rule_ir("Foo", BabelNumRange(0, 9))

    result = decode_ir(ir)

    assert result == [
        NautilusExpr("Foo", options=[NautilusBlock([NautilusRegex("[0-9]")])])
    ]


def test_optional_desugars_to_epsilon_alternative():
    ir = _single_rule_ir("Foo", BabelSymbol("a"), BabelOptional(BabelSymbol("b")))

    result = decode_ir(ir)

    assert result == [
        NautilusExpr(
            "Foo",
            options=[
                NautilusBlock(
                    [
                        NautilusTerminal("a"),
                        NautilusExpr(
                            "Foo_0__GENERATED",
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
    ir = _single_rule_ir("Foo", BabelStar(BabelSymbol("a")))

    result = decode_ir(ir)

    assert result == [
        NautilusExpr(
            "Foo",
            options=[
                NautilusBlock(
                    [
                        NautilusExpr(
                            "Foo_0__GENERATED",
                            options=[
                                NautilusBlock(
                                    [
                                        NautilusTerminal("a"),
                                        NautilusNonterminal("Foo_0__GENERATED"),
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


def test_plus_desugars_to_recursive_rule_with_non_empty_base_case():
    ir = _single_rule_ir("Foo", BabelPlus(BabelSymbol("a")))

    result = decode_ir(ir)

    assert result == [
        NautilusExpr(
            "Foo",
            options=[
                NautilusBlock(
                    [
                        NautilusExpr(
                            "Foo_0__GENERATED",
                            options=[
                                NautilusBlock(
                                    [
                                        NautilusTerminal("a"),
                                        NautilusNonterminal("Foo_0__GENERATED"),
                                    ]
                                ),
                                NautilusBlock([NautilusTerminal("a")]),
                            ],
                        ),
                    ]
                ),
            ],
        )
    ]


def test_nested_star_inside_optional_derives_names_from_parent_scope():
    ir = _single_rule_ir("Foo", BabelOptional(BabelStar(BabelSymbol("a"))))

    result = decode_ir(ir)

    assert result == [
        NautilusExpr(
            "Foo",
            options=[
                NautilusBlock(
                    [
                        NautilusExpr(
                            "Foo_0__GENERATED",
                            options=[
                                NautilusBlock(
                                    [
                                        NautilusExpr(
                                            "Foo_0__GENERATED_0__GENERATED",
                                            options=[
                                                NautilusBlock(
                                                    [
                                                        NautilusTerminal("a"),
                                                        NautilusNonterminal(
                                                            "Foo_0__GENERATED_0__GENERATED"
                                                        ),
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
            "Foo": BabelProduction(
                BabelBlockList(
                    opts=[BabelBlock(atoms=[BabelOptional(BabelSymbol("a"))])]
                )
            ),
            "Bar": BabelProduction(
                BabelBlockList(opts=[BabelBlock(atoms=[BabelStar(BabelSymbol("b"))])])
            ),
        }
    )

    result = decode_ir(ir)

    assert [expr.name for expr in result] == ["Foo", "Bar"]
    # Synthetic names are scoped per parent rule name, so "Foo" and "Bar" each start at 0.
    assert result[0].options[0].children[0].name == "Foo_0__GENERATED"
    assert result[1].options[0].children[0].name == "Bar_0__GENERATED"


# --- regexes are restricted to ASCII (the nautilus regex generator panics otherwise) --------


def test_raw_regex_with_non_ascii_range_is_clamped():
    ir = _single_rule_ir("Foo", BabelRawRegex("[a\\u00c0-\\u00d6]"))
    assert decode_ir(ir) == [
        NautilusExpr("Foo", options=[NautilusBlock([NautilusRegex("[\\x61]")])])
    ]


def test_wildcard_regex_is_restricted_to_ascii():
    ir = _single_rule_ir("Foo", BabelRawRegex("."))
    assert decode_ir(ir) == [
        NautilusExpr(
            "Foo", options=[NautilusBlock([NautilusRegex("[\\x00-\\x09\\x0B-\\x7F]")])]
        )
    ]


def test_alternative_without_any_ascii_match_is_dropped():
    ir = BabelIr(
        {
            "Foo": BabelProduction(
                BabelBlockList(
                    [
                        BabelBlock([BabelSymbol("a")]),
                        BabelBlock([BabelRawRegex("[\\u3040-\\u318f]")]),
                    ]
                )
            )
        }
    )
    assert decode_ir(ir) == [
        NautilusExpr("Foo", options=[NautilusBlock([NautilusTerminal("a")])])
    ]


def test_rule_with_only_unmatchable_alternatives_falls_back_to_printable_ascii():
    ir = _single_rule_ir("Foo", BabelRawRegex("[\\u3040-\\u318f]"))
    assert decode_ir(ir) == [
        NautilusExpr("Foo", options=[NautilusBlock([NautilusRegex("[ -~]")])])
    ]
