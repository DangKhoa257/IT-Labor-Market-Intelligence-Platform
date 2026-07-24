from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_job_id: str
    source_url: str
    title_raw: str
    title_normalized: str | None
    primary_category: str | None
    city: str | None
    work_mode: str | None
    employment_type: str | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    salary_disclosed: bool
    status: str
    posted_at: datetime | None
    collected_at: datetime


class JobDetail(JobOut):
    description_preview: str | None = None
    skills: list[str] = []
    company: dict[str, Any] | None = None


class Page(BaseModel):
    items: list[JobOut]
    page: int
    page_size: int
    total: int
    pages: int
