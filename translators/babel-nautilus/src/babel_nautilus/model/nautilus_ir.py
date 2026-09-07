from abc import ABC
from dataclasses import dataclass

from babel_ir.model import BabelBlock
from babel_nautilus.shared import check_nonterminal_reference, capitalize_name

"""
NautilusRule(name: str, options: [NautilusBlock])
NautilusBlock(children: [NautilusAtom])
NautilusAtom(NautilusRule, NautilusTerminal, NautilusNonterminal)

foo -> BAR [a-z] 'test'

Parses to :

NautilusExpr(
    name: 'foo',
    options: [
        NautilusRuleBlock(
            children: [
                NautilusNonterminal('BAR'),
                NautilusExpr('FOO_RANGE', options: [
                    NautilusRegexBlock([
                        NautilusRegex('[a-z]')
                    ])
                ]),
                NautilusTerminal('test')
            ]
        )
    ]
)

Parses to:

ctx.rule('foo': '<BAR><FOO_RANGE>test')
ctx.regex('FOO_RANGE', '[a-z]')

Rule(name: str, options: [str], mode: RuleMode)

def _get_all_rules(rule: NautilusRule) -> list[Rule]:
    pass
"""

class NautilusAtom(ABC):
    pass

@dataclass
class NautilusTerminal(NautilusAtom):
    terminal: str

@dataclass
class NautilusNonterminal(NautilusAtom):
    nonterminal: str

    def __post_init__(self):
        check_nonterminal_reference(self.nonterminal)

@dataclass
class NautilusRegex(NautilusAtom):
    regex: str

@dataclass
class NautilusBlock:
    children: list[NautilusAtom]

# Maybe add Rule list later only if problems arise

@dataclass
class NautilusExpr(NautilusAtom):
    name: str
    options: list[NautilusBlock]

    @classmethod
    def capitalize_name(cls, name: str, options: list[NautilusBlock]):
        return cls(capitalize_name(name), options)

    def __post_init__(self):
        check_nonterminal_reference(self.name)