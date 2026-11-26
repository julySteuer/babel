use std::collections::{HashMap, HashSet};
use std::io::{Read, Write};
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

use regex::Regex;

const ANTLR_VERSION: &str = "4.13.2";

/// A command that runs the antlr4-tools executable `tool` (`antlr4` or `antlr4-parse`).
///
/// Calls the executable directly when it is on PATH (the project's venv, which `uv run` puts on PATH, or the
/// docker image). `uv run <tool>` costs about a second of CPU per call and, with many calls in parallel on a big
/// machine, several seconds each (uv syncs and locks the environment every time) - one call is made per seed.
/// Falls back to `uv run` if the executable is not on PATH.
fn antlr_tool_command(tool: &str) -> Command {
    let on_path = std::env::var_os("PATH")
        .map(|paths| std::env::split_paths(&paths).any(|dir| dir.join(tool).is_file()))
        .unwrap_or(false);
    if on_path {
        Command::new(tool)
    } else {
        let mut command = Command::new("uv");
        command.args(["run", tool]);
        command
    }
}

/// Comments, plus the string literals and char sets that must survive intact so that `'//'` or `[/]` are not
/// read as a comment.
fn comment_pattern() -> Regex {
    Regex::new(r"(?s)'(?:\\.|[^'\\\n])*'|\[(?:\\.|[^\]\\\n])*\]|/\*.*?\*/|//[^\n]*").unwrap()
}

/// What is left of a grammar once only its rule structure remains: no comments, string literals and char sets
/// (and rule arguments) reduced to `''`, and no `{...}` blocks (actions, @members, options hold target-language
/// code, not rules). Mirrors `first_parser_rule` of nautilus-antlr-test.
fn clean_grammar(source: &str) -> String {
    let comments = comment_pattern();
    let without_comments = comments.replace_all(source, |c: &regex::Captures| {
        if c[0].starts_with('\'') || c[0].starts_with('[') { c[0].to_string() } else { String::new() }
    });
    let masked = Regex::new(r"'(?:\\.|[^'\\\n])*'|\[(?:\\.|[^\]\\\n])*\]")
        .unwrap()
        .replace_all(&without_comments, "''")
        .into_owned();
    let (mut out, mut depth) = (String::with_capacity(masked.len()), 0usize);
    for c in masked.chars() {
        match c {
            '{' => depth += 1,
            '}' if depth > 0 => depth -= 1,
            _ if depth == 0 => out.push(c),
            _ => {}
        }
    }
    out
}

/// `name`, optional `[args]`, `returns [..]`, `locals [..]` (all `''` after cleaning), then the `:`.
const PARSER_RULE_HEAD: &str =
    r"(?m)^[ \t]*([a-z][A-Za-z0-9_]*)(?:\s|'')*(?:(?:returns|locals|throws)(?:\s|'')*(?:\w+(?:\s*,\s*\w+)*)?(?:\s|'')*)*:";

