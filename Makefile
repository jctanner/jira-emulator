IMAGE_NAME ?= jira-emulator
CONTAINER_NAME ?= jira-emulator
PORT ?= 8080
CONTAINER_ENGINE ?= podman

.PHONY: build run stop restart logs status clean test serve

build:
	$(CONTAINER_ENGINE) build -t $(IMAGE_NAME) .

run: build
	$(CONTAINER_ENGINE) run -d \
		--name $(CONTAINER_NAME) \
		-p $(PORT):8080 \
		-v jira-emulator-data:/data \
		$(IMAGE_NAME)
	@echo "Jira Emulator running at http://localhost:$(PORT)"

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
