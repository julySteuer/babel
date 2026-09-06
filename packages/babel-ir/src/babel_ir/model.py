from abc import ABC
from dataclasses import dataclass
from typing import TypeVar


class BabelAtom(ABC):
    pass


class BabelTerminal(BabelAtom, ABC):
    pass


@dataclass
class BabelSymbol(BabelTerminal):
    terminal: str


@dataclass
class BabelNonterminal(BabelAtom):
    nonterminal: str


@dataclass
class BabelOptional(BabelAtom):
    atom: BabelAtom  # Change this to aceppt block like structure

@dataclass
class BabelStar(BabelAtom):
    atom: BabelAtom

@dataclass
class BabelPlus(BabelAtom):
    atom: BabelAtom

@dataclass
class BabelNot(BabelAtom):
    atom: BabelAtom

@dataclass
class BabelWildcard(BabelAtom):
    pass

@dataclass
class BabelRange[RangeType](BabelTerminal, ABC):
    beginning: RangeType
    end: RangeType


@dataclass
class BabelCharRange(BabelRange[str]):
    pass


@dataclass
class BabelNumRange(BabelRange[int]):
    pass

# TODO: BabelRegex maybe that just takes a raw regex expression

# This should propably not be an atom. Tis from earliere TODO: Remove
@dataclass
class BabelBlock(BabelAtom):  # block1 | block2 | block3
    atoms: list[BabelAtom]

@dataclass
class BabelBlockList(BabelAtom):
    opts: list[BabelBlock]

@dataclass
class BabelProduction:
    production: BabelBlockList


@dataclass
class BabelIr:
    production_rules: dict[str, BabelProduction]
