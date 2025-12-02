#!/bin/bash
# Distributed Canary Deployment System - Demo Script
# Starts all three nodes and demonstrates consensus

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

CONDA_ENV="/home/selindemirturk/miniconda3/envs/distributed_systems"
PYTHON="$CONDA_ENV/bin/python"

echo "Starting distributed canary deployment system..."
echo "=================================================="

# Start all three nodes in background
$PYTHON run_nodes.py > /tmp/system.log 2>&1 &
SYSTEM_PID=$!
sleep 4

# Query system state
echo ""
echo "Querying system state..."
echo "=================================================="
$PYTHON query_system.py

# Let it run for a bit longer
echo ""
echo "System running for 5 seconds..."
sleep 5

# Cleanup
echo ""
echo "Shutting down system..."
kill $SYSTEM_PID 2>/dev/null || true
wait 2>/dev/null || true

echo ""
echo "System logs (last 40 lines):"
echo "=================================================="
tail -40 /tmp/system.log

echo ""
echo "Cleaning up state logs..."
rm -rf logs
echo "Done!"
