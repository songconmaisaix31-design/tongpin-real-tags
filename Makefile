.PHONY: fleet-validate fleet-test fleet-gate fleet-status

fleet-validate:
	python scripts/fleet.py validate .agents/plans/hackathon-prize.json

fleet-test:
	python -m unittest discover -s scripts/tests -v

fleet-gate:
	python scripts/gate.py check --run-checks

fleet-status:
	@echo "Usage: python scripts/fleet.py status --state .agents/runs/<RUN>/state.json"
