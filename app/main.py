import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.responses import JSONResponse
import os
import mimetypes
mimetypes.init()
from app.api.generations import router as generations_router
from app.api.users import router as users_router
from app.api.clients import router as clients_router
from app.api.telegram import router as telegram_router
from app.api.video import router as video_router

app = FastAPI(
    title="7G House MVP API",
    description="AI-powered real estate visualization platform",
    version="0.1.0",
)

# CORS
origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001").split(",")
cors_regex = os.getenv("CORS_ORIGIN_REGEX", "")

cors_kwargs = {
    "allow_origins": origins,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}

if cors_regex:
    cors_kwargs["allow_origin_regex"] = cors_regex
elif not os.getenv("ALLOWED_ORIGINS"):
    cors_kwargs["allow_origin_regex"] = r"https?://.*"

app.add_middleware(CORSMiddleware, **cors_kwargs)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/")
def root():
    return {"message": "7G House API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


# Create static directory if it doesn't exist
if not os.path.exists("static"):
    os.makedirs("static", exist_ok=True)

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
app.include_router(telegram_router, prefix="/api", tags=["telegram"])
app.include_router(video_router, prefix="/api", tags=["video"])
