import asyncio
from google import genai
from google.genai import types
import os

async def test():
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", "123"))
    operation_name = "models/veo-3.1-lite-generate-preview/operations/5awtn0edft04"
    operation_obj = types.GenerateVideosOperation(name=operation_name)
    try:
        operation = await asyncio.to_thread(
            client.operations.get,
            operation_obj,
        )
        print("Success:", operation)
    except Exception as e:
        print("Error:", repr(e))
        import traceback
        traceback.print_exc()

asyncio.run(test())
