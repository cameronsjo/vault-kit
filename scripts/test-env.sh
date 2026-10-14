#!/usr/bin/env bash
# Every suite gets an empty Git/XDG configuration, including standalone targets.
set -eu
test_config=$(mktemp -d)
trap 'rm -rf "$test_config"' EXIT
export GIT_CONFIG_GLOBAL=/dev/null
export XDG_CONFIG_HOME="$test_config"
"$@"
