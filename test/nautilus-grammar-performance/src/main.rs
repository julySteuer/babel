//! Grammar quality indicator: generate many random initial Nautilus seeds (no fuzz loop) with
//! libafl's `generate_initial_inputs` and report how much of the grammar they exercise, both on
//! the Nautilus grammar (productions) and, with --antlr, on the original ANTLR grammar (rules).
mod antlr;

use std::borrow::Cow;
use std::collections::{BTreeSet, HashMap, HashSet};
use std::path::PathBuf;
use std::process::exit;
use std::time::Instant;

use libafl::corpus::InMemoryCorpus;
use libafl::events::NopEventManager;
use libafl::executors::{Executor, ExitKind, HasObservers};
use libafl::feedbacks::{ConstFeedback, Feedback, StateInitializer};
use libafl::fuzzer::{HasFeedback, StdFuzzer};
use libafl::generators::nautilus::{NautilusContext, NautilusGenerator};
use libafl::inputs::nautilus::NautilusInput;
use libafl::observers::Observer;
use libafl::schedulers::QueueScheduler;
use libafl::state::{HasExecutions, StdState};
use libafl::Error;
use libafl_bolts::rands::StdRand;
use libafl_bolts::tuples::RefIndexable;
use libafl_bolts::{Named, current_nanos};
use serde::{Deserialize, Serialize};

use antlr::TokenVocabulary;

const USAGE: &str = "usage: nautilus-grammar-performance [-n <seeds>] [--depth <n>] [--antlr <g4>]...
       [--histogram <csv>] [--antlr-histogram <csv>] [--discovery <csv>] <nautilus-grammar.py>
  -n, --seeds <n>         number of random seeds to generate (default 1000)
  --depth <n>             max tree depth for the generator (default 60)
  --antlr <g4>            original ANTLR grammar file (repeatable); enables ANTLR rule coverage
                          via antlr4-parse (slow: one JVM run per distinct seed)
  --histogram <csv>       per Nautilus production: nonterminal,production,seeds (0 = never reached)
  --antlr-histogram <csv> per ANTLR rule: rule,seeds (needs --antlr)
  --discovery <csv>       per Nautilus production: first seed index it appeared in";

/// What one execution (= one seed) observed.
#[derive(Default, Serialize, Deserialize, Debug)]
struct SeedObserver {
    name: Cow<'static, str>,
    productions: HashSet<usize>,
    antlr_rules: HashSet<String>,
    bytes: Vec<u8>,
    nodes: usize,
}
impl Named for SeedObserver {
    fn name(&self) -> &Cow<'static, str> {
        &self.name
    }
}
impl<I, S> Observer<I, S> for SeedObserver {}
type Obs = (SeedObserver, ());

/// "Runs the target": unparses the seed, collects the used productions and, if configured,
/// the ANTLR rules visited when parsing it.
struct SeedExecutor<'a> {
    ctx: &'a NautilusContext,
    antlr: Option<AntlrTrace<'a>>,
    cache: HashMap<Vec<u8>, HashSet<String>>, // identical seeds need only one antlr4-parse run
    obs: Obs,
}
struct AntlrTrace<'a> {
    paths: &'a [PathBuf],
    start_rule: &'a str,
    vocabulary: TokenVocabulary,
}

impl<EM, S: HasExecutions, Z> Executor<EM, NautilusInput, S, Z> for SeedExecutor<'_> {
    fn run_target(&mut self, _: &mut Z, state: &mut S, _: &mut EM, input: &NautilusInput) -> Result<ExitKind, Error> {
        *state.executions_mut() += 1;
        let o = &mut self.obs.0;
        input.unparse(self.ctx, &mut o.bytes);
        o.nodes = input.tree.rules.len();
        o.productions = input.tree.rules.iter().map(|r| usize::from(r.id())).collect();
        if let Some(a) = &self.antlr {
            let text = String::from_utf8_lossy(&o.bytes);
            o.antlr_rules = self
                .cache
                .entry(o.bytes.clone())
                .or_insert_with(|| antlr::trace_visited_rules(a.paths, a.start_rule, &text, &a.vocabulary))
                .clone();
        }
        Ok(ExitKind::Ok)
    }
}
impl HasObservers for SeedExecutor<'_> {
    type Observers = Obs;
    fn observers(&self) -> RefIndexable<&Obs, Obs> {
        RefIndexable::from(&self.obs)
    }
    fn observers_mut(&mut self) -> RefIndexable<&mut Obs, Obs> {
        RefIndexable::from(&mut self.obs)
    }
}

