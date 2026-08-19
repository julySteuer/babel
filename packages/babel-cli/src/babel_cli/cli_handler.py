from babel_antlr.infra import (
    setup as setup_all,
)  # TODO: Decouple this
from babel_antlr.infra import (
    teardown as teardown_all,
)


def _handle_translate(inp: list[str] | None, output: str | None) -> None:
    from babel_antlr.encoder import encode

    if inp is None or output is None:
        return
    # First single file case. Multi file case requires merging algorithm to exist
    grammars = []
    for grammar_file in inp:
        with open(grammar_file, "r") as file:
            content = file.read()
            parsed_content = encode(content)
            grammars.append(parsed_content)

    # TODO: Merge Grammars. Even normal bcs of split grammars
    # decode
    print(f"[BABEL] Input Grammars: {input}; Output Grammar: {output}")
    decoded: str = str(grammars[0])
    file.write(decoded)


def _handle_setup() -> None:
    setup_all()


def _handle_teardown() -> None:
    teardown_all()


def handle_cli(args) -> None:
    match args.mode:
        case "setup":
            _handle_setup()
        case "teardown":
            _handle_teardown()
        case "translate":
            _handle_translate(args.input, args.output)
