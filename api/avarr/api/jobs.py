"""REST endpoints for managing download jobs."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session, select

from ..database import session_dependency
from ..download_manager import DownloadManager, is_url_allowed
from ..models import DownloadJob, JobCreate, JobDeleteResponse, JobRead, JobStatus, JobUpdateFlags
from ..settings import get_settings


router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)
settings = get_settings()


def _get_manager(request: Request) -> DownloadManager:
    return request.app.state.manager


def _resolve_download_path(relative_path: str) -> Path | None:
    relative = relative_path.strip()
    if not relative:
        return None
    # Prevent absolute paths from escaping the download root.
    relative = relative.lstrip("/\\")
    candidate = (settings.download_root / relative).resolve(strict=False)
    try:
        candidate.relative_to(settings.download_root)
    except ValueError:
        logger.warning("Refusing to delete path outside download root: %s", candidate)
        return None
    return candidate


def _cleanup_job_artifacts(job: DownloadJob) -> None:
    if job.output_dir:
        directory = _resolve_download_path(job.output_dir)
        if directory and directory.exists():
            try:
                shutil.rmtree(directory)
            except FileNotFoundError:
                pass

    output_prefix = None
    if job.output_dir:
        normalized = job.output_dir.rstrip("/\\")
        output_prefix = f"{normalized}/"

    for relative_path in job.file_manifest:
        if not relative_path:
            continue
        if output_prefix and relative_path.startswith(output_prefix):
            # Already deleted as part of the directory removal above.
            continue
        file_path = _resolve_download_path(relative_path)
        if file_path and file_path.exists():
            try:
                file_path.unlink()
            except FileNotFoundError:
                continue


@router.get("/", response_model=list[JobRead])
def list_jobs(
    status: JobStatus | None = None,
    watched: bool | None = None,
    starred: bool | None = None,
    session: Session = Depends(session_dependency),
) -> list[JobRead]:
    statement = select(DownloadJob).order_by(DownloadJob.created_at.desc())
    if status:
        statement = statement.where(DownloadJob.status == status)
    if watched is not None:
        statement = statement.where(DownloadJob.watched == watched)
    if starred is not None:
        statement = statement.where(DownloadJob.starred == starred)
    jobs = session.exec(statement).all()
    return [JobRead.from_orm(job) for job in jobs]


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, session: Session = Depends(session_dependency)) -> JobRead:
    job = session.get(DownloadJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobRead.from_orm(job)


@router.patch("/{job_id}/flags", response_model=JobRead)
def update_job_flags(
    job_id: str,
    payload: JobUpdateFlags,
    session: Session = Depends(session_dependency)
) -> JobRead:
    job = session.get(DownloadJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # If starring a job, automatically mark it as watched
    if payload.starred is True:
        job.starred = True
        job.watched = True
    elif payload.starred is False:
        job.starred = False
        # Don't automatically unwatch when unstarring
        if payload.watched is not None:
            job.watched = payload.watched
    else:
        # Only starred field not provided, update watched if specified
        if payload.watched is not None:
            job.watched = payload.watched

    job.touch()
    session.commit()
    session.refresh(job)

    return JobRead.from_orm(job)


@router.get("/{job_id}/files", response_model=list[str])
def list_job_files(job_id: str, session: Session = Depends(session_dependency)) -> list[str]:
    job = session.get(DownloadJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job.file_manifest


@router.delete("/{job_id}", response_model=JobDeleteResponse)
def delete_job(job_id: str, session: Session = Depends(session_dependency)) -> JobDeleteResponse:
    job = session.get(DownloadJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.status in (JobStatus.pending, JobStatus.running):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot remove a job that is pending or running",
        )

    source_url = job.source_url
    try:
        _cleanup_job_artifacts(job)
    except OSError as exc:  # pragma: no cover - error branch
        logger.exception("Failed to delete files for job %s", job_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete download files: {exc}",
        ) from exc

    session.delete(job)
    return JobDeleteResponse(id=job_id, source_url=source_url)


@router.post("/", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    request: Request,
    session: Session = Depends(session_dependency),
) -> JobRead:
    url = payload.url.strip()
    if not is_url_allowed(url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL domain is not allowed by server policy",
        )

    # Check for duplicate URL
    existing_job = session.exec(
        select(DownloadJob).where(DownloadJob.source_url == url)
    ).first()
    if existing_job:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job already exists for this URL (ID: {existing_job.id})",
        )

    job = DownloadJob(source_url=url, telegram_chat_id=payload.telegram_chat_id)
    session.add(job)
    session.commit()
    session.refresh(job)

    manager = _get_manager(request)
    await manager.enqueue_job(job.id)

    return JobRead.from_orm(job)
