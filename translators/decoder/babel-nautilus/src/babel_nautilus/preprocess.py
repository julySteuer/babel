from copy import deepcopy

from babel_ir.model import (
    BabelBlock,
    BabelBlockList,
    BabelAtom,
    BabelIr,
    BabelNonterminal,
    BabelOptional,
    BabelPlus,
    BabelProduction,
    BabelStar,
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


def _referenced_nonterminals(atom: BabelAtom | BabelBlock) -> set[str]:
    match atom:
        case BabelNonterminal(nonterminal=name):
            return {name}
        case BabelOptional(atom=inner) | BabelStar(atom=inner) | BabelPlus(atom=inner):
            return _referenced_nonterminals(inner)
        case BabelBlock(atoms=children):
            return set().union(*map(_referenced_nonterminals, children))
        case BabelBlockList(opts=children):
            return set().union(*map(_referenced_nonterminals, children))
        case _:
            return set()


def add_missing_rules(old_ir: BabelIr) -> BabelIr:
    """Define every referenced but undefined nonterminal as the empty string.

    ANTLR allows tokens without a lexer rule (``tokens { X }``, ``-> type(X)``, tokens
    emitted by custom lexer code, implicit tokens); nautilus needs every nonterminal to
    be derivable, so these are generated as empty.
    """
    ir_copy = deepcopy(old_ir)
    referenced: set[str] = set()
    for production in ir_copy.production_rules.values():
        referenced |= _referenced_nonterminals(production.production)
    for name in sorted(referenced - ir_copy.production_rules.keys()):
        ir_copy.production_rules[name] = _generate_eof_symbol_rule()
    return ir_copy


def _is_productive(atom: BabelAtom | BabelBlock, productive: set[str]) -> bool:
    match atom:
        case BabelNonterminal(nonterminal=name):
            return name in productive
        case BabelOptional() | BabelStar():
            return True  # can always be skipped
        case BabelPlus(atom=inner):
            return _is_productive(inner, productive)
        case BabelBlock(atoms=children):
            return all(_is_productive(child, productive) for child in children)
        case BabelBlockList(opts=children):
            return any(_is_productive(child, productive) for child in children)
        case _:
            return True  # terminals


def _empty_group() -> BabelBlockList:
    return BabelBlockList([BabelBlock([])])


def _prune_block(block: BabelBlock, productive: set[str]) -> BabelBlock:
    pruned = [_prune(child, productive) for child in block.atoms]
    return BabelBlock([child for child in pruned if child is not None])


def _prune(atom: BabelAtom, productive: set[str]) -> BabelAtom | None:
    """Rebuilds `atom` without the parts that cannot terminate. None means "matches only the empty string"."""
    match atom:
        case BabelOptional(atom=inner) | BabelStar(atom=inner) if not _is_productive(
            inner, productive
        ):
            return None
        case BabelOptional(atom=inner):
            return BabelOptional(_prune(inner, productive) or _empty_group())
        case BabelStar(atom=inner):
            return BabelStar(_prune(inner, productive) or _empty_group())
        case BabelPlus(atom=inner):
            return BabelPlus(_prune(inner, productive) or _empty_group())
        case BabelBlockList(opts=children):
            return BabelBlockList(
                [
                    _prune_block(child, productive)
                    for child in children
                    if _is_productive(child, productive)
                ]
            )
        case _:
            return atom


def remove_unproductive_rules(old_ir: BabelIr) -> BabelIr:
    """
    Removes everything from which no finite string can be derived (a rule that only recurses into itself, for
    example). ANTLR tolerates these as long as they are optional somewhere, nautilus rejects the whole grammar.
    Alternatives that use such a rule are dropped, optional / repeated uses are skipped.
    """
    rules = old_ir.production_rules
    productive: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, production in rules.items():
            if name not in productive and _is_productive(
                production.production, productive
            ):
                productive.add(name)
                changed = True

    return BabelIr(
        {
            name: BabelProduction(_prune(production.production, productive))  # type: ignore[arg-type]
            for name, production in rules.items()
            if name in productive
        }
    )
