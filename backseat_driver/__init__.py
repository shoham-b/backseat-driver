"""Backseat Driver describes driving scenes with a vision-language model.

The program is three stages, one package each, run by `pipeline.py`. That is `backseat-driver describe`: one process.

    read/     load scenes and images ──▶ process/  caption each image ──▶ write/  persist the descriptions

Running the process step on other machines adds one thing, a queue between read and process, and what the queue
forces once it crosses machines:

    read/ ──▶ IngestWorker ═ transport/ queue ═▶ CaptionWorker ──▶ write/
      │                                                  │
      └ read/s3/   images in a bucket                    └ write/job_store/   results in a database

The core (read, process, write, pipeline) never imports the added packages. `show/` is a separate role that only
reads what was written.
"""

from importlib.metadata import version

__version__ = version("backseat-driver")
