from google import genai
import inspect

try:
    client = genai.Client(api_key="123")
    client.files.download(file="models/veo-3.1-lite-generate-preview/operations/5awtn0edft04")
except Exception as e:
    print(repr(e))
    import traceback
    traceback.print_exc()

