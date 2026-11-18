//! Grammar quality indicator: generate many random initial Nautilus seeds (no fuzz loop) with
//! libafl's `generate_initial_inputs` and report how much of the grammar they exercise, both on
//! the Nautilus grammar (productions) and, with --antlr, on the original ANTLR grammar (rules).
mod antlr;

use std::borrow::Cow;
use std::cmp::{Ordering, Reverse};
use std::collections::{BTreeSet, BinaryHeap, HashMap, HashSet};
use std::path::PathBuf;
use std::process::exit;
use std::time::{Duration, Instant};

use libafl::corpus::InMemoryCorpus;
use libafl::events::NopEventManager;
use libafl::executors::{Executor, ExitKind, HasObservers};
use libafl::feedbacks::{ConstFeedback, Feedback, StateInitializer};
use libafl::fuzzer::{HasFeedback, StdFuzzer};
use libafl::generators::nautilus::{NautilusContext, NautilusGenerator};
use libafl::generators::Generator;
use libafl::inputs::nautilus::NautilusInput;
use libafl::observers::Observer;
use libafl::schedulers::QueueScheduler;
use libafl::state::{HasExecutions, HasRand, StdState};
use libafl::Error;
use libafl_bolts::rands::StdRand;
use libafl_bolts::tuples::RefIndexable;
use libafl_bolts::{Named, current_nanos};
use serde::{Deserialize, Serialize};

use antlr::TokenVocabulary;

const USAGE: &str = "usage: nautilus-grammar-performance [-n <seeds>] [--depth <n>] [--candidates <m>] [--per-rule] [--per-rule-csv <csv>] [--start-rule <name>] [--dump-seeds <dir>] [--antlr-timeout <secs>] [--antlr <g4>]...
       [--histogram <csv>] [--antlr-histogram <csv>] [--discovery <csv>] <nautilus-grammar.py>
  -n, --seeds <n>         number of random seeds to generate (default 1000)
  --depth <n>             max tree depth for the generator (default 60)
  --candidates <m>        generate m random trees and keep only the n deepest (default m = n, i.e. no
                          selection). Generation is cheap, the antlr step is not.
  --per-rule              instead of seeds from START: for every ANTLR parser rule generate trees directly
                          from its nonterminal (m candidates, the n deepest kept) and parse them with that
                          rule as ANTLR start rule. Measures whether each rule is generable; the trees are
                          rule fragments, not whole-program seeds. Needs --antlr.
  --per-rule-csv <csv>    per ANTLR parser rule: min tree size, seeds tried, seeds parsed without syntax error
  --start-rule <name>     ANTLR start rule used to parse the seeds (default: first parser rule found)
  --dump-seeds <dir>      write every executed seed as <dir>/seed_<i>.txt (for debugging a grammar)
  --antlr-timeout <secs>  kill antlr4-parse after this long on one seed and count the seed as timed out (default 20)
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
    antlr_traced: bool,
    antlr_timed_out: bool,
    bytes: Vec<u8>,
    nodes: usize,
    depth: usize,
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
    cache: HashMap<Vec<u8>, (HashSet<String>, bool)>, // identical seeds need only one antlr4-parse run; bool = timed out
    obs: Obs,
}
struct AntlrTrace<'a> {
    paths: &'a [PathBuf],
    start_rule: &'a str,
    timeout: Duration,
    vocabulary: TokenVocabulary,
}

impl<EM, S: HasExecutions, Z> Executor<EM, NautilusInput, S, Z> for SeedExecutor<'_> {
    fn run_target(&mut self, _: &mut Z, state: &mut S, _: &mut EM, input: &NautilusInput) -> Result<ExitKind, Error> {
        *state.executions_mut() += 1;
        let o = &mut self.obs.0;
        input.unparse(self.ctx, &mut o.bytes);
        o.nodes = input.tree.rules.len();
        o.depth = tree_depth(input);
        o.productions = input.tree.rules.iter().map(|r| usize::from(r.id())).collect();
        o.antlr_traced = self.antlr.is_some();
        if let Some(a) = &self.antlr {
            let text = String::from_utf8_lossy(&o.bytes);
            let (rules, timed_out) = self
                .cache
                .entry(o.bytes.clone())
                .or_insert_with(|| {
                    let trace = antlr::trace_rules(a.paths, a.start_rule, &text, &a.vocabulary, a.timeout);
                    (trace.visited, trace.timed_out)
                })
                .clone();
            o.antlr_rules = rules;
            o.antlr_timed_out = timed_out;
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
    antlr_empty: usize,
    antlr_timeouts: usize,
    unique: HashSet<Vec<u8>>,
    bytes: usize,
    nodes: usize,
    depth: usize,
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
        self.depth += o.depth;
        let mut new = false;
        let n = self.counts.len();
        for &id in o.productions.iter().filter(|&&id| id < n) {
            self.counts[id] += 1;
            if self.first_seen[id] == 0 {
                self.first_seen[id] = self.step;
                new = true;
            }
        }
        if o.antlr_timed_out {
            self.antlr_timeouts += 1;
        } else if o.antlr_traced && o.antlr_rules.is_empty() {
            self.antlr_empty += 1; // antlr4-parse always enters the start rule, so nothing means the tool failed
        }
        for rule in &o.antlr_rules {
            *self.antlr_counts.entry(rule.clone()).or_default() += 1;
        }
        Ok(new)
    }
}

