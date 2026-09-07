mod antlr;
mod executor;
mod feedback;
mod observer;

use std::collections::HashSet;
use std::path::PathBuf;
use std::process::exit;
use std::time::Instant;

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
use serde::Serialize;

use executor::AntlrParseExecutor;
use feedback::RuleCoverageFeedback;

const TREE_DEPTH: usize = 60;

#[derive(Serialize)]
struct PerformanceReport {
    antlr_grammars: Vec<String>,
    repetitions: usize,
    total_rules: usize,
    visited_rules: usize,
    coverage: f64,
    elapsed_secs: f64,
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let [_, nautilus_grammar_path, repetitions, antlr_grammar_paths @ ..] = args.as_slice() else {
        eprintln!(
            "usage: nautilus-antlr-coverage-fuzzer <nautilus-grammar.py> <repetitions> <antlr-grammar.g4>..."
        );
        exit(1);
    };

    if antlr_grammar_paths.is_empty() {
        eprintln!("at least one antlr grammar file is required");
        exit(1);
    }

    let repetitions: usize = repetitions.parse().unwrap_or_else(|_| {
        eprintln!("repetitions must be a positive integer, got {repetitions:?}");
        exit(1);
    });

    let antlr_sources: Vec<String> = antlr_grammar_paths
        .iter()
        .map(|path| {
            std::fs::read_to_string(path).unwrap_or_else(|err| panic!("failed to read {path}: {err}"))
        })
        .collect();

    let all_rules = antlr::parser_rule_names(&antlr_sources);
    let start_rule = all_rules
        .first()
        .expect("no parser rules found in the antlr grammar(s)")
        .clone();
    let total_rules: HashSet<&String> = all_rules.iter().collect();

    let context = NautilusContext::from_file(TREE_DEPTH, nautilus_grammar_path)
        .expect("failed to load nautilus grammar");
    let mut generator = NautilusGenerator::new(&context);

    let antlr_grammar_paths: Vec<PathBuf> = antlr_grammar_paths.iter().map(PathBuf::from).collect();
    let mut executor = AntlrParseExecutor::new(&antlr_grammar_paths, &start_rule, &context);

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

    let start = Instant::now();
    for _ in 0..repetitions {
        let input = generator
            .generate(&mut state)
            .expect("failed to generate a nautilus input");
        fuzzer
            .evaluate_input(&mut state, &mut executor, &mut mgr, &input)
            .expect("failed to evaluate generated input");
    }
    let elapsed_secs = start.elapsed().as_secs_f64();

    let visited_rules = fuzzer.feedback().visited.len();
    let report = PerformanceReport {
        antlr_grammars: antlr_grammar_paths
            .iter()
            .map(|path| path.display().to_string())
            .collect(),
        repetitions,
        total_rules: total_rules.len(),
        visited_rules,
        coverage: if total_rules.is_empty() {
            0.0
        } else {
            visited_rules as f64 / total_rules.len() as f64
        },
        elapsed_secs,
    };

    println!(
        "{}",
        serde_json::to_string(&report).expect("failed to serialize performance report")
    );
}
