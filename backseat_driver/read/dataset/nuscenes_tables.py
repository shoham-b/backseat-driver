"""The nuScenes metadata tables keyframe selection reads, straight from their JSON files.

nuscenes-devkit would serve the same lookups, but importing it pulls in matplotlib, scikit-learn and scipy, and opening
it indexes every table and checks the map files. Ingest runs once per message, so that cost is paid per job. The
devkit's `scene` list and `get(table, token)` are the only parts the loader uses, and they are all this class has.
"""

import json
from pathlib import Path
from typing import Any

Record = dict[str, Any]


class NuScenesTables:
    """Reads `scene`, `sample`, `sample_data`, `calibrated_sensor` and `sensor` from `<dataroot>/<version>/`."""

    def __init__(self, version: str, dataroot: str) -> None:
        self._directory = Path(dataroot) / version
        self._rows: dict[str, list[Record]] = {}
        self._indexes: dict[str, dict[str, Record]] = {}
        self.scene: list[Record] = self._table("scene")

    def get(self, table: str, token: str) -> Record:
        """The record of `table` with `token`; the table is read and indexed on first use. Raises KeyError if absent.

        A `sample` record carries `data`, a map from camera channel to the token of that channel's key-frame
        `sample_data`. The file has no such field: the devkit derives it, and so does this.
        """
        if table not in self._indexes:
            self._indexes[table] = {record["token"]: record for record in self._table(table)}
            if table == "sample":
                self._attach_data(self._indexes[table])
        return self._indexes[table][token]

    def _attach_data(self, samples: dict[str, Record]) -> None:
        sensor_channel = {sensor["token"]: sensor["channel"] for sensor in self._table("sensor")}
        channel_by_calibration = {
            calibrated["token"]: sensor_channel[calibrated["sensor_token"]]
            for calibrated in self._table("calibrated_sensor")
        }
        for sample in samples.values():
            sample["data"] = {}
        for sample_data in self._table("sample_data"):
            if sample_data["is_key_frame"]:
                channel = channel_by_calibration[sample_data["calibrated_sensor_token"]]
                samples[sample_data["sample_token"]]["data"][channel] = sample_data["token"]

    def _table(self, table: str) -> list[Record]:
        if table not in self._rows:
            self._rows[table] = json.loads((self._directory / f"{table}.json").read_text())
        return self._rows[table]
