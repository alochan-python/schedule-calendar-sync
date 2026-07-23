.PHONY: setup run test lint

setup:
	python3 -m venv .venv
	. .venv/bin/activate; pip install --upgrade pip; pip install -r requirements.txt

run:
	. .venv/bin/activate; streamlit run app.py

test:
	. .venv/bin/activate; pytest -q

lint:
	. .venv/bin/activate; ruff check .
