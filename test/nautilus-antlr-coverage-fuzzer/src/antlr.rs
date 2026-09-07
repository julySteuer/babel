use std::collections::HashSet;
use std::io::Write;
use std::path::Path;
use std::process::{Command, Stdio};

use regex::Regex;

const ANTLR_VERSION: &str = "4.13.2";

pub fn parser_rule_names(source: &str) -> Vec<String> {
    let comments = Regex::new(r"(?s)/\*.*?\*/|//[^\n]*").unwrap();
    let cleaned = comments.replace_all(source, "");

    let rule_head = Regex::new(r"(?m)^\s*([a-z][A-Za-z0-9_]*)\s*:").unwrap();
    let mut names = Vec::new();
    let mut seen = HashSet::new();
    for capture in rule_head.captures_iter(&cleaned) {
        let name = capture[1].to_string();
        if seen.insert(name.clone()) {
            names.push(name);
        }
    }
    names
}

pub fn trace_visited_rules(grammar_path: &Path, start_rule: &str, input: &str) -> HashSet<String> {
    let mut child = Command::new("uv")
        .args([
            "run",
            "antlr4-parse",
            "-v",
            ANTLR_VERSION,
            grammar_path.to_str().expect("non-utf8 grammar path"),
            start_rule,
            "-trace",
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("failed to spawn `uv run antlr4-parse`");

    child
        .stdin
        .take()
        .expect("child stdin was not piped")
        .write_all(input.as_bytes())
        .expect("failed to write generated input to antlr4-parse");

    let output = child.wait_with_output().expect("antlr4-parse did not run to completion");
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);

    stdout
        .lines()
        .chain(stderr.lines())
        .filter_map(|line| line.trim().strip_prefix("enter"))
        .filter(|rest| rest.starts_with(char::is_whitespace))
        .filter_map(|rest| rest.split(',').next())
        .map(|name| name.trim().to_string())
        .collect()
}
