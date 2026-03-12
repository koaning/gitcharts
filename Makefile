.PHONY: build update

build:
	uv run generate_repos_list.py

update:
	uv run update_charts.py
	$(MAKE) build
