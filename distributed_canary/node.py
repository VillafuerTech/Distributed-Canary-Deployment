from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from datetime import datetime
from typing import Dict, List, Optional

from aiohttp import web

from .messages import DecisionKind, Message, MessageType, Vote
from .state import RoutingState, RoutingStatus, StateLog
from .tcp_network import TCPNetwork


class Node:
    def __init__(
        self,
        node_id: str,
        role: str,
        peers: List[str],
        network: TCPNetwork,
        stable_model_id: str = "v1",
        canary_model_id: str = "v2",
    ) -> None:
        self.node_id = node_id
        self.role = role
        self.peers = [peer for peer in peers if peer != node_id]
        self.network = network
        self.inbox: asyncio.Queue[Message] = asyncio.Queue()
        self.state_log = StateLog(node_id)
        persisted = self.state_log.last_state()
        if persisted:
            self.state = persisted
        else:
            self.state = RoutingState(
                version=1,
                stable_model_id=stable_model_id,
                canary_model_id=canary_model_id,
                weights={stable_model_id: 1.0, canary_model_id: 0.0},
                status=RoutingStatus.COMMITTED,
                txid="initial",
            )
            self.state_log.append(self.state)
        self.last_committed = (
            self.state if self.state.status == RoutingStatus.COMMITTED else None
        )
        self.running = True
        self._vote_box: Dict[str, List[Vote]] = {}
        self.health_metric = {"p95": 120.0, "error_rate": 0.1, "n": 0}

    async def process_messages(self) -> None:
        while self.running:
            try:
                message = await asyncio.wait_for(self.inbox.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if message.msg_type == MessageType.PREPARE_REQ:
                await self._handle_prepare_request(message)
            elif message.msg_type == MessageType.PREPARE_RESP and self.role == "coordinator":
                self._handle_prepare_response(message)
            elif message.msg_type == MessageType.DECISION:
                await self._handle_decision(message)
            elif message.msg_type == MessageType.HEARTBEAT:
                self._handle_heartbeat(message)
            elif message.msg_type == MessageType.HEALTH_SNAPSHOT:
                self._handle_health_snapshot(message)
            self.inbox.task_done()

    async def _handle_prepare_request(self, message: Message) -> None:
        payload = message.payload
        candidate = RoutingState.from_dict(payload["state"])
        vote_reason = "health gates met"
        vote = Vote.COMMIT
        if not self._passes_health_gate():
            vote = Vote.ABORT
            vote_reason = "health gate triggered"
        candidate.status = RoutingStatus.PREPARED
        self.state_log.append(candidate)
        response = Message(
            msg_type=MessageType.PREPARE_RESP,
            sender=self.node_id,
            payload={"txid": payload["txid"], "vote": vote.value, "reason": vote_reason},
        )
        await self.network.send(message.sender, response)

    def _handle_prepare_response(self, message: Message) -> None:
        txid = message.payload["txid"]
        vote = Vote(message.payload["vote"])
        self._vote_box.setdefault(txid, []).append(vote)

    async def _handle_decision(self, message: Message) -> None:
        payload = message.payload
        decision = DecisionKind(payload["kind"])
        state = RoutingState.from_dict(payload["state"])
        await self._apply_decision(state, decision)

    def _handle_heartbeat(self, message: Message) -> None:
        digest = message.payload.get("digest")
        version = message.payload.get("last_committed_version")
        # Heartbeats allow visibility but do not change local state in this prototype.
        print(f"{self.node_id} received heartbeat from {message.sender}: v{version} digest {digest}")

    def _handle_health_snapshot(self, message: Message) -> None:
        info = message.payload
        print(f"{self.node_id} sees peer {info['node_id']} p95={info['p95']} err={info['error_rate']:.2%}")

    def _passes_health_gate(self) -> bool:
        self.health_metric["n"] += 1
        self.health_metric["p95"] = max(60.0, self.health_metric["p95"] + random.uniform(-5, 5))
        self.health_metric["error_rate"] = max(0.01, self.health_metric["error_rate"] + random.uniform(-0.01, 0.01))
        # Health gates: p95 <= 200ms, error_rate <= 5%
        return self.health_metric["p95"] <= 200 and self.health_metric["error_rate"] <= 0.05

    async def _apply_decision(self, state: RoutingState, decision: DecisionKind) -> None:
        if decision == DecisionKind.COMMIT:
            state.status = RoutingStatus.COMMITTED
            self.state = state
            self.last_committed = state
            self.state_log.append(state)
        else:
            abort_state = RoutingState(
                version=state.version,
                stable_model_id=state.stable_model_id,
                canary_model_id=state.canary_model_id,
                weights=state.weights,
                status=RoutingStatus.ABORTED,
                txid=state.txid,
            )
            self.state_log.append(abort_state)
            if self.last_committed:
                self.state = self.last_committed

    async def send_heartbeat_loop(self) -> None:
        while self.running:
            digest = self._digest()
            heartbeat = {
                "node_id": self.node_id,
                "last_committed_version": self.last_committed.version if self.last_committed else 0,
                "digest": digest,
            }
            for peer in self.peers:
                await self.network.send(
                    peer,
                    Message(msg_type=MessageType.HEARTBEAT, sender=self.node_id, payload=heartbeat),
                )
            await asyncio.sleep(2)

    def _digest(self) -> str:
        if not self.last_committed:
            return ""
        serialized = json.dumps(self.last_committed.to_dict(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()

    async def send_health_snapshots(self) -> None:
        snap = {
            "node_id": self.node_id,
            "p95": self.health_metric["p95"],
            "error_rate": self.health_metric["error_rate"],
            "window_id": f"window-{int(time.time())}",
        }
        for peer in self.peers:
            await self.network.send(
                peer,
                Message(msg_type=MessageType.HEALTH_SNAPSHOT, sender=self.node_id, payload=snap),
            )

    def _health_snapshot_payload(self) -> Dict[str, object]:
        return {
            "node_id": self.node_id,
            "p95": self.health_metric["p95"],
            "error_rate": self.health_metric["error_rate"],
            "window_id": f"window-{int(time.time())}",
            "last_committed_version": self.last_committed.version if self.last_committed else 0,
            "digest": self._digest(),
        }

    async def initiate_rollout(self, canary_share: float = 0.05) -> None:
        if self.role != "coordinator":
            raise RuntimeError("only the coordinator initiates rollouts")
        target_weights = {
            self.state.stable_model_id: max(0.0, 1.0 - canary_share),
            self.state.canary_model_id: max(0.0, canary_share),
        }
        next_version = self.state.version + 1
        txid = f"promote-{self.node_id}-{next_version}-{datetime.utcnow().isoformat()}"
        candidate = RoutingState(
            version=next_version,
            stable_model_id=self.state.stable_model_id,
            canary_model_id=self.state.canary_model_id,
            weights=target_weights,
            status=RoutingStatus.PREPARED,
            txid=txid,
        )
        self.state_log.append(candidate)
        prepare = Message(msg_type=MessageType.PREPARE_REQ, sender=self.node_id, payload={
            "txid": txid,
            "state": candidate.to_dict(),
        })
        for peer in self.peers:
            await self.network.send(peer, prepare)
        decision = await self._collect_votes(txid, len(self.peers))
        await self._broadcast_decision(candidate, decision)

    async def _collect_votes(self, txid: str, expected: int) -> DecisionKind:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            votes = self._vote_box.get(txid, [])
            if len(votes) >= expected:
                break
            await asyncio.sleep(0.1)
        votes = self._vote_box.pop(txid, [])
        if len(votes) < expected:
            return DecisionKind.ABORT
        return DecisionKind.COMMIT if all(vote == Vote.COMMIT for vote in votes) else DecisionKind.ABORT

    async def _broadcast_decision(self, state: RoutingState, decision: DecisionKind) -> None:
        payload_state = state
        payload_state.status = RoutingStatus.COMMITTED if decision == DecisionKind.COMMIT else RoutingStatus.ABORTED
        payload = {
            "txid": state.txid,
            "kind": decision.value,
            "state": payload_state.to_dict(),
        }
        for peer in self.peers:
            await self.network.send(
                peer,
                Message(msg_type=MessageType.DECISION, sender=self.node_id, payload=payload),
            )
        await self._apply_decision(payload_state, decision)

    def _choose_model(self) -> str:
        rnd = random.random()
        cumulative = 0.0
        for model_id, weight in self.state.weights.items():
            cumulative += weight
            if rnd <= cumulative:
                return model_id
        return max(self.state.weights, key=self.state.weights.get)

    async def start_data_plane(self, port: int) -> None:
        app = web.Application()

        async def handle_routing_state(_: web.Request) -> web.Response:
            return web.json_response(self.state.to_dict())

        async def handle_health_snapshot(_: web.Request) -> web.Response:
            return web.json_response(self._health_snapshot_payload())

        async def handle_predict(request: web.Request) -> web.Response:
            try:
                payload = await request.json()
            except json.JSONDecodeError:
                payload = {}
            selected = self._choose_model()
            response = {
                "model_selected": selected,
                "routing_state": self.state.to_dict(),
                "input": payload,
            }
            return web.json_response(response)

        app.add_routes(
            [
                web.get("/routing/state", handle_routing_state),
                web.get("/health/snapshot", handle_health_snapshot),
                web.post("/predict", handle_predict),
            ]
        )
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()
        print(f"{self.node_id} data plane listening on 127.0.0.1:{port}")
        try:
            while self.running:
                await asyncio.sleep(0.5)
        finally:
            await runner.cleanup()