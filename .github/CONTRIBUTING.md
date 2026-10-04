# Contributing to Backseat Driver

Thank you for your interest in contributing!

## Setup

```bash
git clone https://github.com/shoham-b/backseat-driver.git
cd backseat-driver
uv sync --group dev
pre-commit install
```

## Workflow

1. Create a branch: `git checkout -b feat/my-change`
2. Make your changes and add tests
3. Run the full check suite: `just check && just typecheck && just test`
4. Open a pull request against `main`

## Code style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting, and [ty](https://github.com/astral-sh/ty) for type checking. Pre-commit hooks enforce style automatically on commit.

## Tests

- **Unit tests** live in `tests/unittests/` and must not touch the network or disk.
- **Integration tests** live in `tests/integrationtests/` and test the full app in-process.
- **System tests** in `tests/systemtests/` spin up the real service.
- **Smoke tests** in `tests/smoketests/` run against a deployed environment.
- **Benchmarks** in `tests/benchmarks/` time our own overhead with a faked model (`just bench`); CI reports them via CodSpeed. Build test data in fixtures, since the benchmark marker times the whole test body.

Coverage must stay above 80% (`just test` will tell you if it drops).

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`.
