#!/usr/bin/env python3
"""
Distributed Canary Deployment System - All-in-One Node Launcher

Runs all three nodes (Coordinator A, Participant B, Participant C) as separate 
processes in a single script. Each node listens on its own control and data plane ports.

Supports both localhost (single machine) and distributed deployment (3 machines).

Usage (Single Machine - Localhost):
    python run_nodes.py [coordinator|participant_b|participant_c]
    python run_nodes.py  # Run all 3 nodes

Usage (Distributed - 3 Machines):
    # Machine 1 (Coordinator):
    export PEERS_NODE_A=192.168.1.10
    export PEERS_NODE_B=192.168.1.20
    export PEERS_NODE_C=192.168.1.30
    python run_nodes.py coordinator
    
    # Machine 2 (Participant B):
    export PEERS_NODE_A=192.168.1.10
    export PEERS_NODE_B=192.168.1.20
    export PEERS_NODE_C=192.168.1.30
    python run_nodes.py participant_b
    
    # Machine 3 (Participant C):
    export PEERS_NODE_A=192.168.1.10
    export PEERS_NODE_B=192.168.1.20
    export PEERS_NODE_C=192.168.1.30
    python run_nodes.py participant_c
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from distributed_canary.node import Node
from distributed_canary.tcp_network import TCPNetwork


# Peer configuration - supports both localhost and distributed deployment
# Use environment variables PEERS_NODE_A, PEERS_NODE_B, PEERS_NODE_C for distributed setup
# Otherwise defaults to localhost (127.0.0.1)
NODE_A_IP = os.getenv("PEERS_NODE_A", "128.214.11.91")
NODE_B_IP = os.getenv("PEERS_NODE_B", "128.214.9.25")
NODE_C_IP = os.getenv("PEERS_NODE_C", "128.214.9.26")

PEERS_CONFIG = {
    "node-a": (NODE_A_IP, 60001),
    "node-b": (NODE_B_IP, 60002),
    "node-c": (NODE_C_IP, 60003),
}

# Data plane ports for each node
DATA_PLANE_PORTS = {
    "node-a": 50051,
    "node-b": 50052,
    "node-c": 50053,
}


async def run_coordinator():
    """Run node-a as the coordinator on all interfaces port 60001."""
    network = TCPNetwork(PEERS_CONFIG)
    node = Node("node-a", "coordinator", ["node-a", "node-b", "node-c"], network)

    # Start listening for peer connections (0.0.0.0 = all interfaces)
    listen_task = asyncio.create_task(
        network.start_listening("0.0.0.0", 60001, node.inbox.put)
    )

    # Start processing messages, heartbeats, health snapshots, data plane
    msg_task = asyncio.create_task(node.process_messages())
    hb_task = asyncio.create_task(node.send_heartbeat_loop())
    health_task = asyncio.create_task(node.send_health_snapshots())
    data_plane_task = asyncio.create_task(node.start_data_plane(50051))

    print(f"[{node.node_id}] Coordinator started, listening on 0.0.0.0:60001")
    print(f"[{node.node_id}] Data plane on 0.0.0.0:50051")
    print(f"[{node.node_id}] Peers: {PEERS_CONFIG}")

    # Allow tasks to warm up before initiating rollouts
    await asyncio.sleep(2)

    try:
        print(f"[{node.node_id}] Initiating first rollout (5% canary)...")
        await node.initiate_rollout(canary_share=0.05)
        await asyncio.sleep(2)

        print(f"[{node.node_id}] Extending to 20% canary...")
        await node.initiate_rollout(canary_share=0.2)
        await asyncio.sleep(2)

        print(f"[{node.node_id}] Extending to 50% canary...")
        await node.initiate_rollout(canary_share=0.5)
        await asyncio.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        node.running = False


async def run_participant_b():
    """Run node-b as a participant on all interfaces port 60002."""
    network = TCPNetwork(PEERS_CONFIG)
    node = Node("node-b", "participant", ["node-a", "node-b", "node-c"], network)

    # Start listening for peer connections (0.0.0.0 = all interfaces)
    listen_task = asyncio.create_task(
        network.start_listening("0.0.0.0", 60002, node.inbox.put)
    )

    # Start processing messages, heartbeats, health snapshots, data plane
    msg_task = asyncio.create_task(node.process_messages())
    hb_task = asyncio.create_task(node.send_heartbeat_loop())
    health_task = asyncio.create_task(node.send_health_snapshots())
    data_plane_task = asyncio.create_task(node.start_data_plane(50052))

    print(f"[{node.node_id}] Participant started, listening on 0.0.0.0:60002")
    print(f"[{node.node_id}] Data plane on 0.0.0.0:50052")
    print(f"[{node.node_id}] Peers: {PEERS_CONFIG}")

    try:
        await asyncio.gather(
            listen_task, msg_task, hb_task, health_task, data_plane_task
        )
    except KeyboardInterrupt:
        node.running = False
        print(f"[{node.node_id}] Shutting down...")


async def run_participant_c():
    """Run node-c as a participant on all interfaces port 60003."""
    network = TCPNetwork(PEERS_CONFIG)
    node = Node("node-c", "participant", ["node-a", "node-b", "node-c"], network)

    # Start listening for peer connections (0.0.0.0 = all interfaces)
    listen_task = asyncio.create_task(
        network.start_listening("0.0.0.0", 60003, node.inbox.put)
    )

    # Start processing messages, heartbeats, health snapshots, data plane
    msg_task = asyncio.create_task(node.process_messages())
    hb_task = asyncio.create_task(node.send_heartbeat_loop())
    health_task = asyncio.create_task(node.send_health_snapshots())
    data_plane_task = asyncio.create_task(node.start_data_plane(50053))

    print(f"[{node.node_id}] Participant started, listening on 0.0.0.0:60003")
    print(f"[{node.node_id}] Data plane on 0.0.0.0:50053")
    print(f"[{node.node_id}] Peers: {PEERS_CONFIG}")

    try:
        await asyncio.gather(
            listen_task, msg_task, hb_task, health_task, data_plane_task
        )
    except KeyboardInterrupt:
        node.running = False
        print(f"[{node.node_id}] Shutting down...")


async def run_all_nodes():
    """Run all three nodes concurrently."""
    await asyncio.gather(
        run_coordinator(),
        run_participant_b(),
        run_participant_c(),
        return_exceptions=True,
    )


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        # Run specific node
        node_type = sys.argv[1].lower()
        if node_type == "coordinator":
            asyncio.run(run_coordinator())
        elif node_type == "participant_b":
            asyncio.run(run_participant_b())
        elif node_type == "participant_c":
            asyncio.run(run_participant_c())
        else:
            print(f"Unknown node type: {node_type}")
            print("Usage: python run_nodes.py [coordinator|participant_b|participant_c]")
            sys.exit(1)
    else:
        # Run all nodes together
        print("Starting all three nodes...\n")
        asyncio.run(run_all_nodes())


if __name__ == "__main__":
    main()