"""Regression tests for grammars-v4 grammars whose generated nautilus grammar could not be loaded."""

import pytest

from babel_ir.model import (
    BabelBlock,
    BabelBlockList,
    BabelCharRange,
    BabelIr,
    BabelNonterminal,
    BabelOptional,
    BabelProduction,
    BabelSymbol,
)
from babel_nautilus.decoder import decode
from babel_shared.name_generator import stateful_name_generator


@pytest.fixture(autouse=True)
def reset_name_generator():
    stateful_name_generator.counter.clear()


class _RecordingCtx:
    """Stands in for nautilus' python grammar loader; nautilus UTF-8 encodes every argument it receives."""

    def __init__(self):
        self.rules: list[tuple[str, str]] = []
        self.regexes: list[tuple[str, str]] = []

    def rule(self, name: str, body: str) -> None:
        self.rules.append((name, body.encode("utf-8").decode("utf-8")))

    def regex(self, name: str, body: str) -> None:
        self.regexes.append((name, body.encode("utf-8").decode("utf-8")))


def _load(source: str) -> _RecordingCtx:
    ctx = _RecordingCtx()
    exec(source, {"ctx": ctx})  # noqa: S102 - the generated grammar is plain `ctx.rule(...)` calls
    return ctx


def _ir(**rules: list[list]) -> BabelIr:
    return BabelIr(
        {
            name: BabelProduction(
                BabelBlockList([BabelBlock(list(alt)) for alt in alternatives])
            )
            for name, alternatives in rules.items()
        }
    )


def _unproductive(ctx: _RecordingCtx) -> set[str]:
    """Nonterminals nautilus cannot derive a finite string from (what makes it panic with `Broken Grammar`)."""
    import re

    bodies: dict[str, list[str]] = {}
    for name, body in ctx.rules:
        bodies.setdefault(name, []).append(body)
    for name, _ in ctx.regexes:
        bodies.setdefault(name, []).append("")  # a regex is a terminal

    productive: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, alternatives in bodies.items():
            if name in productive:
                continue
            if any(
                set(re.findall(r"\{(\w+)\}", alt)) <= productive for alt in alternatives
            ):
                productive.add(name)
                changed = True
    return set(bodies) - productive


# --- surrogates (Z.g4, classify.g4) -------------------------------------------------------------------------------


def test_surrogate_pair_is_emitted_as_the_single_code_point():
    # Z.g4 spells U+1D538 as the UTF-16 pair \ud835\udd38; python cannot encode lone surrogates to UTF-8
    ir = _ir(Foo=[[BabelSymbol("\ud835\udd38")]])

    source = decode(ir, "Foo")

    ctx = _load(source)
    assert ("Foo", "\U0001d538") in ctx.rules


def test_lone_surrogate_does_not_make_the_grammar_unloadable():
    # classify.g4 has a rule for the surrogate category `\ud800`, which has no UTF-8 form at all
    ir = _ir(Foo=[[BabelSymbol("\ud800")]])

    source = decode(ir, "Foo")

    _load(source)  # must neither raise nor contain anything that cannot be UTF-8 encoded
    source.encode("utf-8")


# --- unproductive rules (lisp.g4) ---------------------------------------------------------------------------------


def test_rule_without_a_base_case_is_pruned_instead_of_breaking_the_grammar():
    # lisp.g4:  ATOMIC_SYMBOL : LETTER ATOM_PART? ;   fragment ATOM_PART : (LETTER | NUMBER) ATOM_PART ;
    # ANTLR accepts this (ATOM_PART never matches, the `?` saves the rule). Nautilus panics on any unproductive rule.
    letter = BabelCharRange("a", "z")
    ir = _ir(
        Atomic=[[letter, BabelOptional(BabelNonterminal("AtomPart"))]],
        AtomPart=[[letter, BabelNonterminal("AtomPart")]],
    )

    ctx = _load(decode(ir, "Atomic"))

    assert _unproductive(ctx) == set()
    assert "Atomic" in {name for name, _ in ctx.rules + ctx.regexes}


def test_alternatives_that_are_productive_survive_pruning():
    ir = _ir(
        Expr=[[BabelSymbol("x")], [BabelNonterminal("Dead")]],
        Dead=[[BabelNonterminal("Dead"), BabelSymbol("y")]],
    )

    ctx = _load(decode(ir, "Expr"))

    assert _unproductive(ctx) == set()
    assert ("Expr", "x") in ctx.rules


def test_grammar_without_any_productive_start_symbol_is_still_an_error():
    # pruning must not hide that the start symbol itself can never derive anything
    ir = _ir(Expr=[[BabelNonterminal("Expr"), BabelSymbol("y")]])

    with pytest.raises(Exception):  # noqa: B017 - the exact exception type is the implementation's choice
        decode(ir, "Expr")
