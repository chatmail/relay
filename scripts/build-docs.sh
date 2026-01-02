#!/bin/sh
#
# Wrapper for building the docs
set -e
# Ensure uv is in PATH
export PATH="$HOME/.local/bin:/root/.local/bin:$PATH"

cd doc/
uv run make html
