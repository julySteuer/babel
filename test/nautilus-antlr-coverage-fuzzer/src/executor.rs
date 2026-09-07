use std::path::Path;

use libafl::Error;
use libafl::executors::{Executor, ExitKind, HasObservers};
use libafl::generators::nautilus::NautilusContext;
use libafl::inputs::nautilus::NautilusInput;
use libafl_bolts::tuples::RefIndexable;

use crate::antlr;
use crate::observer::AntlrTraceObserver;

/// "Runs the target" by unparsing the generated tree and feeding it to `antlr4-parse`,
/// storing the visited rule set into its observer for the feedback to pick up.
pub struct AntlrParseExecutor<'a> {
    grammar_path: &'a Path,
    start_rule: &'a str,
    context: &'a NautilusContext,
    observers: (AntlrTraceObserver, ()),
    bytes: Vec<u8>,
}

impl<'a> AntlrParseExecutor<'a> {
    pub fn new(grammar_path: &'a Path, start_rule: &'a str, context: &'a NautilusContext) -> Self {
        Self {
            grammar_path,
            start_rule,
            context,
            observers: (AntlrTraceObserver::new(), ()),
            bytes: Vec::new(),
        }
    }
}

impl<EM, S, Z> Executor<EM, NautilusInput, S, Z> for AntlrParseExecutor<'_> {
    fn run_target(
        &mut self,
        _fuzzer: &mut Z,
        _state: &mut S,
        _mgr: &mut EM,
        input: &NautilusInput,
    ) -> Result<ExitKind, Error> {
        input.unparse(self.context, &mut self.bytes);
        let generated_input = String::from_utf8_lossy(&self.bytes);
        self.observers.0.visited =
            antlr::trace_visited_rules(self.grammar_path, self.start_rule, &generated_input);
        Ok(ExitKind::Ok)
    }
}

impl HasObservers for AntlrParseExecutor<'_> {
    type Observers = (AntlrTraceObserver, ());

    fn observers(&self) -> RefIndexable<&Self::Observers, Self::Observers> {
        RefIndexable::from(&self.observers)
    }

    fn observers_mut(&mut self) -> RefIndexable<&mut Self::Observers, Self::Observers> {
        RefIndexable::from(&mut self.observers)
    }
}
