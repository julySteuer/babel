use std::borrow::Cow;
use std::collections::HashSet;

use libafl::Error;
use libafl::executors::ExitKind;
use libafl::feedbacks::{Feedback, StateInitializer};
use libafl::inputs::nautilus::NautilusInput;
use libafl_bolts::Named;

use crate::observer::AntlrTraceObserver;

/// Accumulates every ANTLR parser rule seen across the whole run.
pub struct RuleCoverageFeedback {
    name: Cow<'static, str>,
    pub visited: HashSet<String>,
}

impl RuleCoverageFeedback {
    pub fn new() -> Self {
        Self {
            name: Cow::Borrowed("rule_coverage"),
            visited: HashSet::new(),
        }
    }
}

impl Named for RuleCoverageFeedback {
    fn name(&self) -> &Cow<'static, str> {
        &self.name
    }
}

impl<S> StateInitializer<S> for RuleCoverageFeedback {}

impl<EM, S> Feedback<EM, NautilusInput, (AntlrTraceObserver, ()), S> for RuleCoverageFeedback {
    fn is_interesting(
        &mut self,
        _state: &mut S,
        _manager: &mut EM,
        _input: &NautilusInput,
        observers: &(AntlrTraceObserver, ()),
        _exit_kind: &ExitKind,
    ) -> Result<bool, Error> {
        let mut found_new = false;
        for rule in &observers.0.visited {
            found_new |= self.visited.insert(rule.clone());
        }
        Ok(found_new)
    }
}
