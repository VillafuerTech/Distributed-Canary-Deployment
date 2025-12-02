# Step-by-Step Deployment Guide for 3 Computers

Follow this guide to deploy the Distributed Canary Deployment System across 3 different machines.

---

## PHASE 1: PREPARATION (Do This First)

### Step 1.1: Identify Your Machine IPs

Open a terminal on each machine and find its IP address:

```bash
# On Linux/Mac:
ifconfig | grep "inet " | grep -v "127.0.0.1"

# On Windows (use Command Prompt):
ipconfig
```

**Document these IPs:**
- Machine 1 (Coordinator): `_________________`
- Machine 2 (Participant B): `_________________`
- Machine 3 (Participant C): `_________________`

Example:
```
Machine 1 (Coordinator):     192.168.1.100
Machine 2 (Participant B):   192.168.1.101
Machine 3 (Participant C):   192.168.1.102
```

### Step 1.2: Verify Network Connectivity

Ping between machines to ensure they can communicate:

```bash
# From Machine 1, ping Machine 2:
ping 192.168.1.101

# From Machine 1, ping Machine 3:
ping 192.168.1.102

# From Machine 2, ping Machine 1:
ping 192.168.1.100

# (etc. - all should respond)
```

**If ping fails:** Check firewall settings and ensure machines are on the same network.

### Step 1.3: Open Required Ports

Ensure these ports are open on all machines:

**Control Plane (TCP, Peer Communication):**
- Port 60001 (Node A)
- Port 60002 (Node B)
- Port 60003 (Node C)

**Data Plane (HTTP, API Queries):**
- Port 50051 (Node A)
- Port 50052 (Node B)
- Port 50053 (Node C)

**On Linux (ufw):**
```bash
sudo ufw allow 60001:60003/tcp
sudo ufw allow 50051:50053/tcp
```

**On Mac:** Skip (no firewall blocks localhost traffic by default)

**On Windows:** Open Windows Defender Firewall → Advanced Settings → Inbound Rules → Create rules for ports above

---

## PHASE 2: PROJECT SETUP (Do This on All 3 Machines)

### Step 2.1: Copy Project Files to Each Machine

**Option A: Using Git (Recommended)**
```bash
git clone <your-repo-url> distributed_systems
cd distributed_systems/project
```

**Option B: Manual Copy (if no git)**
1. Zip the entire `distributed_systems/project` folder on Machine 1
2. Copy the zip file to Machine 2 and Machine 3
3. Extract on each machine

### Step 2.2: Verify Project Structure

On each machine, verify the files are present:

```bash
cd distributed_systems/project
ls -la
```

Expected output:
```
distributed_canary/          ← directory
COMPLIANCE.md
DEPLOYMENT.md
DESIGN_PLAN.md
DEPLOYMENT_STEPS.md
PROJECT_STATUS.md
README.md
query_system.py
requirements.txt
run_demo.sh
run_nodes.py
test_integration.py
```

### Step 2.3: Install Python Dependencies

**On each machine:**

```bash
cd distributed_systems/project
pip install -r requirements.txt
```

This installs `aiohttp>=3.9` (required for HTTP server).

Verify installation:
```bash
python -c "import aiohttp; print('aiohttp installed successfully')"
```

---

## PHASE 3: CONFIGURATION (Do This on All 3 Machines)

### Step 3.1: Create Configuration Script

On **each of the 3 machines**, create a file called `config.sh`:

```bash
cat > config.sh << 'EOF'
#!/bin/bash

# Replace these with YOUR actual machine IPs
export PEERS_NODE_A=192.168.1.100      # Machine 1 (Coordinator) IP
export PEERS_NODE_B=192.168.1.101      # Machine 2 (Participant B) IP
export PEERS_NODE_C=192.168.1.102      # Machine 3 (Participant C) IP

echo "Configuration loaded:"
echo "  Node A (Coordinator): $PEERS_NODE_A:60001"
echo "  Node B (Participant): $PEERS_NODE_B:60002"
echo "  Node C (Participant): $PEERS_NODE_C:60003"
EOF

chmod +x config.sh
```

**IMPORTANT:** Update the IP addresses in `config.sh` with your actual machine IPs from Step 1.1.

### Step 3.2: Verify Configuration

```bash
source config.sh
```

You should see output showing all 3 node IPs.

---

