use antlr_rust::{parser::ParserNodeType, tree::ParseTreeVisitorCompat};
use babel_ir::model::{BabelIr, BabelProduction};

use crate::antlr::generated::antlrv4parservisitor::{ANTLRv4ParserVisitor, ANTLRv4ParserVisitorCompat};
use crate::antlr::generated::antlrv4parser::ANTLRv4ParserContextType;
use antlr_rust::tree::{Tree, VisitChildren};

pub struct AntlrVisitor {
    production_rules: Vec<BabelProduction>
}

impl AntlrVisitor {
    pub fn new() -> Self {
        Self { production_rules: Vec::new() }
    }
}

impl ParseTreeVisitorCompat<'_> for AntlrVisitor {
    type Node = ANTLRv4ParserContextType;

    type Return = Vec<BabelProduction>;

    fn temp_result(&mut self) -> &mut Self::Return {
        &mut self.production_rules
    }
}

impl ANTLRv4ParserVisitorCompat<'_> for AntlrVisitor {
    fn visit_parserRuleSpec(&mut self, ctx: &super::generated::antlrv4parser::ParserRuleSpecContext<'_>) -> Self::Return {
        println!("Rule Count: {}", ctx.get_child_count());
        Vec::new()
    }
    // Bueno 
}

#[cfg(test)]
mod visitor_test {
    use antlr_rust::tree::ParseTreeVisitorCompat;
use antlr_rust::{InputStream, common_token_stream::CommonTokenStream};

    use crate::antlr::antlr_visitor::AntlrVisitor;
use crate::antlr::generated::antlrv4parser::ANTLRv4Parser;
    use crate::antlr::generated::antlrv4lexer::ANTLRv4Lexer;

    #[test]
    fn simple_visitor_test() {
        let input = "grammar Simple;\nstart : 'a' ;\n";
        let stream = InputStream::new(input);
        let lexer = ANTLRv4Lexer::new(stream);
        let token_source = CommonTokenStream::new(lexer);
        let mut parser = ANTLRv4Parser::new(token_source);

        let root = parser.grammarSpec().unwrap();
        AntlrVisitor::new().visit(&*root);
    }
}