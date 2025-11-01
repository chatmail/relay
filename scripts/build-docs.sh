#!/bin/sh
#
# Wrapper for building the docs
set -e
. venv/bin/activate
cd doc/
make html
