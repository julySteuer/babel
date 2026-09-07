use std::collections::HashSet;
use std::path::Path;

use crate::antlr;

pub trait Observer {
    fn observe(&self, generated_input: &str) -> HashSet<String>;
}

pub struct AntlrTraceObserver<'a> {
    pub grammar_path: &'a Path,
    pub start_rule: &'a str,
}

impl Observer for AntlrTraceObserver<'_> {
    fn observe(&self, generated_input: &str) -> HashSet<String> {
        antlr::trace_visited_rules(self.grammar_path, self.start_rule, generated_input)
    }
}
