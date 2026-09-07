mod antlr;
mod executor;
mod feedback;
mod observer;

use std::collections::HashSet;
use std::path::PathBuf;
use std::process::exit;

use libafl::corpus::InMemoryCorpus;
use libafl::feedbacks::ConstFeedback;
use libafl::fuzzer::{Evaluator, HasFeedback, StdFuzzer};
use libafl::generators::Generator;
use libafl::generators::nautilus::{NautilusContext, NautilusGenerator};
use libafl::inputs::nautilus::NautilusInput;
use libafl::schedulers::QueueScheduler;
use libafl::state::StdState;
use libafl_bolts::current_nanos;
use libafl_bolts::rands::StdRand;

use executor::AntlrParseExecutor;
use feedback::RuleCoverageFeedback;

const TREE_DEPTH: usize = 60;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let [_, nautilus_grammar_path, antlr_grammar_path, repetitions] = args.as_slice() else {
        eprintln!(
            "usage: nautilus-antlr-coverage-fuzzer <nautilus-grammar.py> <antlr-grammar.g4> <repetitions>"
        );
        exit(1);
    };

    let repetitions: usize = repetitions.parse().unwrap_or_else(|_| {
        eprintln!("repetitions must be a positive integer, got {repetitions:?}");
        exit(1);
    });

    let antlr_source = std::fs::read_to_string(antlr_grammar_path)
        .unwrap_or_else(|err| panic!("failed to read {antlr_grammar_path}: {err}"));

    let all_rules = antlr::parser_rule_names(&antlr_source);
    let start_rule = all_rules
        .first()
        .expect("no parser rules found in the antlr grammar")
        .clone();
    let total_rules: HashSet<&String> = all_rules.iter().collect();

    let context = NautilusContext::from_file(TREE_DEPTH, nautilus_grammar_path)
        .expect("failed to load nautilus grammar");
    let mut generator = NautilusGenerator::new(&context);

    let antlr_grammar_path = PathBuf::from(antlr_grammar_path);
    let mut executor = AntlrParseExecutor::new(&antlr_grammar_path, &start_rule, &context);

    let mut feedback = RuleCoverageFeedback::new();
    let mut objective = ConstFeedback::from(false);

    let mut state = StdState::new(
        StdRand::with_seed(current_nanos()),
        InMemoryCorpus::<NautilusInput>::new(),
        InMemoryCorpus::<NautilusInput>::new(),
        &mut feedback,
        &mut objective,
    )
    .expect("failed to build fuzzer state");

    let mut fuzzer = StdFuzzer::new(QueueScheduler::new(), feedback, objective);
    let mut mgr = libafl::events::NopEventManager::new();

    for _ in 0..repetitions {
        let input = generator
            .generate(&mut state)
            .expect("failed to generate a nautilus input");
        fuzzer
            .evaluate_input(&mut state, &mut executor, &mut mgr, &input)
            .expect("failed to evaluate generated input");
    }

    println!(
        "Visited {}/{} rules over {repetitions} runs",
        fuzzer.feedback().visited.len(),
        total_rules.len(),
    );
}
