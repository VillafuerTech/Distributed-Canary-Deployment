from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict


class DeploymentStatus(str, Enum):
    """Simple deployment status - one active version at a time."""
    PREPARED = "PREPARED"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"


@dataclass
class DeploymentState:
    """Simple deployment state - one active version at a time."""
    version: int                    # Incremental state version
    model_id: str                   # Currently active model (e.g., "v1", "v2", "v3")
    status: DeploymentStatus        # PREPARED, COMMITTED, or ABORTED
    txid: str                       # Transaction ID for 2PC
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, object]:
        return {
            "version": self.version,
            "model_id": self.model_id,
            "status": self.status.value,
            "txid": self.txid,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, object]) -> "DeploymentState":
        return cls(
            version=int(raw["version"]),
            model_id=str(raw["model_id"]),
            status=DeploymentStatus(raw["status"]),
            txid=str(raw["txid"]),
            timestamp=str(raw.get("timestamp", datetime.utcnow().isoformat())),
        )


class StateLog:
    """Append-only log for crash recovery."""
    def __init__(self, node_id: str, base_dir: Path | str = "logs") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.base_dir / f"{node_id}.log"

    def append(self, state: DeploymentState) -> None:
        line = json.dumps(state.to_dict(), separators=(',', ':'))
        with self.log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")

    def last_state(self) -> DeploymentState | None:
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
        return DeploymentState.from_dict(payload)