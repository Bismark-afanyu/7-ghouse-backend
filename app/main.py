from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import mimetypes
mimetypes.init()
from app.api.generations import router as generations_router
from app.api.users import router as users_router
from app.api.clients import router as clients_router

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


# Create static directory if it doesn't exist
if not os.path.exists("static"):
    os.makedirs("static")

# Mount static files with explicit headers
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

@app.middleware("http")
async def add_process_time_header(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "public, max-age=3600"
        # Ensure images are treated as inline, not attachments
        if "Content-Disposition" in response.headers:
            del response.headers["Content-Disposition"]
    return response

app.include_router(generations_router, prefix="/api", tags=["generations"])
app.include_router(users_router, prefix="/api/users", tags=["users"])
app.include_router(clients_router, prefix="/api/clients", tags=["clients"])