## PHASE 4: DEPLOYMENT (Start on All 3 Machines)

### Step 4.1: Open 3 Terminal Windows

You need **3 terminal windows** (or SSH sessions):
- Terminal 1 → Machine 1 (Coordinator)
- Terminal 2 → Machine 2 (Participant B)
- Terminal 3 → Machine 3 (Participant C)

### Step 4.2: Start Node on Machine 1 (Coordinator)

**In Terminal 1 on Machine 1:**

```bash
cd ~/distributed_systems/project
source config.sh
python run_nodes.py coordinator
```

**Expected output:**
```
[node-a] Coordinator started, listening on 0.0.0.0:60001
[node-a] Data plane on 0.0.0.0:50051
[node-a] Peers: {'node-a': ('192.168.1.100', 60001), 'node-b': ('192.168.1.101', 60002), 'node-c': ('192.168.1.102', 60003)}
[node-a] Initiating first rollout (5% canary)...
```

✅ **Success:** Node A is running and waiting for peers.

### Step 4.3: Start Node on Machine 2 (Participant B)

**In Terminal 2 on Machine 2:**

```bash
cd ~/distributed_systems/project
source config.sh
python run_nodes.py participant_b
```

**Expected output:**
```
[node-b] Participant started, listening on 0.0.0.0:60002
[node-b] Data plane on 0.0.0.0:50052
[node-b] Peers: {'node-a': ('192.168.1.100', 60001), 'node-b': ('192.168.1.101', 60002), 'node-c': ('192.168.1.102', 60003)}
```

✅ **Success:** Node B is running and connected to the network.

### Step 4.4: Start Node on Machine 3 (Participant C)

**In Terminal 3 on Machine 3:**

```bash
cd ~/distributed_systems/project
source config.sh
python run_nodes.py participant_c
```

**Expected output:**
```
[node-c] Participant started, listening on 0.0.0.0:60003
[node-c] Data plane on 0.0.0.0:50053
[node-c] Peers: {'node-a': ('192.168.1.100', 60001), 'node-b': ('192.168.1.101', 60002), 'node-c': ('192.168.1.102', 60003)}
```

✅ **Success:** All 3 nodes are running!

---

## PHASE 5: VERIFICATION (Do This on Any Machine)

### Step 5.1: Query System State

**From any of the 3 machines (or a 4th machine on the network):**

```bash
cd ~/distributed_systems/project
source config.sh
python query_system.py
```

**Expected output:**
```
============================================================
Querying Canary Deployment System State
============================================================

[Node A] Routing State v1
  Status: COMMITTED
  Weights: {'v1': 1.0, 'v2': 0.0}

[Node A] Health Snapshot
  P95: 120.0ms, Error Rate: 10.00%

[Node A] Prediction routed to: v1

[Node B] Routing State v1
  Status: COMMITTED
  Weights: {'v1': 1.0, 'v2': 0.0}

[Node B] Health Snapshot
  P95: 117.3ms, Error Rate: 10.02%

[Node B] Prediction routed to: v1

[Node C] Routing State v1
  Status: COMMITTED
  Weights: {'v1': 1.0, 'v2': 0.0}

[Node C] Health Snapshot
  P95: 117.9ms, Error Rate: 10.62%

[Node C] Prediction routed to: v1
```

✅ **Success:** All 3 nodes are synchronized!

### Step 5.2: Manual HTTP Queries

Query each node's API directly:

```bash
# Query Node A
curl http://192.168.1.100:50051/routing/state

# Query Node B
curl http://192.168.1.101:50052/routing/state

# Query Node C
curl http://192.168.1.102:50053/routing/state
```

All three should return **identical state** (same version, status, weights).

---

## PHASE 6: MONITORING & TROUBLESHOOTING

### Monitoring During Deployment

While nodes are running, you should see periodic output in each terminal:

```
[node-a] Heartbeat sent to peers
[node-a] Health snapshots sent to peers
[node-a] Processing message from node-b: MessageType.HEARTBEAT
```

This shows nodes are communicating. If you don't see this, nodes aren't connected.

### Troubleshooting Common Issues

#### Issue: "Connection refused" or "Network unreachable"

**Cause:** Nodes can't reach each other's IPs.

**Solution:**
1. Verify IPs in `config.sh` are correct:
   ```bash
   cat config.sh | grep PEERS_NODE
   ```
