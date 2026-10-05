# Report UI appearance

`test-ui` drives the page in headless Chrome: every scene listed, scores and rankings, filters narrowing and clearing,
the camera tabs, no console errors, no sideways scroll on a phone, the stacked phone layout. This checks only what a
script cannot judge: whether it looks right.

Needs the output of [real-run.md](real-run.md) step 1, ideally from two models so the comparison has something to show.

```bash
just ui
```

Open <http://127.0.0.1:8081> and check:

- Nothing overlaps or is cut off, including the metrics table at phone width (about 375 px), and long descriptions wrap.
- Scores look plausible for the captions next to them.
- Dark and light system themes are both readable.

Static report: `just report` writes the HTML file; open it straight from disk (no server) and check the same.
