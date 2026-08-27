from antlr4 import CommonTokenStream
from antlr4.InputStream import InputStream
from babel_antlr._generated.ANTLRv4Lexer import ANTLRv4Lexer
from babel_antlr._generated.ANTLRv4Parser import ANTLRv4Parser
from babel_antlr.lexer_encoder import encode_lexer_rule
from babel_antlr.parser_encoder import encode_parser_rule
from babel_antlr.util import exec_first_valid
from babel_ir.model import BabelIr, BabelProduction


def _encode_rule(rule: ANTLRv4Parser.RuleSpecContext) -> tuple[str, BabelProduction]:
    lexer_rule = rule.lexerRuleSpec()
    parser_rule = rule.parserRuleSpec()

    # Ternary to check which branch is active. Implicitly the other one is valid
    return exec_first_valid((lexer_rule, encode_lexer_rule), (parser_rule, encode_parser_rule)) # TODO: make a first macth function that only executes the only match for alt options

def _encode_rules(rules: ANTLRv4Parser.ParserRuleSpecContext) -> list[tuple[str, BabelProduction]]:
    children = rules.children
    if children is None:
        return []
    return [_encode_rule(rule) for rule in children]

def _encode_to_ir(grammar_spec_context: ANTLRv4Parser.GrammarSpecContext) -> BabelIr:
    productions = _encode_rules(grammar_spec_context.rules())
    ir = { key: value for key, value in productions }
    return BabelIr(ir)


def encode(string: str) -> BabelIr:
    input_stream = InputStream(string)
    lexer = ANTLRv4Lexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = ANTLRv4Parser(stream)

    tree = parser.grammarSpec()
    return _encode_to_ir(tree)
    # Dont use visitor do it functionaliy instaed
    # For ease hook onto every parser and lexer rule and parse them to a production. Same with fragment rules
__all__ = ['encode']