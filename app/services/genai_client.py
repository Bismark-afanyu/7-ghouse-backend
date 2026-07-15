import logging
from google import genai

logger = logging.getLogger(__name__)

VERTEX_PROJECT = "g-house-d458c"
VERTEX_LOCATION = "us-central1"

_client: genai.Client | None = None


def get_genai_client() -> genai.Client:
    global _client
    if _client is None:
        logger.info(f"Creating Vertex AI client (project={VERTEX_PROJECT}, location={VERTEX_LOCATION})")
        _client = genai.Client(
            vertexai=True,
            project=VERTEX_PROJECT,
            location=VERTEX_LOCATION,
        )
    return _client


def reset_client():
    global _client
    _client = None