/// Accumulates coverage over all seeds; a seed is "interesting" if it reached anything new.
struct CoverageFeedback {
    name: Cow<'static, str>,
    step: usize,
    counts: Vec<usize>,      // seeds using each production
    first_seen: Vec<usize>,  // 1-based seed index, 0 = never
    antlr_counts: HashMap<String, usize>,
    unique: HashSet<Vec<u8>>,
    bytes: usize,
    nodes: usize,
}
impl Named for CoverageFeedback {
    fn name(&self) -> &Cow<'static, str> {
        &self.name
    }
}
impl<S> StateInitializer<S> for CoverageFeedback {}
impl<EM, S> Feedback<EM, NautilusInput, Obs, S> for CoverageFeedback {
    fn is_interesting(&mut self, _: &mut S, _: &mut EM, _: &NautilusInput, obs: &Obs, _: &ExitKind) -> Result<bool, Error> {
        let o = &obs.0;
        self.step += 1;
        self.unique.insert(o.bytes.clone());
        self.bytes += o.bytes.len();
        self.nodes += o.nodes;
        let mut new = false;
        let n = self.counts.len();
        for &id in o.productions.iter().filter(|&&id| id < n) {
            self.counts[id] += 1;
            if self.first_seen[id] == 0 {
                self.first_seen[id] = self.step;
                new = true;
            }
        }
        for rule in &o.antlr_rules {
            *self.antlr_counts.entry(rule.clone()).or_default() += 1;
        }
        Ok(new)
    }
}

#[derive(Serialize)]
struct Report {
    grammar: String,
    seeds: usize,
    unique_seeds: usize,
    avg_seed_bytes: f64,
    avg_tree_nodes: f64,
    productions_total: usize,
    productions_visited: usize,
    production_coverage: f64,
    nonterminals_total: usize,
    nonterminals_visited: usize,
    nonterminal_coverage: f64,
    antlr_rules_total: Option<usize>,
    antlr_rules_visited: Option<usize>,
    antlr_coverage: Option<f64>,
    elapsed_secs: f64,
}

fn flag<T: std::str::FromStr>(name: &str, v: Option<String>) -> T {
    v.and_then(|v| v.parse().ok()).unwrap_or_else(|| {
        eprintln!("{name} needs a valid value\n{USAGE}");
        exit(1)
    })
}

