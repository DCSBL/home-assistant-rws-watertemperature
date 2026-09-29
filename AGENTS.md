# AGENTS.md — Rijkswaterstaat Water Temperature

Instructions for AI coding agents working in this repo.

## Source management

- Never push directly to `main`. Every change goes through a pull request.
- Create a branch per change (e.g. `feat/…`, `fix/…`, `docs/…`, `ci/…`), commit in small
  increments with short, concrete messages, and open a PR against `main`.
- Enable auto-merge (squash) on the PR right after opening it. It merges on its own once all
  checks are green.
- If a check fails, fix it on the same branch and push; do not bypass or disable checks.
- Before pushing, run the same checks CI runs:
  `ruff check . && ruff format --check . && pytest` (or `pre-commit run --all-files`).

## Releases

- CalVer: `YYYY.M.N` (e.g. `2026.9.1`), no `v` prefix.
- Release by pushing a tag, or by running the **Release** workflow manually with the version
  as input. The workflow sets the manifest version, builds `rws_watertemperature.zip` and
  publishes the GitHub release that HACS installs from.

## Code

- Custom integration lives in `custom_components/rws_watertemperature/`; follow Home
  Assistant integration conventions (config flow, coordinator, `runtime_data`,
  `has_entity_name`, translation keys).
- User-facing strings go in `strings.json` and `translations/{en,nl}.json`; keep English and
  Dutch in sync.
- Tests use `pytest-homeassistant-custom-component` with the JSON fixtures in
  `tests/fixtures/`. Do not call the real RWS API from tests.
