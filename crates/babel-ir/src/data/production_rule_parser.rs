use pest_derive::Parser;

#[derive(Parser)]
#[grammar = "src/data/production_rule_peg.pest"]
pub struct ProductionRuleParser;