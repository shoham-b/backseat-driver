# Contributing to VLM Scene Description

Thank you for your interest in contributing!

## Setup

```bash
git clone <repo-url>
cd vlm_scene_description
uv sync --group dev
pre-commit install
```

## Workflow

1. Create a branch: `git checkout -b feat/my-change`
2. Make your changes and add tests
3. Run the full check suite: `just check && just typecheck && just test`
4. Open a pull request against `main`

## Code style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting, and [mypy](https://mypy.readthedocs.io/) (strict mode) for type checking. Pre-commit hooks enforce style automatically on commit.

## Tests

- **Unit tests** live in `tests/unittests/` and must not touch the network or disk.
- **Integration tests** live in `tests/integrationtests/` and test the full app in-process.
- **System tests** in `tests/systemtests/` spin up the real service.
- **Smoke tests** in `tests/smoketests/` run against a deployed environment.

Coverage must stay above 80% (`just test` will tell you if it drops).

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`.
