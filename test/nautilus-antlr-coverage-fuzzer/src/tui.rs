use std::io::{Stdout, stdout};
use std::time::Duration;

use crossterm::event::{self, Event, KeyCode, KeyModifiers};
use crossterm::execute;
use crossterm::terminal::{
    EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode,
};
use ratatui::Terminal;
use ratatui::backend::CrosstermBackend;
use ratatui::layout::{Constraint, Direction, Layout};
use ratatui::style::{Color, Modifier, Style};
use ratatui::symbols;
use ratatui::text::{Line, Span};
use ratatui::widgets::{
    Axis, Block, Chart, Dataset, Gauge, GraphType, List, ListItem, Paragraph, Sparkline,
};

use crate::stats::{FuzzStats, StopConditions};

pub struct Tui {
    terminal: Terminal<CrosstermBackend<Stdout>>,
}

impl Tui {
    pub fn start() -> std::io::Result<Self> {
        enable_raw_mode()?;
        execute!(stdout(), EnterAlternateScreen)?;
        // Restore the terminal even if the fuzzer panics, otherwise the shell is left raw.
        let default_hook = std::panic::take_hook();
        std::panic::set_hook(Box::new(move |info| {
            let _ = restore();
            default_hook(info);
        }));
        Ok(Self {
            terminal: Terminal::new(CrosstermBackend::new(stdout()))?,
        })
    }

    /// Returns true if the user asked to quit (`q`, `Esc` or `Ctrl-C`).
    pub fn quit_requested() -> bool {
        while event::poll(Duration::ZERO).unwrap_or(false) {
            if let Ok(Event::Key(key)) = event::read() {
                let ctrl_c =
                    key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL);
                if ctrl_c || matches!(key.code, KeyCode::Char('q') | KeyCode::Esc) {
                    return true;
                }
            }
        }
        false
    }

    pub fn draw(&mut self, stats: &FuzzStats, stop: &StopConditions, finished: Option<&str>) {
        let _ = self
            .terminal
            .draw(|frame| render(frame, stats, stop, finished));
    }

    pub fn wait_for_key(&mut self) {
        while !matches!(event::read(), Ok(Event::Key(_)) | Err(_)) {}
    }
}

impl Drop for Tui {
    fn drop(&mut self) {
        let _ = restore();
    }
}

fn restore() -> std::io::Result<()> {
    disable_raw_mode()?;
    execute!(stdout(), LeaveAlternateScreen)
}

fn render(
    frame: &mut ratatui::Frame,
    stats: &FuzzStats,
    stop: &StopConditions,
    finished: Option<&str>,
) {
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Length(6),
            Constraint::Min(8),
            Constraint::Length(1),
        ])
        .split(frame.area());

    let gauge = Gauge::default()
        .block(Block::bordered().title(" rule coverage "))
        .gauge_style(Style::default().fg(Color::Green))
        .ratio(stats.coverage().clamp(0.0, 1.0))
        .label(format!(
            "{}/{} ({:.1}%)",
            stats.visited,
            stats.total_rules,
            stats.coverage() * 100.0
        ));
    frame.render_widget(gauge, rows[0]);

    let top = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(40), Constraint::Percentage(60)])
        .split(rows[1]);
    frame.render_widget(stats_panel(stats, stop, finished), top[0]);

    let rates: &[u64] = &stats.rate_history;
    let visible = rates
        .len()
        .saturating_sub(top[1].width.saturating_sub(2) as usize);
    let sparkline = Sparkline::default()
        .block(Block::bordered().title(format!(
            " executions/s (now {}) ",
            rates.last().copied().unwrap_or(0)
        )))
        .style(Style::default().fg(Color::Cyan))
        .data(&rates[visible..]);
    frame.render_widget(sparkline, top[1]);

    let bottom = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(65), Constraint::Percentage(35)])
        .split(rows[2]);

    let series = stats.coverage_series();
    let x_max = stats.elapsed.as_secs_f64().max(1.0);
    let y_max = (stats.total_rules as f64).max(1.0);
    let dataset = Dataset::default()
        .marker(symbols::Marker::Braille)
        .graph_type(GraphType::Line)
        .style(Style::default().fg(Color::Green))
        .data(&series);
    let chart = Chart::new(vec![dataset])
        .block(Block::bordered().title(" visited rules over time "))
        .x_axis(
            Axis::default()
                .title("s")
                .bounds([0.0, x_max])
                .labels(vec![Span::raw("0"), Span::raw(format!("{x_max:.0}"))]),
        )
        .y_axis(
            Axis::default()
                .bounds([0.0, y_max])
                .labels(vec![Span::raw("0"), Span::raw(format!("{y_max:.0}"))]),
        );
    frame.render_widget(chart, bottom[0]);

    let capacity = bottom[1].height.saturating_sub(2) as usize;
    let items: Vec<ListItem> = stats
        .discovered
        .iter()
        .rev()
        .take(capacity)
        .map(|(iteration, rule)| ListItem::new(format!("#{iteration:<7} {rule}")))
        .collect();
    frame.render_widget(
        List::new(items).block(Block::bordered().title(" newest rules ")),
        bottom[1],
    );

    let hint = if finished.is_some() {
        "press any key to exit"
    } else {
        "q / Esc: stop fuzzing"
    };
    frame.render_widget(
        Paragraph::new(hint).style(Style::default().fg(Color::DarkGray)),
        rows[3],
    );
}

fn stats_panel(
    stats: &FuzzStats,
    stop: &StopConditions,
    finished: Option<&str>,
) -> Paragraph<'static> {
    let secs = stats.elapsed.as_secs();
    let limit = |value: Option<String>| value.map_or(String::new(), |v| format!(" / {v}"));
    let status = match finished {
        Some(reason) => Span::styled(
            format!("finished: {reason}"),
            Style::default().fg(Color::Yellow),
        ),
        None => Span::styled(
            "running",
            Style::default()
                .fg(Color::Green)
                .add_modifier(Modifier::BOLD),
        ),
    };
    let lines = vec![
        Line::from(status),
        Line::from(format!(
            "elapsed     {:02}:{:02}:{:02}{}",
            secs / 3600,
            secs / 60 % 60,
            secs % 60,
            limit(stop.timeout.map(|t| format!("{}s", t.as_secs())))
        )),
        Line::from(format!(
            "iterations  {}{}",
            stats.iterations,
            limit(stop.max_iterations.map(|n| n.to_string()))
        )),
        Line::from(format!("avg exec/s  {:.1}", stats.iterations_per_sec())),
        Line::from(format!(
            "since new   {}{}",
            stats.since_last_new(),
            limit(stop.stall_iterations.map(|n| n.to_string()))
        )),
    ];
    Paragraph::new(lines).block(Block::bordered().title(" state "))
}
