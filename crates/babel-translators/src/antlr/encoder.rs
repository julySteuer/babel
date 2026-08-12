use babel_adapter::BabelEncoder;
use dbt_antlr4::InputStream;

use crate::antlr::generated::ANTLRv4Lexer;


pub struct AntlrEncoder{

}

impl BabelEncoder for AntlrEncoder {
    fn name() -> &'static str {
        "antlr"
    }

    fn encode(to_encode: &str) -> babel_ir::model::BabelIr {
        let arena = Arena::new(); // Memory allocator new to this implementation for antlr
        let input = InputStream::new(&to_encode);
        let lexer = ANTLRv4Lexer::new(arena, input);
        todo!()
    }
}