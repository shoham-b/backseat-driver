# Report UI appearance

`test-ui` checks that the page works. This checks that it looks right, which only a person can.

Needs the output of [real-run.md](real-run.md) step 1, ideally from two models so the comparison has something to show.

```bash
just ui
```

Open <http://127.0.0.1:8081> and check:

- Every scene is listed, each with its image and every model's description.
- Scores are shown and plausible; the filters narrow the list and clear again.
- Nothing overlaps or is cut off, and long descriptions wrap.
- Resize to phone width (about 375 px): no horizontal scrolling.
- Dark and light system themes are both readable.
- The browser console shows no errors.

Static report: `just report` writes the HTML file; open it straight from disk (no server) and repeat the first two
checks.
