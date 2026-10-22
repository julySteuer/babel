from copy import deepcopy

from babel_ir.model import (
    BabelBlock,
    BabelBlockList,
    BabelIr,
    BabelNonterminal,
    BabelProduction,
)


def _generate_start_symbol_rule(start_symbol_name: str) -> BabelProduction:
    return BabelProduction(
        BabelBlockList([BabelBlock([BabelNonterminal(start_symbol_name)])])
    )


def _generate_eof_symbol_rule() -> BabelProduction:
    return BabelProduction(BabelBlockList([BabelBlock([])]))


def add_start_rule(old_ir: BabelIr, start_symbol_name: str) -> BabelIr:
    # TODO: Disambiguate start symbol here
    ir_copy = deepcopy(old_ir)  # i dont want to have weird refferencing errors
    # yes this could be made more functional but its late
    ir_copy.production_rules["START"] = _generate_start_symbol_rule(start_symbol_name)
    return ir_copy


# TODO: Add EOF Rule
def add_eof_rule(old_ir: BabelIr) -> BabelIr:
    ir_copy = deepcopy(old_ir)

    ir_copy.production_rules["EOF"] = _generate_eof_symbol_rule()
    return ir_copy
