import os
import sys
import httpx
from dotenv import load_dotenv

load_dotenv()

def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/register_webhook.py <WEBHOOK_URL>")
        print("Example: python scripts/register_webhook.py https://g-house-backend-xxxxx.a.run.app")
        sys.exit(1)

    url = sys.argv[1]
    if not url.startswith("https://"):
        print("Error: Webhook URL must use HTTPS")
        sys.exit(1)

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not found in environment")
        sys.exit(1)

    webhook_url = f"{url.rstrip('/')}/api/telegram/webhook"
    
    api_url = f"https://api.telegram.org/bot{token}/setWebhook"
    print(f"Registering webhook to: {webhook_url}")
    response = httpx.post(api_url, data={"url": webhook_url})
    
    if response.is_success:
        print(f"✅ Webhook successfully registered!")
        print(response.json())
    else:
        print(f"❌ Failed to register webhook: {response.text}")
        sys.exit(1)

if __name__ == "__main__":
    main()
