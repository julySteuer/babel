from antlr4 import CommonTokenStream
from antlr4.InputStream import InputStream

from babel_antlr._generated.ANTLRv4Lexer import ANTLRv4Lexer
from babel_antlr._generated.ANTLRv4Parser import ANTLRv4Parser
from babel_antlr.antlr_ir_decoder import decode_antlr_irs_to_babel_irs
from babel_antlr.antlr_ir_encoder import encode_to_antlr_ir
from babel_antlr.model.antlr_ir import AntlrIr
from babel_ir.model import BabelIr


def _to_antlr_ir(string: str) -> AntlrIr:
    input_stream = InputStream(string)
    lexer = ANTLRv4Lexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = ANTLRv4Parser(stream)

    tree = parser.grammarSpec()
    return encode_to_antlr_ir(tree)
    # Dont use visitor do it functionaliy instaed
    # For ease hook onto every parser and lexer rule and parse them to a production. Same with fragment rules


def encode_all(strings: list[str]) -> BabelIr:
    return decode_antlr_irs_to_babel_irs([_to_antlr_ir(string) for string in strings])


def encode(string: str) -> BabelIr:
    return encode_all([string])


__all__ = ["encode", "encode_all"]