/// Real depth (longest root-to-leaf path in nodes). Nodes are stored in preorder, so a parent always
/// precedes its children and one forward pass is enough.
fn tree_depth(input: &NautilusInput) -> usize {
    let t = input.tree();
    let mut d = vec![1usize; t.rules.len()];
    for i in 1..d.len() {
        d[i] = d[t.paren[i].to_i()] + 1;
    }
    d.into_iter().max().unwrap_or(0)
}

/// A generated tree ordered by its depth only.
struct Cand(usize, NautilusInput);
impl PartialEq for Cand {
    fn eq(&self, o: &Self) -> bool {
        self.0 == o.0
    }
}
impl Eq for Cand {}
impl PartialOrd for Cand {
    fn partial_cmp(&self, o: &Self) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}
impl Ord for Cand {
    fn cmp(&self, o: &Self) -> Ordering {
        self.0.cmp(&o.0)
    }
}

#[derive(Serialize)]
struct Report {
    grammar: String,
    seeds: usize,
    unique_seeds: usize,
    avg_seed_bytes: f64,
    avg_tree_nodes: f64,
    avg_tree_depth: f64,
    candidates: usize,
    productions_total: usize,
    productions_visited: usize,
    production_coverage: f64,
    nonterminals_total: usize,
    nonterminals_visited: usize,
    nonterminal_coverage: f64,
    antlr_start_rule: Option<String>,
    antlr_vocabulary_size: Option<usize>,
    antlr_empty_traces: Option<usize>,
    antlr_timeouts: Option<usize>,
    antlr_rules_total: Option<usize>,
    antlr_rules_visited: Option<usize>,
    antlr_coverage: Option<f64>,
    elapsed_secs: f64,
}

fn frac_of(a: usize, b: usize) -> f64 {
    if b == 0 { 0.0 } else { a as f64 / b as f64 }
}

fn flag<T: std::str::FromStr>(name: &str, v: Option<String>) -> T {
    v.and_then(|v| v.parse().ok()).unwrap_or_else(|| {
        eprintln!("{name} needs a valid value\n{USAGE}");
        exit(1)
    })
}

