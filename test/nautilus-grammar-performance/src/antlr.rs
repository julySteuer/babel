use std::collections::{HashMap, HashSet};
use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};

use regex::Regex;

const ANTLR_VERSION: &str = "4.13.2";

pub fn parser_rule_names(sources: &[String]) -> Vec<String> {
    let comments = Regex::new(r"(?s)/\*.*?\*/|//[^\n]*").unwrap();
    let rule_head = Regex::new(r"(?m)^\s*([a-z][A-Za-z0-9_]*)\s*:").unwrap();

    let mut names = Vec::new();
    let mut seen = HashSet::new();
    for source in sources {
        let cleaned = comments.replace_all(source, "");
        for capture in rule_head.captures_iter(&cleaned) {
            let name = capture[1].to_string();
            if seen.insert(name.clone()) {
                names.push(name);
            }
        }
    }
    names
}

/// Named (non-fragment) lexer rules that can actually surface as a token in the
/// stream, i.e. not `fragment` rules and not `-> skip`/`-> channel(HIDDEN)` rules.
pub fn lexer_rule_names(sources: &[String]) -> Vec<String> {
    let comments = Regex::new(r"(?s)/\*.*?\*/|//[^\n]*").unwrap();
    let rule = Regex::new(r"(?ms)^[ \t]*(fragment\s+)?([A-Z][A-Za-z0-9_]*)\s*:(.*?);").unwrap();

    let mut names = Vec::new();
    let mut seen = HashSet::new();
    for source in sources {
        let cleaned = comments.replace_all(source, "");
        for capture in rule.captures_iter(&cleaned) {
            if capture.get(1).is_some() {
                continue;
            }
            let body = &capture[3];
            if body.contains("skip") && body.contains("->") {
                continue;
            }
            if body.contains("channel(HIDDEN)") {
                continue;
            }
            let name = capture[2].to_string();
            if seen.insert(name.clone()) {
                names.push(name);
            }
        }
    }
    names
}

/// Maps ANTLR token type numbers to the lexer rule that produces them, so that
/// tokens consumed while parsing can be attributed back to a lexer rule. Built
/// once per grammar via the real `antlr4` compiler, since `antlr4-parse`'s
/// interpreter only exposes numeric token types, not rule names.
pub struct TokenVocabulary {
    type_to_rule: HashMap<i64, String>,
}

impl TokenVocabulary {
    pub fn rule_for_type(&self, token_type: i64) -> Option<&str> {
        self.type_to_rule.get(&token_type).map(String::as_str)
    }
}

pub fn build_token_vocabulary(grammar_paths: &[PathBuf]) -> TokenVocabulary {
    let out_dir = std::env::temp_dir().join(format!(
        "nautilus-antlr-tokens-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    std::fs::create_dir_all(&out_dir).expect("failed to create antlr tokens scratch dir");

    let _ = Command::new("uv")
        .args(["run", "antlr4", "-v", ANTLR_VERSION, "-o"])
        .arg(&out_dir)
        .args(
            grammar_paths
                .iter()
                .map(|path| path.to_str().expect("non-utf8 grammar path")),
        )
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    let mut type_to_rule = HashMap::new();
    if let Ok(entries) = std::fs::read_dir(&out_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|ext| ext.to_str()) != Some("tokens") {
                continue;
            }
            let Ok(content) = std::fs::read_to_string(&path) else {
                continue;
            };
            for line in content.lines() {
                let Some((name, number)) = line.rsplit_once('=') else {
                    continue;
                };
                if name.starts_with('\'') || name.starts_with("T__") {
                    continue;
                }
                if let Ok(number) = number.trim().parse::<i64>() {
                    type_to_rule.entry(number).or_insert_with(|| name.to_string());
                }
            }
        }
    }

    let _ = std::fs::remove_dir_all(&out_dir);
    TokenVocabulary { type_to_rule }
}

pub fn trace_visited_rules(
    grammar_paths: &[PathBuf],
    start_rule: &str,
    input: &str,
    vocabulary: &TokenVocabulary,
) -> HashSet<String> {
    let mut child = Command::new("uv")
        .args(["run", "antlr4-parse", "-v", ANTLR_VERSION])
        .args(
            grammar_paths
                .iter()
                .map(|path| path.to_str().expect("non-utf8 grammar path")),
        )
        .args([start_rule, "-trace"])
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

    let token_type = Regex::new(r"<(-?\d+)>").unwrap();
    let mut visited = HashSet::new();

    for line in stdout.lines().chain(stderr.lines()) {
        let trimmed = line.trim();
        if let Some(rest) = trimmed.strip_prefix("enter")
            && rest.starts_with(char::is_whitespace)
            && let Some(name) = rest.split(',').next()
        {
            visited.insert(name.trim().to_string());
        } else if trimmed.starts_with("consume")
            && let Some(captures) = token_type.captures(trimmed)
            && let Ok(token_type) = captures[1].parse::<i64>()
            && let Some(rule_name) = vocabulary.rule_for_type(token_type)
        {
            visited.insert(rule_name.to_string());
        }
    }

    visited
}
