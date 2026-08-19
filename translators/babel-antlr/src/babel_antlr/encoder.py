from antlr4 import CommonTokenStream
from antlr4.InputStream import InputStream
from babel_ir.model import BabelIr
from babel_antlr._generated import ANTLRv4ParserVisitor
from babel_antlr._generated.ANTLRv4Lexer import ANTLRv4Lexer
from babel_antlr._generated.ANTLRv4Parser import ANTLRv4Parser


class Visitor(ANTLRv4ParserVisitor):
    pass


def encode(string: str) -> BabelIr:
    input_stream = InputStream(string)
    lexer = ANTLRv4Lexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = ANTLRv4Parser(stream)

    tree = parser.grammarSpec()

    parse_tree_visitor = Visitor()
    parse_tree_visitor.visit(tree)
    # For ease hook onto every parser and lexer rule and parse them to a production. Same with fragment rules
