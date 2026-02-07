# Release Checklist

## Pre-release

- Update `pyproject.toml` version.
- Update `CHANGELOG.md` with release notes.
- Run local checks:
  - `uv sync --all-groups`
  - `uv run ruff check src`
  - `uv run python -m compileall src`
  - `uv run ym-bridge --help`
- Verify daemon runtime:
  - `uv run ym-bridge run`
  - `playerctl --player=ymbridge metadata`
  - `uv run ym-bridge ctl status`
  - `uv run ym-bridge waybar`

## Packaging

- Build wheel/sdist:
  - `uv build`
- Validate install in clean environment.

## Tagging

- Create annotated tag:
  - `git tag -a v0.1.0 -m "ym-bridge v0.1.0"`
- Push branch and tag.

## Post-release

- Verify docs examples against release artifact.
- Rotate any token used during manual testing.
