from abc import ABC
from dataclasses import dataclass

from babel_nautilus.shared import check_nonterminal_reference


@dataclass
class Block(ABC):
    pass


@dataclass
class RegexBlock(Block):
    content: str


@dataclass
class RuleBlock(Block):
    content: str


@dataclass
class EmptyBlock(Block):
    pass


class Atom(ABC):
    pass


@dataclass
class TerminalAtom(Atom):
    content: str


@dataclass
class NonterminalAtom(Atom):
    refferer: str

    def __post_init__(self):
        if (
            not self.refferer.startswith("{")
            or not self.refferer.endswith("}")
            or not self.refferer[1].isupper()
        ):
            raise Exception(f"Malformed NonterminalAtom: {self.refferer}")


@dataclass
class RegexAtom(Atom):
    regex: str


@dataclass
class Rule:
    name: str
    blocks: list[Block]

    def __post_init__(self):
        check_nonterminal_reference(self.name)
