#!/usr/bin/env python3
"""Utility script to test the distributed canary system."""

import asyncio
import json
import sys
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).parent))


async def query_node_state(node_port: int, node_name: str) -> None:
    """Query a node's routing state, health, and predict endpoints."""
    base_url = f"http://127.0.0.1:{node_port}"

    async with aiohttp.ClientSession() as session:
        try:
            # Get routing state
            async with session.get(f"{base_url}/routing/state") as resp:
                if resp.status == 200:
                    state = await resp.json()
                    print(f"\n[{node_name}] Routing State v{state['version']}")
                    print(f"  Status: {state['status']}")
                    print(f"  Weights: {state['weights']}")
                else:
                    print(f"[{node_name}] Routing state unavailable (status {resp.status})")

            # Get health snapshot
            async with session.get(f"{base_url}/health/snapshot") as resp:
                if resp.status == 200:
                    health = await resp.json()
                    print(f"\n[{node_name}] Health Snapshot")
                    print(
                        f"  P95: {health['p95']:.1f}ms, Error Rate: {health['error_rate']*100:.2f}%"
                    )
                else:
                    print(f"[{node_name}] Health snapshot unavailable")

            # Test prediction (should route to v1 or v2 based on weights)
            async with session.post(
                f"{base_url}/predict", json={"test": "input"}
            ) as resp:
                if resp.status == 200:
                    pred = await resp.json()
                    print(
                        f"\n[{node_name}] Prediction routed to: {pred['model_selected']}"
                    )
                else:
                    print(f"[{node_name}] Prediction unavailable")

        except aiohttp.ClientConnectorError:
            print(f"\n[{node_name}] Cannot connect to {base_url}")


async def main():
    """Query all three nodes."""
    print("=" * 60)
    print("Querying Canary Deployment System State")
    print("=" * 60)

    await query_node_state(50051, "Node A")
    await query_node_state(50052, "Node B")
    await query_node_state(50053, "Node C")


if __name__ == "__main__":
    asyncio.run(main())
