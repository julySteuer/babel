use antlr_rust::common_token_stream::CommonTokenStream;
use antlr_rust::InputStream;
use antlr_rust::tree::ParseTreeVisitorCompat;
use babel_ir::model::BabelIr;

use crate::antlr::generated::antlrv4lexer::ANTLRv4Lexer;
use crate::antlr::generated::antlrv4parser::ANTLRv4Parser;

pub enum MultiFileInput {
    CombinedFile(String),
    LexerFile(String),
    ParserFile(String)
}

pub enum Input {
    MultiFileInput(Vec<MultiFileInput>),
    CombinedFileInput(String)
} 

pub fn encode(to_encode: Input) -> BabelIr {
    match to_encode {
        Input::CombinedFileInput(input) => parse_combined_file_input(input),
        _ => unreachable!()
    }
}

fn parse_combined_file_input(input: String) -> BabelIr {
    let stream = InputStream::new(input.as_str());
    let lexer = ANTLRv4Lexer::new(stream);
    let token_source = CommonTokenStream::new(lexer);
    let mut parser = ANTLRv4Parser::new(token_source);

    
    todo!()
}