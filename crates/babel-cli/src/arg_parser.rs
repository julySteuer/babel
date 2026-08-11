use clap::{Parser, Subcommand};

#[derive(Parser)]
pub struct BabelCli {
    #[command(subcommand)]
    command: Commands
}

#[derive(Subcommand)]
pub enum Commands {
    Translate { from_file: String, from_encoder: String, to_file: String, to_decoder: String },
    // More to come like merging
}