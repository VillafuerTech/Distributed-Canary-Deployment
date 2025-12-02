from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, cast


class RoutingStatus(str, Enum):
    PREPARED = "PREPARED"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"


@dataclass
class RoutingState:
    version: int
    stable_model_id: str
    canary_model_id: str
    weights: Dict[str, float]
    status: RoutingStatus
    txid: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, object]:
        return {
            "version": self.version,
            "stable_model_id": self.stable_model_id,
            "canary_model_id": self.canary_model_id,
            "weights": self.weights,
            "status": self.status.value,
            "txid": self.txid,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, object]) -> "RoutingState":
        return cls(
            version=int(raw["version"]),
            stable_model_id=str(raw["stable_model_id"]),
            canary_model_id=str(raw["canary_model_id"]),
            weights={
                str(key): float(value)
                for key, value in cast(Dict[str, object], raw.get("weights", {})).items()
            },
            status=RoutingStatus(raw["status"]),
            txid=str(raw["txid"]),
            timestamp=str(raw.get("timestamp", datetime.utcnow().isoformat())),
        )


class StateLog:
    def __init__(self, node_id: str, base_dir: Path | str = "logs") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.base_dir / f"{node_id}.log"

    def append(self, state: RoutingState) -> None:
        line = json.dumps(state.to_dict(), separators=(',', ':'))
        with self.log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")

    def last_state(self) -> RoutingState | None:
        if not self.log_file.exists():
            return None
        last_line: str | None = None
        with self.log_file.open(encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    last_line = stripped
        if not last_line:
            return None
        payload = json.loads(last_line)
        return RoutingState.from_dict(payload)