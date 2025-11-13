"""Asynchronous download queue powered by yt-dlp."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from sqlmodel import select

from .database import get_session
from .models import DownloadJob, JobStatus
from .notifier import TelegramNotifier
from .settings import get_settings

logger = logging.getLogger(__name__)


def _json_default(value: Any) -> str:
    """Serialize otherwise unsupported objects when persisting metadata."""

    if isinstance(value, bytes):
        # Preserve the raw payload while keeping the metadata readable.
        return base64.b64encode(value).decode("ascii")
    # Fallback to the object's string representation so yt-dlp helper classes
    # (e.g. FFmpegFixupM3u8PP) do not break metadata dumps.
    return str(value)


def _dedupe_thumbnails(payload: Any) -> None:
    """Remove duplicate thumbnail entries in-place throughout metadata."""

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            thumbnails = node.get("thumbnails")
            if isinstance(thumbnails, list):
                seen: set[tuple[Any, Any]] = set()
                deduped: list[Any] = []
                for entry in thumbnails:
                    if isinstance(entry, dict):
                        key = (entry.get("id"), entry.get("url"))
                    else:
                        key = (None, entry)
                    if key in seen:
                        continue
                    seen.add(key)
                    deduped.append(entry)
                node["thumbnails"] = deduped
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(payload)


_SANITIZE_PATTERN = re.compile(r"[^\w\s().-]", re.UNICODE)


def _sanitize_directory_name(title: str) -> Optional[str]:
    """Return a filesystem-friendly directory name based on a title."""

    normalized = unicodedata.normalize("NFKC", title).strip()
    if not normalized:
        return None
    sanitized = _SANITIZE_PATTERN.sub("_", normalized)
    sanitized = re.sub(r"\s+", "_", sanitized)
    sanitized = sanitized.strip("._-")
    if not sanitized:
        return None
    return sanitized[:120]


@dataclass
class JobContext:
    id: str
    source_url: str
    telegram_chat_id: Optional[int]


@dataclass
class DownloadResult:
    title: Optional[str]
    output_dir: str
    metadata_path: Optional[str]
    description_path: Optional[str]
    manifest: List[str]


class DownloadManager:
    """Multi-worker queue that processes yt-dlp downloads concurrently."""

    def __init__(self, notifier: TelegramNotifier) -> None:
        self.settings = get_settings()
        self.notifier = notifier
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_tasks: List[asyncio.Task[None]] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._progress_checkpoints: Dict[str, float] = {}
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        if self._worker_tasks:
            return
        self._loop = asyncio.get_running_loop()
        self._shutdown_event.clear()
        await self.notifier.start()
        resumed_jobs = self._recover_incomplete_jobs()
        for job_id in resumed_jobs:
            self.queue.put_nowait(job_id)
        if resumed_jobs:
            logger.info("Requeued %d incomplete jobs", len(resumed_jobs))
        num_workers = self.settings.max_concurrent_downloads
        for worker_id in range(num_workers):
            task = asyncio.create_task(self._worker(worker_id))
            self._worker_tasks.append(task)
        logger.info("Download manager started with %d workers", num_workers)

    async def stop(self) -> None:
        if not self._worker_tasks:
            return
        self._shutdown_event.set()
        for task in self._worker_tasks:
            task.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()
        await self.notifier.close()
        logger.info("Download manager stopped")

    async def enqueue_job(self, job_id: str) -> None:
        await self.queue.put(job_id)
        logger.debug("Job %s queued", job_id)

    async def _worker(self, worker_id: int) -> None:
        logger.debug("Worker %d started", worker_id)
        while not self._shutdown_event.is_set():
            try:
                job_id = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                logger.debug("Worker %d processing job %s", worker_id, job_id)
                await self._execute_job(job_id)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Worker %d: Job %s failed with unexpected error", worker_id, job_id)
                self._mark_failed(job_id, str(exc))
            finally:
                self.queue.task_done()
        logger.debug("Worker %d stopped", worker_id)

    async def _execute_job(self, job_id: str) -> None:
        with get_session() as session:
            job = session.get(DownloadJob, job_id)
            if job is None:
                logger.warning("Job %s disappeared before execution", job_id)
                return
            job.status = JobStatus.running
            job.progress = 0.0
            job.touch()

        job_ctx = JobContext(
            id=job.id, source_url=job.source_url, telegram_chat_id=job.telegram_chat_id
        )

        await self._notify_started(job_ctx)

        try:
            result = await asyncio.to_thread(self._run_download, job_ctx)
        except Exception as exc:
            self._mark_failed(job_id, str(exc))
            await self._notify_failure(job_id, str(exc))
            return

        with get_session() as session:
            db_job = session.get(DownloadJob, job_id)
            if db_job is None:
                return
            db_job.status = JobStatus.completed
            db_job.progress = 100.0
            db_job.title = result.title
            db_job.output_dir = result.output_dir
            db_job.metadata_path = result.metadata_path
            db_job.description_path = result.description_path
            db_job.set_manifest(result.manifest)
            db_job.error = None
        await self._notify_success(job_id)

    def _run_download(self, job: JobContext) -> DownloadResult:
        dest_dir = (self.settings.download_root / f"{job.id}").resolve()
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        progress_hook = self._build_progress_hook(job.id)
        outtmpl = str(dest_dir / "%(title).200B_%(id)s.%(ext)s")
        ydl_opts = {
            "outtmpl": outtmpl,
            "writedescription": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "writethumbnail": True,
            "write_all_thumbnails": True,
            "progress_hooks": [progress_hook],
            "paths": {"home": str(dest_dir)},
        }

        logger.info("Starting download for job %s", job.id)
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(job.source_url, download=True)

        _dedupe_thumbnails(info)
        metadata_filename = "metadata.json"
        metadata_path = dest_dir / metadata_filename
        metadata_json = json.dumps(info, indent=2, default=_json_default)
        metadata_path.write_text(metadata_json, encoding="utf-8")

        description_filename = "description.txt"
        description_path = dest_dir / description_filename
        has_description = bool(info.get("description"))
        if has_description:
            description_path.write_text(info["description"], encoding="utf-8")
        else:
            if description_path.exists():
                description_path.unlink()

        final_dir = self._rename_download_directory(dest_dir, info.get("title"), job.id)

        manifest = [
            str(path.relative_to(self.settings.download_root))
            for path in final_dir.rglob("*")
            if path.is_file()
        ]

        metadata_rel = None
        metadata_candidate = final_dir / metadata_filename
        if metadata_candidate.exists():
            metadata_rel = str(
                metadata_candidate.relative_to(self.settings.download_root)
            )

        description_rel = None
        if has_description:
            description_candidate = final_dir / description_filename
            if description_candidate.exists():
                description_rel = str(
                    description_candidate.relative_to(self.settings.download_root)
                )

        return DownloadResult(
            title=info.get("title"),
            output_dir=str(final_dir.relative_to(self.settings.download_root)),
            metadata_path=metadata_rel,
            description_path=description_rel,
            manifest=manifest,
        )

    def _recover_incomplete_jobs(self) -> List[str]:
        with get_session() as session:
            statement = select(DownloadJob).where(
                DownloadJob.status.in_((JobStatus.pending, JobStatus.running))
            )
            jobs = session.exec(statement).all()
            resumed: List[str] = []
            for job in jobs:
                if job.status == JobStatus.running:
                    job.status = JobStatus.pending
                    job.progress = 0.0
                    job.output_dir = None
                    job.metadata_path = None
                    job.description_path = None
                    job.file_manifest = []
                    job.error = None
                resumed.append(job.id)
                job.touch()
        return resumed

    def _build_progress_hook(self, job_id: str):
        def hook(status: dict) -> None:
            if status.get("status") != "downloading":
                return
            downloaded = status.get("downloaded_bytes")
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            if not downloaded or not total:
                return
            percent = max(0.0, min(100.0, (downloaded / total) * 100))
            self._update_progress(job_id, percent)

        return hook

    def _rename_download_directory(
        self, directory: Path, title: Optional[str], job_id: str
    ) -> Path:
        """Rename the destination directory to match the video title if possible."""

        if not title:
            return directory
        safe_name = _sanitize_directory_name(title)
        if not safe_name:
            return directory
        parent = directory.parent
        if parent == directory:
            return directory

        def _candidate_name(attempt: int) -> str:
            if attempt == 0:
                return safe_name
            if attempt == 1:
                return f"{safe_name}-{job_id[:6]}"
            return f"{safe_name}-{job_id[:6]}-{attempt - 1}"

        for attempt in range(0, 20):
            name = _candidate_name(attempt)
            candidate = parent / name
            if candidate == directory:
                return directory
            if candidate.exists():
                continue
            try:
                directory.rename(candidate)
                logger.info(
                    "Renamed download directory %s -> %s", directory.name, candidate.name
                )
                return candidate
            except FileExistsError:
                continue
            except OSError:
                logger.warning(
                    "Failed to rename download directory %s -> %s",
                    directory,
                    candidate,
                    exc_info=True,
                )
                return directory

        logger.warning(
            "Unable to find unique directory name for %s after multiple attempts",
            directory,
        )
        return directory

    def _update_progress(self, job_id: str, percent: float) -> None:
        with get_session() as session:
            job = session.get(DownloadJob, job_id)
            if not job:
                return
            job.progress = percent
            job.touch()
            checkpoint = self._progress_checkpoints.get(job_id, -100.0)
            if (
                job.telegram_chat_id
                and self._loop
                and percent - checkpoint >= self.settings.notifier_min_percent_step
            ):
                self._progress_checkpoints[job_id] = percent
                asyncio.run_coroutine_threadsafe(
                    self._push_progress(job.id, percent), self._loop
                )

    async def _push_progress(self, job_id: str, percent: float) -> None:
        if not self.notifier.bot_token:
            return
        with get_session() as session:
            job = session.get(DownloadJob, job_id)
            if not job or not job.telegram_chat_id:
                return
            message = f"Download update ({percent:.0f}%): {job.title or job.source_url}"
            if job.telegram_message_id:
                await self.notifier.edit_message(
                    job.telegram_chat_id, job.telegram_message_id, message
                )
            else:
                message_id = await self.notifier.send_message(
                    job.telegram_chat_id, message
                )
                if message_id:
                    job.telegram_message_id = message_id

    def _mark_failed(self, job_id: str, error: str) -> None:
        with get_session() as session:
            job = session.get(DownloadJob, job_id)
            if not job:
                return
            job.status = JobStatus.failed
            job.error = error
            job.touch()

    async def _notify_started(self, job_ctx: JobContext) -> None:
        if not self.notifier.bot_token or not job_ctx.telegram_chat_id:
            return
        message = f"Queued download: {job_ctx.source_url}"
        message_id = await self.notifier.send_message(job_ctx.telegram_chat_id, message)
        if message_id:
            with get_session() as session:
                job = session.get(DownloadJob, job_ctx.id)
                if job:
                    job.telegram_message_id = message_id

    async def _notify_success(self, job_id: str) -> None:
        if not self.notifier.bot_token:
            return
        with get_session() as session:
            job = session.get(DownloadJob, job_id)
            if not job or not job.telegram_chat_id:
                return
            link_hint = ""
            if job.output_dir:
                link_hint = f"\nFiles: /downloads/{job.output_dir}"
            text = f"✅ Download complete: {job.title or job.source_url}{link_hint}"
            if job.telegram_message_id:
                await self.notifier.edit_message(
                    job.telegram_chat_id, job.telegram_message_id, text
                )
            else:
                await self.notifier.send_message(job.telegram_chat_id, text)

    async def _notify_failure(self, job_id: str, error: str) -> None:
        if not self.notifier.bot_token:
            return
        with get_session() as session:
            job = session.get(DownloadJob, job_id)
            if not job or not job.telegram_chat_id:
                return
            text = f"❌ Download failed: {job.source_url}\n{error}"
            if job.telegram_message_id:
                await self.notifier.edit_message(
                    job.telegram_chat_id, job.telegram_message_id, text
                )
            else:
                await self.notifier.send_message(job.telegram_chat_id, text)


def is_url_allowed(url: str) -> bool:
    settings = get_settings()
    if not settings.allowed_source_domains:
        return True
    hostname = urlparse(url).hostname or ""
    hostname = hostname.lower()
    return any(
        hostname.endswith(domain.lower()) for domain in settings.allowed_source_domains
    )


__all__ = ["DownloadManager", "is_url_allowed"]
