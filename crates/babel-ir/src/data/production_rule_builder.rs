use pest::Parser;

use crate::{
    data::production_rule_parser::{ProductionRuleParser, Rule}, model::{Block, ProductionRule, Symbols},
};

fn append_immut<A: Clone>(list: Vec<A>, item: A) -> Vec<A> {
    [list, vec![item]].concat()
}

type SymbolStack = (Vec<Symbols>, Vec<Block>);

pub fn parse_production_rule(production_rule: &str) -> Result<ProductionRule, String> {
    let mut ppp = ProductionRuleParser::parse(Rule::RHS, &production_rule)
        .map_err(|_| "Parsing Error Occured")?;
    let top_level_rule = ppp.next().unwrap(); // RHS
    let blocks: SymbolStack =
        top_level_rule
            .into_inner()
            .fold((Vec::new(), Vec::new()), |acc, pair| {
                match pair.as_rule() {
                    Rule::NONTERM => {
                        let word = pair.into_inner().next().unwrap(); // Due to Nonterm -> *WORD* -> Word
                        return (
                            append_immut(acc.0, Symbols::NonTerminal(word.to_string())),
                            acc.1,
                        );
                    }
                    Rule::TERM => {
                        // TODO: Handle Escape Sequence
                        return (
                            append_immut(acc.0, Symbols::Terminal(pair.to_string())),
                            acc.1,
                        );
                    }
                    Rule::OR => {
                        return (Vec::new(), append_immut(acc.1, Block(acc.0)));
                    }
                    _ => unreachable!(),
                }
            });
    Ok(ProductionRule(append_immut(blocks.1, Block(blocks.0)))) // Add Remaining Items
}

/// Not the most exhaustive test suite but will serve as good example for later
#[cfg(test)]
mod production_unit_tests {
    use crate::{data::production_rule_builder::parse_production_rule, model::Symbols};


    #[test]
    fn parse_simple_term() {
        let test_str = "abc";
        let under_test = parse_production_rule(test_str);
        let value = under_test.unwrap(); // Should not fail
        assert_eq!(value.0.len(), 1); // One Block 
    }

    #[test]
    fn parse_simple_nonterm() {
        let test_str = "*ABC*";
        let under_test = parse_production_rule(test_str);
        let value = under_test.unwrap(); // Should not fail
        assert_eq!(value.0.len(), 1); // One Block 
    }

    #[test]
    fn parse_simple_with_or() {
        let test_str = "*ABC*|ab";
        let under_test = parse_production_rule(test_str);
        let value = under_test.unwrap(); // Should not fail
        assert_eq!(value.0.len(), 2); // Two blocks 
        assert_eq!(
            *value.0.get(0).unwrap().0.get(0).unwrap(),
            Symbols::NonTerminal("ABC".to_string())
        );
        assert_eq!(
            *value.0.get(1).unwrap().0.get(0).unwrap(),
            Symbols::Terminal("a".to_string())
        );
        assert_eq!(
            *value.0.get(1).unwrap().0.get(1).unwrap(),
            Symbols::Terminal("b".to_string())
        );
    }

    #[test]
    fn parse_complex_block_with_whitespace() {
        let test_str = "*AB*c*CD* |a b";
        let under_test = parse_production_rule(test_str);
        let value = under_test.unwrap();
        let first_block = value.0.get(0).unwrap();
        let second_block = value.0.get(1).unwrap();
        assert_eq!(value.0.len(), 2);
        assert_eq!(
            first_block.0.get(0).unwrap().clone(),
            Symbols::NonTerminal("AB".to_string())
        );
        assert_eq!(
            first_block.0.get(1).unwrap().clone(),
            Symbols::Terminal("c".to_string())
        );
        assert_eq!(
            second_block.0.get(0).unwrap().clone(),
            Symbols::Terminal("a".to_string())
        );
        assert_eq!(
            second_block.0.get(1).unwrap().clone(),
            Symbols::Terminal(" ".to_string())
        );
        assert_eq!(
            second_block.0.get(2).unwrap().clone(),
            Symbols::Terminal("b".to_string())
        );
    }
}
