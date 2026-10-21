"""
LibAFL's nautilus regex generator (`regex_mutator::append_unicode_range`) reads the UTF-8 bytes of a class range as a
little-endian integer instead of a code point. That is only correct for ASCII; any class that reaches beyond it
(non-ASCII ranges, negated classes, `.`) makes it panic on `char::from_u32(..).unwrap()`.
So every character class is narrowed to its ASCII part before it is handed to `ctx.regex`.
"""

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
        if body[i + 2:i + 3] == "{":
            end = body.index("}", i)
            return int(body[i + 3:end], 16), end + 1
        return int(body[i + 2:i + 6], 16), i + 6
    if escaped == "x":
        return int(body[i + 2:i + 4], 16), i + 4
    if escaped in "pPdDwWsS":
        raise _Unsupported
    return _SIMPLE_ESCAPES.get(escaped, ord(escaped)), i + 2


def _parse_class(regex: str) -> tuple[bool, list[tuple[int, int]]]:
    body = regex[1:-1]
    negated = body.startswith("^")
    i = 1 if negated else 0
    ranges = []
    while i < len(body):
        low, i = _read_char(body, i)
        high = low
        if body[i:i + 1] == "-" and i + 1 < len(body):
            high, i = _read_char(body, i + 1)
        ranges.append((low, high))
    return negated, ranges


def _to_class(codes: list[int]) -> str:
    spans: list[list[int]] = []
    for code in codes:
        if spans and spans[-1][1] == code - 1:
            spans[-1][1] = code
        else:
            spans.append([code, code])
    return "[" + "".join(
        f"\\x{low:02X}" if low == high else f"\\x{low:02X}-\\x{high:02X}" for low, high in spans
    ) + "]"


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
        negated, ranges = _parse_class(regex)
    except (_Unsupported, ValueError, IndexError):
        return regex

    if not negated and all(high < 128 for _, high in ranges):
        return regex

    members = {code for low, high in ranges for code in range(low, min(high, 127) + 1)}
    codes = [code for code in _ASCII if (code in members) != negated]
    if not codes:
        raise EmptyAsciiClass(regex)
    return _to_class(codes)
