import subprocess
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class InitAntlrOnStartHook(BuildHookInterface):
    PLUGIN_NAME = "Init Antlr4 Hook"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        base_antlr4_download_path = Path(
            Path(self.root) / "translators" / "babel-antlr" / "src" / "babel_antlr" / "_generated"
        )
        # TODO: Add A Environment Variable to trigger rebuild
        if base_antlr4_download_path.exists():
            print("Skipping download and regeneration phase. When Rebuild requires re pulling delete the _generated directory from babel_antlr")
            return

        antlrv4_lexer_grammar_file = "ANTLRv4Lexer.g4"
        antlrv4_parser_grammar_file = "ANTLRv4Parser.g4"
        antlrv4_jar_url = "http://www.antlr.org/download/antlr-4.13.1-complete.jar"
        antlrv4_grammar_base_url = "https://raw.githubusercontent.com/antlr/grammars-v4/refs/heads/master/antlr/antlr4/"
        antlrv4_grammar_python_base = antlrv4_grammar_base_url + "/Python3"
        antlrv4_lexer_grammar_url = (
            antlrv4_grammar_base_url + antlrv4_lexer_grammar_file
        )
        antlrv4_parser_grammar_url = (
            antlrv4_grammar_base_url + antlrv4_parser_grammar_file
        )

        base_antlr4_download_path.mkdir(parents=True, exist_ok=True)
        (base_antlr4_download_path / "__init__.py").touch(exist_ok=True)

        urlretrieve(antlrv4_jar_url, base_antlr4_download_path / "antlrv4.jar")
        urlretrieve(
            antlrv4_lexer_grammar_url,
            base_antlr4_download_path / antlrv4_lexer_grammar_file,
        )
        urlretrieve(
            antlrv4_parser_grammar_url,
            base_antlr4_download_path / antlrv4_parser_grammar_file,
        )

        lexer_adaptor_path = base_antlr4_download_path / "LexerAdaptor.py"
        urlretrieve(
            antlrv4_grammar_python_base + "/LexerAdaptor.py", lexer_adaptor_path
        )

        lexer_adaptor_path.write_text(
            lexer_adaptor_path.read_text().replace(
                "from ANTLRv4Parser import ANTLRv4Parser",
                "from .ANTLRv4Parser import ANTLRv4Parser",
            )
        )

        urlretrieve(
            antlrv4_grammar_python_base + "/transformGrammar.py",
            base_antlr4_download_path / "transformGrammar.py",
        )

        subprocess.check_output(
            ["python3", str(base_antlr4_download_path / "transformGrammar.py")],
            cwd=base_antlr4_download_path,
        )

        subprocess.check_output(
            [
                "java",
                "-jar",
                str(base_antlr4_download_path / "antlrv4.jar"),
                "-Dlanguage=Python3",
                str(base_antlr4_download_path / antlrv4_lexer_grammar_file),
            ]
        )
        subprocess.check_output(
            [
                "java",
                "-jar",
                str(base_antlr4_download_path / "antlrv4.jar"),
                "-Dlanguage=Python3",
                str(base_antlr4_download_path / antlrv4_parser_grammar_file),
            ]
        )
