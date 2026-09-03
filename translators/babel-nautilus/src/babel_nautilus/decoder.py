from abc import ABC
from dataclasses import dataclass
from enum import Enum

from babel_ir.model import BabelIr, BabelProduction, BabelBlockList, BabelBlock
from babel_nautilus.model.rule import Rule, Block, RegexBlock, RuleBlock
from babel_nautilus.rule_decoder import decode_to_rules

from babel_nautilus.ir_decoder import decode_ir

def _string_from_block(block: Block, name: str) -> str:
    match block:
        case RegexBlock(content=content):
            return f"ctx.regex(\"{name}\", \"{content}\")"
        case RuleBlock(content=content):
            return f"ctx.rule(\"{name}\", \"{content}\")"

def _generate_rule(rule: Rule) -> str:
    name = rule.name

    rules = [
        _string_from_block(block, name) for block in rule.blocks
    ]

    return "\n".join(rules)

def _generate_rules(rules: list[Rule]) -> list[str]:
    return [
        _generate_rule(rule) for rule in rules
    ]

def decode(babel_ir: BabelIr) -> str:
    decoded = decode_ir(babel_ir)
    decoded_rules = decode_to_rules(decoded)

    generated_rules = _generate_rules(decoded_rules)
    return "\n".join(generated_rules)


__all__ = ["decode"]