pub fn parser_rule_names(sources: &[String]) -> Vec<String> {
    let rule_head = Regex::new(PARSER_RULE_HEAD).unwrap();

    let mut names = Vec::new();
    let mut seen = HashSet::new();
    for source in sources {
        let cleaned = clean_grammar(source);
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
    let rule = Regex::new(r"(?ms)^[ \t]*(fragment\s+)?([A-Z][A-Za-z0-9_]*)\s*:(.*?);").unwrap();

    let mut names = Vec::new();
    let mut seen = HashSet::new();
    for source in sources {
        let cleaned = clean_grammar(source);
        for capture in rule.captures_iter(&cleaned) {
            if capture.get(1).is_some() {
                continue;
            }
            let body = &capture[3];
            if body.contains("skip") && body.contains("->") {
                continue;
            }
            if Regex::new(r"channel\s*\(\s*HIDDEN\s*\)").unwrap().is_match(body) {
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
    pub fn len(&self) -> usize {
        self.type_to_rule.len()
    }

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

    let _ = antlr_tool_command("antlr4")
        .args(["-v", ANTLR_VERSION, "-o"])
        .arg(&out_dir)
        // absolute paths: with a relative one antlr4 writes into a subdirectory of the output dir
        .args(grammar_paths.iter().map(|path| {
            std::fs::canonicalize(path)
                .unwrap_or_else(|_| path.clone())
                .into_os_string()
        }))
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

/// What one `antlr4-parse` run of a seed showed.
pub struct Trace {
    pub visited: HashSet<String>,
    /// ANTLR printed a syntax error (`line L:C ...`). Trailing input after the start rule is not an error.
    pub had_error: bool,
    /// antlr4-parse was killed after `timeout`; `visited` then holds what it had traced so far.
    pub timed_out: bool,
}

/// Kills `child` and everything it started (`uv` runs `java` as a child of its own).
fn kill_process_group(child: &mut Child) {
    let _ = Command::new("kill")
        .args(["-s", "KILL", "--", &format!("-{}", child.id())])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
    let _ = child.kill();
}

pub fn trace_rules(
    grammar_paths: &[PathBuf],
    start_rule: &str,
    input: &str,
    vocabulary: &TokenVocabulary,
    timeout: Duration,
) -> Trace {
    let mut child = antlr_tool_command("antlr4-parse")
        .args(["-v", ANTLR_VERSION])
        .args(
            grammar_paths
                .iter()
                .map(|path| path.to_str().expect("non-utf8 grammar path")),
        )
        .args([start_rule, "-trace"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .process_group(0) // its own group, so that a timeout can kill uv and java together
        .spawn()
        .expect("failed to spawn `uv run antlr4-parse`");

    // Feed and drain on their own threads: the child must never block on a full pipe while we wait for it.
    let mut stdin = child.stdin.take().expect("child stdin was not piped");
    let bytes = input.as_bytes().to_vec();
    let writer = std::thread::spawn(move || {
        let _ = stdin.write_all(&bytes);
    });
    let drain = |mut pipe: Box<dyn Read + Send>| {
        std::thread::spawn(move || {
            let mut buffer = Vec::new();
            let _ = pipe.read_to_end(&mut buffer);
            buffer
        })
    };
    let stdout_reader = drain(Box::new(child.stdout.take().expect("child stdout was not piped")));
    let stderr_reader = drain(Box::new(child.stderr.take().expect("child stderr was not piped")));

    let deadline = Instant::now() + timeout;
    let mut timed_out = false;
    loop {
        match child.try_wait() {
            Ok(Some(_)) | Err(_) => break,
            Ok(None) if Instant::now() >= deadline => {
                timed_out = true;
                kill_process_group(&mut child);
                let _ = child.wait();
                break;
            }
            Ok(None) => std::thread::sleep(Duration::from_millis(10)),
        }
    }
    let _ = writer.join();
    let stdout = String::from_utf8_lossy(&stdout_reader.join().unwrap_or_default()).into_owned();
    let stderr = String::from_utf8_lossy(&stderr_reader.join().unwrap_or_default()).into_owned();

    let token_type = Regex::new(r"<(-?\d+)>").unwrap();
    let syntax_error = Regex::new(r"^line \d+:\d+ ").unwrap();
    let mut visited = HashSet::new();
    let mut had_error = false;

    for line in stdout.lines().chain(stderr.lines()) {
        let trimmed = line.trim();
        if syntax_error.is_match(trimmed) {
            had_error = true;
        }
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

    Trace { visited, had_error, timed_out }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rules(source: &str) -> Vec<String> {
        parser_rule_names(&[source.to_string()])
    }

    #[test]
    fn rules_with_arguments_and_returns_are_parser_rules() {
        let g = "grammar G;\nexpr[int p] returns [int v] locals [int x]\n  : A ;\nother : A ;\nA : 'a' ;\n";
        assert_eq!(rules(g), vec!["expr", "other"]);
    }

    #[test]
    fn code_blocks_and_comments_hold_no_rules() {
        let g = "grammar G;\n@members {\n  if x:\n    pass\n}\n// fake : rule\nstart : A { key: value } B ;\nA : 'a' ;\n";
        assert_eq!(rules(g), vec!["start"]);
    }

    #[test]
    fn a_double_slash_literal_is_not_a_comment_and_hidden_rules_are_excluded() {
        let g = "lexer grammar L;\nIDENT : [a-z]+ ;\nLINE_COMMENT\n  : '//' ~[\\r\\n]* -> channel (HIDDEN)\n  ;\nSEMI : ';' -> skip ;\n";
        assert_eq!(lexer_rule_names(&[g.to_string()]), vec!["IDENT"]);
    }
}
