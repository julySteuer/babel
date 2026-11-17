import pytest

from babel_nautilus.ascii_regex import EmptyAsciiClass, restrict_to_ascii


@pytest.mark.parametrize(
    "regex",
    ["[a-z]", "[0-9]", "[a-zA-Z_]", "[\\n\\r]", "abc", "[a-z]+", "[]"],
)
def test_ascii_classes_and_non_classes_are_untouched(regex):
    assert restrict_to_ascii(regex) == regex


def test_non_ascii_ranges_are_clamped():
    assert restrict_to_ascii("[a-c\\u00c0-\\u00d6]") == "[\\x61-\\x63]"


def test_braced_unicode_escape_is_understood():
    assert restrict_to_ascii("[a\\u{1F600}]") == "[\\x61]"


def test_negated_class_is_complemented_within_ascii():
    result = restrict_to_ascii("[^\\x00-\\x7e]")
    assert result == "[\\x7F]"


def test_negated_class_excludes_the_given_characters():
    result = restrict_to_ascii("[^\\n\\r]")
    assert result == "[\\x00-\\x09\\x0B-\\x0C\\x0E-\\x7F]"


def test_negated_class_with_escaped_backslash_and_quote():
    result = restrict_to_ascii("[^'\\\\]")
    assert result == "[\\x00-\\x26\\x28-\\x5B\\x5D-\\x7F]"


def test_wildcard_is_every_ascii_character_but_newline():
    assert restrict_to_ascii(".") == "[\\x00-\\x09\\x0B-\\x7F]"


def test_class_without_ascii_characters_is_empty():
    with pytest.raises(EmptyAsciiClass):
        restrict_to_ascii("[\\u3040-\\u318f]")
