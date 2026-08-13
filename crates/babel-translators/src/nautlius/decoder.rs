use babel_ir::model::BabelBlock;

fn map_babel_production_to_string(production: babel_ir::model::BabelProduction) -> String {
    map_blocks(&production.name, production.rhs) // Make this for multiple blocks
}

fn map_blocks(name: &str, blocks: Vec<BabelBlock>) -> String {
    blocks.iter().map(|block| {
        format!("ctx.rule(u\'{}\',u\'{}\')\n", name, map_babel_block_to_string(block))
    }).collect()
}

fn map_babel_block_to_string(block: &BabelBlock) -> String {
    block.0.iter().map(|symbol| {
        match symbol {
            babel_ir::model::BabelSymbol::Terminal(term) => term.to_string(),
            babel_ir::model::BabelSymbol::NonTerminal(nonterm) => format!("{{{}}}", nonterm.to_string()),
        }
    }).collect()
}

pub struct NautilusDecoder {

}

impl NautilusDecoder {
    pub fn decode(to_decode: babel_ir::model::BabelIr) -> String {
        let productions = to_decode.0;
        productions.into_iter().map(map_babel_production_to_string).collect()
    }
}

#[cfg(test)]
mod test_decoder {
use babel_ir::model::{BabelBlock, BabelIr, BabelProduction, BabelSymbol::Terminal};

use crate::nautlius::decoder::NautilusDecoder;

    #[test]
    fn test() {
        let ir = BabelIr(vec![BabelProduction { name: "START".to_string(), rhs: vec![BabelBlock(vec![Terminal("a".to_string())])] } ]);
        let decoded = NautilusDecoder::decode(ir);
        let expected = "ctx.rule(u\"START\", u\"a\")\n".to_string();
        assert_eq!(decoded, expected)
    }
}