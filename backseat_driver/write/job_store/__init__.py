"""The database behind the job store: `orm.py` (the tables) and `storage.py` (the engine, sessions and queries).

This is the part that actually writes. The port and its adapters, which map these rows to domain models and say when a
job is complete, live with the seam in `transport/job_store/`.
"""
