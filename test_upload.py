import asyncio
from app.services.storage_service import upload_file

async def main():
    try:
        res = await upload_file(b"test", "test_user", "test_gen", "test.mp4", "video/mp4")
        print("Success:", res)
    except Exception as e:
        print("Upload Error:", e)

asyncio.run(main())
