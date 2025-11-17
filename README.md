# Canary Model Rollout Orchestrator (Prototype)

Three server nodes agree on versioned routing state via 2PC to perform safe canary rollouts (5%→10%→50%→100%). Nodes keep append-only logs + snapshots and recover on crash. HTTP/JSON only; runs on separate VMs with distinct IPs.

## Quickstart
```bash
make setup
make run-a | make run-b | make run-c
# promote via scripts/promote.py (see docs/demo-checklist.md)

