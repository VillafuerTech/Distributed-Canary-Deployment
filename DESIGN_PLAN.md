# Distributed Canary Deployment System – Design Plan

## Project Information
- **Team Members**: Selin Demirtürk, Roberto Villafuerte, Jan Thurner
- **Topic**: Distributed Canary Model Rollout Orchestrator
- **Implementation Language**: Python 3.11
- **Communication Protocol**: TCP (message passing) + HTTP (data plane)

---

## 1. System Overview

This project implements a **distributed canary deployment system** that orchestrates gradual rollouts of new ML model versions across a cluster of serving nodes. The system maintains a globally-agreed-upon routing state and uses **Two-Phase Commit (2PC)** consensus to ensure all nodes transition to the same model weights atomically.

### Key Use Case
In a large-scale ML serving infrastructure (e.g., 100s of nodes across regions), deploying a new model v2 typically requires:
1. **Canary phase**: Serve v2 to 5% of traffic while monitoring SLOs
2. **Gradual ramp**: If health is good, increase to 10%, 20%, 50%, 100%
3. **Rollback**: If SLOs degrade, abort and revert to v1

This system ensures that **all nodes flip to the new configuration at the same logical moment**, preventing split-brain routing decisions.

---

## 2. System Architecture

### 2.1 High-Level Topology

```
┌─────────────────────────────────────────────────────────┐
│              CONTROL PLANE (2PC Protocol)               │
│                                                         │
│   Coordinator (Node A)                                 │
│    ├─ Proposes new version weights                     │
│    ├─ Collects votes from participants                 │
│    └─ Broadcasts atomic commit/abort decision          │
│                                                         │
│   Participant B & C                                    │
│    ├─ Evaluate local health gates                      │
│    ├─ Vote COMMIT or ABORT                             │
│    └─ Apply coordinator's decision atomically          │
└─────────────────────────────────────────────────────────┘
         TCP Messages (PREPARE, COMMIT, HEARTBEAT)
         ↓            ↓            ↓
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Node A      │ │  Node B      │ │  Node C      │
│ (Coordinator)│ │(Participant) │ │(Participant) │
│              │ │              │ │              │
│  Control:    │ │  Control:    │ │  Control:    │
│  :60001      │ │  :60002      │ │  :60003      │
│              │ │              │ │              │
│  Data:       │ │  Data:       │ │  Data:       │
│  :50051      │ │  :50052      │ │  :50053      │
│  /predict    │ │  /predict    │ │  /predict    │
│  /health     │ │  /health     │ │  /health     │
│  /routing    │ │  /routing    │ │  /routing    │
└──────────────┘ └──────────────┘ └──────────────┘
       ↑              ↑              ↑
       └──────────────┴──────────────┘
        HTTP client queries
```

### 2.2 Shared Global State

Each node maintains an identical `RoutingState`:

```json
{
  "version": 2,
  "stable_model_id": "v1",
  "canary_model_id": "v2",
  "weights": {
    "v1": 0.95,
    "v2": 0.05
  },
  "status": "COMMITTED",
  "txid": "promote-2025-12-01T10:22:31Z"
}
```

**Invariant**: After 2PC completes, all nodes must have identical `version`, `weights`, and `status`.

---

## 3. Distributed Features Implementation

### 3.1 Shared Distributed State ✓

**Implementation**: `RoutingState` class in `distributed_canary/state.py`

- Each node holds an in-memory copy of the routing state
- State persisted to append-only log (`logs/{node_id}.log`)
- Upon startup, last state replayed from log
- All nodes maintain identical state via 2PC

**Design**: State includes version number for ordering and txid for idempotent message handling.

### 3.2 Synchronization & Consistency ✓

**Implementation**: Two-Phase Commit (2PC) protocol

**Phase 1: PREPARE**
- Coordinator sends `PREPARE_REQ` with proposed state to all participants
- Each participant:
  - Stages the new model version
  - Runs local health gates (p95 latency, error rate checks)
  - Persists `PREPARED <version>` to log
  - Votes `COMMIT` or `ABORT`

