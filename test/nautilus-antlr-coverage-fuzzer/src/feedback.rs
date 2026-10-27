use std::borrow::Cow;
use std::collections::HashSet;

use libafl::Error;
use libafl::executors::ExitKind;
use libafl::HasMetadata;
use libafl::feedbacks::{Feedback, NautilusChunksMetadata, StateInitializer};
use libafl::generators::nautilus::NautilusContext;
use libafl::inputs::nautilus::NautilusInput;
use libafl_bolts::Named;

use crate::observer::AntlrTraceObserver;

/// Accumulates every ANTLR parser rule seen across the whole run.
pub struct RuleCoverageFeedback<'a> {
    context: &'a NautilusContext,
    name: Cow<'static, str>,
    pub visited: HashSet<String>,
    /// Rules first seen since the caller last drained this with `mem::take`.
    pub new_rules: Vec<String>,
}

impl<'a> RuleCoverageFeedback<'a> {
    pub fn new(context: &'a NautilusContext) -> Self {
        Self {
            context,
            name: Cow::Borrowed("rule_coverage"),
            visited: HashSet::new(),
            new_rules: Vec::new(),
        }
    }
}

impl Named for RuleCoverageFeedback<'_> {
    fn name(&self) -> &Cow<'static, str> {
        &self.name
    }
}

impl<S> StateInitializer<S> for RuleCoverageFeedback<'_> {}

impl<EM, S: HasMetadata> Feedback<EM, NautilusInput, (AntlrTraceObserver, ()), S> for RuleCoverageFeedback<'_> {
    fn is_interesting(
        &mut self,
        state: &mut S,
        _manager: &mut EM,
        input: &NautilusInput,
        observers: &(AntlrTraceObserver, ()),
        _exit_kind: &ExitKind,
    ) -> Result<bool, Error> {
        let mut found_new = false;
        for rule in &observers.0.visited {
            if self.visited.insert(rule.clone()) {
                self.new_rules.push(rule.clone());
                found_new = true;
            }
        }
        if found_new {
            // The splice mutator draws subtrees from this chunk store.
            state
                .metadata_map_mut()
                .get_mut::<NautilusChunksMetadata>()
                .expect("NautilusChunksMetadata not in the state")
                .cks
                .add_tree(input.tree.clone(), &self.context.ctx);
        }
        Ok(found_new)
    }
}
