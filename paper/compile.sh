#!/usr/bin/env bash
# Compila el paper APA7 desde este directorio (paper/).
set -euo pipefail
cd "$(dirname "$0")"
latexmk -pdf -interaction=nonstopmode paper_final_APA7.tex
echo "OK → $(pwd)/paper_final_APA7.pdf"
