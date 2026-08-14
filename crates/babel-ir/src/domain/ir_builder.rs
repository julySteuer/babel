use crate::model::BabelIr;

// Rewrite this builder to run on JSON. Its easier to parse and i dont have to fuck around with parsing smoke tests
pub fn from_json(data: &str) -> BabelIr {
    return serde_json::from_str(data).expect("Serde Deserialization failed")
}