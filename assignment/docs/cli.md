# CLI Reference

All commands are run via `uv run vlm_scene_description <command>`.

Global help: `uv run vlm_scene_description --help`

---

## `--version` / `-V`

Print the installed version and exit.

```bash
uv run vlm_scene_description --version
# vlm_scene_description 0.1.0
```

---

## `test smoke`

Run the smoke test suite against a live API.

```bash
uv run vlm_scene_description test smoke [OPTIONS]
```

| Option | Env var | Default | Description |
|---|---|---|---|
| `--api-url` | `API_URL` | `http://127.0.0.1:8080` | Base URL of the running API |
| `--verbose` / `-v` | — | off | Pass `-v` to pytest |

**Examples:**

```bash
# Against the local dev server
uv run vlm_scene_description test smoke

# Against a remote target
uv run vlm_scene_description test smoke --api-url https://staging.example.com

# Via environment variable
API_URL=https://staging.example.com uv run vlm_scene_description test smoke --verbose
```

Exits with the pytest exit code. Exits `0` when all tests pass or when no smoke tests are collected yet.
