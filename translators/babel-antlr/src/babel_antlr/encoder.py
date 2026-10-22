from antlr4 import CommonTokenStream
from antlr4.InputStream import InputStream

from babel_antlr._generated.ANTLRv4Lexer import ANTLRv4Lexer
from babel_antlr._generated.ANTLRv4Parser import ANTLRv4Parser
from babel_antlr.antlr_ir_decoder import decode_antlr_ir_to_babel_ir
from babel_antlr.antlr_ir_encoder import encode_to_antlr_ir
from babel_ir.model import BabelIr


def encode(string: str) -> BabelIr:
    input_stream = InputStream(string)
    lexer = ANTLRv4Lexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = ANTLRv4Parser(stream)

    tree = parser.grammarSpec()
    antlr_ir = encode_to_antlr_ir(tree)
    return decode_antlr_ir_to_babel_ir(antlr_ir)
    # Dont use visitor do it functionaliy instaed
    # For ease hook onto every parser and lexer rule and parse them to a production. Same with fragment rules


__all__ = ["encode"]
