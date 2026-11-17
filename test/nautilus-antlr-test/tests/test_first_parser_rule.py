from pathlib import Path

from nautilus_antlr_test import GrammarUnit, first_parser_rule


def _unit(tmp_path: Path, source: str) -> GrammarUnit:
    path = tmp_path / "G.g4"
    path.write_text(source)
    return GrammarUnit(name="G", files=[path])


def test_python_code_in_a_members_block_is_not_a_parser_rule(tmp_path):
    # Python2.g4: an `else:` inside @members was picked up as the start rule "Else"
    unit = _unit(
        tmp_path,
        "grammar G;\n@members {\n    if x:\n        pass\n    else:\n        pass\n}\nstart : 'a' ;\n",
    )

    assert first_parser_rule(unit) == "start"


def test_labels_inside_inline_actions_are_not_parser_rules(tmp_path):
    unit = _unit(
        tmp_path,
        "grammar G;\nstart : A {\n    key: value\n} B ;\nother : A ;\n",
    )

    assert first_parser_rule(unit) == "start"


def test_comment_and_lexer_rules_are_skipped(tmp_path):
    unit = _unit(
        tmp_path,
        "grammar G;\n// fake : rule\nA : 'a' ;\n/* block : comment */\nreal : A ;\n",
    )

    assert first_parser_rule(unit) == "real"
