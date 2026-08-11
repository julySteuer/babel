use babel_ir::model::BabelIr;

pub trait BabelEncoder {
    /// For identification of the Encoder Type (nautilus/antlr4)
    fn name() -> String;
    fn encode(to_encode: String) -> BabelIr;
}

pub trait BabelDecoder {
    /// For identification of the Decoder Type (nautilus/antlr4)
    fn name() -> String;
    fn decode(to_decode: BabelIr) -> String;
}