2. Ping each machine:
   ```bash
   ping 192.168.1.100  # ping all 3 IPs
   ```
3. Check ports are open:
   ```bash
   netstat -tuln | grep 600  # should show 60001, 60002, 60003
   ```

#### Issue: Nodes start but don't synchronize

**Cause:** Firewall blocking communication.

**Solution:**
1. Check if ports are listening:
   ```bash
   # On each machine, verify ports are open:
   netstat -tuln | grep LISTEN | grep -E "600[123]|500[123]"
   ```
2. Disable firewall temporarily to test:
   ```bash
   sudo ufw disable  # Linux only
   ```
3. Re-enable with specific rules:
   ```bash
   sudo ufw enable
   sudo ufw allow 60001:60003/tcp
   sudo ufw allow 50051:50053/tcp
   ```

#### Issue: `python: command not found`

**Cause:** Python not installed or not in PATH.

**Solution:**
```bash
# Check Python installation
python3 --version

# Use python3 instead of python
python3 run_nodes.py coordinator
```

#### Issue: `ModuleNotFoundError: No module named 'aiohttp'`

**Cause:** Dependencies not installed.

**Solution:**
```bash
pip install -r requirements.txt
# Or if using Python 3:
pip3 install -r requirements.txt
```

---

## PHASE 7: STOPPING & CLEANUP

### Stop Nodes Gracefully

Press `Ctrl+C` in each terminal window:

```bash
^C  # In Terminal 1, Terminal 2, Terminal 3
```

Each node will shut down cleanly.

### View Logs

Each node saves its state log:

```bash
# On each machine:
ls -la logs/
cat logs/node-a.log      # On Machine 1
cat logs/node-b.log      # On Machine 2
cat logs/node-c.log      # On Machine 3
```

These logs show the complete history of state changes and can be replayed for recovery.

---

## QUICK REFERENCE SUMMARY

| Step | Action | Machine | Command |
|------|--------|---------|---------|
| 1 | Get IP address | All | `ifconfig` / `ipconfig` |
| 2 | Test connectivity | All | `ping <other-machine-ip>` |
| 3 | Open ports | All | `sudo ufw allow 60001:60003/tcp` |
| 4 | Copy project | All | `git clone <repo>` |
| 5 | Install dependencies | All | `pip install -r requirements.txt` |
| 6 | Create config | All | Create `config.sh` with actual IPs |
| 7 | Start Node A | Machine 1 | `source config.sh && python run_nodes.py coordinator` |
| 8 | Start Node B | Machine 2 | `source config.sh && python run_nodes.py participant_b` |
| 9 | Start Node C | Machine 3 | `source config.sh && python run_nodes.py participant_c` |
| 10 | Verify | Any | `python query_system.py` |

---

## NETWORK DIAGRAM

```
                    Network (Ethernet/WiFi)
                         /     |      \
                        /      |       \
            Machine 1           Machine 2           Machine 3
        192.168.1.100       192.168.1.101       192.168.1.102
        ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
        │  Node A      │    │  Node B      │    │  Node C      │
        │(Coordinator) │    │(Participant) │    │(Participant) │
        │              │    │              │    │              │
        │ 60001 (ctrl) │←──→│ 60002 (ctrl) │←──→│ 60003 (ctrl) │
        │ 50051 (data) │    │ 50052 (data) │    │ 50053 (data) │
        └──────────────┘    └──────────────┘    └──────────────┘
             (Listens)           (Listens)           (Listens)
           on 0.0.0.0:*        on 0.0.0.0:*        on 0.0.0.0:*
```

**Control Plane (TCP 60001-60003):** Two-Phase Commit consensus messages
**Data Plane (HTTP 50051-50053):** Query and prediction endpoints

---

## NEXT STEPS

✅ After successful deployment:

1. **Test State Changes:** Modify weights on one node and verify all sync
2. **Simulate Failures:** Stop one node, restart it, verify recovery
3. **Monitor Logs:** Check `logs/node-*.log` for state changes
4. **Performance Test:** Query endpoints under load
5. **Production Hardening:** Add TLS, authentication, monitoring (see DEPLOYMENT.md)

---

## NEED HELP?

- **System Design:** See `DESIGN_PLAN.md`
- **Requirements Compliance:** See `COMPLIANCE.md`
- **Architecture Details:** See `README.md`
- **Advanced Deployment:** See `DEPLOYMENT.md`
