#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec uv run --locked --project "$project_dir" python "$project_dir/photo_id_generator.py" "$@"
