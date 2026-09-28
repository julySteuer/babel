from abc import ABC
from dataclasses import dataclass

"""
For safety it might be better to have a type (discriminated union) which holds all the LexerAtom and one that holds all the parser Atoms. Currently I think they are all the same but lets see
"""

class AntlrAtom(ABC):
    pass

class AntlrTerminal(AntlrAtom, ABC):
    pass

@dataclass
class AntlrSymbol(AntlrTerminal):
    terminal: str


@dataclass
class AntlrNonterminal(AntlrAtom, ABC):
    nonterminal: str

@dataclass
class AntlrLexerNonterminal(AntlrNonterminal):
    pass

@dataclass
class AntlrParserNonterminal(AntlrNonterminal):
    pass

@dataclass
class AntlrOptional(AntlrAtom):
    atom: AntlrAtom  # Change this to aceppt block like structure

@dataclass
class AntlrStar(AntlrAtom):
    atom: AntlrAtom

@dataclass
class AntlrPlus(AntlrAtom):
    atom: AntlrAtom

@dataclass
class AntlrNot(AntlrAtom):
    atom: AntlrLexerNonterminal

@dataclass
class AntlrLexerWildcard(AntlrAtom):
    pass

@dataclass
class AntlrParserWildcard(AntlrAtom):
    pass

AntlrWildcard = AntlrLexerWildcard | AntlrParserWildcard

@dataclass
class AntlrRange[RangeType](AntlrTerminal, ABC):
    beginning: RangeType
    end: RangeType

@dataclass
class AntlrCharRange(AntlrRange[str]):
    pass


@dataclass
class AntlrNumRange(AntlrRange[int]):
    pass

@dataclass
class AntlrRawRegex(AntlrTerminal):
    raw: str

@dataclass
class AntlrBlock(AntlrAtom):  # block1 | block2 | block3
    atoms: list[AntlrAtom]

@dataclass
class AntlrBlockList(AntlrAtom):
    opts: list[AntlrBlock]

@dataclass
class AntlrChannel:
    pass

@dataclass
class AntlrSkip:
    pass

AntlrAction = AntlrChannel | AntlrSkip

# -> rules and such are only permitted in lexer rules so only lexer rules need a channel argument
@dataclass
class AntlrProduction(ABC):
    production: AntlrBlockList

@dataclass
class AntlrLexerProduction(AntlrProduction, ABC):
    pass

@dataclass
class ActedLexerProduction(AntlrLexerProduction):
    channel: AntlrAction

@dataclass
class RegularLexerProduction(AntlrLexerProduction):
    pass

@dataclass
class AntlrParserProduction(AntlrProduction):
    pass

@dataclass
class AntlrIr:
    production_rules: dict[str, AntlrProduction]
    action_rules: list[str] # Named references for rulesin production_rules
