from abc import ABC
from dataclasses import dataclass

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

@dataclass
class RegexAtom(Atom):
    regex: str

@dataclass
class Rule:
    name: str
    blocks: list[Block]