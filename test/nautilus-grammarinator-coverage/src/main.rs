//! LibAFL+Nautilus fuzzer for the instrumented sqlite harness.
//! usage: nautilus-grammarinator-coverage <nautilus-grammar.py> <harness> <out.csv> <limit> <corpus-dir>
//! <limit> is a number of executions (`90000`), a duration (`30s`, `15m`, `12h`, `3d`) or `inf` (run until Ctrl-C).
//! Writes `step,edges,seconds` (cumulative edge coverage; one row whenever it grows, plus a final row) to <out.csv>.
//! The file is flushed every few seconds, so it is usable while the fuzzer runs and after an interrupt.
use std::io::{BufWriter, Write};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};
use std::path::PathBuf;

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
use libafl::executors::forkserver::ForkserverExecutor;
use libafl::executors::StdChildArgs;
use libafl::inputs::nautilus::NautilusBytesConverter;
use libafl::observers::{HitcountsMapObserver, StdMapObserver};
use libafl::schedulers::QueueScheduler;
use libafl::stages::StdMutationalStage;
use libafl::stages::generation::GenStage;
use libafl::state::{HasCorpus, HasExecutions, StdState};
use libafl::{Error, HasMetadata};
use libafl_bolts::rands::StdRand;
use libafl_bolts::shmem::{ShMem, ShMemProvider};
#[cfg(target_os = "macos")]
use libafl_bolts::shmem::MmapShMemProvider;
#[cfg(not(target_os = "macos"))]
use libafl_bolts::shmem::UnixShMemProvider;
use libafl_bolts::{StdTargetArgs, ToSlice, ToSliceMut};
use libafl_bolts::tuples::{RefIndexable, tuple_list};
use libafl_bolts::current_nanos;

static STOP: AtomicBool = AtomicBool::new(false);
#[cfg(target_os = "macos")]
type ShProv = MmapShMemProvider;
#[cfg(not(target_os = "macos"))]
type ShProv = UnixShMemProvider;
const MAP_SIZE: usize = 1 << 16; // AFL++ default; the afl-clang-fast harness maps ~46k guards into it

/// Wraps the LibAFL forkserver executor (AFL++-style, like afl-fuzz does for Grammarinator) and, after each run,
/// tracks cumulative edge coverage from the shared map, saves corpus entries and writes the CSV.
struct Counting<'a, E> {
    ctx: &'a NautilusContext,
    inner: E,
    map: *const u8,
    bytes: Vec<u8>,
    seen: Vec<bool>,
    edges: usize,
    csv: BufWriter<std::fs::File>,
    start: Instant,
    last_flush: Instant,
    corpus: PathBuf,
}

impl<EM, S: HasExecutions, Z, E: Executor<EM, NautilusInput, S, Z>> Executor<EM, NautilusInput, S, Z> for Counting<'_, E> {
    fn run_target(&mut self, z: &mut Z, state: &mut S, mgr: &mut EM, input: &NautilusInput) -> Result<ExitKind, Error> {
        let kind = self.inner.run_target(z, state, mgr, input)?; // forkserver run; counts the execution
        let map = unsafe { std::slice::from_raw_parts(self.map, MAP_SIZE) };
        let before = self.edges;
        for (i, _) in map.iter().enumerate().filter(|(_, b)| **b != 0) {
            if !std::mem::replace(&mut self.seen[i], true) {
                self.edges += 1;
            }
        }
        let execs = *state.executions();
        if self.edges > before {
            self.bytes.clear();
            input.unparse(self.ctx, &mut self.bytes);
            std::fs::write(self.corpus.join((execs - 1).to_string()), &self.bytes)?; // corpus for cov-analysis
            writeln!(self.csv, "{},{},{:.1}", execs, self.edges, self.start.elapsed().as_secs_f64())?;
        }
        if self.last_flush.elapsed() > Duration::from_secs(5) {
            self.csv.flush()?;
            self.last_flush = Instant::now();
        }
        Ok(kind)
    }
}

