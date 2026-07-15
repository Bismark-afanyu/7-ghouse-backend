import asyncio
from app.services.video_service import submit_veo_render

async def main():
    img_url = "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png" 
    prompt = "A test video prompt"
    try:
        op = await submit_veo_render(img_url, prompt)
        print("Success:", op)
    except Exception as e:
        print("Error submitting:", e)

asyncio.run(main())
