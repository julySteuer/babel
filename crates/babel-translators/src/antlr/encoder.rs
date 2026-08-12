use babel_adapter::BabelEncoder;
use dbt_antlr4::InputStream;

pub struct AntlrEncoder{
    
}

impl BabelEncoder for AntlrEncoder {
    fn name() -> String {
        "antlr".to_string() // should be &'static str
    }

    fn encode(to_encode: String) -> babel_ir::model::BabelIr {
        let input = InputStream::new(&to_encode);
        todo!()
    }
}