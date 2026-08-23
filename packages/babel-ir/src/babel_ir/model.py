from abc import ABC
from dataclasses import dataclass
from typing import Generic, TypeVar



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


RangeType = TypeVar("RangeType")


@dataclass
class BabelRange(BabelTerminal, ABC, Generic[RangeType]):
    beginning: RangeType
    end: RangeType


@dataclass
class BabelCharRange(BabelRange[str]):
    pass


@dataclass
class BabelNumRange(BabelRange[int]):
    pass


@dataclass
class BabelBlock(BabelAtom):  # block1 | block2 | block3
    atoms: list[BabelAtom]


@dataclass
class BabelProduction:
    production: list[BabelBlock]


@dataclass
class BabelIr:
    production_rules: dict[str, BabelProduction]
