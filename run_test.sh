#!/usr/bin/env bash
# Usage: ./run_test.sh <just-recipe> [args...]
#   e.g. ./run_test.sh test_grammars_v4 3 10
set -euo pipefail
cd "$(dirname "$0")"

docker build -t babel-tests -f test.Dockerfile .
mkdir -p test/out
docker run --rm -v "$PWD/test/out:/app/test/out" babel-tests "$@"
