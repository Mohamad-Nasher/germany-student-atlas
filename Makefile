.PHONY: install test build sample analyze serve
install:
	pip install -e ".[dev]"
test:
	ruff check . && pytest -q
build:
	atlas build
sample:
	atlas sample
analyze:
	atlas analyze
serve:
	python -m http.server 8000 --directory docs
