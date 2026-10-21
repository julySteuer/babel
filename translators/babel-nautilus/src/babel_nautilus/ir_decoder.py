from babel_ir.model import (
    BabelIr,
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
    BabelRawRegex,
)

from babel_nautilus.model.nautilus_ir import (
    NautilusExpr,
    NautilusAtom,
    NautilusBlock,
    NautilusTerminal,
    NautilusNonterminal,
    NautilusRegex,
)
from babel_nautilus.shared import capitalize_name

from babel_shared.name_generator import stateful_name_generator

def _create_capital_nonterminal(nonterminal: str) -> NautilusNonterminal:
    return NautilusNonterminal(capitalize_name(nonterminal))

def _from_babel_optional(optional: BabelOptional, parent_name: str) -> NautilusExpr:
    name = stateful_name_generator.generate_for(parent_name)
    inner = _from_babel_atom(optional.atom, name)
    return NautilusExpr.capitalize_name(
        name,
        options=[
            NautilusBlock([inner]),
            NautilusBlock([]),
        ],
    )

def _from_babel_terminal(terminal: BabelTerminal) -> NautilusAtom:
    match terminal:
        case BabelRawRegex(raw=regex):
            return NautilusRegex(regex)
        case BabelSymbol(terminal=symbol):
            return NautilusTerminal(symbol)
        case BabelCharRange(beginning=beginning, end=end) | BabelNumRange(beginning=beginning, end=end):
            return NautilusRegex(f"[{beginning}-{end}]")

def _from_babel_star(star: BabelStar, parent_name: str) -> NautilusExpr:
    name = stateful_name_generator.generate_for(parent_name)
    inner = _from_babel_atom(star.atom, name)
    return NautilusExpr.capitalize_name(
        name,
        options=[
            NautilusBlock([inner, _create_capital_nonterminal(name)]),
            NautilusBlock([]),
        ],
    )

def _from_babel_plus(plus: BabelPlus, parent_name: str) -> NautilusExpr:
    name = stateful_name_generator.generate_for(parent_name)
    return NautilusExpr.capitalize_name(
        name,
        options=[
            NautilusBlock([_from_babel_atom(plus.atom, name), _create_capital_nonterminal(name)]),
            NautilusBlock([_from_babel_atom(plus.atom, name)]),
        ],
    )

def _from_block_list(block_list: BabelBlockList, parent_name: str) -> NautilusExpr:
    name = stateful_name_generator.generate_for(parent_name)
    return _make_rule(name, block_list)

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
        case BabelNonterminal():
            return _create_capital_nonterminal(atom.nonterminal)
        case BabelBlockList():
            return _from_block_list(atom, parent_name)

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
    return NautilusExpr.capitalize_name(
        name,
        options
    )

def decode_ir(ir: BabelIr) -> list[NautilusExpr]:
    return [
        _make_rule(k, v.production) for k,v in ir.production_rules.items()
    ]

__all__ = ['decode_ir']