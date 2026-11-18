from pathlib import Path

from nautilus_antlr_test import GrammarUnit, find_start_rule


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

    assert find_start_rule(unit) == "start"


def test_labels_inside_inline_actions_are_not_parser_rules(tmp_path):
    unit = _unit(
        tmp_path,
        "grammar G;\nstart : A {\n    key: value\n} B ;\nother : A ;\n",
    )

    assert find_start_rule(unit) == "start"


def test_comment_and_lexer_rules_are_skipped(tmp_path):
    unit = _unit(
        tmp_path,
        "grammar G;\n// fake : rule\nA : 'a' ;\n/* block : comment */\nreal : A ;\n",
    )

    assert find_start_rule(unit) == "real"


def test_rule_with_arguments_and_returns_is_a_parser_rule(tmp_path):
    unit = _unit(
        tmp_path,
        "grammar G;\nexpr[int p] returns [int v] locals [int x]\n    : A ;\nother : A ;\nA : 'a' ;\n",
    )

    assert find_start_rule(unit) == "expr"


def test_entry_rule_with_eof_beats_the_first_rule(tmp_path):
    # Ada2005Parser.g4: the first rule is `identifier`, the entry rule `compilation` is far below
    unit = _unit(
        tmp_path,
        "grammar G;\nidentifier : ID ;\nunit : identifier ;\ncompilation : unit* EOF ;\nID : 'a' ;\n",
    )

    assert find_start_rule(unit) == "compilation"


def test_first_eof_rule_is_taken_when_no_eof_rule_is_unreferenced(tmp_path):
    unit = _unit(
        tmp_path,
        "grammar G;\nprogram : stmt EOF ;\nstmt : 'a' sub ;\nsub : 'b' EOF ;\ntop : program ;\n",
    )

    # `top` is the only rule nothing refers to but it has no EOF; no EOF rule is unreferenced either, so the
    # first rule that uses EOF is taken
    assert find_start_rule(unit) == "program"


def test_a_rule_that_only_matches_nothing_is_not_the_entry(tmp_path):
    # algol60.g4: `empty_` comes first, the entry rule is `program : ... EOF`
    unit = _unit(
        tmp_path,
        "grammar G;\nempty_ : ;\nblock : empty_ 'x' ;\nprogram : block EOF ;\n",
    )

    assert find_start_rule(unit) == "program"


def test_without_eof_the_first_unreferenced_rule_is_the_entry(tmp_path):
    unit = _unit(
        tmp_path,
        "grammar G;\nleaf : 'a' ;\nroot : leaf leaf ;\nA : 'a' ;\n",
    )

    assert find_start_rule(unit) == "root"


def test_recursion_alone_does_not_make_a_rule_referenced(tmp_path):
    unit = _unit(tmp_path, "grammar G;\nexpr : expr '+' expr | 'a' ;\n")

    assert find_start_rule(unit) == "expr"


def test_alternative_labels_are_not_references(tmp_path):
    # `# add` labels an alternative of `expr`; if it counted as a use of the rule `add`, `other` would win
    unit = _unit(
        tmp_path,
        "grammar G;\nadd : 'a' EOF ;\nother : 'o' EOF ;\nexpr : 'x' # add\n  | 'y' # sub\n  ;\n",
    )

    assert find_start_rule(unit) == "add"


def test_comment_openers_in_literals_do_not_hide_rules(tmp_path):
    unit = _unit(
        tmp_path,
        "grammar G;\nc : '/*' | '//' ;\nstart : c EOF ;\n",
    )

    assert find_start_rule(unit) == "start"
