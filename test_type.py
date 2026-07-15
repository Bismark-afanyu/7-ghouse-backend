import asyncio
from google.genai import types
from app.services.genai_client import get_genai_client

async def main():
    client = get_genai_client()
    op_name = "projects/g-house-d458c/locations/us-central1/publishers/google/models/veo-3.1-generate-001/operations/400f0604-b477-46b3-bb9c-1eb9d7eddae5"
    op = client.operations.get(operation=types.GenerateVideosOperation(name=op_name))
    vid = op.response.generated_videos[0].video
    b = getattr(vid, "video_bytes", None)
    print("Type of video_bytes:", type(b))

asyncio.run(main())
