use clap::Parser;

use crate::arg_parser::BabelCli;

mod arg_parser;
mod command_handler;

// babel-cli translate nautilus.py nautilus antlr4.g4 antlr4
// babel-cli <namespace> 
// babel-cli translate <source_file_name1, source_file_name2 (stable)> <encoder_to_use> <target_file_name> <decoder_to_use>
fn main() {
    let cli = BabelCli::parse();

    
}
