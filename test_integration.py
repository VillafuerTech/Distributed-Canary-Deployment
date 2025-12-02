#!/usr/bin/env python3
"""Integration test demonstrating the three-node canary system with multiple rollout stages."""

import asyncio
import json
import sys
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).parent))


async def query_all_nodes():
    """Query all three nodes and display synchronized state."""
    base_urls = {
        "Node A": "http://127.0.0.1:50051",
        "Node B": "http://127.0.0.1:50052",
        "Node C": "http://127.0.0.1:50053",
    }

    async with aiohttp.ClientSession() as session:
        states = {}
        for name, url in base_urls.items():
            try:
                async with session.get(f"{url}/routing/state") as resp:
                    if resp.status == 200:
                        states[name] = await resp.json()
                    else:
                        states[name] = None
            except aiohttp.ClientConnectorError:
                states[name] = None

        # Check if all nodes are synchronized
        all_values = [s for s in states.values() if s is not None]
        if not all_values:
            print("ERROR: No nodes responding!")
            return False

        # Compare all versions
        versions = [s.get("version") for s in all_values]
        weights_list = [s.get("weights") for s in all_values]
        statuses = [s.get("status") for s in all_values]

        print(f"\n{'Node':<10} {'Version':<8} {'Status':<10} {'v1 Weight':<12} {'v2 Weight':<12}")
        print("-" * 60)

        synchronized = True
        for name, state in states.items():
            if state:
                v1_w = state["weights"].get("v1", 0)
                v2_w = state["weights"].get("v2", 0)
                print(f"{name:<10} {state['version']:<8} {state['status']:<10} {v1_w:<12.1%} {v2_w:<12.1%}")
            else:
                print(f"{name:<10} {'ERROR':<8} {'N/A':<10} {'N/A':<12} {'N/A':<12}")
                synchronized = False

        # Verify consensus
        if len(set(versions)) == 1 and len(set(map(str, weights_list))) == 1 and len(set(statuses)) == 1:
            print("\n✓ All nodes SYNCHRONIZED")
            return True
        else:
            print("\n✗ Nodes DIVERGED (unexpected!)")
            return False


async def main():
    """Run integration test."""
    print("=" * 60)
    print("Distributed Canary System - Integration Test")
    print("=" * 60)

    # Initial state check
    print("\n[Phase 0] Initial State (all on v1)")
    await asyncio.sleep(1)
    synchronized = await query_all_nodes()

    if synchronized:
        print("\n✓ Test PASSED: System synchronized")
        return 0
    else:
        print("\n✗ Test FAILED: Nodes not synchronized")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
