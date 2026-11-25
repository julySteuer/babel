# Self-contained environment for the Nautilus vs. Grammarinator(AFL++) sqlite fuzzing comparison.
# Based on the official AFL++ image (AFL++ 5.04a, clang, cmake, gnuplot already built), so AFL++ is not compiled here.
# Build context is the repository root (it needs the babel packages):
#
#   podman build -f test/nautilus-grammarinator-coverage/Dockerfile -t babel-fuzz .
#   podman run --rm -v "$PWD/test/nautilus-grammarinator-coverage/out-docker:/app/test/nautilus-grammarinator-coverage/out" \
#       babel-fuzz forever 20m cov
#
# Arguments after the image name are `just` recipes: `forever 20m` fuzzes both for 20 minutes, `cov` makes the cov-analysis reports.
FROM docker.io/aflplusplus/aflplusplus:latest

ENV DEBIAN_FRONTEND=noninteractive \
    ANTLR4_TOOLS_ANTLR_VERSION=4.13.1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    CARGO_HOME=/usr/local/cargo \
    RUSTUP_HOME=/usr/local/rustup \
    AFL_DIR=/AFLplusplus \
    PATH=/usr/local/cargo/bin:/root/.local/bin:/app/.venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        default-jre-headless curl ca-certificates unzip git findutils gawk pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/* \
    && for t in llvm-cov llvm-profdata llvm-config; do ln -sf /usr/bin/$t-20 /usr/local/bin/$t; done

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Rust toolchain (LibAFL/Nautilus fuzzer), `just`, and conan (Grammarinator's C++ backend dependencies)
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal && uv tool install rust-just && uv tool install conan

WORKDIR /app
COPY . .
RUN uv sync --all-packages

# Grammarinator's C++ backend needs C++20 <format>: the image's default g++-11 lacks it, clang 20 has it
ENV CC=clang CXX=clang++

# Build everything up front (sqlite harnesses, Grammarinator C++ mutator, Nautilus fuzzer, llvm-cov build) so a run only fuzzes
WORKDIR /app/test/nautilus-grammarinator-coverage
RUN just build covbin

# The Nautilus fuzzer links libpython of the uv-managed interpreter behind /app/.venv; make the loader find it
RUN echo "$(dirname "$(dirname "$(readlink -f /app/.venv/bin/python3)")")/lib" > /etc/ld.so.conf.d/uv-python.conf && ldconfig \
    && ldd target/release/nautilus-grammarinator-coverage | grep -q "libpython.*=> /" 

ENTRYPOINT ["just"]
CMD ["--list"]