**Phase 2: DECISION**
- Coordinator waits 2 seconds for all votes (timeout = abort)
- If all vote COMMIT → broadcasts `DECISION COMMIT`
- Otherwise → broadcasts `DECISION ABORT`
- Each participant:
  - Atomically applies decision
  - Flips in-memory router weights if COMMIT
  - Persists final state to log

**Consistency Guarantee**: Only if all nodes vote COMMIT does any node change routing weights.

### 3.3 Consensus ✓

**Implementation**: Unanimous voting with coordinator arbitration

- Coordinator is a **designated leader** (Node A)
- Consensus = all participants vote COMMIT
- **Safety**: On timeout, coordinator defaults to ABORT (conservative)
- **Idempotency**: All messages carry txid + version for duplicate suppression

### 3.4 Fault Tolerance ✓

**Implementation**: Append-only logging + recovery protocol

**Persistence**:
- Every state transition persisted to log before returning to client
- Log entries: JSON, one per line (easy replay)

**Recovery Scenarios**:

| Failure | Recovery |
|---------|----------|
| Participant crashes before vote | Coordinator timeout → ABORT; node replays log on restart |
| Participant crashes after PREPARED | On restart, finds PREPARED without decision; queries peers for decision |
| Coordinator crashes during PREPARE | Participants timeout, elect highest node-id as temporary resolver, query peers |
| Network partition | 2PC requires unanimous votes; promotion pauses or aborts |

**Heartbeats** (2s interval): Periodic `{node_id, last_committed_version, digest}` to detect stale states and trigger catchup.

---

## 4. Node Roles & Functionalities

### 4.1 Node A (Coordinator)

**Role**: Initiates and orchestrates rollouts

**Responsibilities**:
- Proposes new `RoutingState` (with updated weights)
- Sends `PREPARE_REQ` to all participants
- Collects votes for 2 seconds (timeout = ABORT)
- Broadcasts atomic `DECISION`
- Handles timeouts conservatively (safety-first)

**Entry Point**: `node_a.py`

### 4.2 Nodes B & C (Participants)

**Role**: Evaluate health and vote on rollouts

**Responsibilities**:
- Listen for incoming `PREPARE_REQ` messages
- Evaluate health gates locally:
  - p95 latency ≤ 200 ms
  - error rate ≤ 5%
- Persist `PREPARED <version>` to log
- Send vote (`COMMIT` or `ABORT`)
- Apply coordinator's decision atomically
- Persist final state

**Entry Points**: `node_b.py`, `node_c.py`

### 4.3 Data Plane (All Nodes)

**HTTP Endpoints** (required by spec for demonstration):

1. **GET /routing/state**
   - Returns current `RoutingState` JSON
   - Used by clients to know which model versions are active

2. **GET /health/snapshot**
   - Returns node's health metrics
   - `{p95_ms, error_rate, window_id, last_committed_version}`

3. **POST /predict**
   - Routes request to v1 or v2 based on current weights (random weighted)
   - Demonstrates live model selection

---

## 5. Message Protocol

### 5.1 Control Plane (TCP)

All messages sent via TCP with 4-byte length prefix + JSON payload.

| Message | Direction | Payload | Purpose |
|---------|-----------|---------|---------|
| `PREPARE_REQ` | Coord → Part | version, RoutingState, txid | Propose new version |
| `PREPARE_RESP` | Part → Coord | txid, vote (COMMIT/ABORT), reason | Participant votes |
| `DECISION` | Coord → Part | txid, kind (COMMIT/ABORT), RoutingState | Atomic decision |
| `HEARTBEAT` | Peer ↔ Peer | node_id, last_committed_version, digest | Periodic visibility |
| `HEALTH_SNAPSHOT` | Peer ↔ Peer | node_id, p95, error_rate, window_id | Health metrics |

### 5.2 Data Plane (HTTP)

Standard REST endpoints for client queries and system monitoring.

---

## 6. Scalability Considerations

