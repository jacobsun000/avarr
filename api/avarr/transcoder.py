"""Background ffmpeg transcoding helpers."""

from __future__ import annotations

import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable

from .database import get_session
from .models import DownloadJob


VIDEO_EXTENSIONS = {
    ".webm",
    ".mkv",
    ".mov",
    ".avi",
    ".flv",
    ".ts",
    ".m4v",
}


class TranscodeService:
    """Schedule ffmpeg jobs without blocking the asyncio event loop."""

    def __init__(self, download_root: Path, max_workers: int = 1) -> None:
        self._download_root = download_root.resolve()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="transcode"
        )
        self._logger = logging.getLogger(__name__)
        self._inflight: set[str] = set()

    def schedule_manifest(self, job_id: str, manifest: Iterable[str]) -> None:
        if not manifest:
            return
        for relative_path in manifest:
            self._maybe_submit(job_id, relative_path)

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)

    def _maybe_submit(self, job_id: str, relative_path: str) -> None:
        normalized = relative_path.strip()
        if not normalized or not self._needs_transcode(normalized):
            return
        if normalized in self._inflight:
            return
        self._inflight.add(normalized)
        future = self._executor.submit(self._transcode_file, job_id, normalized)
        future.add_done_callback(lambda _: self._inflight.discard(normalized))

    def _needs_transcode(self, relative_path: str) -> bool:
        extension = Path(relative_path).suffix.lower()
        return bool(extension) and extension in VIDEO_EXTENSIONS

    def _transcode_file(self, job_id: str, relative_path: str) -> None:
        source = (self._download_root / relative_path).resolve()
        try:
            source.relative_to(self._download_root)
        except ValueError:
            self._logger.warning("Refusing to transcode outside download root: %s", source)
            return
        if not source.exists():
            self._logger.warning("Source missing for transcode: %s", source)
            return

        destination = source.with_suffix(".mp4")
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(destination),
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except FileNotFoundError:
            self._logger.error("ffmpeg binary not found while transcoding %s", source)
            return
        except subprocess.CalledProcessError as exc:
            self._logger.error("ffmpeg failed for %s: %s", source, exc.stderr)
            if destination.exists():
                destination.unlink()
            return

        try:
            source.unlink()
        except FileNotFoundError:
            pass

        new_relative = str(destination.relative_to(self._download_root))
        with get_session() as session:
            job = session.get(DownloadJob, job_id)
            if not job:
                return
            manifest = [entry for entry in job.file_manifest if entry != relative_path]
            if new_relative not in manifest:
                manifest.append(new_relative)
            job.set_manifest(manifest)
        self._logger.info("Transcoded %s -> %s", relative_path, new_relative)


__all__ = ["TranscodeService", "VIDEO_EXTENSIONS"]
