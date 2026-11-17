# Runs a `just` recipe from test/Justfile inside a self-contained environment.
#
#   docker build -t babel-tests .
#   docker run --rm babel-tests test_grammars_v4 3 10
#   docker run --rm -v "$PWD/test/out:/app/test/out" babel-tests nautilus 1000
#
# All arguments after the image name are passed to `just`.
FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim

ENV DEBIAN_FRONTEND=noninteractive \
    ANTLR4_TOOLS_ANTLR_VERSION=4.13.1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    CARGO_HOME=/usr/local/cargo \
    RUSTUP_HOME=/usr/local/rustup \
    PATH=/usr/local/cargo/bin:/app/.venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        default-jre-headless curl ca-certificates unzip git just \
        build-essential clang llvm pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Rust toolchain (for the LibAFL/Nautilus fuzzers)
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal

WORKDIR /app
COPY . .

# Install Python deps (also triggers the ANTLR generation build hook)
RUN uv sync --all-packages

WORKDIR /app/test
ENTRYPOINT ["just"]
CMD ["--list"]
