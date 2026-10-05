"""Stage 3, write: persist the `SceneDescription`s.

    describe (one process)   list[SceneDescription] ──▶ json_writer.write_json ──▶ output/*.json
    workers (many machines)  one SceneDescription   ──▶ transport.job_store    ──▶ SQLite / Postgres

The two are different contracts: a batch written once at the end, and results recorded one by one. The second also
carries the completion rule, since the job record says how many results to expect. It is part of the seam, so it lives
in `transport/job_store/`, over the database in `write/job_store/`. `show/` reads either and is not part of this stage.
"""
