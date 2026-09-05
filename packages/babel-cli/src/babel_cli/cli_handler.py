from pathlib import Path

from babel_core.domain import generate_nautilus


def _handle_translate(inp: list[str] | None, output: str | None, start_symbol: str | None) -> None:
    if inp is None or output is None or start_symbol is None:
        return
    # First single file case. Multi file case requires merging algorithm to exist
    grammars = [
        Path(file_name).read_text() for file_name in inp
    ]

    translated_nautilus = generate_nautilus(grammars, start_symbol)

    print(f"[BABEL] Input Grammars: {input}; Output Grammar: {output}")
    Path(output).write_text(translated_nautilus)

def handle_cli(args) -> None:
    match args.mode:
        case "translate":
            _handle_translate(args.input, args.output, args.start_symbol)
