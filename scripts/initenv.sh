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

python3 -m venv --upgrade-deps venv

venv/bin/pip install -e chatmaild 
venv/bin/pip install -e cmdeploy
venv/bin/pip install sphinx sphinxcontrib-mermaid sphinx-autobuild furo  # for building the docs
