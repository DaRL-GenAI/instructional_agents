#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
VENV="$SCRIPT_DIR/.venv"

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: uv is required but was not found on PATH." >&2
  exit 1
fi

echo "Creating isolated Python 3.12 environment at $VENV"
uv venv --python 3.12 "$VENV"

echo "Installing Instructional Agents dependencies and pytest"
uv pip install --python "$VENV/bin/python" \
  -r "$REPO_ROOT/requirements.txt" \
  pytest

export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

if [ "${SKIP_TESTS:-0}" != "1" ]; then
  echo "Running local CLI tests"
  "$VENV/bin/python" -m pytest "$SCRIPT_DIR/tests"

  echo "Running existing Instructional Agents tests"
  "$VENV/bin/python" -m pytest "$REPO_ROOT/tests"
fi

echo "Checking local toolchain and OpenAI authentication"
"$SCRIPT_DIR/course" doctor --live-openai

echo
echo "Setup complete. Try:"
echo "  ./local_course_cli/course --help"
