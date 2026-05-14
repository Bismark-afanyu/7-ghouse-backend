from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.generations import router as generations_router

app = FastAPI(
    title="7G House MVP API",
    description="AI-powered real estate visualization platform",
    version="0.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "7G House API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(generations_router, prefix="/api", tags=["generations"])
