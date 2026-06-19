import os
import firebase_admin
from firebase_admin import credentials, auth, firestore, storage
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "7G House MVP API"
    FIREBASE_CREDENTIALS_PATH: str = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase-adminsdk.json")
    FIREBASE_STORAGE_BUCKET: str = os.getenv("FIREBASE_STORAGE_BUCKET", "seven-g-house.appspot.com")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    NANO_BANANA_API_KEY: str = os.getenv("NANO_BANANA_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    FAL_API_KEY: str = os.getenv("FAL_API_KEY", "")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Initialize Firebase
def init_firebase():
    if not firebase_admin._apps:
        try:
            if os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
                cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
                firebase_admin.initialize_app(cred, {
                    'storageBucket': settings.FIREBASE_STORAGE_BUCKET
                })
                print("Firebase Admin initialized successfully with credentials file.")
            else:
                # Fallback to default credentials (e.g. Google Cloud Run)
                firebase_admin.initialize_app(options={
                    'storageBucket': settings.FIREBASE_STORAGE_BUCKET
                })
                print("Firebase Admin initialized with default credentials.")
        except Exception as e:
            print(f"Error initializing Firebase: {e}")

# Call init on import
init_firebase()

# Export clients
try:
    db = firestore.client()
    bucket = storage.bucket()
except Exception:
    db = None
    bucket = None