### For the Prototype
- 3 nodes (minimum requirement)
- Synchronous 2PC with 2-second timeout
- All nodes in-memory state

### At Scale (100s of nodes)
- **Bottleneck**: Coordinator becomes a single point of throttling
  - 2PC requires waiting for slowest participant (O(n) latency)
  - Throughput = 1 rollout every 2+ seconds per coordinator

- **Solutions**:
  1. **Multi-region sharding**: Each region has its own coordinator + participants; orchestrate rollouts region-by-region
  2. **Batch promotions**: Queue multiple state changes; apply in sequence
  3. **Replace 2PC with Raft**: Allow majority progress (not unanimous), faster consensus
  4. **Async notifications**: Decouple proposal from decision application

- **Performance Metrics**:
  - Rollout latency: ~2s (2s PREPARE timeout + messaging)
  - Data plane latency: ~1ms per /predict call (random weighted model selection)
  - State consistency: 100% after each 2PC round (all nodes identical)

---

## 7. Design Trade-Offs

| Decision | Rationale |
|----------|-----------|
| 2PC over Raft | Simpler for 3-node prototype; matches spec; unanimous safety |
| Coordinator pattern | Single leader simplifies consensus (no leader election complexity) |
| TCP + asyncio | Explicit message framing; no RPC framework overhead; Python standard |
| Append-only log | Simplicity; crash recovery via replay; all writes atomic |
| Health gates per node | Decentralized SLO enforcement; no single point of health judgment |
| HTTP data plane | Easy client access; standard tools (curl, browser) for testing |

---

## 8. Demonstration Plan

### Quick Start
```bash
# Terminal 1
python node_a.py

# Terminal 2
python node_b.py

# Terminal 3
python node_c.py

# Terminal 4 (while nodes running)
python query_system.py
```

### Expected Output
All three nodes return identical `version`, `weights`, `status` after each rollout phase.

### Staging
Coordinator initiates:
1. 5% canary (v1: 95%, v2: 5%)
2. 20% canary (v1: 80%, v2: 20%)
3. 50% canary (v1: 50%, v2: 50%)

Health gates randomly COMMIT or ABORT; on unanimous COMMIT, all nodes flip weights atomically.

---

## 9. Testing & Evaluation

### Functional Testing
- [ ] 2PC commits when all nodes healthy
- [ ] 2PC aborts when any node health gate fails
- [ ] Heartbeats detect version divergence
- [ ] Log replay recovers state correctly
- [ ] Query endpoints return current state

### Scalability Demonstration
- [ ] Start with 3 nodes
- [ ] Add nodes dynamically (extend peer list)
- [ ] Verify 2PC completes within 2s even with 5+ nodes

### Failure Scenarios
- [ ] Kill a participant mid-PREPARE → coordinator times out, aborts
- [ ] Kill a participant mid-DECISION → on restart, queries peers for final decision
- [ ] Network partition → 2PC pauses or aborts

---

## 10. Repository Structure

```
distributed_systems/project/
├── distributed_canary/
│   ├── __init__.py
│   ├── state.py           # RoutingState, StateLog
│   ├── messages.py        # Message types (PREPARE, DECISION, etc.)
│   ├── node.py            # Node class + 2PC logic
│   └── tcp_network.py     # TCP communication layer
├── node_a.py              # Coordinator entry point
├── node_b.py              # Participant B entry point
├── node_c.py              # Participant C entry point
├── query_system.py        # HTTP client for testing
├── run_demo.sh            # Demo script
├── README.md              # User guide
├── requirements.txt       # Python dependencies
└── logs/                  # Append-only state logs (created at runtime)
```

---

## 11. Conclusion

This distributed canary deployment system demonstrates:
1. **Shared state** via replicated RoutingState
2. **Synchronization** via Two-Phase Commit
3. **Consensus** via unanimous voting
4. **Fault tolerance** via append-only logging
5. **Communication** via TCP (control plane) + HTTP (data plane)

The prototype is deployable on 3 separate VMs/computers and scales to larger clusters via region sharding or Raft migration.
