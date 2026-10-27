from babel_antlr.encoder import encode_all
from babel_nautilus.decoder import decode


def generate_nautilus(antlr_content: list[str], starting_symbol: str) -> str:
    return decode(encode_all(antlr_content), starting_symbol)
