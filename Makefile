JIRA_EMU_IMAGE ?= jira-emulator
JIRA_EMU_CONTAINER ?= jira-emulator
JIRA_EMU_PORT ?= 8080
JIRA_EMU_MCP_PORT ?= 8081
JIRA_EMU_USER ?= admin
JIRA_EMU_TOKEN ?= jira-emulator-default-token
CONTAINER_ENGINE ?= podman

.PHONY: build run stop restart logs status clean test lint lint-fix typecheck ci integration serve serve-mcp serve-all data-init env

build:
	$(CONTAINER_ENGINE) build -t $(JIRA_EMU_IMAGE) .

run: build
	$(CONTAINER_ENGINE) run -d \
		--name $(JIRA_EMU_CONTAINER) \
		-p $(JIRA_EMU_PORT):8080 \
		-p $(JIRA_EMU_MCP_PORT):8081 \
		-v jira-emulator-data:/data \
		$(JIRA_EMU_IMAGE)
	@echo "Jira Emulator API: http://localhost:$(JIRA_EMU_PORT)"
	@echo "Jira MCP server:   http://localhost:$(JIRA_EMU_MCP_PORT)/sse"

stop:
	-$(CONTAINER_ENGINE) stop $(JIRA_EMU_CONTAINER)
	-$(CONTAINER_ENGINE) rm $(JIRA_EMU_CONTAINER)

restart: stop run

logs:
	$(CONTAINER_ENGINE) logs -f $(JIRA_EMU_CONTAINER)

status:
	@$(CONTAINER_ENGINE) ps -f name=$(JIRA_EMU_CONTAINER) --format "{{.Names}}\t{{.Status}}\t{{.Ports}}"

clean: stop
	-$(CONTAINER_ENGINE) rmi $(JIRA_EMU_IMAGE)
	-$(CONTAINER_ENGINE) volume rm jira-emulator-data

test:
	uv run pytest tests/ -x -q

lint:
	uv run ruff check src/ tests/ mcp_servers/
	uv run ruff format --check src/ tests/ mcp_servers/
	uv run mypy src/

lint-fix:
	uv run ruff check --fix src/ tests/ mcp_servers/
	uv run ruff format src/ tests/ mcp_servers/

typecheck:
	uv run mypy src/

ci: lint test

integration:
	@./scripts/run-integration-tests.sh

DATABASE_URL ?= sqlite+aiosqlite:///data/jira.db

env:
	@echo "# Jira Emulator environment — paste into your shell:"
	@echo "export JIRA_EMU_SERVER=http://localhost:$(JIRA_EMU_PORT)"
	@echo "export JIRA_EMU_USER=$(JIRA_EMU_USER)"
	@echo "export JIRA_EMU_TOKEN=$(JIRA_EMU_TOKEN)"
	@echo "export JIRA_EMU_MCP_PORT=$(JIRA_EMU_MCP_PORT)"
	@echo ""
	@echo "# Point standard Jira env vars at the emulator (for scripts, CLIs, Claude sessions):"
	@echo "export JIRA_URL=http://localhost:$(JIRA_EMU_PORT)"
	@echo "export JIRA_USERNAME=$(JIRA_EMU_USER)"
	@echo "export JIRA_API_TOKEN=$(JIRA_EMU_TOKEN)"
	@echo ""
	@echo "# Or run:  eval \$$(make env)"
	@echo "#"
	@echo "# WARNING: This overrides JIRA_URL/JIRA_USERNAME/JIRA_API_TOKEN in your shell."
	@echo "# Your production Jira credentials will be masked until you open a new shell."

data-init:
	@case "$(DATABASE_URL)" in \
		sqlite*:///*) \
			db_path=$$(echo "$(DATABASE_URL)" | sed 's|.*:///||'); \
			mkdir -p "$$(dirname $$db_path)"; \
			echo "Created $$(dirname $$db_path)/ directory for local database storage";; \
		*) \
			echo "DATABASE_URL is not a local SQLite file path — nothing to initialize";; \
	esac

serve:
	@case "$(DATABASE_URL)" in \
		sqlite*:///*) \
			db_path=$$(echo "$(DATABASE_URL)" | sed 's|.*:///||'); \
			if [ ! -d "$$(dirname $$db_path)" ]; then \
				echo "Error: directory '$$(dirname $$db_path)' does not exist. Run 'make data-init' first."; \
				exit 1; \
			fi;; \
	esac
	DATABASE_URL=$(DATABASE_URL) uv run python -m jira_emulator serve --port $(JIRA_EMU_PORT) --reload

serve-mcp:
	JIRA_SERVER=http://localhost:$(JIRA_EMU_PORT) JIRA_USER=$(JIRA_EMU_USER) JIRA_TOKEN=$(JIRA_EMU_TOKEN) MCP_PORT=$(JIRA_EMU_MCP_PORT) \
		uv run python mcp_servers/atlassian_jira.py

serve-all:
	@echo "Starting Jira Emulator on port $(JIRA_EMU_PORT) and MCP server on port $(JIRA_EMU_MCP_PORT)..."
	uv run python -m jira_emulator serve --port $(JIRA_EMU_PORT) --reload &
	@sleep 2
	JIRA_SERVER=http://localhost:$(JIRA_EMU_PORT) JIRA_USER=$(JIRA_EMU_USER) JIRA_TOKEN=$(JIRA_EMU_TOKEN) MCP_PORT=$(JIRA_EMU_MCP_PORT) \
		uv run python mcp_servers/atlassian_jira.py
