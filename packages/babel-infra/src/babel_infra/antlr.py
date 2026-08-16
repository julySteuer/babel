import subprocess
from pathlib import Path
from urllib.request import urlretrieve
from shutil import rmtree

from babel_infra.root import ROOT

BASE_ANTLR4_DOWNLOAD_PATH = Path(ROOT / "babel-translators" / "src" / "babel_translators" / "antlr" / "_generated")

def setup():
    print("Setting up...")
    BASE_ANTLR4_DOWNLOAD_PATH.mkdir(parents=True, exist_ok=True)
    (BASE_ANTLR4_DOWNLOAD_PATH / "__init__.py").touch(exist_ok=True)

    ANTLRV4_LEXER_GRAMMAR_FILE = "ANTLRv4Lexer.g4"
    ANTLRV4_PARSER_GRAMMAR_FILE = "ANTLRv4Parser.g4"
    ANTLRV4_JAR_URL = "http://www.antlr.org/download/antlr-4.13.1-complete.jar"
    ANTLRV4_GRAMMAR_BASE_URL = "https://raw.githubusercontent.com/antlr/grammars-v4/refs/heads/master/antlr/antlr4/"
    ANTLRV4_GRAMMAR_PYTHON_BASE = ANTLRV4_GRAMMAR_BASE_URL + "/Python3"
    ANTLRV4_LEXER_GRAMMAR_URL = ANTLRV4_GRAMMAR_BASE_URL + ANTLRV4_LEXER_GRAMMAR_FILE
    ANTLRV4_PARSER_GRAMMAR_URL = ANTLRV4_GRAMMAR_BASE_URL + ANTLRV4_PARSER_GRAMMAR_FILE

    urlretrieve(ANTLRV4_JAR_URL, BASE_ANTLR4_DOWNLOAD_PATH / "antlrv4.jar")
    urlretrieve(ANTLRV4_LEXER_GRAMMAR_URL, BASE_ANTLR4_DOWNLOAD_PATH / ANTLRV4_LEXER_GRAMMAR_FILE)
    urlretrieve(ANTLRV4_PARSER_GRAMMAR_URL, BASE_ANTLR4_DOWNLOAD_PATH / ANTLRV4_PARSER_GRAMMAR_FILE)

    lexer_adaptor_path = BASE_ANTLR4_DOWNLOAD_PATH / "LexerAdaptor.py"
    urlretrieve(ANTLRV4_GRAMMAR_PYTHON_BASE + "/LexerAdaptor.py", lexer_adaptor_path)

    lexer_adaptor_path.write_text(
        lexer_adaptor_path.read_text().replace(
            "from ANTLRv4Parser import ANTLRv4Parser",
            "from .ANTLRv4Parser import ANTLRv4Parser",
        )
    )

    urlretrieve(ANTLRV4_GRAMMAR_PYTHON_BASE + "/transformGrammar.py", BASE_ANTLR4_DOWNLOAD_PATH / "transformGrammar.py")

    subprocess.check_output(["python3", str(BASE_ANTLR4_DOWNLOAD_PATH / "transformGrammar.py")], cwd=BASE_ANTLR4_DOWNLOAD_PATH)

    subprocess.check_output(["java", "-jar", str(BASE_ANTLR4_DOWNLOAD_PATH / "antlrv4.jar"), "-Dlanguage=Python3", str(BASE_ANTLR4_DOWNLOAD_PATH / ANTLRV4_LEXER_GRAMMAR_FILE), "-visitor"])
    subprocess.check_output(["java", "-jar", str(BASE_ANTLR4_DOWNLOAD_PATH / "antlrv4.jar"), "-Dlanguage=Python3", "-visitor", str(BASE_ANTLR4_DOWNLOAD_PATH / ANTLRV4_PARSER_GRAMMAR_FILE)])

def teardown():
    print("Tearing down...")
    rmtree(BASE_ANTLR4_DOWNLOAD_PATH)