from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class MessageType(str, Enum):
    PREPARE_REQ = "PREPARE_REQ"
    PREPARE_RESP = "PREPARE_RESP"
    DECISION = "DECISION"
    HEARTBEAT = "HEARTBEAT"
    HEALTH_SNAPSHOT = "HEALTH_SNAPSHOT"


class Vote(str, Enum):
    COMMIT = "COMMIT"
    ABORT = "ABORT"


class DecisionKind(str, Enum):
    COMMIT = "COMMIT"
    ABORT = "ABORT"


@dataclass
class Message:
    msg_type: MessageType
    sender: str
    payload: Dict[str, Any]