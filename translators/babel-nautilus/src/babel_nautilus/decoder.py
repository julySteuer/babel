from collections.abc import Generator
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar, Any

from babel_ir.model import (
    BabelAtom,
    BabelBlock,
    BabelBlockList,
    BabelIr,
    BabelNonterminal,
    BabelNot,
    BabelOptional,
    BabelPlus,
    BabelProduction,
    BabelRange,
    BabelStar,
    BabelSymbol,
    BabelWildcard,
)

# TODO: Rework this whole thing with a recursive data structure

class NautilusMode(Enum):
    RULE = "rule"
    REGEX = "regex"


@dataclass
class DecodedNautilusBlock:
    parsed_str: str
    mode: NautilusMode


deep_nautilus_block = DecodedNautilusBlock | list[DecodedNautilusBlock]
deep_nautilus_blocks = list[deep_nautilus_block] # Maybe replace this with the generator version
deep_nautilus_generator = Generator[deep_nautilus_block]

def _flat_map(
    elems: Any | list[Any],
) -> Generator[Any]:
    match elems:
        case list():
            for elem in elems:
                yield from _flat_map(elem)
        case _:
            yield elems


def _raw_str_to_decoded_nautilus_block(elem: str) -> list[DecodedNautilusBlock]:
    if elem == "":
        return []
    return [DecodedNautilusBlock(elem, NautilusMode.RULE)]

# TODO: Refactor in more functional way
def _reduce_to_blocks(
    atoms: list[DecodedNautilusBlock | list[DecodedNautilusBlock] | str],
) -> Generator[deep_nautilus_block]:
    curr_str = ""
    for atom in atoms:
        match atom:
            case DecodedNautilusBlock() | list():
                yield DecodedNautilusBlock(curr_str, NautilusMode.RULE)
                curr_str = ""
                yield atom
            case str():
                curr_str = curr_str + atom
    if curr_str != "":
        yield DecodedNautilusBlock(curr_str, NautilusMode.RULE)


def _decode_symbol(symbol: BabelSymbol) -> str:
    return symbol.terminal


# They just contain strings
def _decode_terminating_atom(
    atom: BabelSymbol | BabelNonterminal,
) -> str:
    match atom:
        case BabelSymbol(terminal):
            return terminal
        case BabelNonterminal(nonterminal):
            return f"<{nonterminal}>"

def _decode_plus(plus: BabelPlus) -> deep_nautilus_block:
    child_atoms = plus.atom

# They may expand into more complex blocks
def _decode_non_terminating_atom(
    atom: BabelPlus
    | BabelNot
    | BabelOptional
    | BabelStar
    | BabelBlock
    | BabelBlockList
    | BabelRange
    | BabelWildcard
) -> deep_nautilus_block:
    match atom:
        case BabelPlus():
            return _decode_plus(atom)


def _decode_atom(atom: BabelAtom) -> deep_nautilus_block | str:
    # <Terminating Atom> <Terminating Atom> <ExtraRuleAtom>
    match atom:
        case BabelSymbol() | BabelNonterminal():
            return _decode_terminating_atom(atom)
        case (
            BabelPlus()
            | BabelNot()
            | BabelOptional()
            | BabelStar()
            | BabelBlock()
            | BabelBlockList()
            | BabelRange()
            | BabelWildcard()
        ):
            return _decode_non_terminating_atom(atom)


def _decode_babel_block(option: BabelBlock) -> deep_nautilus_blocks:
    atoms = option.atoms
    decoded_atoms = [_decode_atom(atom) for atom in atoms]

    return list(_reduce_to_blocks(decoded_atoms))


def _decode_babel_block_list_with_name(
    name: str, babel_block_list: BabelBlockList
) -> str:
    opts = babel_block_list.opts
    blocks = [_decode_babel_block(block) for block in opts]
    parsed_blocks = [
        f'ctx.{block.mode}("{name}", "{block.parsed_str}")'
        for block in _flat_map(blocks)
    ]
    return "\n".join(
        parsed_blocks
    )  # This is a bug feature. It adds in the end two \n so rules are better readable


def _decode_babel_production_with_name(name: str, production: BabelProduction) -> str:
    return _decode_babel_block_list_with_name(name, production.production)


def decode(babel_ir: BabelIr) -> str:
    decoded_productions = [
        _decode_babel_production_with_name(name, production)
        for name, production in babel_ir.production_rules
    ]
    return "\n".join(decoded_productions)


__all__ = ["decode"]
