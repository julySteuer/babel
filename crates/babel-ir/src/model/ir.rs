pub struct BabelProduction {
    pub name: String,
    pub rhs: Vec<BabelBlock>
}

pub enum BabelSymbol {
    Terminal(String),
    Nonterminal(String)
}

pub struct BabelBlock(pub Vec<BabelSymbol>);
// Very similar to Productin Rule. might use unified interfaces when exact structure is clear otherwiese spagetthi
pub struct BabelIr(pub Vec<BabelProduction>);