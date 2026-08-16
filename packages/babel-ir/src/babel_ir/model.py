from abc import ABC
from dataclasses import dataclass
from typing import Generic, TypeVar

"""
BabelIr
└── production_rules: list[BabelProduction]
    └── production: list[BabelBlock]
        └── atoms: list[BabelAtom]
            ├── BabelNonterminal
            ├── BabelOptional (contains atom: BabelAtom)
            └── BabelTerminal
                ├── BabelSymbol
                ├── BabelCharRange
                └── BabelNumRange
"""

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
    atom: BabelAtom

RangeType = TypeVar('RangeType')

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
class BabelBlock: # block1 | block2 | block3
    atoms: list[BabelAtom]

@dataclass
class BabelProduction:
    production: list[BabelBlock]

@dataclass
class BabelIr:
    production_rules: dict[str, BabelProduction]