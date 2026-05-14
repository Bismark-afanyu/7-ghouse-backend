.PHONY: dev install clean

VENV_BIN := venv/bin

# Run the FastAPI development server
dev:
	$(VENV_BIN)/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Install dependencies
install:
	$(VENV_BIN)/pip install -r requirements.txt

# Clean up pycache
clean:
	find . -type d -name "__pycache__" -exec rm -r {} +
