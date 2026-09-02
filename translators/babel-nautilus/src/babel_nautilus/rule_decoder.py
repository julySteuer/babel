import itertools
from abc import ABC
from dataclasses import dataclass

from babel_nautilus.model.nautilus_ir import NautilusExpr, NautilusBlock, NautilusAtom, NautilusNonterminal, \
    NautilusTerminal, NautilusRegex
from babel_nautilus.model.rule import Rule, RuleMode
from babel_nautilus.name_generator import stateful_name_generator

@dataclass
class IntRule(ABC):
    content: str

@dataclass
class IntRegexRule(IntRule):
    pass

@dataclass
class IntTerminatingRule(IntRule):
    pass

def flatten[T](l: list[list[T]]) -> list[T]:
    return list(itertools.chain(*l))

# This seems scuffed. first element are all the children. the second one is the pipeline of all the previous rules. Always flat
# list[str] -> atoms
child_rule_return = tuple[Rule, list[Rule]]
atom_return = tuple[IntRule, list[Rule]]

def _decode_regex(regex: NautilusRegex) -> atom_return:
    name = stateful_name_generator.generate_for('regex')
    return IntRegexRule(name), list()

def _str_to_nonterm(string: str) -> str:
    return f"<{string}>"

def _decode_atom(atom: NautilusAtom) -> atom_return:
    match atom:
        case NautilusNonterminal(nonterminal=nonterminal):
            return IntTerminatingRule(_str_to_nonterm(nonterminal)), list()
        case NautilusTerminal(terminal=terminal):
            return IntTerminatingRule(terminal), list()
        case NautilusRegex():
            return _decode_regex(atom)
        case NautilusExpr():
            return _decode_expr(atom)

def _create_regex_rule_when_unmatched(rule_mode: RuleMode, name: str, intermediate: IntRule) -> tuple[str,Rule] | None:
    if rule_mode is RuleMode.regex or intermediate is not IntRegexRule:
        return None

    generated_name = stateful_name_generator.generate_for(name)

    return generated_name, Rule(
        generated_name,
        RuleMode.regex,
        intermediate.content
    )

def _decode_block(block: NautilusBlock, name: str) -> child_rule_return:
    atoms = [
        _decode_atom(atom) for atom in block.children
    ]

    rules = [res[1] for res in atoms]

    children = [res[0] for res in atoms]

    rule_mode = _determine_rule_mode(children)

    rule = Rule(
        name,
        rule_mode,
    )

    return rule, flatten(rules)

def _determine_rule_mode(direct_child_rules: list[IntRule]) -> RuleMode:
    for elem in direct_child_rules:
        if not isinstance(elem, IntRegexRule):
            return RuleMode.rule
    return RuleMode.regex

def _decode_expr(expr: NautilusExpr) -> atom_return:
    name = expr.name
    options = [
        _decode_block(block, name) for block in expr.options
    ]

    # TODO: THE RULE CREATION SHOULD BE ON THE BLOCK LEVEL AND NOT HERE. Otherwise it cannot be decided or it is not optimal

    return IntTerminatingRule(_str_to_nonterm(name)), list(itertools.chain(*all_child_rules)) # returns the refferer name

"""
For every expression. Walk down the tree. yield each rule that is generated with its name.
Check if a rule can be simplified to a regex rule 
"""
def _decode_to_rules(nautilus_expressions: list[NautilusExpr]) -> list[Rule]:
    expressions = [
        _decode_expr(expr) for expr in nautilus_expressions
    ]

    return expressions