use std::io;

use crate::arg_parser::Commands;

pub fn handle_command(command: Commands) -> io::Result<()> {
    match command {
        Commands::Translate { from_file, from_encoder, to_file, to_decoder } => handle_translate(from_file, from_encoder, to_file, to_decoder),
    }
}

fn handle_translate(from_file: String, from_encoder: String, to_file: String, to_decoder: String) -> io::Result<()> {
    todo!()
}