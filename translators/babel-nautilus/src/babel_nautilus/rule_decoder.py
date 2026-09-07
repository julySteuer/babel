import itertools
from abc import ABC
from dataclasses import dataclass

from babel_nautilus.model.nautilus_ir import NautilusExpr, NautilusBlock, NautilusAtom, NautilusNonterminal, \
    NautilusTerminal, NautilusRegex
from babel_nautilus.model.rule import (
    Rule,
    Block,
    Atom,
    TerminalAtom,
    NonterminalAtom,
    RegexAtom,
    RegexBlock,
    RuleBlock,
    EmptyBlock,
)
from babel_nautilus.name_generator import stateful_name_generator
from babel_nautilus.shared import make_nonterminal_str, capitalize_name


def _flatten[T](l: list[list[T]]) -> list[T]:
    return list(itertools.chain(*l))

def _decode_atom(atom: NautilusAtom) -> tuple[Atom, list[Rule]]:
    match atom:
        case NautilusTerminal(terminal=terminal):
            return TerminalAtom(terminal), list()
        case NautilusNonterminal(nonterminal=name):
            return NonterminalAtom(make_nonterminal_str(name)), list()
        case NautilusRegex(regex=regex):
            return RegexAtom(regex), list()
        case NautilusExpr():
            return _decode_expression(atom)

def _construct_rule_for_regex(regex: RegexAtom, parent_name: str) -> tuple[str, Rule]: # Refferer and rule
    name = stateful_name_generator.generate_for(parent_name)
    return make_nonterminal_str(capitalize_name(name)), Rule( # TODO: Make this a function to generate nonterminals
        capitalize_name(name),
        [
            RegexBlock(
                regex.regex
            )
        ]
    )

def _construct_block_with_additional_references(child_atom: Atom, name: str) -> tuple[str, Rule | None]:
    match child_atom:
        case RegexAtom():
            return _construct_rule_for_regex(child_atom, name)
        case NonterminalAtom(refferer=text) | TerminalAtom(content=text):
            return text, None

def _construct_block(child_atoms: list[Atom], name: str) -> tuple[Block, list[Rule]]:
    # TODO: Make this more nuanced. So that empty rules with child_atoms == [] a ruleBlock with an empty list
    if not child_atoms:
        return EmptyBlock(), list()
    is_regex_rule = all(isinstance(atom, RegexAtom) for atom in child_atoms)

    if is_regex_rule:
        # Merge all the children
        # This might thorw a type error. but all have been checked
        content = "".join(regex.regex for regex in child_atoms)
        return RegexBlock(content), list() # No new rules generated

    block_data = [
        _construct_block_with_additional_references(child_atom, name) for child_atom in child_atoms
    ]
    # Has to be done this way
    additional_rules = [
        block[1] for block in block_data
    ]
    additional_rules = [
        block for block in additional_rules if block is not None
    ]
    content = "".join(
        [
            block[0] for block in block_data
        ]
    )
    return RuleBlock(
        content
    ), additional_rules



def _decode_block(block: NautilusBlock, name: str) -> tuple[Block, list[Rule]]:
    child_atoms = [
        _decode_atom(atom) for atom in block.children
    ]

    rules = _flatten(
        [
            child[1] for child in child_atoms
        ]
    )

    children = [
        child[0] for child in child_atoms
    ]

    block_with_refs = _construct_block(children, name)

    return block_with_refs[0], rules + block_with_refs[1]


def _decode_expression(nautilus_expr: NautilusExpr) -> tuple[Atom, list[Rule]]:
    name = nautilus_expr.name
    blocks = [
        _decode_block(block, name) for block in nautilus_expr.options
    ]

    block_data = [
        block[0] for block in blocks
    ]

    inner_rule = Rule(
        name,
        block_data
    )

    child_rules = _flatten([
        block[1] for block in blocks
    ])

    return NonterminalAtom(make_nonterminal_str(name)), child_rules + [inner_rule]


def decode_to_rules(nautilus_expressions: list[NautilusExpr]) -> list[Rule]:
    rules = [
        _decode_expression(expr)[1] for expr in nautilus_expressions
    ]

    return _flatten(rules)

__all__ = ['decode_to_rules']