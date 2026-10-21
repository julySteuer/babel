from abc import ABC
from dataclasses import dataclass

"""
For safety it might be better to have a type (discriminated union) which holds all the LexerAtom and one that holds all the parser Atoms. Currently I think they are all the same but lets see
Lot of these things here are done bcs lots of info is not available at comptime
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
# TODO: These rules might not be nessesary due to them requireing swmantic analysis
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
    atom: AntlrLexerNonterminal # This needs to be a reference for not checking which means this should be done in another pass for validation

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
class AntlrBlock(AntlrAtom, ABC):  # block1 | block2 | block3
    atoms: list[AntlrAtom]

@dataclass
class AntlrChannel:
    pass

@dataclass
class AntlrSkip:
    pass

AntlrAction = AntlrChannel | AntlrSkip

@dataclass
class AntlrLexerBlock(AntlrBlock):
    pass

@dataclass
class ActedAntlrLexerBlock(AntlrLexerBlock):
    channel: AntlrAction

@dataclass
class RegularAntlrLexerBlock(AntlrLexerBlock):
    pass

@dataclass
class AntlrParserBlock(AntlrBlock):
    pass

@dataclass
class AntlrBlockList(AntlrAtom):
    opts: list[AntlrBlock]

# -> rules and such are only permitted in lexer rules so only lexer rules need a channel argument
@dataclass
class AntlrProduction(ABC):
    production: AntlrBlockList

@dataclass
class AntlrLexerProduction(AntlrProduction):
    pass

@dataclass
class AntlrParserProduction(AntlrProduction):
    pass

@dataclass
class AntlrIr:
    production_rules: dict[str, AntlrProduction]
    action_blocks: list[tuple[str, ActedAntlrLexerBlock]] # Named references for rulesin production_rules
