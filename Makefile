.PHONY: setup run-a run-b run-c test format
setup:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
run-a:
	. .venv/bin/activate && python -m server.app --id A --port 50051 --peers B:50052,C:50053 --data var/nodes/A
run-b:
	. .venv/bin/activate && python -m server.app --id B --port 50052 --peers A:50051,C:50053 --data var/nodes/B
run-c:
	. .venv/bin/activate && python -m server.app --id C --port 50053 --peers A:50051,B:50052 --data var/nodes/C
test:
	. .venv/bin/activate && pytest -q
format:
	. .venv/bin/activate && python -m black server tests