impl<E: HasObservers> HasObservers for Counting<'_, E> {
    type Observers = E::Observers;
    fn observers(&self) -> RefIndexable<&Self::Observers, Self::Observers> {
        self.inner.observers()
    }
    fn observers_mut(&mut self) -> RefIndexable<&mut Self::Observers, Self::Observers> {
        self.inner.observers_mut()
    }
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let [grammar, harness, out, limit, corpus] = args.as_slice() else {
        eprintln!("usage: nautilus-grammarinator-coverage <nautilus-grammar.py> <harness> <out.csv> <executions|30s|15m|12h|3d|inf> <corpus-dir>");
        std::process::exit(1);
    };
    let (max_execs, max_time) = parse_limit(limit);
    ctrlc::set_handler(|| STOP.store(true, Ordering::SeqCst)).expect("failed to install Ctrl-C handler");

    let context = NautilusContext::from_file(60, grammar).expect("failed to load nautilus grammar");
    let mut generator = NautilusGenerator::new(&context);

    std::fs::create_dir_all(corpus).unwrap();
    let mut shmem_provider = ShProv::new().unwrap();
    let mut shmem = shmem_provider.new_shmem(MAP_SIZE).unwrap();
    unsafe {
        shmem.write_to_env("__AFL_SHM_ID").unwrap(); // SysV id on Linux (what AFL++'s runtime reads there); LibAFL insists on it
        // macOS: AFL++ uses shm_open, and mmap shmems are identified by an open file descriptor, which AFL++'s runtime
        // attaches to via __AFL_SHM_FD. Pass an inheritable duplicate above the forkserver pipes (198/199).
        #[cfg(target_os = "macos")]
        {
            let fd: i32 = shmem.id().to_string().parse().expect("mmap shmem id is an fd");
            let dup = libc::fcntl(fd, libc::F_DUPFD, 200);
            assert!(dup >= 200, "could not duplicate the shmem fd");
            std::env::set_var("__AFL_SHM_FD", dup.to_string());
        }
    }
    let map_ptr = ToSlice::to_slice(&shmem).as_ptr();
    let observer = HitcountsMapObserver::new(unsafe { StdMapObserver::new("edges", ToSliceMut::to_slice_mut(&mut shmem)) });
    let mut feedback = feedback_or!(MaxMapFeedback::new(&observer), NautilusFeedback::new(&context));
    let mut objective = ConstFeedback::from(false);

    let dir = std::env::temp_dir().join(format!("nautilus-sqlite-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let forkserver = ForkserverExecutor::builder()
        .program(harness)
        .coverage_map_size(MAP_SIZE)
        .timeout(Duration::from_secs(2))
        .arg_input_file_std()
        .build(tuple_list!(observer))
        .expect("failed to start the forkserver (is <harness> built with afl-clang-fast? see `just harness-afl`)");
    let mut executor = Counting {
        ctx: &context,
        inner: forkserver,
        map: map_ptr,
        bytes: Vec::new(),
        seen: vec![false; MAP_SIZE],
        edges: 0,
        csv: {
            let mut w = BufWriter::new(std::fs::File::create(out).unwrap());
            writeln!(w, "step,edges,seconds").unwrap();
            w
        },
        start: Instant::now(),
        last_flush: Instant::now(),
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

    let mut fuzzer = StdFuzzer::builder()
        .scheduler(QueueScheduler::new())
        .feedback(feedback)
        .objective(objective)
        .target_bytes_converter(NautilusBytesConverter::new(&context))
        .build();
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

    let start = Instant::now();
    while !STOP.load(Ordering::SeqCst)
        && (*state.executions() as usize) < max_execs
        && start.elapsed() < max_time
    {
        if state.corpus().count() == 0 {
            let input = generator.generate(&mut state).unwrap();
            fuzzer.evaluate_input(&mut state, &mut executor, &mut mgr, &input).unwrap();
        } else {
            fuzzer.fuzz_one(&mut stages, &mut executor, &mut state, &mut mgr).unwrap();
        }
    }

    // final row so the curve extends to the end of the run
    writeln!(executor.csv, "{},{},{:.1}", state.executions(), executor.edges, executor.start.elapsed().as_secs_f64()).unwrap();
    executor.csv.flush().unwrap();
    let _ = std::fs::remove_dir_all(&dir);
}

/// `90000` -> executions, `30s|15m|12h|3d` -> duration, `inf` -> unbounded.
fn parse_limit(s: &str) -> (usize, Duration) {
    if s == "inf" {
        return (usize::MAX, Duration::MAX);
    }
    let (num, mult) = match s.chars().last() {
        Some('s') => (&s[..s.len() - 1], 1),
        Some('m') => (&s[..s.len() - 1], 60),
        Some('h') => (&s[..s.len() - 1], 3600),
        Some('d') => (&s[..s.len() - 1], 86400),
        _ => return (s.parse().expect("limit must be a number, <n>s|m|h|d or inf"), Duration::MAX),
    };
    (usize::MAX, Duration::from_secs(num.parse::<u64>().expect("bad duration") * mult))
}
