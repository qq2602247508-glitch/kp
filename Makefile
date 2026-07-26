.PHONY: setup dev backend frontend check isolation

setup:
	./scripts/setup.sh

dev:
	./scripts/dev.sh

backend:
	./scripts/dev-backend.sh

frontend:
	./scripts/dev-frontend.sh

check:
	./scripts/check.sh

isolation:
	./scripts/check-domain-isolation.sh

