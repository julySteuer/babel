from babel_antlr.antlr_ir_encoder import encode
from babel_ir.domain import merge
from babel_nautilus.decoder import decode


def generate_nautilus(antlr_content: list[str], starting_symbol: str) -> str:
    parsed_irs = [
        encode(antlr) for antlr in antlr_content
    ]

    merged_ir = merge(parsed_irs)

    return decode(merged_ir, starting_symbol)