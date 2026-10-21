from pathlib import Path

from babel_core.domain import generate_nautilus

def _generate_file_list_display_str(file_list: list[str]) -> str:
    return ", ".join(file_list)


def _handle_translate(inp: list[str] | None, output: str | None, start_symbol: str | None) -> None:
    if inp is None or output is None or start_symbol is None:
        return

    grammars = [
        Path(file_name).read_text() for file_name in inp
    ]

    translated_nautilus = generate_nautilus(grammars, start_symbol) # TODO: Make this modular. Should delegate to another function in babel-core

    print(f"[BABEL] Input Grammars: {_generate_file_list_display_str(inp)}; Output Grammar: {output}")
    Path(output).write_text(translated_nautilus)

def handle_cli(args) -> None:
    match args.mode:
        case "translate":
            _handle_translate(args.input, args.output, args.start_symbol)
