"""FastAPI application factory and production application."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.orm import Session

from it_labor_market_intelligence.database.models import JobPosting
from it_labor_market_intelligence.database.repositories import (
    AnalyticsRepository,
    CompanyRepository,
    DuplicateRepository,
    JobRepository,
    QualityRepository,
    SkillRepository,
)

from .dependencies import configure_database, get_session
from .schemas import JobDetail, JobOut, Page
from .settings import APISettings

SessionDep = Annotated[Session, Depends(get_session)]


def _meta(session: Session) -> dict:
    overview = AnalyticsRepository(session).overview()
    return {
        "sample_size": overview["total_jobs"],
        "generated_at": datetime.now(UTC).isoformat(),
        "source_coverage": overview["source_coverage"],
        "limitations": [
            "Descriptive statistics for the persisted dataset only.",
            "Currencies are never combined.",
        ],
    }


def _job_out(job: JobPosting) -> JobOut:
    return JobOut.model_validate(job)


def create_app(database_url: str | None = None) -> FastAPI:
    settings = APISettings(database_url=database_url) if database_url else APISettings()
    if database_url:
        configure_database(database_url)
    app = FastAPI(title="IT Labor Market Analytics API", version="1.0.0")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get(f"{settings.api_prefix}/jobs", response_model=Page)
    def jobs(
        session: SessionDep,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
        category: str | None = None,
        city: str | None = None,
        company_id: int | None = None,
        skill: str | None = None,
        employment_type: str | None = None,
        work_mode: str | None = None,
        status: str | None = None,
        salary_disclosed: bool | None = None,
        salary_min: float | None = None,
        salary_max: float | None = None,
        keyword: str | None = None,
        sort: Literal["posted_at", "collected_at", "salary"] = "posted_at",
        order: Literal["asc", "desc"] = "desc",
    ) -> Page:
        items, total = JobRepository(session).list(
            page=page,
            page_size=page_size,
            category=category,
            city=city,
            company_id=company_id,
            skill=skill,
            employment_type=employment_type,
            work_mode=work_mode,
            status=status,
            salary_disclosed=salary_disclosed,
            salary_min=salary_min,
            salary_max=salary_max,
            keyword=keyword,
            sort=sort,
            order=order,
        )
        return Page(
            items=[_job_out(item) for item in items],
            page=page,
            page_size=page_size,
            total=total,
            pages=math.ceil(total / page_size),
        )

    @app.get(f"{settings.api_prefix}/jobs/{{job_id}}", response_model=JobDetail)
    def job_detail(job_id: int, session: SessionDep) -> JobDetail:
        job = JobRepository(session).get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        preview = re.sub(r"<[^>]+>", " ", job.description_raw or "").strip()[:500] or None
        return JobDetail(
            **_job_out(job).model_dump(),
            description_preview=preview,
            skills=[link.skill.canonical_name for link in job.skills],
            company={"id": job.company.id, "name": job.company.name} if job.company else None,
        )

    @app.get(f"{settings.api_prefix}/companies")
    def companies(session: SessionDep) -> list[dict]:
        return CompanyRepository(session).list()

    @app.get(f"{settings.api_prefix}/companies/{{company_id}}")
    def company(company_id: int, session: SessionDep) -> dict:
        result = CompanyRepository(session).get(company_id)
        if result is None:
            raise HTTPException(404, "Company not found")
        return result

    @app.get(f"{settings.api_prefix}/skills")
    def skills(session: SessionDep) -> list[dict]:
        return SkillRepository(session).list()

    @app.get(f"{settings.api_prefix}/analytics/overview")
    def overview(session: SessionDep) -> dict:
        return _meta(session) | {"data": AnalyticsRepository(session).overview()}

    @app.get(f"{settings.api_prefix}/analytics/categories")
    def categories(session: SessionDep) -> dict:
        metadata = _meta(session)
        rows = AnalyticsRepository(session).grouped(JobPosting.primary_category)
        total = metadata["sample_size"]
        for row in rows:
            row["percentage"] = round(row["count"] / total * 100, 2) if total else 0.0
        return metadata | {"data": rows}

    @app.get(f"{settings.api_prefix}/analytics/skills")
    def analytics_skills(session: SessionDep) -> dict:
        return _meta(session) | {"data": SkillRepository(session).list()}

    @app.get(f"{settings.api_prefix}/analytics/salaries")
    def salaries(session: SessionDep) -> dict:
        return _meta(session) | {"data": AnalyticsRepository(session).salaries()}

    @app.get(f"{settings.api_prefix}/analytics/locations")
    def locations(session: SessionDep) -> dict:
        return _meta(session) | {
            "cities": AnalyticsRepository(session).grouped(JobPosting.city),
            "provinces": AnalyticsRepository(session).grouped(JobPosting.province),
            "work_modes": AnalyticsRepository(session).grouped(JobPosting.work_mode),
        }

    @app.get(f"{settings.api_prefix}/quality/summary")
    def quality(session: SessionDep) -> dict:
        return QualityRepository(session).summary()

    @app.get(f"{settings.api_prefix}/duplicates")
    def duplicates(session: SessionDep) -> list[dict]:
        return DuplicateRepository(session).list()

    return app


app = create_app()
