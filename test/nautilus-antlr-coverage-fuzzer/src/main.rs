mod antlr;
mod executor;
mod feedback;
mod observer;
mod stats;
mod tui;

use std::collections::HashSet;
use std::path::PathBuf;
use std::process::exit;
use std::time::{Duration, Instant};

use libafl::HasMetadata;
use libafl::corpus::{Corpus, InMemoryCorpus};
use libafl::feedbacks::ConstFeedback;
use libafl::feedbacks::NautilusChunksMetadata;
use libafl::fuzzer::{Evaluator, Fuzzer, HasFeedback, StdFuzzer};
use libafl::generators::Generator;
use libafl::generators::nautilus::{NautilusContext, NautilusGenerator};
use libafl::inputs::nautilus::NautilusInput;
use libafl::mutators::{
    HavocScheduledMutator, NautilusRandomMutator, NautilusRecursionMutator, NautilusSpliceMutator,
};
use libafl::schedulers::QueueScheduler;
use libafl::stages::StdMutationalStage;
use libafl::stages::generation::GenStage;
use libafl::state::HasCorpus;
use libafl::state::HasExecutions;
use libafl::state::StdState;
use libafl_bolts::current_nanos;
use libafl_bolts::rands::StdRand;
use libafl_bolts::tuples::tuple_list;
use serde::Serialize;
use std::num::NonZeroUsize;

use executor::AntlrParseExecutor;
use feedback::RuleCoverageFeedback;
use stats::{FuzzStats, StopConditions, StopReason};
use tui::Tui;

/// Nautilus' limit on the number of rule applications in one generated tree (not its depth).
const DEFAULT_TREE_SIZE: usize = 60;

#[derive(Serialize)]
struct PerformanceReport {
    antlr_grammars: Vec<String>,
    repetitions: usize,
    stop_reason: &'static str,
    total_rules: usize,
    visited_rules: usize,
    coverage: f64,
    elapsed_secs: f64,
}

const USAGE: &str = "usage: nautilus-antlr-coverage-fuzzer [options] <nautilus-grammar.py> <repetitions> <antlr-grammar.g4>...

<repetitions> is the iteration limit; 0 means unlimited (use another stop option then).

options:
  --tui                   live terminal monitor (q / Esc stops the run)
  --timeout <secs>        stop after this much wall-clock time
  --target-coverage <f>   stop once this fraction (0..1) of all rules is visited
  --stall <n>             stop after n consecutive inputs without a new rule
  --histogram <file>      write a CSV histogram (rule,count,fraction): per rule, the number of
                          executed inputs that visited it; fraction = count / executed inputs
  --discovery <file>      write a CSV (rule,step) with the execution step each rule was first visited
  --mutations <n>         max mutated inputs tried per corpus entry (default 8)";

fn parse_flag<T: std::str::FromStr>(name: &str, value: Option<String>) -> T {
    value.and_then(|v| v.parse().ok()).unwrap_or_else(|| {
        eprintln!("{name} needs a valid value\n\n{USAGE}");
        exit(1);
    })
}

