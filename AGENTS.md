# Repository Guidelines

## Project Structure & Module Organization
- `api/` — FastAPI backend; `avarr/` package holds config, database, download manager, and routers; `pyproject.toml` + `uv.lock` live here.
- `web/` — React dashboard built with Vite; `src/` contains views and API client; served separately in dev and optionally mounted under `/app` after building.
- `downloads/` (inside `api/`) — runtime artifacts written by yt-dlp; should remain out of version control except for `.gitkeep`.
- `tests/` (add at `api/tests/`) — mirror the runtime package layout and name files `test_<module>.py`.

## Build, Test, and Development Commands
- `uv run python main.py` (from `api/`) — launch the FastAPI server with uvicorn via the console entry point.
- `uv run pytest` — run the test suite; add `-k name` to focus specific tests.
- `uv sync` — install or update dependencies after editing `pyproject.toml` or `uv.lock`.
- `uv lock --upgrade-package <pkg>` — refresh a dependency while preserving others.
- From `web/`, run `pnpm dev` for local development or `pnpm build` to emit the static bundle mounted under `/app`.

## Coding Style & Naming Conventions
- Follow Python 3.12+ idioms and PEP 8 spacing (4-space indents, snake_case for functions/variables, UpperCamelCase for classes) inside `api/`.
- Type hints are required for public functions; prefer small dataclasses (e.g., download contexts) instead of passing large dictionaries.
- Keep modules under 300 logical lines; split helpers into `avarr/utils/*.py` as the surface area grows.
- Run `uv run ruff check . && uv run ruff format .` plus `pnpm lint --filter web` before review to ensure both stacks are consistent.

## Testing Guidelines
- Use `pytest` and place fixtures inside `tests/conftest.py` to share state.
- Name tests descriptively: `test_<unit>_<behavior>` (e.g., `test_downloader_handles_private_listing`).
- Target >=90% coverage on new modules; run `uv run pytest --cov=avarr --cov-report=term-missing` before review.

## Commit & Pull Request Guidelines
- History currently contains only the scaffold; continue with imperative, present-tense subjects (e.g., `Add downloader adapter`).
- Reference issues in the footer using `Refs #<id>` when applicable.
- Keep commits focused (one feature/fix per commit) and include any relevant `uv` or schema updates in the same change.
- Pull requests must describe intent, testing performed (`pytest`, linters), and note user-facing impacts; attach screenshots or log snippets when behavior is visual or CLI-facing.

## Security & Configuration Tips
- Never commit credential files (e.g., `cookies-*.txt`); store them outside the repo and load paths via environment variables.
- Review third-party plugins declared in `pyproject.toml` before upgrading; document any pin changes under a “Security” note in the PR.
