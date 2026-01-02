#!/bin/sh
set -e

if command -v lsb_release 2>&1 >/dev/null; then
  case "$(lsb_release -is)" in
    Ubuntu | Debian )
      if ! dpkg -l | grep python3-dev 2>&1 >/dev/null
      then
        echo "You need to install python3-dev for installing the other dependencies."
        exit 1
      fi
      if ! gcc --version 2>&1 >/dev/null
      then
        echo "You need to install gcc for building Python dependencies."
        exit 1
      fi
      ;;
  esac
fi

# Ensure uv is in PATH
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv &> /dev/null; then
    echo "uv not found. Please install it first or run init.sh"
    exit 1
fi

uv venv venv

uv pip install -e chatmaild 
uv pip install -e cmdeploy
uv pip install sphinx sphinxcontrib-mermaid sphinx-autobuild furo  # for building the docs
