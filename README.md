# Distributed Canary Deployment System

A three-node distributed system that orchestrates gradual canary deployments using Two-Phase Commit (2PC) consensus.

## Project Requirements Compliance

✅ **Three separate nodes**: Each runs as an independent process with its own IP/port  
✅ **Message passing**: TCP-based inter-node communication with proper message framing  
✅ **Shared distributed state**: RoutingState replicated and agreed across all nodes  
✅ **Synchronization & consistency**: 2PC protocol ensures atomic state transitions  
✅ **Consensus**: Coordinator-based voting mechanism for commit/abort decisions  
✅ **Fault tolerance**: Append-only logging for recovery and crash resilience  
✅ **Logging**: All important events logged to file (logs/ directory)  

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│         Control Plane (2PC, Heartbeats)                 │
│  Coordinator  ←→  Participant B  ←→  Participant C    │
│     (Node A)                                             │
└─────────────────────────────────────────────────────────┘
         ↓                 ↓                  ↓
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Data Plane  │    │  Data Plane  │    │  Data Plane  │
│   /predict   │    │   /predict   │    │   /predict   │
│   /health    │    │   /health    │    │   /health    │
│  /routing    │    │  /routing    │    │  /routing    │
└──────────────┘    └──────────────┘    └──────────────┘
   :50051              :50052              :50053
```

## Nodes

- **Node A (Coordinator)**: Initiates rollouts, collects votes, broadcasts decisions
- **Node B (Participant)**: Evaluates health gates, votes on rollouts, applies decisions
- **Node C (Participant)**: Evaluates health gates, votes on rollouts, applies decisions

## Running the System

### Prerequisites
```bash
pip install aiohttp
```

### Option 1: Run All Nodes Together (Recommended)
```bash
python run_nodes.py
```
Starts Coordinator A, Participant B, and Participant C concurrently.

### Option 2: Run Individual Nodes
```bash
# Terminal 1 - Coordinator
python run_nodes.py coordinator

# Terminal 2 - Participant B
python run_nodes.py participant_b

# Terminal 3 - Participant C
python run_nodes.py participant_c

# Terminal 4 - Query System State
python query_system.py
```

### Option 3: Automated Demo Script
```bash
bash run_demo.sh
```
Starts the system, queries state, and displays results.

## Example Output

When all nodes are running, Node A will initiate staged rollouts:
- 5% canary → 20% canary → 50% canary
- Each node evaluates health gates and votes
- On unanimous COMMIT, all nodes atomically flip routing weights

## Communication Protocols

### Control Plane Messages (TCP)
- **PREPARE_REQ**: Coordinator proposes new version
- **PREPARE_RESP**: Participant votes COMMIT/ABORT
- **DECISION**: Coordinator broadcasts final decision
- **HEARTBEAT**: Periodic peer visibility (2s interval)
- **HEALTH_SNAPSHOT**: Node health metrics (4s interval)

### Data Plane Endpoints (HTTP)
- `GET /routing/state` → Current RoutingState JSON
- `GET /health/snapshot` → Health metrics (p95, error_rate)
- `POST /predict` → Route request to v1 or v2 by weight

## State Persistence

Each node maintains an append-only log in `logs/{node_id}.log`:
```json
{"version": 1, "stable_model_id": "v1", "canary_model_id": "v2", "weights": {"v1": 1.0, "v2": 0.0}, "status": "COMMITTED", "txid": "initial", "timestamp": "..."}
{"version": 2, "stable_model_id": "v1", "canary_model_id": "v2", "weights": {"v1": 0.95, "v2": 0.05}, "status": "PREPARED", "txid": "promote-...", "timestamp": "..."}
{"version": 2, "stable_model_id": "v1", "canary_model_id": "v2", "weights": {"v1": 0.95, "v2": 0.05}, "status": "COMMITTED", "txid": "promote-...", "timestamp": "..."}
```

## Distributed Features

1. **Global Routing State**: All nodes maintain identical `RoutingState` (version, weights, status)
2. **Two-Phase Commit**: Atomic promotion across the cluster
3. **Health Gates**: Each node locally evaluates SLO thresholds before voting
4. **Heartbeats**: Periodic peer discovery and version reconciliation
5. **Recovery**: Log replay reconstructs state on startup
6. **Scalability**: Can extend to N nodes; 2PC cost grows linearly with participant count

## Design Decisions

- **2PC over Raft**: Simpler for small clusters, matches design plan specification
- **TCP Messages**: Explicit framing with length prefix enables reliable message boundaries
- **Async/await**: Concurrent message handling without thread complexity
- **HTTP Data Plane**: Easy client access to routing decisions and health metrics
- **Coordinator Pattern**: Single leader simplifies consensus decision-making

## Testing & Demonstration

Run `python query_system.py` while nodes are operational to view:
- Current routing state across all nodes
- Health metrics (latency, error rate)
- Model selection verification (v1 vs v2 routing)

You should see all three nodes return identical `version`, `weights`, and `status` values, demonstrating consensus.
