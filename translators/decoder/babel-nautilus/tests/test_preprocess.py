from babel_ir.model import (
    BabelBlock,
    BabelBlockList,
    BabelIr,
    BabelNonterminal,
    BabelPlus,
    BabelProduction,
    BabelStar,
    BabelSymbol,
)
from babel_nautilus.preprocess import remove_unproductive_rules


def _rule(*options: list) -> BabelProduction:
    return BabelProduction(BabelBlockList([BabelBlock(list(o)) for o in options]))


def test_plus_of_pruned_star_gets_an_empty_group():
    # (loop*)+ is productive (the star can be skipped), but the pruned star body is empty
    ir = BabelIr(
        {
            "r": _rule([BabelPlus(BabelStar(BabelNonterminal("loop")))]),
            "loop": _rule([BabelNonterminal("loop")]),
        }
    )
    result = remove_unproductive_rules(ir).production_rules
    assert "loop" not in result
    assert result["r"] == _rule([BabelPlus(BabelBlockList([BabelBlock([])]))])


def test_pruned_group_stays_a_block_list():
    ir = BabelIr({"r": _rule([BabelSymbol("a")], [BabelNonterminal("loop")]), "loop": _rule([BabelNonterminal("loop")])})
    result = remove_unproductive_rules(ir).production_rules
    assert result["r"] == _rule([BabelSymbol("a")])