fn main() {
    let (mut seeds, mut depth, mut candidates) = (1000usize, 60usize, 0usize);
    let mut start_rule_flag: Option<String> = None;
    let mut dump_dir: Option<PathBuf> = None;
    let mut antlr_timeout = 20u64;
    let (mut per_rule, mut per_rule_csv): (bool, Option<String>) = (false, None);
    let (mut histogram, mut antlr_histogram, mut discovery): (Option<String>, Option<String>, Option<String>) = (None, None, None);
    let (mut grammar, mut g4): (Option<String>, Vec<PathBuf>) = (None, Vec::new());
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        match a.as_str() {
            "-n" | "--seeds" => seeds = flag(&a, args.next()),
            "--depth" => depth = flag(&a, args.next()),
            "--candidates" => candidates = flag(&a, args.next()),
            "--per-rule" => per_rule = true,
            "--start-rule" => start_rule_flag = Some(flag(&a, args.next())),
            "--dump-seeds" => dump_dir = Some(flag(&a, args.next())),
            "--antlr-timeout" => antlr_timeout = flag(&a, args.next()),
            "--per-rule-csv" => per_rule_csv = Some(flag(&a, args.next())),
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
    let candidates = candidates.max(seeds);

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
    let start_rule = start_rule_flag.or_else(|| parser_rules.first().cloned()).unwrap_or_default();
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
            timeout: Duration::from_secs(antlr_timeout),
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
        antlr_empty: 0,
        antlr_timeouts: 0,
        unique: HashSet::new(),
        bytes: 0,
        nodes: 0,
        depth: 0,
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
    if per_rule {
        let a = executor.antlr.as_ref().expect("--per-rule needs --antlr");
        let nt_names: HashSet<&String> = productions.iter().collect();
        let mut csv = String::from("rule,nonterminal,min_size,seeds_tried,seeds_clean\n");
        let mut union: HashSet<String> = HashSet::new(); // rules visited by parses without syntax error
        let mut union_any: HashSet<String> = HashSet::new(); // rules visited by any parse attempt
        let (mut total, mut generable, mut clean_rules) = (0usize, 0usize, 0usize);
        for rule in antlr::parser_rule_names(&sources) {
            total += 1;
            let mut cs = rule.chars();
            let nt_name: String = cs.next().map(|c| c.to_uppercase().collect::<String>()).unwrap_or_default() + cs.as_str();
            if !nt_names.contains(&nt_name) {
                csv += &format!("{rule},{nt_name},,0,0\n");
                continue;
            }
            let nt = generator.nonterminal(&nt_name);
            let (min, len) = (context.ctx.get_min_len_for_nt(nt), context.ctx.get_random_len_for_nt(&nt));
            if min > len {
                csv += &format!("{rule},{nt_name},{min},0,0\n");
                continue;
            }
            generable += 1;
            let mut kept: BinaryHeap<Reverse<Cand>> = BinaryHeap::with_capacity(seeds + 1);
            for _ in 0..candidates {
                let mut input = NautilusInput::empty();
                generator.generate_from_nonterminal(state.rand_mut(), &mut input, nt, len);
                kept.push(Reverse(Cand(tree_depth(&input), input)));
                if kept.len() > seeds {
                    kept.pop();
                }
            }
            let (mut tried, mut clean) = (0usize, 0usize);
            let mut seen: HashSet<Vec<u8>> = HashSet::new();
            for Reverse(Cand(_, input)) in kept.into_sorted_vec().into_iter().rev() {
                let mut bytes = Vec::new();
                input.unparse(&context, &mut bytes);
                if !seen.insert(bytes.clone()) {
                    continue;
                }
                let trace = antlr::trace_rules(a.paths, &rule, &String::from_utf8_lossy(&bytes), &a.vocabulary, a.timeout);
                tried += 1;
                union_any.extend(trace.visited.iter().cloned());
                if !trace.had_error && !trace.timed_out {
                    clean += 1;
                    union.extend(trace.visited);
                }
            }
            if clean > 0 {
                clean_rules += 1;
            }
            csv += &format!("{rule},{nt_name},{min},{tried},{clean}\n");
        }
        let covered = antlr_total.iter().filter(|r| union.contains(*r)).count();
        let covered_any = antlr_total.iter().filter(|r| union_any.contains(*r)).count();
        println!(
            "{}",
            serde_json::json!({
                "mode": "per-rule", "seeds_per_rule": seeds, "candidates_per_rule": candidates,
                "parser_rules": total, "rules_generable_within_budget": generable,
                "rules_with_clean_parse": clean_rules,
                "antlr_rules_total": antlr_total.len(), "antlr_rules_visited_clean": covered,
                "antlr_coverage_clean": frac_of(covered, antlr_total.len()),
                "antlr_rules_visited_any": covered_any,
                "antlr_coverage_any": frac_of(covered_any, antlr_total.len()),
                "elapsed_secs": t0.elapsed().as_secs_f64(),
            })
        );
        if let Some(path) = per_rule_csv {
            std::fs::write(&path, csv).unwrap_or_else(|e| panic!("cannot write {path}: {e}"));
        }
        return;
    }
    let mut mgr = NopEventManager::new();
    macro_rules! run {
        ($input:expr) => {{
            let input: &NautilusInput = $input;
            executor.run_target(&mut fuzzer, &mut state, &mut mgr, input).expect("execution failed");
            fuzzer
                .feedback_mut()
                .is_interesting(&mut state, &mut mgr, input, &executor.obs, &ExitKind::Ok)
                .expect("feedback failed");
        }};
    }
    // Generate `candidates` trees, keep the `seeds` deepest (a min-heap of size `seeds`), run only those.
    let mut kept: BinaryHeap<Reverse<Cand>> = BinaryHeap::with_capacity(seeds + 1);
    for _ in 0..candidates {
        let input = generator.generate(&mut state).expect("seed generation failed");
        kept.push(Reverse(Cand(tree_depth(&input), input)));
        if kept.len() > seeds {
            kept.pop();
        }
    }
    if let Some(dir) = &dump_dir {
        std::fs::create_dir_all(dir).expect("cannot create the seed dump directory");
    }
    for (i, Reverse(Cand(_, input))) in kept.into_sorted_vec().into_iter().rev().enumerate() {
        if let Some(dir) = &dump_dir {
            // before running it, so a seed that hangs antlr4-parse is still on disk
            let mut bytes = Vec::new();
            input.unparse(&context, &mut bytes);
            let _ = std::fs::write(dir.join(format!("seed_{i}.txt")), bytes);
        }
        run!(&input);
    }
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
            avg_tree_depth: fb.depth as f64 / n,
            candidates,
            productions_total: grammar_ids.len(),
            productions_visited: visited.len(),
            production_coverage: frac(visited.len(), grammar_ids.len()),
            nonterminals_total: total_nts.len(),
            nonterminals_visited: visited_nts.len(),
            nonterminal_coverage: frac(visited_nts.len(), total_nts.len()),
            antlr_start_rule: with_antlr.then(|| start_rule.clone()),
            antlr_vocabulary_size: executor.antlr.as_ref().map(|a| a.vocabulary.len()),
            antlr_empty_traces: with_antlr.then_some(fb.antlr_empty),
            antlr_timeouts: with_antlr.then_some(fb.antlr_timeouts),
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
