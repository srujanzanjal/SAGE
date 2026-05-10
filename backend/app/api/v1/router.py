from fastapi import APIRouter

from app.api.v1.endpoints import ingest, jobs, qa, sources

api_router = APIRouter()
api_router.include_router(ingest.router)
api_router.include_router(jobs.router)
api_router.include_router(qa.router)
api_router.include_router(sources.router)
