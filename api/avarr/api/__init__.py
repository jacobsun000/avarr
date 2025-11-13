"""API routers."""

from fastapi import APIRouter

from . import jobs, telegram


router = APIRouter()
router.include_router(jobs.router)
router.include_router(telegram.router)


__all__ = ["router"]
