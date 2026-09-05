from abc import ABC
from dataclasses import dataclass

@dataclass
class Block(ABC):
    content: str

@dataclass
class RegexBlock(Block):
    pass

@dataclass
class RuleBlock(Block):
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