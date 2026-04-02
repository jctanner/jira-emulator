IMAGE_NAME ?= jira-emulator
CONTAINER_NAME ?= jira-emulator
PORT ?= 8080
MCP_PORT ?= 8081
JIRA_USER ?= admin
JIRA_TOKEN ?= jira-emulator-default-token
CONTAINER_ENGINE ?= podman

.PHONY: build run stop restart logs status clean test serve serve-mcp serve-all

build:
	$(CONTAINER_ENGINE) build -t $(IMAGE_NAME) .

run: build
	$(CONTAINER_ENGINE) run -d \
		--name $(CONTAINER_NAME) \
		-p $(PORT):8080 \
		-p $(MCP_PORT):8081 \
		-v jira-emulator-data:/data \
		$(IMAGE_NAME)
	@echo "Jira Emulator API: http://localhost:$(PORT)"
	@echo "Jira MCP server:   http://localhost:$(MCP_PORT)/sse"

stop:
	-$(CONTAINER_ENGINE) stop $(CONTAINER_NAME)
	-$(CONTAINER_ENGINE) rm $(CONTAINER_NAME)

restart: stop run

logs:
	$(CONTAINER_ENGINE) logs -f $(CONTAINER_NAME)

status:
	@$(CONTAINER_ENGINE) ps -f name=$(CONTAINER_NAME) --format "{{.Names}}\t{{.Status}}\t{{.Ports}}"

clean: stop
	-$(CONTAINER_ENGINE) rmi $(IMAGE_NAME)
	-$(CONTAINER_ENGINE) volume rm jira-emulator-data

test:
	uv run pytest tests/ -x -q

serve:
	uv run python -m jira_emulator serve --port $(PORT) --reload

serve-mcp:
	JIRA_SERVER=http://localhost:$(PORT) JIRA_USER=$(JIRA_USER) JIRA_TOKEN=$(JIRA_TOKEN) MCP_PORT=$(MCP_PORT) \
		uv run python mcp_servers/atlassian_jira.py

serve-all:
	@echo "Starting Jira Emulator on port $(PORT) and MCP server on port $(MCP_PORT)..."
	uv run python -m jira_emulator serve --port $(PORT) --reload &
	@sleep 2
	JIRA_SERVER=http://localhost:$(PORT) JIRA_USER=$(JIRA_USER) JIRA_TOKEN=$(JIRA_TOKEN) MCP_PORT=$(MCP_PORT) \
		uv run python mcp_servers/atlassian_jira.py
