use serde::{Deserialize, Serialize};

#[derive(Debug, PartialEq, Serialize, Deserialize)]
pub struct BabelProduction {
    pub name: String,
    pub rhs: Vec<BabelBlock>
}

#[derive(Debug, PartialEq, Serialize, Deserialize)]
pub enum BabelSymbol {
    Terminal(String),
    NonTerminal(String)
}
#[derive(Debug, PartialEq, Serialize, Deserialize)]
pub struct BabelBlock(Vec<BabelSymbol>);
// Very similar to Productin Rule. might use unified interfaces when exact structure is clear otherwiese spagetthi
#[derive(Debug, PartialEq, Serialize, Deserialize)]
pub struct BabelIr(Vec<BabelProduction>); // Need posibility to add metadata (e.g. Naututilus regex ? could also be made that this is encdoed just as normal rule that happens to be regular. would be easier to merge)

impl BabelIr {
    pub fn new(babel_productions: Vec<BabelProduction>) -> Self {
        Self(babel_productions)
    }
}

impl BabelProduction {
    pub fn new(name: String, rhs: Vec<BabelBlock>) -> Self {
        Self {
            name,
            rhs
        }
    }
}

impl BabelBlock {
    pub fn new(babel_symbols: Vec<BabelSymbol>) -> Self {
        Self(babel_symbols)
    }
}