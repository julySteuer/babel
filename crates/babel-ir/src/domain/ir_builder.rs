use std::collections::HashMap;

use crate::model::{
    BabelBlock, BabelIr, BabelProduction, BabelSymbol, Block, Name, ProductionRule,
    Symbols,
};

pub struct BabelIrBuilder {
    nonterms: HashMap<String, ProductionRule>,
    order: Vec<String>
}

impl BabelIrBuilder {
    pub fn new() -> Self {
        BabelIrBuilder {
            nonterms: HashMap::new(),// Need some kind of stable hash map here
            order: Vec::new()
        }
    }

    pub fn add_nonterminal(&mut self, name: Name, production_rule: ProductionRule) {
        let name = name.get();
        let nonterm = self.nonterms.remove(&name); // If nonterm already exists add block
        match nonterm {
            Some(old_rule) => {
                self.nonterms.insert(name, ProductionRule([old_rule.0, production_rule.0].concat()));
            },
            None => { 
                // Clone is neccesary
                self.nonterms.insert(name.clone(), production_rule);
                self.order.push(name);
             }
        };
    }

    fn map_production(name: String, production_rule: ProductionRule) -> BabelProduction {
        BabelProduction {
            name: name,
            rhs: production_rule.0.into_iter().map(Self::map_block).collect(),
        }
    }

    fn map_block(block: Block) -> BabelBlock {
        BabelBlock(block.0.into_iter().map(Self::map_symbols).collect())
    }

    fn map_symbols(symbol: Symbols) -> BabelSymbol {
        match symbol {
            Symbols::Terminal(name) => BabelSymbol::Terminal(name),
            Symbols::NonTerminal(name) => BabelSymbol::NonTerminal(name),
        }
    }

    pub fn build(mut self) -> BabelIr {
        let productions = self
            .order
            .into_iter()
            .map(|key| Self::map_production(key.clone(), self.nonterms.remove(&key).unwrap()))
            .collect();
        BabelIr(productions)
    }
}

#[cfg(test)]
mod ir_builder_integration_test {
    use crate::{
        data::production_rule_builder::parse_production_rule, domain::ir_builder::BabelIrBuilder, model::{BabelSymbol, Name},
    };

    #[test]
    fn check_if_build_correct() -> Result<(), String> {
        let mut builder = BabelIrBuilder::new();
        builder.add_nonterminal(Name::new("hello")?, parse_production_rule("a|b")?);
        builder.add_nonterminal(Name::new("world")?, parse_production_rule("c|d")?);

        let ir = builder.build();

        assert_eq!(ir.0.len(), 2);
        println!("{:?}", ir);
        Ok(())
    }
}
