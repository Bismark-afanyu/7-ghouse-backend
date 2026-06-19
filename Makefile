.PHONY: dev prod install clean

VENV_BIN := venv/bin

dev:
	$(VENV_BIN)/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

prod:
	uvicorn app.main:app --host 0.0.0.0 --port $(PORT)

install:
	$(VENV_BIN)/pip install -r requirements.txt

clean:
	find . -type d -name "__pycache__" -exec rm -r {} +

docker-build:
	docker build -t 7g-house-api .

docker-run:
	docker run -p 8080:8080 -e PORT=8080 7g-house-api

deploy:
	gcloud run deploy g-house-backend \
		--source . \
		--region europe-west1 \
		--allow-unauthenticated \
		--project g-house-d458c

set-webhook:
	$(VENV_BIN)/python scripts/register_webhook.py $(URL)
