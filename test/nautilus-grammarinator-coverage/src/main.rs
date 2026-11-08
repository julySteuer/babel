//! LibAFL+Nautilus fuzzer for the instrumented sqlite harness.
//! usage: nautilus-grammarinator-coverage <nautilus-grammar.py> <harness> <out.csv> <executions> <corpus-dir>
//! Writes `step,edges` (cumulative edge coverage after each execution) to <out.csv>.
use std::io::Write;
use std::os::unix::process::ExitStatusExt;
use std::path::PathBuf;
use std::process::{Command, Stdio};

use libafl::corpus::{Corpus, InMemoryCorpus};
use libafl::executors::{Executor, ExitKind, HasObservers};
use libafl::feedback_or;
use libafl::feedbacks::{ConstFeedback, MaxMapFeedback, NautilusChunksMetadata, NautilusFeedback};
use libafl::fuzzer::{Evaluator, Fuzzer, StdFuzzer};
use libafl::generators::Generator;
use libafl::generators::nautilus::{NautilusContext, NautilusGenerator};
use libafl::inputs::nautilus::NautilusInput;
use libafl::mutators::{
    HavocScheduledMutator, NautilusRandomMutator, NautilusRecursionMutator, NautilusSpliceMutator,
};
use libafl::observers::StdMapObserver;
use libafl::schedulers::QueueScheduler;
use libafl::stages::StdMutationalStage;
use libafl::stages::generation::GenStage;
use libafl::state::{HasCorpus, HasExecutions, StdState};
use libafl::{Error, HasMetadata};
use libafl_bolts::rands::StdRand;
use libafl_bolts::tuples::{RefIndexable, tuple_list};
use libafl_bolts::current_nanos;

const MAP_SIZE: usize = 1 << 20; // must match harness.c
static mut MAP: [u8; MAP_SIZE] = [0; MAP_SIZE];

type Obs = (StdMapObserver<'static, u8, false>, ());

/// Runs the harness binary on the unparsed input and copies its edge map into `MAP`.
struct HarnessExecutor<'a> {
    ctx: &'a NautilusContext,
    harness: PathBuf,
    dir: PathBuf,
    obs: Obs,
    bytes: Vec<u8>,
    seen: Vec<bool>,
    edges: usize,
    log: Vec<String>,
    corpus: PathBuf,
}

impl<EM, S: HasExecutions, Z> Executor<EM, NautilusInput, S, Z> for HarnessExecutor<'_> {
    fn run_target(&mut self, _: &mut Z, state: &mut S, _: &mut EM, input: &NautilusInput) -> Result<ExitKind, Error> {
        *state.executions_mut() += 1;
        input.unparse(self.ctx, &mut self.bytes);
        let (sql, map) = (self.dir.join("input.sql"), self.dir.join("edges.map"));
        std::fs::write(&sql, &self.bytes)?;
        let _ = std::fs::remove_file(&map); // fresh map per execution
        let status = Command::new(&self.harness)
            .arg(&sql)
            .env("COV_MAP", &map)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()?;
        let cov = std::fs::read(&map).unwrap_or_default();
        let dst = unsafe { std::slice::from_raw_parts_mut(&raw mut MAP as *mut u8, MAP_SIZE) };
        dst.fill(0);
        let n = cov.len().min(MAP_SIZE);
        dst[..n].copy_from_slice(&cov[..n]);
        let before = self.edges;
        for (i, _) in dst.iter().enumerate().filter(|(_, b)| **b != 0) {
            if !std::mem::replace(&mut self.seen[i], true) {
                self.edges += 1;
            }
        }
        if self.edges > before {
            std::fs::write(self.corpus.join(self.log.len().to_string()), &self.bytes)?; // corpus for cov-analysis
        }
        self.log.push(format!("{},{}", self.log.len() + 1, self.edges));
        Ok(if status.signal().is_some() { ExitKind::Crash } else { ExitKind::Ok })
    }
}

impl HasObservers for HarnessExecutor<'_> {
    type Observers = Obs;
    fn observers(&self) -> RefIndexable<&Obs, Obs> {
        RefIndexable::from(&self.obs)
    }
    fn observers_mut(&mut self) -> RefIndexable<&mut Obs, Obs> {
        RefIndexable::from(&mut self.obs)
    }
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let [grammar, harness, out, n, corpus] = args.as_slice() else {
        eprintln!("usage: nautilus-grammarinator-coverage <nautilus-grammar.py> <harness> <out.csv> <executions> <corpus-dir>");
        std::process::exit(1);
    };
    let n: usize = n.parse().expect("executions must be a number");

    let context = NautilusContext::from_file(60, grammar).expect("failed to load nautilus grammar");
    let mut generator = NautilusGenerator::new(&context);

    std::fs::create_dir_all(corpus).unwrap();
    let observer = unsafe { StdMapObserver::from_mut_ptr("edges", &raw mut MAP as *mut u8, MAP_SIZE) };
    let mut feedback = feedback_or!(MaxMapFeedback::new(&observer), NautilusFeedback::new(&context));
    let mut objective = ConstFeedback::from(false);

    let dir = std::env::temp_dir().join(format!("nautilus-sqlite-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let mut executor = HarnessExecutor {
        ctx: &context,
        harness: PathBuf::from(harness),
        dir: dir.clone(),
        obs: tuple_list!(observer),
        bytes: Vec::new(),
        seen: vec![false; MAP_SIZE],
        edges: 0,
        log: Vec::new(),
        corpus: PathBuf::from(corpus),
    };

    let mut state = StdState::new(
        StdRand::with_seed(current_nanos()),
        InMemoryCorpus::<NautilusInput>::new(),
        InMemoryCorpus::<NautilusInput>::new(),
        &mut feedback,
        &mut objective,
    )
    .unwrap();
    state.add_metadata(NautilusChunksMetadata::new(dir.join("chunks").display().to_string()));

    let mut fuzzer = StdFuzzer::new(QueueScheduler::new(), feedback, objective);
    let mut mgr = libafl::events::NopEventManager::new();
    let mutator = HavocScheduledMutator::new(tuple_list!(
        NautilusRandomMutator::new(&context),
        NautilusRandomMutator::new(&context),
        NautilusRandomMutator::new(&context),
        NautilusRecursionMutator::new(&context),
        NautilusSpliceMutator::new(&context),
        NautilusSpliceMutator::new(&context),
    ));
    let mut stages = tuple_list!(
        GenStage::new(NautilusGenerator::new(&context)),
        StdMutationalStage::with_max_iterations(mutator, std::num::NonZeroUsize::new(8).unwrap()),
    );

    while (*state.executions() as usize) < n {
        if state.corpus().count() == 0 {
            let input = generator.generate(&mut state).unwrap();
            fuzzer.evaluate_input(&mut state, &mut executor, &mut mgr, &input).unwrap();
        } else {
            fuzzer.fuzz_one(&mut stages, &mut executor, &mut state, &mut mgr).unwrap();
        }
    }

    let mut f = std::fs::File::create(out).unwrap();
    writeln!(f, "step,edges").unwrap();
    for line in executor.log.iter().take(n) {
        writeln!(f, "{line}").unwrap();
    }
    let _ = std::fs::remove_dir_all(&dir);
}