fn main() {
    let (mut seeds, mut depth) = (1000usize, 60usize);
    let (mut histogram, mut antlr_histogram, mut discovery): (Option<String>, Option<String>, Option<String>) = (None, None, None);
    let (mut grammar, mut g4): (Option<String>, Vec<PathBuf>) = (None, Vec::new());
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        match a.as_str() {
            "-n" | "--seeds" => seeds = flag(&a, args.next()),
            "--depth" => depth = flag(&a, args.next()),
            "--antlr" => g4.push(flag(&a, args.next())),
            "--histogram" => histogram = Some(flag(&a, args.next())),
            "--antlr-histogram" => antlr_histogram = Some(flag(&a, args.next())),
            "--discovery" => discovery = Some(flag(&a, args.next())),
            "-h" | "--help" => return println!("{USAGE}"),
            _ => grammar = Some(a),
        }
    }
    let Some(grammar) = grammar else {
        eprintln!("{USAGE}");
        exit(1)
    };

    let context = NautilusContext::from_file(depth, &grammar).expect("failed to load nautilus grammar");
    let ctx = &context.ctx;

    // Productions are numbered 0..N; Context has no length accessor, so probe until it panics.
    std::panic::set_hook(Box::new(|_| {}));
    let mut productions: Vec<String> = Vec::new(); // nonterminal name of production i
    while let Ok(nt) = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        ctx.nt_id_to_s(ctx.get_rule(productions.len().into()).nonterm())
    })) {
        productions.push(nt);
    }
    let _ = std::panic::take_hook();
    // The loader's synthetic START production is not part of the grammar under test.
    let in_grammar = |i: usize| productions[i] != "START";
    let grammar_ids: Vec<usize> = (0..productions.len()).filter(|&i| in_grammar(i)).collect();
    let total_nts: HashSet<&String> = grammar_ids.iter().map(|&i| &productions[i]).collect();

    // ANTLR side: rule universe + executor tracing (same approach as nautilus-antlr-coverage-fuzzer).
    let sources: Vec<String> = g4
        .iter()
        .map(|p| std::fs::read_to_string(p).unwrap_or_else(|e| panic!("failed to read {}: {e}", p.display())))
        .collect();
    let parser_rules = antlr::parser_rule_names(&sources);
    let start_rule = parser_rules.first().cloned().unwrap_or_default();
    let antlr_total: BTreeSet<String> = parser_rules.into_iter().chain(antlr::lexer_rule_names(&sources)).collect();
    if !g4.is_empty() && start_rule.is_empty() {
        eprintln!("no parser rules found in the antlr grammar(s)");
        exit(1);
    }

    let mut executor = SeedExecutor {
        ctx: &context,
        antlr: (!g4.is_empty()).then(|| AntlrTrace {
            paths: &g4,
            start_rule: &start_rule,
            vocabulary: antlr::build_token_vocabulary(&g4),
        }),
        cache: HashMap::new(),
        obs: (SeedObserver::default(), ()),
    };
    let mut feedback = CoverageFeedback {
        name: Cow::Borrowed("coverage"),
        step: 0,
        counts: vec![0; productions.len()],
        first_seen: vec![0; productions.len()],
        antlr_counts: HashMap::new(),
        unique: HashSet::new(),
        bytes: 0,
        nodes: 0,
    };
    let mut objective = ConstFeedback::from(false);
    let mut state = StdState::new(
        StdRand::with_seed(current_nanos()),
        InMemoryCorpus::<NautilusInput>::new(),
        InMemoryCorpus::<NautilusInput>::new(),
        &mut feedback,
        &mut objective,
    )
    .unwrap();
    let mut fuzzer = StdFuzzer::new(QueueScheduler::new(), feedback, objective);
    let mut generator = NautilusGenerator::new(&context);

    let t0 = Instant::now();
    state
        .generate_initial_inputs(&mut fuzzer, &mut executor, &mut generator, &mut NopEventManager::new(), seeds)
        .expect("seed generation failed");
    let elapsed_secs = t0.elapsed().as_secs_f64();

    let fb = fuzzer.feedback();
    let visited: Vec<usize> = grammar_ids.iter().copied().filter(|&i| fb.counts[i] > 0).collect();
    let visited_nts: HashSet<&String> = visited.iter().map(|&i| &productions[i]).collect();
    let antlr_visited = antlr_total.iter().filter(|r| fb.antlr_counts.contains_key(*r)).count();
    let frac = |a: usize, b: usize| if b == 0 { 0.0 } else { a as f64 / b as f64 };
    let n = seeds.max(1) as f64;
    let with_antlr = !g4.is_empty();
    println!(
        "{}",
        serde_json::to_string(&Report {
            grammar,
            seeds,
            unique_seeds: fb.unique.len(),
            avg_seed_bytes: fb.bytes as f64 / n,
            avg_tree_nodes: fb.nodes as f64 / n,
            productions_total: grammar_ids.len(),
            productions_visited: visited.len(),
            production_coverage: frac(visited.len(), grammar_ids.len()),
            nonterminals_total: total_nts.len(),
            nonterminals_visited: visited_nts.len(),
            nonterminal_coverage: frac(visited_nts.len(), total_nts.len()),
            antlr_rules_total: with_antlr.then_some(antlr_total.len()),
            antlr_rules_visited: with_antlr.then_some(antlr_visited),
            antlr_coverage: with_antlr.then(|| frac(antlr_visited, antlr_total.len())),
            elapsed_secs,
        })
        .unwrap()
    );

    let write = |path: String, csv: String| std::fs::write(&path, csv).unwrap_or_else(|e| panic!("cannot write {path}: {e}"));
    if let Some(path) = histogram {
        let mut csv = String::from("nonterminal,production,seeds\n");
        for &i in &grammar_ids {
            csv += &format!("{},{},{}\n", productions[i], i, fb.counts[i]);
        }
        write(path, csv);
    }
    if let Some(path) = antlr_histogram {
        let mut csv = String::from("rule,seeds\n");
        for rule in &antlr_total {
            csv += &format!("{rule},{}\n", fb.antlr_counts.get(rule).copied().unwrap_or(0));
        }
        write(path, csv);
    }
    if let Some(path) = discovery {
        let mut seen: Vec<usize> = visited.clone();
        seen.sort_by_key(|&i| (fb.first_seen[i], i));
        let mut csv = String::from("production,nonterminal,seed\n");
        for i in seen {
            csv += &format!("{i},{},{}\n", productions[i], fb.first_seen[i]);
        }
        write(path, csv);
    }
}
