# Makefile — developer shortcuts for the ADK Summarizer Agent
# Usage: make <target>
# Requires: PROJECT_ID env var or pass as: make deploy PROJECT_ID=my-project

PROJECT_ID   ?= $(shell gcloud config get-value project 2>/dev/null)
REGION       ?= us-central1
SERVICE_NAME ?= adk-summarizer-agent
REPO         ?= cloud-run-agents
IMAGE        := $(REGION)-docker.pkg.dev/$(PROJECT_ID)/$(REPO)/$(SERVICE_NAME)

.PHONY: help setup install run lint docker-build docker-run deploy logs url test

help:
	@echo ""
	@echo "ADK Summarizer Agent — available targets"
	@echo "────────────────────────────────────────────"
	@echo "  make setup        Bootstrap GCP project (run once)"
	@echo "  make install      Install Python deps locally"
	@echo "  make run          Run server locally"
	@echo "  make lint         Run ruff linter"
	@echo "  make docker-build Build Docker image locally"
	@echo "  make docker-run   Run Docker image locally"
	@echo "  make deploy       Build + push + deploy via Cloud Build"
	@echo "  make logs         Tail Cloud Run logs"
	@echo "  make url          Print the Cloud Run service URL"
	@echo "  make test         Quick smoke test against live URL"
	@echo ""

setup:
	bash setup.sh $(PROJECT_ID) $(REGION)

install:
	pip install -r requirements.txt

run:
	python main.py

lint:
	ruff check . || true

docker-build:
	docker build -t $(SERVICE_NAME):local .

docker-run:
	docker run --rm -p 8080:8080 \
	  --env-file .env \
	  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/key.json \
	  $(SERVICE_NAME):local

deploy:
	gcloud builds submit \
	  --config=cloudbuild.yaml \
	  --substitutions=_REGION=$(REGION),_SERVICE_NAME=$(SERVICE_NAME),_REPOSITORY=$(REPO) \
	  --project=$(PROJECT_ID)

logs:
	gcloud run services logs tail $(SERVICE_NAME) --region=$(REGION) --project=$(PROJECT_ID)

url:
	@gcloud run services describe $(SERVICE_NAME) \
	  --region=$(REGION) --project=$(PROJECT_ID) \
	  --format='value(status.url)'

test:
	$(eval URL := $(shell make url --no-print-directory))
	@echo "Testing: $(URL)"
	@curl -sf $(URL)/health | python3 -m json.tool
	@curl -sf -X POST $(URL)/run \
	  -H "Content-Type: application/json" \
	  -d '{"text":"The James Webb Space Telescope (JWST) is a space telescope designed to conduct infrared astronomy. Its high-resolution and high-sensitivity instruments allow it to view objects too old, distant, or faint for the Hubble Space Telescope. It is the largest optical telescope in space and its greatly improved infrared resolution and sensitivity allows it to view objects too old, distant, or faint. JWST was launched in December 2021 and reached its destination, the Sun-Earth L2 point, in January 2022.", "user_id": "smoke-test"}' \
	| python3 -m json.tool
