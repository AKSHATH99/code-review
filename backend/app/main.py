import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.analysis import router as analysis_router
from app.routes.ollama import router as ollama_router
from app.routes.repositories import router as repositories_router

load_dotenv()

app = FastAPI(title="GitScope API", version="0.1.0")

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    repositories_router, prefix="/repositories", tags=["repositories"]
)
app.include_router(
    analysis_router, prefix="/repositories", tags=["analysis"]
)
app.include_router(ollama_router, prefix="/api/ollama", tags=["ollama"])


@app.get("/health")
def health():
    return {"status": "ok", "service": "gitscope-api"}
