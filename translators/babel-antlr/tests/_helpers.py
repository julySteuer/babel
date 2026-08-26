"""Shared test helpers for the babel_antlr test suite.

encode() (and the encode_parser_rule/encode_lexer_rule it dispatches to)
still returns raw antlr4 TerminalNode objects wherever the IR model
declares a plain ``str`` (BabelNonterminal.nonterminal, BabelSymbol.terminal
for lexer-encoded literals, BabelCharRange.beginning/end, and the
BabelIr.production_rules keys) rather than calling .getText() on them.
normalize() walks the returned tree and replaces every such node with
node.getText(), so tests can compare against BabelIr/BabelBlock/... built
with plain string literals instead of depending on antlr4 object identity.
"""

from babel_antlr.encoder import encode
from babel_ir.model import (
    BabelBlock,
    BabelBlockList,
    BabelCharRange,
    BabelIr,
    BabelNonterminal,
    BabelNot,
    BabelOptional,
    BabelPlus,
    BabelProduction,
    BabelStar,
    BabelSymbol,
)


def normalize(node):
    if isinstance(node, BabelIr):
        return BabelIr({str(k): normalize(v) for k, v in node.production_rules.items()})
    if isinstance(node, BabelProduction):
        return BabelProduction(normalize(node.production))
    if isinstance(node, BabelBlockList):
        return BabelBlockList([normalize(a) for a in node.opts])
    if isinstance(node, BabelBlock):
        return BabelBlock([normalize(a) for a in node.atoms])
    if isinstance(node, BabelSymbol):
        return BabelSymbol(str(node.terminal))
    if isinstance(node, BabelNonterminal):
        return BabelNonterminal(str(node.nonterminal))
    if isinstance(node, BabelCharRange):
        return BabelCharRange(str(node.beginning), str(node.end))
    if isinstance(node, (BabelOptional, BabelStar, BabelPlus, BabelNot)):
        return type(node)(normalize(node.atom))
    return node


def encode_grammar(grammar_source: str) -> BabelIr:
    """Encode a full grammar (including the `grammar Name;` header) and normalize the result."""
    return normalize(encode(grammar_source))


def encode_rule(rule_source: str, rule_name: str = "r") -> BabelProduction:
    """Wrap a single rule body in a minimal grammar, encode it, and return its normalized BabelProduction."""
    ir = encode_grammar(f"grammar Test;\n{rule_source}\n")
    return ir.production_rules[rule_name]
