# Intermediate Representation 
This intermedaite is based on Chomsky Type-2 Grammar (Context Free Grammar). The IR also holds metadata if certain grammars hold grammars that are Type-1 or Type-0 grammar. Most of the Fuzzing grammars (antlr/gramatron) are Type-2 grammar but e.g. Nautilus fuzzing grammar is Type-0 grammar when using scripts.

## How does it work
The Grammar is based on the Greibach-Normal-Form and Deterministic CFGs. This is due to being significantly easier to compare and later merge as well as being good practice to make things as Strict as possible. 

## Creation Interface
This Crate also exposes interfaces to create this Intermediate Representation without the end user having to explicitly put things into the normal form. 

```rust
// TODO: Interface for creation
struct BabelIRBuilder {
    // ...
}

impl BabelIrBuilder {
    // Explicit types for name and preoductio rule to check if they are valid (No spaces in names and no disallowed characters in Production Rule for example)
    pub fn add_nonterminal(&mut self, name: Name, production_rule: ProductionRule) {
        // ...
    }

    // This puts it in the final Greibach-Form
    pub fn build(self) -> BabelIR {
        // ...
    }
}
```

## Babel IR Grammar
### Example
```
S -> a*B**C**D*
B -> c
C -> b | *A*
A -> a*B*
D -> d
```
Where * denotes the scope of the nonterminal (so that `*B**A*` != `*BA*`)