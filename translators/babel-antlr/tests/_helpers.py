"""Helpers for testing the ANTLR grammar -> AntlrIr encoding step."""

from antlr4 import CommonTokenStream
from antlr4.InputStream import InputStream

from babel_antlr._generated.ANTLRv4Lexer import ANTLRv4Lexer
from babel_antlr._generated.ANTLRv4Parser import ANTLRv4Parser
from babel_antlr.antlr_ir_encoder import encode_to_antlr_ir
from babel_antlr.model.antlr_ir import AntlrIr, AntlrProduction


def to_antlr_ir(grammar_source: str) -> AntlrIr:
    """Encode a full grammar (including the `grammar Name;` header) to an AntlrIr."""
    parser = ANTLRv4Parser(CommonTokenStream(ANTLRv4Lexer(InputStream(grammar_source))))
    return encode_to_antlr_ir(parser.grammarSpec())


def rule(rule_source: str, name: str) -> AntlrProduction:
    """Wrap rule source in a minimal grammar, encode it and return the production called `name`."""
    return to_antlr_ir(f"grammar Test;\n{rule_source}\n").production_rules[name]
