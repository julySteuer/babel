"""
LibAFL's nautilus regex generator (`regex_mutator::append_unicode_range`) reads the UTF-8 bytes of a class range as a
little-endian integer instead of a code point. That is only correct for ASCII; any class that reaches beyond it
(non-ASCII ranges, negated classes, `.`) makes it panic on `char::from_u32(..).unwrap()`.
So every character class is narrowed to its ASCII part before it is handed to `ctx.regex`.
"""

import re
import unicodedata

_ASCII = range(128)
_SIMPLE_ESCAPES = {"n": 0x0A, "r": 0x0D, "t": 0x09, "b": 0x08, "f": 0x0C}


class EmptyAsciiClass(Exception):
    """The class does not match a single ASCII character."""


class _Unsupported(Exception):
    pass


def _read_char(body: str, i: int) -> tuple[int, int]:
    if body[i] != "\\":
        return ord(body[i]), i + 1
    if i + 1 >= len(body):
        raise _Unsupported
    escaped = body[i + 1]
    if escaped == "u":
        if body[i + 2 : i + 3] == "{":
            end = body.index("}", i)
            return int(body[i + 3 : end], 16), end + 1
        return int(body[i + 2 : i + 6], 16), i + 6
    if escaped == "x":
        return int(body[i + 2 : i + 4], 16), i + 4
    if escaped in "pPdDwWsS":
        raise _Unsupported
    return _SIMPLE_ESCAPES.get(escaped, ord(escaped)), i + 2


_WHITE_SPACE = {0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x20}  # Unicode White_Space within ASCII


def _property_members(name: str) -> set[int]:
    """The ASCII code points that have the unicode property `name`. Unknown properties match nothing."""
    if name in ("White_Space", "space", "Space", "WSpace"):
        return set(_WHITE_SPACE)
    if name in ("ASCII", "Any"):
        return set(_ASCII)
    if name.isalpha() and len(name) <= 2:  # general category: `L`, `Lu`, `Nd`, ...
        return {c for c in _ASCII if unicodedata.category(chr(c)).startswith(name)}
    return set()  # `Prop=Value`, scripts, blocks, ... have no (supported) ASCII members


def _read_property(body: str, i: int) -> tuple[set[int], int]:
    """Reads `\\p{..}`, `\\P{..}` or `\\pL` starting at the backslash at `body[i]`."""
    negated = body[i + 1] == "P"
    if body[i + 2 : i + 3] == "{":
        end = body.index("}", i)
        name, i = body[i + 3 : end], end + 1
    else:
        name, i = body[i + 2], i + 3
    members = _property_members(name.lstrip("^"))
    if negated != name.startswith("^"):
        members = set(_ASCII) - members
    return members, i


def _parse_class(regex: str) -> tuple[bool, list[tuple[int, int]], set[int]]:
    body = regex[1:-1]
    negated = body.startswith("^")
    i = 1 if negated else 0
    ranges: list[tuple[int, int]] = []
    extra: set[int] = set()
    while i < len(body):
        if body[i] == "\\" and body[i + 1 : i + 2] in ("p", "P"):
            members, i = _read_property(body, i)
            extra |= members
            continue
        low, i = _read_char(body, i)
        high = low
        if body[i : i + 1] == "-" and i + 1 < len(body):
            high, i = _read_char(body, i + 1)
        ranges.append((low, high))
    return negated, ranges, extra


def _to_class(codes: list[int]) -> str:
    spans: list[list[int]] = []
    for code in codes:
        if spans and spans[-1][1] == code - 1:
            spans[-1][1] = code
        else:
            spans.append([code, code])
    return (
        "["
        + "".join(
            f"\\x{low:02X}" if low == high else f"\\x{low:02X}-\\x{high:02X}"
            for low, high in spans
        )
        + "]"
    )


def _is_safe_ascii_class(
    regex: str, negated: bool, ranges: list[tuple[int, int]], extra: set[int]
) -> bool:
    """
    Whether the class can be passed on unchanged: plain ASCII and free of everything that antlr and rust's
    regex-syntax read differently (`[` nests a class, `&&` / `~~` / `--` are set operators, `\\b` is backspace in
    antlr but a word boundary in rust).
    """
    body = regex[1:-1]
    if negated or extra or any(high >= 128 for _, high in ranges):
        return False
    if "\\p" in body or "\\P" in body or "\\b" in body:
        return False
    plain = re.sub(r"\\.", "", body)  # what is left once escapes are removed
    return "[" not in plain and not any(op in plain for op in ("&&", "~~", "--"))


def restrict_to_ascii(regex: str) -> str:
    """
    Narrows a single character class (or `.`) to ASCII. Classes that are already plain ASCII are returned untouched,
    and anything else that is not a class is passed through as is.
    Raises `EmptyAsciiClass` when nothing ASCII is left.
    """
    if regex == ".":
        return _to_class([code for code in _ASCII if code != 0x0A])
    if not (regex.startswith("[") and regex.endswith("]") and len(regex) > 2):
        return regex
    try:
        negated, ranges, extra = _parse_class(regex)
    except (_Unsupported, ValueError, IndexError):
        return regex

    if _is_safe_ascii_class(regex, negated, ranges, extra):
        return regex

    members = {code for low, high in ranges for code in range(low, min(high, 127) + 1)}
    members |= extra
    codes = [code for code in _ASCII if (code in members) != negated]
    if not codes:
        raise EmptyAsciiClass(regex)
    return _to_class(codes)
