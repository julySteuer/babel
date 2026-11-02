use std::time::Duration;

/// Conditions that end the fuzz loop. Every unset condition is ignored; the loop
/// ends as soon as any set one is met (or the user quits the TUI).
#[derive(Default, Clone)]
pub struct StopConditions {
    /// Maximum number of generated inputs (`None` = unlimited).
    pub max_iterations: Option<usize>,
    /// Wall-clock budget.
    pub timeout: Option<Duration>,
    /// Stop once this fraction (0.0..=1.0) of all rules was visited.
    pub target_coverage: Option<f64>,
    /// Stop after this many consecutive inputs without a newly visited rule.
    pub stall_iterations: Option<usize>,
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum StopReason {
    MaxIterations,
    Timeout,
    TargetCoverage,
    Stalled,
    UserQuit,
}

impl StopReason {
    pub fn describe(self) -> &'static str {
        match self {
            StopReason::MaxIterations => "iteration limit reached",
            StopReason::Timeout => "timeout reached",
            StopReason::TargetCoverage => "target coverage reached",
            StopReason::Stalled => "no new rule for too long (stalled)",
            StopReason::UserQuit => "quit by user",
        }
    }
}

/// Live state of the fuzz loop, shared between the loop and the monitor.
pub struct FuzzStats {
    pub total_rules: usize,
    pub iterations: usize,
    pub visited: usize,
    pub elapsed: Duration,
    /// Iteration at which the most recent new rule was found.
    pub last_new_iteration: usize,
    /// `(elapsed seconds, visited rules)`, one point per coverage increase plus the latest state.
    pub coverage_history: Vec<(f64, f64)>,
    /// Executions per second in consecutive sampling windows.
    pub rate_history: Vec<u64>,
    /// Newly found rules, in discovery order.
    pub discovered: Vec<(usize, String)>,
    window_start: Duration,
    window_iterations: usize,
}

const RATE_WINDOW: Duration = Duration::from_millis(500);

impl FuzzStats {
    pub fn new(total_rules: usize) -> Self {
        Self {
            total_rules,
            iterations: 0,
            visited: 0,
            elapsed: Duration::ZERO,
            last_new_iteration: 0,
            coverage_history: vec![(0.0, 0.0)],
            rate_history: Vec::new(),
            discovered: Vec::new(),
            window_start: Duration::ZERO,
            window_iterations: 0,
        }
    }

    pub fn coverage(&self) -> f64 {
        if self.total_rules == 0 {
            0.0
        } else {
            self.visited as f64 / self.total_rules as f64
        }
    }

    pub fn iterations_per_sec(&self) -> f64 {
        let secs = self.elapsed.as_secs_f64();
        if secs > 0.0 {
            self.iterations as f64 / secs
        } else {
            0.0
        }
    }

    pub fn since_last_new(&self) -> usize {
        self.iterations - self.last_new_iteration
    }

    /// Record `executions` target runs finished since the last call. `new_rules` are the
    /// rules first seen in them.
    pub fn record(&mut self, elapsed: Duration, executions: usize, new_rules: &[String]) {
        self.iterations += executions;
        self.window_iterations += executions;
        self.elapsed = elapsed;

        if !new_rules.is_empty() {
            self.visited += new_rules.len();
            self.last_new_iteration = self.iterations;
            let t = elapsed.as_secs_f64();
            // Hold the previous value up to now so the plot shows a step, not a slope.
            let previous = self.coverage_history.last().map_or(0.0, |p| p.1);
            self.coverage_history.push((t, previous));
            self.coverage_history.push((t, self.visited as f64));
            for rule in new_rules {
                self.discovered.push((self.iterations, rule.clone()));
            }
        }

        let window = elapsed - self.window_start;
        if window >= RATE_WINDOW {
            self.rate_history
                .push((self.window_iterations as f64 / window.as_secs_f64()).round() as u64);
            self.window_start = elapsed;
            self.window_iterations = 0;
        }
    }

    /// Extend the coverage plot to "now" so it does not end at the last discovery.
    pub fn coverage_series(&self) -> Vec<(f64, f64)> {
        let mut series = self.coverage_history.clone();
        series.push((self.elapsed.as_secs_f64(), self.visited as f64));
        series
    }

    pub fn check_stop(&self, conditions: &StopConditions) -> Option<StopReason> {
        if conditions
            .max_iterations
            .is_some_and(|max| self.iterations >= max)
        {
            return Some(StopReason::MaxIterations);
        }
        if conditions
            .timeout
            .is_some_and(|limit| self.elapsed >= limit)
        {
            return Some(StopReason::Timeout);
        }
        if conditions
            .target_coverage
            .is_some_and(|target| self.coverage() >= target)
        {
            return Some(StopReason::TargetCoverage);
        }
        if conditions
            .stall_iterations
            .is_some_and(|limit| self.since_last_new() >= limit)
        {
            return Some(StopReason::Stalled);
        }
        None
    }
}
