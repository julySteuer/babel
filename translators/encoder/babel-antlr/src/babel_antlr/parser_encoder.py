from babel_antlr._generated.ANTLRv4Parser import ANTLRv4Parser
from babel_antlr.model.antlr_ir import (
    AntlrAtom,
    AntlrBlock,
    AntlrBlockList,
    AntlrParserProduction,
    AntlrParserWildcard,
    AntlrParserNonterminal,
    AntlrParserBlock,
)
from babel_antlr.shared_encoder import (
    encode_ebnf_suffix_with_inner,
    encode_not_set,
    encode_terminal_def,
)
from babel_antlr.util import exec_first_valid

# TODO: Untangle All rules that have more than one argument. Leads to spaghetti code


def _encode_alt_list(alt_list: ANTLRv4Parser.AltListContext) -> AntlrBlockList:
    return AntlrBlockList(list(map(_encode_alternative, alt_list.alternative())))


def _encode_labeled_element(
    labeled_element: ANTLRv4Parser.LabeledElementContext,
    ebnf_suffix: ANTLRv4Parser.EbnfSuffixContext | None,
) -> AntlrAtom:
    atom = labeled_element.atom()
    block = labeled_element.block()

    return exec_first_valid(
        (atom, lambda at: _encode_atom(at, ebnf_suffix)),
        (
            block,
            lambda bl: encode_ebnf_suffix_with_inner(
                ebnf_suffix, _encode_alt_list(bl.altList())
            ),
        ),
    )


def _encode_ebnf(ebnf: ANTLRv4Parser.EbnfContext) -> AntlrAtom:
    block = ebnf.block()

    inner = AntlrBlockList(
        list(map(_encode_alternative, block.altList().alternative()))
    )  # Parse this to a BabelBlockSet so inline Options
    if ebnf.blockSuffix() is not None:
        suffix = ebnf.blockSuffix().ebnfSuffix()
        return encode_ebnf_suffix_with_inner(suffix, inner)
    return inner


def _encode_ruleref(ruleref: ANTLRv4Parser.RulerefContext) -> AntlrParserNonterminal:
    content = (
        ruleref.RULE_REF().getText()
    )  # I suppose non terminal here but who knows. Testing this is absolutly horrible
    # Ignore Action block and elementOptions for now
    return AntlrParserNonterminal(content)


def _encode_atom(
    atom: ANTLRv4Parser.AtomContext, ebnf_suffix: ANTLRv4Parser.EbnfSuffixContext | None
) -> AntlrAtom:
    terminal_def = atom.terminalDef()
    ruleref = atom.ruleref()
    not_set = atom.notSet()
    wildcard = atom.wildcard()

    inner = exec_first_valid(
        (terminal_def, lambda elem: encode_terminal_def(elem, AntlrParserNonterminal)),
        (ruleref, _encode_ruleref),
        (
            not_set,
            lambda elem: encode_not_set(elem, AntlrParserNonterminal, AntlrParserBlock),
        ),
        (wildcard, lambda _: AntlrParserWildcard()),
    )

    return encode_ebnf_suffix_with_inner(ebnf_suffix, inner)


def _encode_element(
    element: ANTLRv4Parser.ElementContext,
) -> AntlrAtom:  # Have to rethink if this is a good idea to return a Atom at this stage
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


def _encode_alternative(alternative: ANTLRv4Parser.AlternativeContext) -> AntlrBlock:
    encoded = (_encode_element(elem) for elem in alternative.element())
    return AntlrParserBlock([atom for atom in encoded if atom is not None])


def _encode_labeled_alt(alt: ANTLRv4Parser.LabeledAltContext) -> AntlrBlock:
    return _encode_alternative(alt.alternative())


def _encode_rule_alt_list(
    alt_list: ANTLRv4Parser.RuleAltListContext,
) -> list[AntlrBlock]:
    return [
        _encode_labeled_alt(alt) for alt in alt_list.labeledAlt()
    ]  # Gets all alts even first one


def encode_parser_rule(
    parser_rule: ANTLRv4Parser.ParserRuleSpecContext,
) -> tuple[str, AntlrParserProduction]:
    name = parser_rule.RULE_REF().getText()
    return name, AntlrParserProduction(
        AntlrBlockList(_encode_rule_alt_list(parser_rule.ruleBlock().ruleAltList()))
    )


__all__ = ["encode_parser_rule"]
