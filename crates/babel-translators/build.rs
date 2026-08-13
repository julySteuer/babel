use std::{
    fs::{self, create_dir_all},
    path::Path,
    process::Command,
};

const ANTLR_DOWNLOAD_URL: &str = "https://github.com/sdf-labs/antlr4/releases/download/dbt-antlr4-2.0.2/dbt-antlr4-2.0.2-complete.jar"; // Make version better
const ANTLR_BASE_PATH: &str = "antlr/";
const ANTLR_DOWNLOAD_NAME: &str = "antlr.jar";
const ANTLR_GRAMMAR_URL_BASE: &str =
    "https://raw.githubusercontent.com/antlr/grammars-v4/refs/heads/master/antlr/antlr4/";
const ANTLR_PARSER: &str = "antlr/ANTLRv4Parser.g4";
const ANTLR_LEXER: &str = "antlr/ANTLRv4Lexer.g4";
const GENERATED_ANTLR_PATH: &str = "src/antlr/generated";

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-changed=src/");
    let antlr_path = format!("{}{}", ANTLR_BASE_PATH, ANTLR_DOWNLOAD_NAME);
    if Path::new(&antlr_path).exists() {
        println!("cargo:warning=antlr/ found");
        return;
    }
    println!("cargo:warning=antlr/ not found, downloading...");
    create_dir_all(&ANTLR_BASE_PATH).unwrap();
    install_antlr_jar(&antlr_path);
    install_antlr_grammar();
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

fn copy_rust() {
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