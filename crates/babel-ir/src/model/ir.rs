#[derive(Debug, PartialEq)]
pub struct BabelProduction {
    pub name: String,
    pub rhs: Vec<BabelBlock>
}

#[derive(Debug, PartialEq)]
pub enum BabelSymbol {
    Terminal(String),
    NonTerminal(String)
}
#[derive(Debug, PartialEq)]
pub struct BabelBlock(pub Vec<BabelSymbol>);
// Very similar to Productin Rule. might use unified interfaces when exact structure is clear otherwiese spagetthi
#[derive(Debug, PartialEq)]
pub struct BabelIr(pub Vec<BabelProduction>); // Need posibility to add metadata (e.g. Naututilus regex ? could also be made that this is encdoed just as normal rule that happens to be regular. would be easier to merge)