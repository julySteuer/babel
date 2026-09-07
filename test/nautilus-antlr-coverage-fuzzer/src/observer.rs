use std::borrow::Cow;
use std::collections::HashSet;

use libafl::observers::Observer;
use libafl_bolts::Named;
use serde::{Deserialize, Serialize};

/// Holds the ANTLR parser rules visited by the most recent execution.
/// Populated by `AntlrParseExecutor::run_target`, read back by `RuleCoverageFeedback`.
#[derive(Debug, Serialize, Deserialize)]
pub struct AntlrTraceObserver {
    name: Cow<'static, str>,
    pub visited: HashSet<String>,
}

impl AntlrTraceObserver {
    pub fn new() -> Self {
        Self {
            name: Cow::Borrowed("antlr_trace"),
            visited: HashSet::new(),
        }
    }
}

impl Named for AntlrTraceObserver {
    fn name(&self) -> &Cow<'static, str> {
        &self.name
    }
}

impl<I, S> Observer<I, S> for AntlrTraceObserver {}
