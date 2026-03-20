#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$ROOT_DIR/bin"
mkdir -p "$OUT_DIR"

g++ -O2 -std=c++17 "$ROOT_DIR/cpp_solver.cpp" -o "$OUT_DIR/path_solver"
echo "Built C++ solver at $OUT_DIR/path_solver"
