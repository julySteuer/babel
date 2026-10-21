from babel_ir.model import BabelIr
from babel_nautilus import preprocess
from babel_nautilus.model.rule import Rule, Block, RegexBlock, RuleBlock, EmptyBlock
from babel_nautilus.rule_decoder import decode_to_rules

from babel_nautilus.ir_decoder import decode_ir

def _python_string_literal_body(content: str) -> str:
    """Escapes content so that it reads back unchanged when the generated python grammar is executed."""
    escaped = []
    for char in content:
        match char:
            case "\\":
                escaped.append("\\\\")
            case '"':
                escaped.append('\\"')
            case "\n":
                escaped.append("\\n")
            case "\r":
                escaped.append("\\r")
            case "\t":
                escaped.append("\\t")
            case _ if ord(char) < 0x20 or ord(char) == 0x7f:
                escaped.append(f"\\x{ord(char):02x}")
            case _:
                escaped.append(char)
    return "".join(escaped)

def _string_from_block(block: Block, name: str) -> str:
    match block:
        case RegexBlock(content=content):
            return f"ctx.regex(\"{name}\", \"{_python_string_literal_body(content)}\")"
        case RuleBlock(content=content):
            return f"ctx.rule(\"{name}\", \"{_python_string_literal_body(content)}\")"
        case EmptyBlock():
            return f"ctx.rule(\"{name}\", \"\")"

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

def decode(babel_ir: BabelIr, start_rule_name: str) -> str:
    processed_ir = preprocess.add_start_rule(babel_ir, start_rule_name)
    added_eof_ir = preprocess.add_eof_rule(processed_ir)
    decoded = decode_ir(added_eof_ir)
    decoded_rules = decode_to_rules(decoded)

    generated_rules = _generate_rules(decoded_rules)
    return "\n".join(generated_rules)


__all__ = ["decode"]
