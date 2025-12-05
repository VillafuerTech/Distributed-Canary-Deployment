from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime
from typing import Dict, List

from aiohttp import web

from .messages import DecisionKind, Message, MessageType, Vote
from .state import DeploymentState, DeploymentStatus, StateLog
from .tcp_network import TCPNetwork


class Node:
    def __init__(
        self,
        node_id: str,
        role: str,
        peers: List[str],
        network: TCPNetwork,
        initial_model: str = "v1",
    ) -> None:
        self.node_id = node_id
        self.role = role
        self.peers = [peer for peer in peers if peer != node_id]
        self.network = network
        self.inbox: asyncio.Queue[Message] = asyncio.Queue()
        self.state_log = StateLog(node_id)
        
        # Load persisted state or create initial
        persisted = self.state_log.last_state()
        if persisted:
            self.state = persisted
            print(f"[{node_id}] Recovered state: model={persisted.model_id}, version={persisted.version}")
        else:
            self.state = DeploymentState(
                version=1,
                model_id=initial_model,
                status=DeploymentStatus.COMMITTED,
                txid="initial",
            )
            self.state_log.append(self.state)
        
        self.last_committed = self.state if self.state.status == DeploymentStatus.COMMITTED else None
        self.running = True
        self._vote_box: Dict[str, List[Vote]] = {}
        
        # Track deployed models
        self.deployed_models: Dict[str, dict] = {
            initial_model: {"deployed_at": datetime.utcnow().isoformat(), "status": "active"}
        }
        
        # Health metrics
        self.health_metric = {"p95": 120.0, "error_rate": 0.01, "n": 0}

    # ─────────────────────────────────────────────────────────────
    # MESSAGE PROCESSING
    # ─────────────────────────────────────────────────────────────

    async def process_messages(self) -> None:
        """Main message loop."""
        while self.running:
            try:
                message = await asyncio.wait_for(self.inbox.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            if message.msg_type == MessageType.PREPARE_REQ:
                await self._handle_prepare_request(message)
            elif message.msg_type == MessageType.PREPARE_RESP:
                self._handle_prepare_response(message)
            elif message.msg_type == MessageType.DECISION:
                await self._handle_decision(message)
            elif message.msg_type == MessageType.HEARTBEAT:
                self._handle_heartbeat(message)

    async def _handle_prepare_request(self, message: Message) -> None:
        """Participant receives deploy request from coordinator."""
        payload = message.payload
        candidate = DeploymentState.from_dict(payload["state"])
        
        # Check if we can accept this deployment
        vote = Vote.COMMIT
        vote_reason = "ready to deploy"
        
        if not self._passes_health_gate():
            vote = Vote.ABORT
            vote_reason = "health check failed"
        
        # Log the prepared state
        candidate.status = DeploymentStatus.PREPARED
        self.state_log.append(candidate)
        
        print(f"[{self.node_id}] Received deploy request for {candidate.model_id}, voting {vote.value}")
        
        # Send vote back
        response = Message(
            msg_type=MessageType.PREPARE_RESP,
            sender=self.node_id,
            payload={"txid": payload["txid"], "vote": vote.value, "reason": vote_reason},
        )
        await self.network.send(message.sender, response)

    def _handle_prepare_response(self, message: Message) -> None:
        """Coordinator collects votes from participants."""
        txid = message.payload["txid"]
        vote = Vote(message.payload["vote"])
        reason = message.payload.get("reason", "")
        
        print(f"[{self.node_id}] Received vote {vote.value} from {message.sender}: {reason}")
        self._vote_box.setdefault(txid, []).append(vote)

    async def _handle_decision(self, message: Message) -> None:
        """Participant applies the coordinator's decision."""
        payload = message.payload
        decision = DecisionKind(payload["kind"])
        state = DeploymentState.from_dict(payload["state"])
        
        await self._apply_decision(state, decision)

    def _handle_heartbeat(self, message: Message) -> None:
        """Handle heartbeat from peer."""
        model = message.payload.get("model_id")
        version = message.payload.get("version")
        print(f"[{self.node_id}] Heartbeat from {message.sender}: model={model}, v{version}")

    def _passes_health_gate(self) -> bool:
        """Check if node is healthy enough to accept deployment."""
        return self.health_metric["p95"] <= 200 and self.health_metric["error_rate"] <= 0.05

    async def _apply_decision(self, state: DeploymentState, decision: DecisionKind) -> None:
        """Apply commit or abort decision."""
        if decision == DecisionKind.COMMIT:
            state.status = DeploymentStatus.COMMITTED
            self.state = state
            self.last_committed = state
            self.state_log.append(state)
            
            # Update deployed models
            self.deployed_models[state.model_id] = {
                "deployed_at": datetime.utcnow().isoformat(),
                "status": "active"
            }
            
            print(f"[{self.node_id}] ✓ COMMITTED: Now running {state.model_id}")
        else:
            abort_state = DeploymentState(
                version=state.version,
                model_id=self.last_committed.model_id if self.last_committed else "v1",
                status=DeploymentStatus.ABORTED,
                txid=state.txid,
            )
            self.state_log.append(abort_state)
            
            if self.last_committed:
                self.state = self.last_committed
            
            print(f"[{self.node_id}] ✗ ABORTED: Staying on {self.state.model_id}")

    # ─────────────────────────────────────────────────────────────
    # DEPLOYMENT (COORDINATOR ONLY)
    # ─────────────────────────────────────────────────────────────

    async def deploy_version(self, new_model_id: str, max_retries: int = 3, retry_delay: float = 2.0) -> dict:
        """Deploy a new version to all nodes using 2PC with retry on failure."""
        if self.role != "coordinator":
            return {"error": "only coordinator can deploy"}
        
        for attempt in range(1, max_retries + 1):
            print(f"\n[{self.node_id}] ═══════════════════════════════════════")
            print(f"[{self.node_id}] DEPLOYING: {self.state.model_id} → {new_model_id} (attempt {attempt}/{max_retries})")
            print(f"[{self.node_id}] ═══════════════════════════════════════\n")
            
            # Create candidate state (only increment version on first attempt)
            if attempt == 1:
                next_version = self.state.version + 1
            txid = f"deploy-{self.node_id}-{next_version}-{int(time.time())}"
            
            candidate = DeploymentState(
                version=next_version,
                model_id=new_model_id,
                status=DeploymentStatus.PREPARED,
                txid=txid,
            )
            
            # Log locally
            self.state_log.append(candidate)
            
            # Phase 1: Send PREPARE to all participants
            print(f"[{self.node_id}] Phase 1: Sending PREPARE to {self.peers}")
            prepare_msg = Message(
                msg_type=MessageType.PREPARE_REQ,
                sender=self.node_id,
                payload={"txid": txid, "state": candidate.to_dict()},
            )
            
            for peer in self.peers:
                await self.network.send(peer, prepare_msg)
            
            # Collect votes
            decision = await self._collect_votes(txid, expected=len(self.peers))
            
            # Phase 2: Broadcast decision
            print(f"[{self.node_id}] Phase 2: Decision is {decision.value}")
            await self._broadcast_decision(candidate, decision)
            
            if decision == DecisionKind.COMMIT:
                # Success!
                return {
                    "status": "committed",
                    "model_id": new_model_id,
                    "version": self.state.version,
                    "attempts": attempt,
                }
            else:
                # Failed - retry if attempts remaining
                if attempt < max_retries:
                    print(f"[{self.node_id}] ✗ Deployment aborted. Retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                else:
                    print(f"[{self.node_id}] ✗ Deployment failed after {max_retries} attempts.")
        
        # All retries exhausted
        return {
            "status": "aborted",
            "model_id": self.state.model_id,
            "version": self.state.version,
            "attempts": max_retries,
            "error": f"Deployment of {new_model_id} failed after {max_retries} attempts",
        }

    async def _collect_votes(self, txid: str, expected: int) -> DecisionKind:
        """Wait for votes from all participants."""
        deadline = time.monotonic() + 3.0  # 3 second timeout
        
        while time.monotonic() < deadline:
            votes = self._vote_box.get(txid, [])
            if len(votes) >= expected:
                break
            await asyncio.sleep(0.1)
        
        votes = self._vote_box.pop(txid, [])
        
        if len(votes) < expected:
            print(f"[{self.node_id}] Timeout: only {len(votes)}/{expected} votes received")
            return DecisionKind.ABORT
        
        if all(v == Vote.COMMIT for v in votes):
            return DecisionKind.COMMIT
        else:
            return DecisionKind.ABORT

    async def _broadcast_decision(self, state: DeploymentState, decision: DecisionKind) -> None:
        """Send decision to all participants and apply locally."""
        decision_msg = Message(
            msg_type=MessageType.DECISION,
            sender=self.node_id,
            payload={"kind": decision.value, "state": state.to_dict()},
        )
        
        for peer in self.peers:
            await self.network.send(peer, decision_msg)
        
        # Apply locally
        await self._apply_decision(state, decision)

    # ─────────────────────────────────────────────────────────────
    # HEARTBEAT & HEALTH
    # ─────────────────────────────────────────────────────────────

    async def send_heartbeat_loop(self) -> None:
        """Periodically send heartbeats to peers."""
        while self.running:
            await asyncio.sleep(2.0)
            
            heartbeat = Message(
                msg_type=MessageType.HEARTBEAT,
                sender=self.node_id,
                payload={
                    "model_id": self.state.model_id,
                    "version": self.state.version,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
            
            for peer in self.peers:
                try:
                    await self.network.send(peer, heartbeat)
                except Exception:
                    pass

    def _digest(self) -> str:
        if not self.last_committed:
            return ""
        serialized = json.dumps(self.last_committed.to_dict(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()

    # ─────────────────────────────────────────────────────────────
    # DATA PLANE (HTTP API)
    # ─────────────────────────────────────────────────────────────

    async def start_data_plane(self, port: int) -> None:
        """HTTP server for deployment API and health checks."""
        app = web.Application()

        async def handle_state(_: web.Request) -> web.Response:
            """Get current deployment state."""
            return web.json_response(self.state.to_dict())

        async def handle_health(_: web.Request) -> web.Response:
            """Get health metrics."""
            return web.json_response({
                "node_id": self.node_id,
                "model_id": self.state.model_id,
                "version": self.state.version,
                "health": self.health_metric,
                "status": "healthy" if self._passes_health_gate() else "unhealthy",
            })

        async def handle_models(_: web.Request) -> web.Response:
            """List deployed models."""
            return web.json_response({
                "current": self.state.model_id,
                "models": self.deployed_models,
            })

        async def handle_deploy(request: web.Request) -> web.Response:
            """Deploy a new version (coordinator only)."""
            if self.role != "coordinator":
                return web.json_response({"error": "only coordinator can deploy"}, status=403)
            
            try:
                data = await request.json()
                model_id = data.get("model_id")
                
                if not model_id:
                    return web.json_response({"error": "model_id required"}, status=400)
                
                if model_id == self.state.model_id:
                    return web.json_response({"error": f"already running {model_id}"}, status=400)
                
                result = await self.deploy_version(model_id)
                return web.json_response(result)
                
            except json.JSONDecodeError:
                return web.json_response({"error": "invalid JSON"}, status=400)

        async def handle_rollback(_: web.Request) -> web.Response:
            """Rollback to previous version (coordinator only)."""
            if self.role != "coordinator":
                return web.json_response({"error": "only coordinator can rollback"}, status=403)
            
            if not self.last_committed:
                return web.json_response({"error": "no previous version"}, status=400)
            
            # Find previous model
            models = list(self.deployed_models.keys())
            if len(models) < 2:
                return web.json_response({"error": "no previous version available"}, status=400)
            
            previous = models[-2] if models[-1] == self.state.model_id else models[-1]
            result = await self.deploy_version(previous)
            return web.json_response(result)

        async def handle_predict(request: web.Request) -> web.Response:
            """Handle prediction request (routes to current model)."""
            try:
                payload = await request.json()
            except json.JSONDecodeError:
                payload = {}
            
            return web.json_response({
                "model": self.state.model_id,
                "version": self.state.version,
                "input": payload,
                "prediction": f"result_from_{self.state.model_id}",
            })

        app.add_routes([
            web.get("/state", handle_state),
            web.get("/health", handle_health),
            web.get("/models", handle_models),
            web.post("/deploy", handle_deploy),
            web.post("/rollback", handle_rollback),
            web.post("/predict", handle_predict),
        ])

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        print(f"[{self.node_id}] Data plane on http://0.0.0.0:{port}")

        try:
            while self.running:
                await asyncio.sleep(0.5)
        finally:
            await runner.cleanup()