from functools import reduce

from babel_ir.model import BabelIr


def merge(irs: list[BabelIr]) -> BabelIr:
    # TODO: This on its own is wildly unsafe. the merging logic needs to account for double rules and merge their blocks
    return reduce(lambda ir, acc: BabelIr(ir.production_rules | acc.production_rules), irs)