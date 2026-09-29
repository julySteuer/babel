from babel_antlr._generated.ANTLRv4Parser import ANTLRv4Parser
from babel_antlr.lexer_encoder import encode_lexer_rule
from babel_antlr.model.antlr_ir import (
    AntlrIr,
    AntlrProduction,
    ActedAntlrLexerBlock,
    AntlrBlock,
)
from babel_antlr.parser_encoder import encode_parser_rule
from babel_antlr.util import exec_first_valid


def _encode_rule(rule: ANTLRv4Parser.RuleSpecContext) -> tuple[str, AntlrProduction]:
    lexer_rule = rule.lexerRuleSpec()
    parser_rule = rule.parserRuleSpec()

    # Ternary to check which branch is active. Implicitly the other one is valid
    return exec_first_valid((lexer_rule, encode_lexer_rule), (parser_rule, encode_parser_rule)) # TODO: make a first macth function that only executes the only match for alt options

def _encode_rules(rules: ANTLRv4Parser.ParserRuleSpecContext) -> list[tuple[str, AntlrProduction]]:
    children = rules.children
    if children is None:
        return []
    return [_encode_rule(rule) for rule in children]

def _find_action_rules(productions: dict[str, AntlrProduction]) -> dict[str, list[ActedAntlrLexerBlock]]:
    return {
        name: [block for block in value.production.opts if isinstance(block, ActedAntlrLexerBlock)]
        for name, value in productions.items()
    }

def encode_to_antlr_ir(grammar_spec_context: ANTLRv4Parser.GrammarSpecContext) -> AntlrIr:
    productions = _encode_rules(grammar_spec_context.rules())
    ir = { key: value for key, value in productions }
    action_rules = _find_action_rules(ir)
    return AntlrIr(ir, action_rules)

__all__ = ["encode_to_antlr_ir"]