from babel_infra import setup_all, teardown_all
from babel_translators.antlr.encoder import encode

def _handle_translate(input: list[str] | None, output: str | None) -> None:
    if input == None or output == None:
        return
    # First single file case. Multi file case requires merging algorithm to exist
    grammars = []
    for grammar_file in input:
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

def handle_cli(args: any) -> None:
    match args.mode:
        case "setup":
            _handle_setup()
        case "teardown":
            _handle_teardown()
        case "translate":
            _handle_translate(args.input, args.output)