# Repository Guidelines

## Project Structure & Module Organization
- `src/daypilot/` contains the Python package.
- `src/daypilot/start_nodes/` holds the LangGraph node implementations (`gather_input_node.py`, `analyze_priorities_node.py`, `create_schedule_node.py`, `present_plan_node.py`).
- `src/daypilot/start.py` wires the flow; `src/daypilot/state.py` defines shared state.
- `src/daypilot/cli.py` exposes the Typer CLI entry point.
- `README.md` is currently empty; update it when adding user-facing docs.

## Build, Test, and Development Commands
- `uv sync`: install dependencies from `pyproject.toml`/`uv.lock`.
- `uv run cli`: run the CLI defined by `project.scripts` (alias for `daypilot.cli:app`).
- `uv run python -m daypilot.start`: run the flow directly for debugging.
- `uv run ruff check src`: lint imports/errors.
- `uv run ruff format src`: format code to match repo rules.

## Coding Style & Naming Conventions
- Python 3.12; 4-space indentation.
- Ruff formatting with `line-length = 100`, double quotes, and import sorting (`E`, `F`, `I`).
- Module and function names use `snake_case`; classes use `PascalCase`.

## Testing Guidelines
- No test framework is set up yet. If you add tests, place them under `tests/` and name files `test_*.py`.
- Prefer minimal, fast unit tests; document any new test commands here.

## Commit & Pull Request Guidelines
- Commit messages are short, imperative, and descriptive (e.g., "Add ruff", "Refactor start.py...").
- Include a summary of changes in PR descriptions and link relevant issues if any.
- Add screenshots or CLI output when changes affect user-visible behavior.

## Security & Configuration Tips
- Store secrets in `.env` (the repo ignores it). Use `python-dotenv` for local loading.
- Avoid committing API keys or model outputs with sensitive data.
