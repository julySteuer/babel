use std::collections::HashMap;

use crate::model::{
    BabelBlock, BabelIr, BabelProduction, BabelSymbol, Block, Name, ProductionRule,
    Symbols,
};

pub struct BabelIrBuilder {
    nonterms: HashMap<String, ProductionRule>,
}

impl BabelIrBuilder {
    pub fn new() -> Self {
        BabelIrBuilder {
            nonterms: HashMap::new(),
        }
    }

    pub fn add_nonterminal(&mut self, name: Name, production_rule: ProductionRule) {
        self.nonterms.insert(name.get(), production_rule);
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
            Symbols::NonTerminal(name) => BabelSymbol::Nonterminal(name),
        }
    }

    pub fn build(self) -> BabelIr {
        let productions = self
            .nonterms
            .into_iter()
            .map(|(key, value)| Self::map_production(key, value))
            .collect();
        BabelIr(productions)
    }
}

#[cfg(test)]
mod ir_builder_integration_test {
    use crate::{
        data::production_rule_builder::parse_production_rule,
        domain::ir_builder::BabelIrBuilder,
        model::{Name},
    };

    #[test]
    fn check_if_builder_correct() -> Result<(), String> {
        let mut builder = BabelIrBuilder::new();
        builder.add_nonterminal(Name::new("hello")?, parse_production_rule("a|b")?);
        builder.add_nonterminal(Name::new("world")?, parse_production_rule("c|d")?);

        assert_eq!(builder.nonterms.len(), 2);
        assert_eq!(
            *builder.nonterms.get("hello").unwrap(),
            parse_production_rule("a|b")?
        );
        Ok(())
    }
}
