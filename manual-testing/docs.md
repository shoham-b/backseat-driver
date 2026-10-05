# Documentation

CI builds the site with `mkdocs build --strict`, so broken links, pages missing from the nav and docstrings the API
reference cannot render fail a PR. It cannot tell whether what the pages *say* is true, or whether a newcomer can follow
them. That takes a person.

Run this when a change touches behaviour the docs describe (commands, options, settings, deployment) and before each
release.

## 1. Follow the pages as a newcomer

On a clean checkout (or a fresh clone in another folder), with no `.env` and no `data/`, follow
[Getting Started](../docs/getting-started.md) and [Running It](../docs/running.md) exactly as written, copying each
command.

Good looks like:

- Every command works as written, with no step you had to guess.
- The output and the files it produces match what the page says.
- Every option, default and environment variable the pages mention exists (`uv run backseat-driver describe --help`,
  `.env.example`).

Do the same for the Compose and Kubernetes steps in [Deployment](../docs/deployment.md) when those changed.

## 2. Claims still match the code

Read the pages that describe behaviour you changed ([Design Decisions](../docs/design-decisions.md),
[Distributed Mode](../docs/distributed.md), [Technology](../docs/technology.md)). Good looks like:

- No statement is out of date: removed options, old defaults, "not yet" and "known to" notes that no longer hold.
- Diagrams match the current flow.
- The numbers quoted (limits, retries, defaults) match the code and manifests.

## 3. The rendered site

```bash
just docs-open
```

Good looks like:

- Navigation order and titles make sense, and the search finds a page by a term it contains.
- Mermaid diagrams render, and tables and code blocks are not cut off.
- Pages read well at phone width.

After a release, open the published site and check the same, plus that the new version's changes appear.
