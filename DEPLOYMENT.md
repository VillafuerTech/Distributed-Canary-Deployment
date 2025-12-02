# Multi-Machine Deployment Guide

The Distributed Canary Deployment System supports running on **3 different computers** with TCP-based communication.

## Setup

### Prerequisites
- Python 3.8+ on each machine
- Network connectivity between all 3 machines
- Ports 60001-60003 and 50051-50053 open for communication

### Prepare Machines

**Step 1: Copy project to each machine**
```bash
# On Machine 1 (Coordinator):
git clone <repo> && cd distributed_systems/project

# On Machine 2 (Participant B):
git clone <repo> && cd distributed_systems/project

# On Machine 3 (Participant C):
git clone <repo> && cd distributed_systems/project
```

**Step 2: Install dependencies on each machine**
```bash
pip install -r requirements.txt
```

## Running on 3 Different Machines

### Configuration
Replace these IP addresses with your actual machine IPs:
- **Machine 1** (Coordinator): `192.168.1.10` (example)
- **Machine 2** (Participant B): `192.168.1.20` (example)
- **Machine 3** (Participant C): `192.168.1.30` (example)

### Method 1: Environment Variables (Recommended)

**Machine 1 - Coordinator Node:**
```bash
export PEERS_NODE_A=192.168.1.10
export PEERS_NODE_B=192.168.1.20
export PEERS_NODE_C=192.168.1.30
python run_nodes.py coordinator
```

**Machine 2 - Participant B Node:**
```bash
export PEERS_NODE_A=192.168.1.10
export PEERS_NODE_B=192.168.1.20
export PEERS_NODE_C=192.168.1.30
python run_nodes.py participant_b
```

**Machine 3 - Participant C Node:**
```bash
export PEERS_NODE_A=192.168.1.10
export PEERS_NODE_B=192.168.1.20
export PEERS_NODE_C=192.168.1.30
python run_nodes.py participant_c
```

### Method 2: With bash script (all 3 machines)

Create a `deploy.sh` script on each machine with the IP configuration:

```bash
#!/bin/bash

export PEERS_NODE_A=192.168.1.10
export PEERS_NODE_B=192.168.1.20
export PEERS_NODE_C=192.168.1.30

if [ "$1" == "coordinator" ]; then
    python run_nodes.py coordinator
elif [ "$1" == "participant_b" ]; then
    python run_nodes.py participant_b
elif [ "$1" == "participant_c" ]; then
    python run_nodes.py participant_c
fi
```

Then run:
```bash
bash deploy.sh coordinator    # On Machine 1
bash deploy.sh participant_b  # On Machine 2
bash deploy.sh participant_c  # On Machine 3
```

## Querying the System

From any machine (or a 4th machine), query the distributed system:

```bash
# First, update the IP addresses in query_system.py if different
python query_system.py
```

Or manually query each node:

```bash
# Coordinator (Machine 1)
curl http://192.168.1.10:50051/routing/state

# Participant B (Machine 2)
curl http://192.168.1.20:50052/routing/state

# Participant C (Machine 3)
curl http://192.168.1.30:50053/routing/state
```

## Network Architecture

### Control Plane (TCP, Distributed Consensus)
- **Node A (Coordinator)**: Listens on port 60001
- **Node B (Participant)**: Listens on port 60002
- **Node C (Participant)**: Listens on port 60003

### Data Plane (HTTP, Query/Predict)
- **Node A (Coordinator)**: Listens on port 50051
  - `GET /routing/state` - Get current routing state
  - `GET /health/snapshot` - Get health metrics
  - `POST /predict` - Predict version for request
  
- **Node B (Participant)**: Listens on port 50052
  - Same endpoints as Node A
  
- **Node C (Participant)**: Listens on port 50053
  - Same endpoints as Node A

## Troubleshooting

### Nodes can't connect
- **Check firewall**: Ensure ports 60001-60003 and 50051-50053 are open
- **Check IPs**: Verify `PEERS_NODE_A`, `PEERS_NODE_B`, `PEERS_NODE_C` match actual machine IPs
- **Check network**: Ping between machines to verify connectivity
  ```bash
  ping 192.168.1.10
  ping 192.168.1.20
  ping 192.168.1.30
  ```

### Nodes not synchronizing
- **Check control plane**: Verify nodes are listening with `netstat -tuln | grep 600`
- **Check data plane**: Verify HTTP is working with `curl http://192.168.1.10:50051/health/snapshot`
- **Check logs**: Review output from each node for connection errors

### Specific IP errors
- **Update PEERS_NODE_* variables** if you used different IPs
- **Ensure all 3 machines** have the same IP configuration
- **Double-check spelling** of IP addresses (no typos)

## Localhost Testing (Single Machine)

If testing on a single machine first, omit the environment variables:

```bash
python run_nodes.py coordinator    # Terminal 1
python run_nodes.py participant_b  # Terminal 2
python run_nodes.py participant_c  # Terminal 3
```

This defaults to `127.0.0.1` and works on a single machine.

## Performance Considerations

- **Latency**: Network latency between machines affects 2PC decision time
- **Bandwidth**: Health snapshots and heartbeats use minimal bandwidth (< 1KB/sec per node)
- **Reliability**: System handles temporary network partitions via timeouts (see node.py)

## Security Notes

For production deployment, consider:
- TLS encryption for TCP control plane
- Authentication between nodes
- Firewall rules to restrict port access
- VPN or private network for node communication

## Monitoring

Monitor each node's output for:
- "Coordinator started" / "Participant started" - Successful startup
- "Connected to peer" - Successful peer connection
- "2PC: COMMIT" / "2PC: ABORT" - Consensus decisions
- "Routing state updated" - State synchronization
