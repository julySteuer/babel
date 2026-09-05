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


def add_start_rule(old_ir: BabelIr, start_symbol_name: str) -> BabelIr:
    # TODO: Disambiguate start symbol here
    ir_copy = deepcopy(old_ir)  # i dont want to have weird refferencing errors
    # yes this could be made more functional but its late
    ir_copy.production_rules["START"] = _generate_start_symbol_rule(start_symbol_name)
    return ir_copy
