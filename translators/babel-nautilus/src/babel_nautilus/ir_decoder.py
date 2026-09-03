from babel_ir.model import (
    BabelIr,
    BabelProduction,
    BabelBlockList,
    BabelBlock,
    BabelAtom,
    BabelNonterminal,
    BabelOptional,
    BabelTerminal,
    BabelSymbol,
    BabelCharRange,
    BabelNumRange,
    BabelStar,
    BabelPlus,
    BabelNot,
)

from babel_nautilus.model.nautilus_ir import (
    NautilusExpr,
    NautilusAtom,
    NautilusBlock,
    NautilusTerminal,
    NautilusNonterminal,
    NautilusRegex,
)
from babel_nautilus.name_generator import stateful_name_generator

def _from_babel_optional(optional: BabelOptional, parent_name: str) -> NautilusExpr:
    name = stateful_name_generator.generate_for(parent_name)
    inner = _from_babel_atom(optional.atom, name)
    return NautilusExpr(
        name,
        options=[
            NautilusBlock([inner]),
            NautilusBlock([]),
        ],
    )

def _from_babel_terminal(terminal: BabelTerminal) -> NautilusAtom:
    match terminal:
        case BabelSymbol(terminal=symbol):
            return NautilusTerminal(symbol)
        case BabelCharRange(beginning=beginning, end=end) | BabelNumRange(beginning=beginning, end=end):
            return NautilusRegex(f"[{beginning}-{end}]")

def _from_babel_star(star: BabelStar, parent_name: str) -> NautilusExpr:
    name = stateful_name_generator.generate_for(parent_name)
    inner = _from_babel_atom(star.atom, name)
    return NautilusExpr(
        name,
        options=[
            NautilusBlock([inner, NautilusNonterminal(name)]),
            NautilusBlock([]),
        ],
    )

def _from_babel_plus(plus: BabelPlus, parent_name: str) -> NautilusExpr:
    name = stateful_name_generator.generate_for(parent_name)
    return NautilusExpr(
        name,
        options=[
            NautilusBlock([_from_babel_atom(plus.atom, name), NautilusNonterminal(name)]),
            NautilusBlock([_from_babel_atom(plus.atom, name)]),
        ],
    )

def _from_babel_not(note: BabelNot, parent_name: str) -> NautilusExpr:
    name = stateful_name_generator.generate_for(parent_name)
    match note.atom:
        case BabelSymbol(terminal=symbol):
            negated = NautilusRegex(f"[^{symbol}]")
        case BabelCharRange(beginning=beginning, end=end):
            negated = NautilusRegex(f"[^{beginning}-{end}]")
        case BabelNumRange(beginning=beginning, end=end):
            negated = NautilusRegex(f"[^{beginning}-{end}]")
        case _:
            raise NotImplementedError(
                "BabelNot is only supported over terminal/range atoms; "
                f"cannot negate a {type(note.atom).__name__} in a context-free grammar"
            )
    return NautilusExpr(name, options=[NautilusBlock([negated])])

def _from_babel_atom(atom: BabelAtom, parent_name: str) -> NautilusAtom:
    match atom:
        case BabelOptional():
            return _from_babel_optional(atom, parent_name)
        case BabelTerminal():
            return _from_babel_terminal(atom)
        case BabelStar():
            return _from_babel_star(atom, parent_name)
        case BabelPlus():
            return _from_babel_plus(atom, parent_name)
        case BabelNot():
            return _from_babel_not(atom, parent_name)
        case BabelNonterminal():
            return NautilusNonterminal(atom.nonterminal)
        # TODO: Add Block List

def _from_block(block: BabelBlock, parent_name: str) -> NautilusBlock:
    # TODO: Determine which block by checking the children. If they are just regex they can be combined otherwise new rule
    # TODO: Make the regex rule parser in another function just return as is
    # TODO: This Also desides which type the parent expressionn is. Do this not here but on the next pass
    parsed_children = [
        _from_babel_atom(atom, parent_name) for atom in block.atoms
    ]
    return NautilusBlock(parsed_children)

def _make_rule(name: str, production: BabelBlockList) -> NautilusExpr:
    options = [
        _from_block(block, name) for block in production.opts
    ]
    return NautilusExpr(
        name,
        options
    )

def decode_ir(ir: BabelIr) -> list[NautilusExpr]:
    return [
        _make_rule(k, v.production) for k,v in ir.production_rules.items()
    ]

__all__ = ['decode_ir']