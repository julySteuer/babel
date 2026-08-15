use std::{
    fs::{self, create_dir_all},
    path::Path,
    process::Command,
};

const ANTLR_DOWNLOAD_URL: &str = "https://github.com/rrevenantt/antlr4rust/releases/download/antlr4-4.8-2-Rust0.3.0-beta/antlr4-4.8-2-SNAPSHOT-complete.jar";
const ANTLR_BASE_PATH: &str = "antlr/";
const ANTLR_DOWNLOAD_NAME: &str = "antlr.jar";
const ANTLR_GRAMMAR_URL_BASE: &str =
    "https://raw.githubusercontent.com/antlr/grammars-v4/refs/heads/master/antlr/antlr4/";
const ANTLR_PARSER: &str = "antlr/ANTLRv4Parser.g4";
const ANTLR_LEXER: &str = "antlr/ANTLRv4Lexer.g4";
const GENERATED_ANTLR_PATH: &str = "src/antlr/generated";
const LEXER_ADAPTOR_PATH: &str = "lexer_adaptor.rs";
const LEXER_GRAMMAR_DECL: &str = "lexer grammar ANTLRv4Lexer;";

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-changed=src/");
    println!("cargo:rerun-if-changed={LEXER_ADAPTOR_PATH}");
    let antlr_path = format!("{}{}", ANTLR_BASE_PATH, ANTLR_DOWNLOAD_NAME);
    if Path::new(&antlr_path).exists() {
        println!("cargo:warning=antlr/ found");
        return;
    }
    println!("cargo:warning=antlr/ not found, downloading...");
    create_dir_all(&ANTLR_BASE_PATH).unwrap();
    install_antlr_jar(&antlr_path);
    install_antlr_grammar();
    inject_lexer_adaptor();
    Command::new("java")
        .args([
            "-jar",
            &antlr_path,
            "-Dlanguage=Rust",
            "-visitor",
            "-Xexact-output-dir",
            ANTLR_LEXER,
            "-o",
            "antlr/generated",
        ])
        .status()
        .unwrap();

    Command::new("java")
        .args([
            "-jar",
            &antlr_path,
            "-Dlanguage=Rust",
            "-visitor",
            "-Xexact-output-dir",
            ANTLR_PARSER,
            "-lib",
            "antlr/generated",
            "-o",
            "antlr/generated",
        ])
        .status()
        .unwrap();
    // move generted rust
    copy_rust();
    generate_mod_rs();
}

fn install_from_url(url: &str, path: &str) {
    let res = Command::new("wget")
        .arg("-O")
        .arg(path)
        .arg(url)
        .status()
        .unwrap();
    println!("cargo:warning={}", res);
}

fn install_antlr_grammar() {
    let antlr_lexer = format!("{}{}", ANTLR_GRAMMAR_URL_BASE, "ANTLRv4Lexer.g4");
    let antlr_parser = format!("{}{}", ANTLR_GRAMMAR_URL_BASE, "ANTLRv4Parser.g4");
    install_from_url(&antlr_lexer, ANTLR_LEXER);
    install_from_url(&antlr_parser, ANTLR_PARSER);
}

fn install_antlr_jar(antlr_path: &str) {
    install_from_url(ANTLR_DOWNLOAD_URL, antlr_path);
}

fn inject_lexer_adaptor() {
    let adaptor_src = fs::read_to_string(LEXER_ADAPTOR_PATH).unwrap();
    let fields = read_adaptor_section(&adaptor_src, "fields");
    let init = read_adaptor_section(&adaptor_src, "init");
    let members = read_adaptor_section(&adaptor_src, "members");
    let extend = read_adaptor_section(&adaptor_src, "extend");

    let named_actions = format!(
        "\n@fields {{\n{fields}\n}}\n@init {{\n{init}\n}}\n@members {{\n{members}\n}}\n@extend {{\n{extend}\n}}\n"
    );

    let contents = fs::read_to_string(ANTLR_LEXER).unwrap();
    let contents = contents.replace(
        LEXER_GRAMMAR_DECL,
        &format!("{LEXER_GRAMMAR_DECL}\n{named_actions}"),
    );
    let contents = contents
        .replace(
            "{ this.handleBeginArgument(); }",
            "{ if recog.in_lexer_rule() { recog.push_mode(LexerCharSet); recog.more(); } else { recog.push_mode(Argument); } }",
        )
        .replace(
            "{ this.handleEndArgument(); }",
            "{ recog.pop_mode(); if !recog.mode_stack.is_empty() { recog.set_type(ARGUMENT_CONTENT); } }",
        );
    fs::write(ANTLR_LEXER, contents).unwrap();
}

fn read_adaptor_section(source: &str, name: &str) -> String {
    let marker = format!("//>>{name}\n");
    let start = source
        .find(&marker)
        .unwrap_or_else(|| panic!("lexer_adaptor.rs: missing //>>{name} section"))
        + marker.len();
    let rest = &source[start..];
    let end = rest.find("//>>").unwrap_or(rest.len());
    rest[..end].trim().to_string()
}

fn copy_rust() {
    let _ = fs::remove_dir_all(GENERATED_ANTLR_PATH);
    create_dir_all(GENERATED_ANTLR_PATH).unwrap();
    fs::read_dir("antlr/generated")
        .unwrap()
        .filter_map(Result::ok)
        .map(|f| f.path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "rs"))
        .for_each(|path| {
            let dest = Path::new(GENERATED_ANTLR_PATH).join(path.file_name().unwrap());
            fs::rename(&path, dest).unwrap(); // Only works on the same drive but ez
        });
}

fn generate_mod_rs() {
    let mut modules: Vec<_> = fs::read_dir(GENERATED_ANTLR_PATH)
        .unwrap()
        .filter_map(Result::ok)
        .map(|f| f.path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "rs"))
        .filter_map(|path| path.file_stem().map(|s| s.to_str().unwrap().to_string()))
        .filter(|stem| stem != "mod")
        .collect();
    modules.sort();

    let contents: String = modules
        .iter()
        .map(|stem| format!("pub mod {stem};\n"))
        .collect();

    fs::write(format!("{GENERATED_ANTLR_PATH}/mod.rs"), contents).unwrap();
}