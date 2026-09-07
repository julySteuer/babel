use std::collections::HashSet;

pub trait Feedback {
    fn is_interesting(&mut self, observed: &HashSet<String>) -> bool;
    fn visited(&self) -> &HashSet<String>;
}

#[derive(Default)]
pub struct RuleCoverageFeedback {
    visited: HashSet<String>,
}

impl Feedback for RuleCoverageFeedback {
    fn is_interesting(&mut self, observed: &HashSet<String>) -> bool {
        let mut found_new = false;
        for rule in observed {
            found_new |= self.visited.insert(rule.clone());
        }
        found_new
    }

    fn visited(&self) -> &HashSet<String> {
        &self.visited
    }
}
