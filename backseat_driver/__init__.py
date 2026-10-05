"""Backseat Driver describes driving scenes with a vision-language model.

The program is three stages, one package each, run by `pipeline.py`. That is `backseat-driver describe`: one process.

    read/     load scenes and images ──▶ process/  caption each image ──▶ write/  persist the descriptions

Running the process step as tasks adds a queue between read and process, and the job store the queue forces: results
arrive one at a time, so they are recorded as they come, along with when a job is complete. Both live in `transport/`.
Crossing machines adds one more thing, a bucket, because the workers then share no disk:

    read/ ──▶ IngestWorker ═ transport/ queue ═▶ CaptionWorker ──▶ write/
      │                                  results and job state ──▶ transport/job_store/
      └ read/s3/   images in a bucket (machines)

The core (read, process, write, pipeline) never imports the added packages. `show/` is a separate role that only
reads what was written.
"""

from importlib.metadata import version

__version__ = version("backseat-driver")
