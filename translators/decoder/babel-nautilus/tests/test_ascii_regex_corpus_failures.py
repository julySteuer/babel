"""Regression tests for character classes that made nautilus (regex-syntax) reject grammars-v4 grammars.

Every case is a class that babel emitted verbatim and that the Rust `regex-syntax` crate, or LibAFL's regex generator,
cannot handle. The tests compare the *set of ASCII characters* a class matches, so they do not depend on how the class
is spelled (`\\x2A`, `\\*`, ...).
"""

import re

import pytest

from babel_nautilus.ascii_regex import EmptyAsciiClass, restrict_to_ascii

# Characters that are special inside a Rust regex class and must never appear unescaped
_RUST_CLASS_SPECIALS = "[]^\\"
_RUST_CLASS_OPERATORS = ("&&", "--", "~~")


_ANTLR_ESCAPES = {"n": 0x0A, "r": 0x0D, "t": 0x09, "b": 0x08, "f": 0x0C}


def _members(regex: str) -> set[int]:
    """The code points matched by a class made of `\\xHH`, `\\xHH-\\xHH`, escaped punctuation and plain characters."""
    assert regex.startswith("[") and regex.endswith("]"), regex
    body = regex[1:-1]
    members: set[int] = set()
    i = 0

    def read() -> int:
        nonlocal i
        if body[i] != "\\":
            i += 1
            return ord(body[i - 1])
        if body[i + 1] == "x":
            i += 4
            return int(body[i - 2 : i], 16)
        i += 2
        return _ANTLR_ESCAPES.get(body[i - 1], ord(body[i - 1]))

    while i < len(body):
        low = read()
        if i < len(body) and body[i] == "-":
            i += 1
            members |= set(range(low, read() + 1))
        else:
            members.add(low)
    return members


def _bare_specials(regex: str) -> list[str]:
    """Characters inside the class that regex-syntax would interpret instead of matching literally."""
    body = regex[1:-1]
    unescaped = re.sub(r"\\x[0-9A-Fa-f]{2}|\\.", "E", body)  # every escape sequence is one literal member
    found = [c for c in unescaped if c in "[]^"]
    found += [op for op in _RUST_CLASS_OPERATORS if op in unescaped]
    return found


def _ascii(chars: str) -> set[int]:
    return {ord(c) for c in chars}


def test_nested_class_bracket_is_a_literal_member():
    # prolog.g4: `[!(),;[{}|%]` -- ANTLR reads `[` literally, regex-syntax reads it as a nested class (ClassUnclosed)
    result = restrict_to_ascii("[!(),;[{}|%]")

    assert _members(result) == _ascii("!(),;[{}|%")
    assert _bare_specials(result) == []


@pytest.mark.parametrize("members", ["a&&b", "a~~b", "x\\-\\-y"])
def test_rust_class_set_operators_are_not_emitted_unescaped(members):
    # `&&`, `~~` and `--` are intersection / symmetric difference / difference inside a Rust class
    result = restrict_to_ascii(f"[{members}]")

    assert _bare_specials(result) == []
    assert _members(result) == _ascii(members.replace("\\", ""))


def test_backspace_escape_is_not_a_word_boundary():
    # Java20.g4: `[.\r\b]` -- in ANTLR `\b` is backspace; in Rust `\b` is a word boundary and invalid in a class
    result = restrict_to_ascii("[.\\r\\b]")

    assert _members(result) == {ord("."), 0x0D, 0x08}
    assert "\\b" not in result


@pytest.mark.parametrize(
    ("escape", "code"), [("\\f", 0x0C), ("\\n", 0x0A), ("\\t", 0x09)]
)
def test_antlr_control_escapes_keep_their_antlr_meaning(escape, code):
    assert _members(restrict_to_ascii(f"[a{escape}]")) == {ord("a"), code}


def test_general_category_property_is_narrowed_to_its_ascii_members():
    # ixml.g4: `[_\p{L}]` -- non-ASCII classes make LibAFL's regex generator panic, so only ASCII may remain
    result = restrict_to_ascii("[_\\p{L}]")

    letters = _ascii("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    assert _members(result) == letters | {ord("_")}
    assert "\\p" not in result


@pytest.mark.parametrize(
    ("prop", "expected"),
    [
        ("Nd", _ascii("0123456789")),
        ("Lu", _ascii("ABCDEFGHIJKLMNOPQRSTUVWXYZ")),
        ("Ll", _ascii("abcdefghijklmnopqrstuvwxyz")),
        ("Zs", {0x20}),
    ],
)
def test_other_general_categories(prop, expected):
    assert _members(restrict_to_ascii(f"[\\p{{{prop}}}]")) == expected


def test_white_space_property_is_the_unicode_definition():
    # PowerQuery.g4: `[\p{White_Space}]`. Unicode White_Space is TAB..CR and space; notably NOT 0x1C-0x1F, which
    # Python's str.isspace() would include.
    result = restrict_to_ascii("[\\p{White_Space}]")

    assert _members(result) == {0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x20}


def test_negated_property_is_complemented_within_ascii():
    result = restrict_to_ascii("[^\\p{L}]")

    assert _members(result) == set(range(128)) - _ascii(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    )


def test_unknown_property_value_contributes_nothing():
    # Graphemes.g4: `[\p{EmojiPresentation=TextDefault}]` -- ICU `Property=Value` syntax that regex-syntax rejects
    result = restrict_to_ascii("[\\p{EmojiPresentation=TextDefault}a]")

    assert _members(result) == _ascii("a")
    assert "=" not in result


def test_class_that_only_holds_an_unknown_property_has_no_ascii_members():
    with pytest.raises(EmptyAsciiClass):
        restrict_to_ascii("[\\p{EmojiPresentation=TextDefault}]")
