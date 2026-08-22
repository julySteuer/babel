from babel_antlr._generated.ANTLRv4Parser import ANTLRv4Parser
from babel_antlr.util import exec_first_valid
from babel_ir.model import BabelProduction, BabelBlock, BabelAtom

def _encode_labeled_element(labeled_element: ANTLRv4Parser.LabeledElementContext, ebnf_suffix: ANTLRv4Parser.EbnfSuffixContext | None) -> BabelAtom:
    pass

def _encode_enbf(ebnf: ANTLRv4Parser.EbnfContext) -> BabelAtom:
    pass

def _encode_atom(atom: ANTLRv4Parser.AtomContext, ebnf_suffix: ANTLRv4Parser.EbnfSuffixContext | None) -> BabelAtom:
    pass

def _encode_element(element: ANTLRv4Parser.ElementContext) -> BabelAtom:
    labeled_element = element.labeledElement()
    atom = element.atom()
    ebnf = element.ebnf()

    ebnf_suffix_opt = element.ebnfSuffix()
    # Ignore actionBlock bcs currently not needed

    return exec_first_valid(
        (atom, lambda at: _encode_atom(at, ebnf_suffix_opt)),
        (labeled_element, lambda le: _encode_labeled_element(le, ebnf_suffix_opt)),
        (ebnf, _encode_enbf)
    )

def _encode_block(alt: ANTLRv4Parser.LabeledAltContext) -> BabelBlock:
    return BabelBlock(list(map(lambda elem: _encode_element(elem),alt.alternative().element())))

def _encode_blocks(alt_list: ANTLRv4Parser.RuleAltListContext) -> list[BabelBlock]:
    return list(map(lambda alt: _encode_block(alt), alt_list.labeledAlt()))  # Gets all alts even first one

def encode_parser_rule(parser_rule: ANTLRv4Parser.ParserRuleSpecContext) -> tuple[str, BabelProduction]:
    name = parser_rule.RULE_REF()
    return name, BabelProduction(_encode_blocks(parser_rule.ruleBlock().ruleAltList()))