fn main() {
    let mut use_tui = false;
    let mut stop = StopConditions::default();
    let mut mutations: usize = 8;
    let mut histogram_path: Option<PathBuf> = None;
    let mut discovery_path: Option<PathBuf> = None;
    let mut positional: Vec<String> = Vec::new();
    let mut raw_args = std::env::args().skip(1);
    while let Some(arg) = raw_args.next() {
        match arg.as_str() {
            "--tui" => use_tui = true,
            "--timeout" => {
                stop.timeout = Some(Duration::from_secs_f64(parse_flag(&arg, raw_args.next())))
            }
            "--target-coverage" => stop.target_coverage = Some(parse_flag(&arg, raw_args.next())),
            "--histogram" => histogram_path = Some(parse_flag(&arg, raw_args.next())),
            "--discovery" => discovery_path = Some(parse_flag(&arg, raw_args.next())),
            "--mutations" => mutations = parse_flag(&arg, raw_args.next()),
            "--tree-size" => tree_size = parse_flag(&arg, raw_args.next()),
            "--stall" => stop.stall_iterations = Some(parse_flag(&arg, raw_args.next())),
            "--help" | "-h" => {
                println!("{USAGE}");
                return;
            }
            _ => positional.push(arg),
        }
    }
    let [nautilus_grammar_path, repetitions, antlr_grammar_paths @ ..] = positional.as_slice()
    else {
        eprintln!("{USAGE}");
        exit(1);
    };

    if antlr_grammar_paths.is_empty() {
        eprintln!("at least one antlr grammar file is required");
        exit(1);
    }

    let repetitions: usize = repetitions.parse().unwrap_or_else(|_| {
        eprintln!("repetitions must be a non-negative integer, got {repetitions:?}");
        exit(1);
    });
    stop.max_iterations = (repetitions > 0).then_some(repetitions);
    if stop.max_iterations.is_none()
        && stop.timeout.is_none()
        && stop.target_coverage.is_none()
        && stop.stall_iterations.is_none()
        && !use_tui
    {
        eprintln!("unlimited run without --tui needs --timeout, --target-coverage or --stall");
        exit(1);
    }

    let antlr_sources: Vec<String> = antlr_grammar_paths
        .iter()
        .map(|path| {
            std::fs::read_to_string(path)
                .unwrap_or_else(|err| panic!("failed to read {path}: {err}"))
        })
        .collect();

    let parser_rules = antlr::parser_rule_names(&antlr_sources);
    let start_rule = parser_rules
        .first()
        .expect("no parser rules found in the antlr grammar(s)")
        .clone();
    let lexer_rules = antlr::lexer_rule_names(&antlr_sources);
    let total_rules: HashSet<String> = parser_rules.into_iter().chain(lexer_rules).collect();

    let context = NautilusContext::from_file(tree_size, nautilus_grammar_path)
        .expect("failed to load nautilus grammar");
    let mut generator = NautilusGenerator::new(&context);

    let antlr_grammar_paths: Vec<PathBuf> = antlr_grammar_paths.iter().map(PathBuf::from).collect();
    let mut executor = AntlrParseExecutor::new(&antlr_grammar_paths, &start_rule, &context);

    let mutations = NonZeroUsize::new(mutations).unwrap_or_else(|| {
        eprintln!("--mutations must be at least 1");
        exit(1);
    });
    let mut feedback = RuleCoverageFeedback::new(&context);
    let mut objective = ConstFeedback::from(false);

    let mut state = StdState::new(
        StdRand::with_seed(current_nanos()),
        InMemoryCorpus::<NautilusInput>::new(),
        InMemoryCorpus::<NautilusInput>::new(),
        &mut feedback,
        &mut objective,
    )
    .expect("failed to build fuzzer state");
    let chunk_dir =
        std::env::temp_dir().join(format!("nautilus-antlr-chunks-{}", std::process::id()));
    state.add_metadata(NautilusChunksMetadata::new(chunk_dir.display().to_string()));

    let mut fuzzer = StdFuzzer::new(QueueScheduler::new(), feedback, objective);
    let mut mgr = libafl::events::NopEventManager::new();

    // Fresh random generation keeps exploring; the mutators then rework inputs that
    // found new rules (subtree regeneration, recursion unrolling, splicing).
    let mutator = HavocScheduledMutator::new(tuple_list!(
        NautilusRandomMutator::new(&context),
        NautilusRandomMutator::new(&context),
        NautilusRandomMutator::new(&context),
        NautilusRandomMutator::new(&context),
        NautilusRandomMutator::new(&context),
        NautilusRandomMutator::new(&context),
        NautilusRecursionMutator::new(&context),
        NautilusSpliceMutator::new(&context),
        NautilusSpliceMutator::new(&context),
        NautilusSpliceMutator::new(&context),
    ));
    let mut stages = tuple_list!(
        GenStage::new(NautilusGenerator::new(&context)),
        StdMutationalStage::with_max_iterations(mutator, mutations),
    );

    let mut tui = use_tui.then(|| Tui::start().expect("failed to start the terminal UI"));
    let mut stats = FuzzStats::new(total_rules.len());
    let start = Instant::now();
    let mut last_draw = Instant::now() - Duration::from_secs(1);
    let mut executions_seen = 0usize;
    let stop_reason = loop {
        if let Some(reason) = stats.check_stop(&stop) {
            break reason;
        }
        if tui.is_some() && Tui::quit_requested() {
            break StopReason::UserQuit;
        }

        if state.corpus().count() == 0 {
            // The scheduler needs a corpus entry; keep generating until one input is interesting.
            let input = generator
                .generate(&mut state)
                .expect("failed to generate a nautilus input");
            fuzzer
                .evaluate_input(&mut state, &mut executor, &mut mgr, &input)
                .expect("failed to evaluate generated input");
        } else {
            fuzzer
                .fuzz_one(&mut stages, &mut executor, &mut state, &mut mgr)
                .expect("fuzzing iteration failed");
        }
        let executions = *state.executions() as usize;
        let new_rules = std::mem::take(&mut fuzzer.feedback_mut().new_rules);
        stats.record(start.elapsed(), executions - executions_seen, &new_rules);
        executions_seen = executions;

        if let Some(tui) = tui.as_mut() {
            if last_draw.elapsed() >= Duration::from_millis(100) {
                tui.draw(&stats, &stop, None);
                last_draw = Instant::now();
            }
        }
    };
    let elapsed_secs = start.elapsed().as_secs_f64();

    if let Some(mut tui) = tui.take() {
        tui.draw(&stats, &stop, Some(stop_reason.describe()));
        if stop_reason != StopReason::UserQuit {
            tui.wait_for_key();
        }
    }
    eprintln!("stopped: {}", stop_reason.describe());

    let visited_rules = fuzzer.feedback().visited.len();
    let report = PerformanceReport {
        antlr_grammars: antlr_grammar_paths
            .iter()
            .map(|path| path.display().to_string())
            .collect(),
        repetitions: stats.iterations,
        stop_reason: stop_reason.describe(),
        total_rules: total_rules.len(),
        visited_rules,
        coverage: if total_rules.is_empty() {
            0.0
        } else {
            visited_rules as f64 / total_rules.len() as f64
        },
        elapsed_secs,
    };

    if let Some(path) = histogram_path {
        let all_rules: Vec<&String> = total_rules
            .iter()
            .chain(fuzzer.feedback().hit_counts.keys())
            .collect::<std::collections::BTreeSet<_>>()
            .into_iter()
            .collect();
        let mut csv = String::from("rule,count,fraction\n");
        for rule in all_rules {
            let count = fuzzer.feedback().hit_counts.get(rule).copied().unwrap_or(0);
            let fraction = count as f64 / stats.iterations.max(1) as f64;
            csv.push_str(&format!("{rule},{count},{fraction:.6}\n"));
        }
        std::fs::write(&path, csv)
            .unwrap_or_else(|err| panic!("failed to write histogram {}: {err}", path.display()));
    }

    if let Some(path) = discovery_path {
        let mut csv = String::from("rule,step\n");
        for (step, rule) in &fuzzer.feedback().discoveries {
            csv.push_str(&format!("{rule},{step}\n"));
        }
        std::fs::write(&path, csv)
            .unwrap_or_else(|err| panic!("failed to write discovery {}: {err}", path.display()));
    }

    println!(
        "{}",
        serde_json::to_string(&report).expect("failed to serialize performance report")
    );
}
