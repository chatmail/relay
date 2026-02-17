#!/bin/sh
# Build the chatmail Docker image with the current git hash baked in.
# Usage: ./docker/build.sh [extra docker-compose build args...]
#
# .git/ is excluded from the build context (.dockerignore) so the hash
# must be passed as a build arg from the host.

export GIT_HASH=$(git rev-parse --short HEAD)
exec docker compose build "$@"
