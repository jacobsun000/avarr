"""Data models for download jobs."""

from __future__ import annotations

import enum
import json
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.utcnow()


def _uuid() -> str:
    return uuid.uuid4().hex


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class DownloadJob(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True, index=True)
    source_url: str = Field(index=True)
    status: JobStatus = Field(default=JobStatus.pending)
    progress: float = Field(default=0.0, ge=0.0, le=100.0)
    title: Optional[str] = None
    output_dir: Optional[str] = None
    metadata_path: Optional[str] = None
    description_path: Optional[str] = None
    file_manifest: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    error: Optional[str] = None
    telegram_chat_id: Optional[int] = Field(default=None, index=True)
    telegram_message_id: Optional[int] = None
    watched: bool = Field(default=False, index=True)
    starred: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    def touch(self) -> None:
        self.updated_at = _now()

    def set_manifest(self, manifest: List[str]) -> None:
        self.file_manifest = manifest
        self.touch()


class JobCreate(SQLModel):
    url: str
    telegram_chat_id: Optional[int] = None


class JobRead(SQLModel):
    id: str
    source_url: str
    status: JobStatus
    progress: float
    title: Optional[str]
    output_dir: Optional[str]
    metadata_path: Optional[str]
    description_path: Optional[str]
    file_manifest: List[str]
    error: Optional[str]
    telegram_chat_id: Optional[int]
    watched: bool
    starred: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm(cls, job: DownloadJob) -> "JobRead":
        data = json.loads(job.model_dump_json())
        return cls(**data)


class JobDeleteResponse(SQLModel):
    id: str
    source_url: str


class JobUpdateFlags(SQLModel):
    watched: Optional[bool] = None
    starred: Optional[bool] = None


__all__ = [
    "DownloadJob",
    "JobCreate",
    "JobRead",
    "JobStatus",
    "JobDeleteResponse",
    "JobUpdateFlags",
]
