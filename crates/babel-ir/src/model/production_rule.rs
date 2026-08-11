#[derive(Clone, Debug, PartialEq)]
pub enum Symbols {
    Terminal(String), // This could be char 
    NonTerminal(String)
}

#[derive(Clone, Debug, PartialEq)]
pub struct Block(pub Vec<Symbols>); // Mix of Terminals and nonterminals A -> <Block> | <Block>

#[derive(Debug, PartialEq, Clone)]
pub struct ProductionRule(pub Vec<Block>);