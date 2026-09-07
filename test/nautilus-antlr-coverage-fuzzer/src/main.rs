mod antlr;
mod feedback;
mod observer;

use std::collections::HashSet;
use std::path::PathBuf;
use std::process::exit;

use libafl::generators::Generator;
use libafl::generators::nautilus::{NautilusContext, NautilusGenerator};
use libafl::inputs::nautilus::NautilusInput;
use libafl::state::NopState;

use feedback::{Feedback, RuleCoverageFeedback};
use observer::{AntlrTraceObserver, Observer};

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
    let mut state = NopState::<NautilusInput>::new();

    let antlr_grammar_path = PathBuf::from(antlr_grammar_path);
    let observer = AntlrTraceObserver {
        grammar_path: &antlr_grammar_path,
        start_rule: &start_rule,
    };
    let mut feedback = RuleCoverageFeedback::default();

    let mut bytes = Vec::new();
    for _ in 0..repetitions {
        let input = generator
            .generate(&mut state)
            .expect("failed to generate a nautilus input");
        bytes.clear();
        input.unparse(&context, &mut bytes);

        let generated_input = String::from_utf8_lossy(&bytes);
        let observed = observer.observe(&generated_input);
        feedback.is_interesting(&observed);
    }

    println!(
        "Visited {}/{} rules over {repetitions} runs",
        feedback.visited().len(),
        total_rules.len(),
    );
}
