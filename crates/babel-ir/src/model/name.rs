#[derive(Eq, Hash, PartialEq)]
pub struct Name(String);

impl Name {
    pub fn new(name: &str) -> Result<Self, &'static str> {
        Name::validate(&name).map(|_| Name(name.to_string()))
    }

    fn validate(name: &str) -> Result<(), &'static str>{
        let has_whitespaces = name.contains(" ");
        if has_whitespaces {
            return Err("Name has Whitespaces which is not Allowed");
        }
        Ok(())
    }

    pub fn get(self) -> String {
        self.0
    }
}