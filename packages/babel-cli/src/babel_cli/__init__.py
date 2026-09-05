from argparse import ArgumentParser

from babel_cli.cli_handler import handle_cli

# Maybe do this with subparser
def main() -> None:
    parser = ArgumentParser(description="Translation tool for AntlrV4 Grammar")
    parser.add_argument("mode", choices=["translate"])
    parser.add_argument(
        "-i", "--input", help="AntlrV4 input files", nargs="+", type=str
    )
    parser.add_argument("-o", "--output", help="Output Nautilus grammar", type=str)
    parser.add_argument("-s", "--start-symbol", help="Start Symbol name of the grammar", type=str)
    args = parser.parse_args()
    handle_cli(args)
