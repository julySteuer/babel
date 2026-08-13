use babel_ir::model::BabelIr;
use dbt_antlr4::{Arena, InputStream};

use crate::antlr::generated::ANTLRv4Lexer;

pub enum MultiFileInput {
    CombinedFile(String),
    LexerFile(String),
    ParserFile(String)
}

pub enum Input {
    MultiFileInput(MultiFileInput),
    CombinedFileInput(String)
} 


pub struct AntlrEncoder{

}

impl AntlrEncoder {
    pub fn encode(to_encode: Input) -> BabelIr {
        match to_encode {
            Input::CombinedFileInput(input) => AntlrEncoder::parse_combined_file_input(input),
            _ => unreachable!()
        }
    }

    fn parse_combined_file_input(input: String) -> BabelIr {
        Arena::with(|arena| {
            let input = InputStream::new(&input);
            let lexer: ANTLRv4Lexer<'_, '_, InputStream<'_>> = ANTLRv4Lexer::new(arena, input);
            let token_source = CommonTokenStream::new(lexer);
            let mut parser = ANTLRv4Parser::new(token_source);
        });

        todo!()
    }
}