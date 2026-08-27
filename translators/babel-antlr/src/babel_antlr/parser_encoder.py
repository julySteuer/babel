from babel_antlr._generated.ANTLRv4Parser import ANTLRv4Parser
from babel_antlr.shared_encoder import (
    ENCODE_WILDCARD_IN_EXEC_FIRST_VALID,
    encode_ebnf_suffix_with_inner,
    encode_not_set,
    encode_terminal_def,
)
from babel_antlr.util import exec_first_valid
from babel_ir.model import (
    BabelAtom,
    BabelBlock,
    BabelBlockList,
    BabelNonterminal,
    BabelProduction,
)

# TODO: Untangle All rules that have more than one argument. Leads to spaghetti code


def _encode_labeled_element(
    labeled_element: ANTLRv4Parser.LabeledElementContext,
    ebnf_suffix: ANTLRv4Parser.EbnfSuffixContext | None,
) -> BabelAtom:
    atom = labeled_element.atom()
    block = labeled_element.block()

    return exec_first_valid(
        (atom, lambda at: _encode_atom(at, ebnf_suffix)),
        (
            block,
            lambda bl: encode_ebnf_suffix_with_inner(
                ebnf_suffix, BabelBlockList(_encode_alt_list(bl.altList()))
            ),
        ),
    )


def _encode_ebnf(ebnf: ANTLRv4Parser.EbnfContext) -> BabelAtom:
    block = ebnf.block()

    inner = BabelBlockList(
        list(map(_encode_alternative, block.altList().alternative()))
    )  # Parse this to a BabelBlockSet so inline Options
    if ebnf.blockSuffix() is not None:
        suffix = ebnf.blockSuffix().ebnfSuffix()
        return encode_ebnf_suffix_with_inner(suffix, inner)
    return inner


def _encode_ruleref(ruleref: ANTLRv4Parser.RulerefContext) -> BabelNonterminal:
    content = (
        ruleref.RULE_REF()
    )  # I suppose non terminal here but who knows. Testing this is absolutly horrible
    # Ignore Action block and elementOptions for now
    return BabelNonterminal(content)


def _encode_atom(
    atom: ANTLRv4Parser.AtomContext, ebnf_suffix: ANTLRv4Parser.EbnfSuffixContext | None
) -> BabelAtom:
    terminal_def = atom.terminalDef()
    ruleref = atom.ruleref()
    not_set = atom.notSet()
    wildcard = atom.wildcard()

    inner = exec_first_valid(
        (terminal_def, encode_terminal_def),
        (ruleref, _encode_ruleref),
        (not_set, encode_not_set),
        (wildcard, ENCODE_WILDCARD_IN_EXEC_FIRST_VALID),
    )

    return encode_ebnf_suffix_with_inner(ebnf_suffix, inner)


def _encode_element(
    element: ANTLRv4Parser.ElementContext,
) -> BabelAtom:  # Have to rethink if this is a good idea to return a Atom at this stage
    labeled_element = element.labeledElement()
    atom = element.atom()
    ebnf = element.ebnf()

    ebnf_suffix_opt = element.ebnfSuffix()
    # Ignore actionBlock bcs currently not needed

    return exec_first_valid(
        (atom, lambda at: _encode_atom(at, ebnf_suffix_opt)),
        (labeled_element, lambda le: _encode_labeled_element(le, ebnf_suffix_opt)),
        (ebnf, _encode_ebnf),
    )


def _encode_alternative(alternative: ANTLRv4Parser.AlternativeContext) -> BabelBlock:
    return BabelBlock([_encode_element(elem) for elem in alternative.element()])


def _encode_labeled_alt(alt: ANTLRv4Parser.LabeledAltContext) -> BabelBlock:
    return _encode_alternative(alt.alternative())


def _encode_alt_list(alt_list: ANTLRv4Parser.RuleAltListContext) -> list[BabelBlock]:
    return [
        _encode_labeled_alt(alt) for alt in alt_list.labeledAlt()
    ]  # Gets all alts even first one


def encode_parser_rule(
    parser_rule: ANTLRv4Parser.ParserRuleSpecContext,
) -> tuple[str, BabelProduction]:
    name = parser_rule.RULE_REF()  # Lets hope this casts to a string
    return name, BabelProduction(
        BabelBlockList(_encode_alt_list(parser_rule.ruleBlock().ruleAltList()))
    )


__all__ = ["encode_parser_rule"]
