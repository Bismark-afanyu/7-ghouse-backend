import asyncio
from google.genai import types
from app.services.genai_client import get_genai_client
from app.services.video_service import _download_from_gcs

async def main():
    client = get_genai_client()
    op_name = "projects/g-house-d458c/locations/us-central1/publishers/google/models/veo-3.1-generate-001/operations/400f0604-b477-46b3-bb9c-1eb9d7eddae5"
    op_obj = types.GenerateVideosOperation(name=op_name)
    op = client.operations.get(operation=op_obj)
    print("Done:", op.done)
    if op.done:
        vid = op.response.generated_videos[0].video
        print("URI:", getattr(vid, "uri", None))
        print("Video bytes length:", len(getattr(vid, "video_bytes", b"")) if getattr(vid, "video_bytes", None) else 0)
        uri = getattr(vid, "uri", None)
        if uri:
            try:
                b = _download_from_gcs(uri)
                print("Downloaded GCS bytes length:", len(b))
            except Exception as e:
                print("GCS Download Error:", e)

asyncio.run(main())
