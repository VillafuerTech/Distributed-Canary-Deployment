#!/usr/bin/env python3
"""
Simple Distributed Deployment System - Version Rollout with 2PC

Deploys new versions atomically to all nodes using 2-Phase Commit.
Each node runs on a separate physical machine.

Usage (Distributed - 3 Machines):
    # Machine 1 (Coordinator):
    export PEERS_NODE_A=<Machine1_IP>
    export PEERS_NODE_B=<Machine2_IP>
    export PEERS_NODE_C=<Machine3_IP>
    python run_nodes.py coordinator
    
    # Machine 2 (Participant B):
    export PEERS_NODE_A=<Machine1_IP>
    export PEERS_NODE_B=<Machine2_IP>
    export PEERS_NODE_C=<Machine3_IP>
    python run_nodes.py participant_b
    
    # Machine 3 (Participant C):
    export PEERS_NODE_A=<Machine1_IP>
    export PEERS_NODE_B=<Machine2_IP>
    export PEERS_NODE_C=<Machine3_IP>
    python run_nodes.py participant_c

Ports:
    - Control Plane (TCP): 60001 (all nodes use same port on different machines)
    - Data Plane (HTTP):   50051 (all nodes use same port on different machines)
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from distributed_canary.node import Node
from distributed_canary.tcp_network import TCPNetwork


# Peer configuration - MUST set environment variables for distributed deployment
NODE_A_IP = os.getenv("PEERS_NODE_A", "128.214.11.91")
NODE_B_IP = os.getenv("PEERS_NODE_B", "128.214.9.25")
NODE_C_IP = os.getenv("PEERS_NODE_C", "128.214.9.26")

# All nodes use the same ports (running on different machines)
CONTROL_PORT = 60001
DATA_PORT = 50051

PEERS_CONFIG = {
    "node-a": (NODE_A_IP, CONTROL_PORT),
    "node-b": (NODE_B_IP, CONTROL_PORT),
    "node-c": (NODE_C_IP, CONTROL_PORT),
}


def check_env_vars():
    """Ensure all required environment variables are set."""
    missing = []
    if not NODE_A_IP:
        missing.append("PEERS_NODE_A")
    if not NODE_B_IP:
        missing.append("PEERS_NODE_B")
    if not NODE_C_IP:
        missing.append("PEERS_NODE_C")
    
    if missing:
        print("ERROR: Missing required environment variables:")
        for var in missing:
            print(f"  - {var}")
        print("\nSet them with your machine IPs:")
        print("  export PEERS_NODE_A=<Machine1_IP>")
        print("  export PEERS_NODE_B=<Machine2_IP>")
        print("  export PEERS_NODE_C=<Machine3_IP>")
        sys.exit(1)


async def run_coordinator():
    """Run coordinator node (Machine 1)."""
    network = TCPNetwork(PEERS_CONFIG)
    node = Node("node-a", "coordinator", ["node-a", "node-b", "node-c"], network)

    listen_task = asyncio.create_task(network.start_listening("0.0.0.0", CONTROL_PORT, node.inbox.put))
    msg_task = asyncio.create_task(node.process_messages())
    hb_task = asyncio.create_task(node.send_heartbeat_loop())
    data_plane_task = asyncio.create_task(node.start_data_plane(DATA_PORT))

    print(f"\n[{node.node_id}] Coordinator ready")
    print(f"[{node.node_id}] Current model: {node.state.model_id}")
    print(f"[{node.node_id}] Control plane: 0.0.0.0:{CONTROL_PORT}")
    print(f"[{node.node_id}] Data plane:    http://0.0.0.0:{DATA_PORT}")
    print(f"[{node.node_id}] Peers: node-a={NODE_A_IP}, node-b={NODE_B_IP}, node-c={NODE_C_IP}")
    print(f"\n[{node.node_id}] Waiting for participants to connect...\n")

    await asyncio.sleep(5)  # Wait for participants to start

    # Demo: Deploy v2, then v3
    print(f"\n[{node.node_id}] Demo: Deploying v2...")
    await node.deploy_version("v2")
    
    await asyncio.sleep(3)
    
    print(f"\n[{node.node_id}] Demo: Deploying v3...")
    await node.deploy_version("v3")

    # Keep running
    try:
        await asyncio.gather(listen_task, msg_task, hb_task, data_plane_task)
    except KeyboardInterrupt:
        node.running = False


async def run_participant(node_id: str):
    """Run participant node (Machine 2 or 3)."""
    network = TCPNetwork(PEERS_CONFIG)
    node = Node(node_id, "participant", ["node-a", "node-b", "node-c"], network)

    listen_task = asyncio.create_task(network.start_listening("0.0.0.0", CONTROL_PORT, node.inbox.put))
    msg_task = asyncio.create_task(node.process_messages())
    hb_task = asyncio.create_task(node.send_heartbeat_loop())
    data_plane_task = asyncio.create_task(node.start_data_plane(DATA_PORT))

    print(f"\n[{node.node_id}] Participant ready")
    print(f"[{node.node_id}] Current model: {node.state.model_id}")
    print(f"[{node.node_id}] Control plane: 0.0.0.0:{CONTROL_PORT}")
    print(f"[{node.node_id}] Data plane:    http://0.0.0.0:{DATA_PORT}")
    print(f"[{node.node_id}] Peers: node-a={NODE_A_IP}, node-b={NODE_B_IP}, node-c={NODE_C_IP}\n")

    try:
        await asyncio.gather(listen_task, msg_task, hb_task, data_plane_task)
    except KeyboardInterrupt:
        node.running = False


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("ERROR: You must specify a node type.")
        print("\nUsage: python run_nodes.py <coordinator|participant_b|participant_c>")
        print("\nThis system requires 3 separate machines.")
        print("Run one node type per machine.")
        sys.exit(1)
    
    check_env_vars()
    
    node_type = sys.argv[1].lower()
    if node_type == "coordinator":
        asyncio.run(run_coordinator())
    elif node_type == "participant_b":
        asyncio.run(run_participant("node-b"))
    elif node_type == "participant_c":
        asyncio.run(run_participant("node-c"))
    else:
        print(f"Unknown node type: {node_type}")
        print("Usage: python run_nodes.py <coordinator|participant_b|participant_c>")
        sys.exit(1)


if __name__ == "__main__":
    main()