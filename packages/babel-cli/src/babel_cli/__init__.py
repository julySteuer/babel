from argparse import ArgumentParser

from babel_cli.cli_handler import handle_cli


def main() -> None:
    parser = ArgumentParser(description="Tranlsation tool for AntlrV4 Grammar")
    parser.add_argument("mode", choices=["setup", "translate", "teardown"])
    parser.add_argument(
        "-i", "--input", help="AntlrV4 input files", nargs="+", type=str
    )
    parser.add_argument("-o", "--output", help="Output Nautilus grammar", type=str)
    args = parser.parse_args()
    handle_cli(args)
