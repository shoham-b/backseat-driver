# Performance on real data

The CodSpeed benchmarks run on synthetic data and shared runners, so they catch regressions in the code, not the speed of
a real run. Do this when a change touches batching, startup, the scene loader or a backend.

Use the same machine and model for both sides, and close other heavy programs.

1. Check out the previous release tag and the change in two worktrees.
2. In each, time the same run, twice (the first run warms the model cache):

   ```bash
   just describe --camera front --model Salesforce/blip-image-captioning-base
   ```

3. Record wall time, scenes per second and peak memory (Task Manager, or `/usr/bin/time -v` on Linux).

Good looks like: the change is no slower than the previous release on the same hardware, and any speed-up claimed in the
PR shows up here. Repeat with `--all-cameras` for the batched path, and with a GPU if you ship one.

Put the numbers in the PR description.
