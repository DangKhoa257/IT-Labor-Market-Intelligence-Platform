"""Idempotent canonical JSONL importer."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from it_labor_market_intelligence.data_io import iter_jsonl

from ..models import Company, CrawlRun, DataQualityIssue, JobPosting, JobSkill, Skill, Source


def _date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _decimal(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


class DatasetImporter:
    def __init__(self, session: Session) -> None:
        self.session = session

    def import_path(
        self,
        path: Path,
        *,
        source_name: str | None = None,
        replace_existing: bool = False,
        batch_size: int = 100,
        dry_run: bool = False,
    ) -> dict[str, int]:
        counts = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0}
        run = CrawlRun(run_type="IMPORT")
        self.session.add(run)
        self.session.flush()
        try:
            for index, payload in enumerate(iter_jsonl(path), start=1):
                raw = payload.get("raw", {})
                normalized = payload.get("normalized", {})
                source_value = source_name or raw.get("source") or normalized.get("source")
                if not source_value or not raw.get("source_job_id"):
                    counts["failed"] += 1
                    continue
                source = self.session.scalar(select(Source).where(Source.name == source_value))
                if source is None:
                    source = Source(name=source_value)
                    self.session.add(source)
                    self.session.flush()
                run.source_id = source.id
                job = self.session.scalar(
                    select(JobPosting).where(
                        JobPosting.source_id == source.id,
                        JobPosting.source_job_id == str(raw["source_job_id"]),
                    )
                )
                existing = job is not None
                if existing and not replace_existing:
                    counts["skipped"] += 1
                    continue
                company_data = payload.get("enrichment", {}).get("company", {})
                company_key = company_data.get("company_comparison_key")
                company = None
                if company_key:
                    company = self.session.scalar(
                        select(Company).where(Company.comparison_key == company_key)
                    )
                    if company is None:
                        company = Company(
                            name=company_data.get("company_name_normalized")
                            or raw.get("company_name_raw"),
                            comparison_key=company_key,
                        )
                        self.session.add(company)
                        self.session.flush()
                if job is None:
                    job = JobPosting(
                        source_id=source.id,
                        source_job_id=str(raw["source_job_id"]),
                        source_url=str(raw.get("source_url") or ""),
                        title_raw=str(raw.get("title_raw") or ""),
                        collected_at=_date(
                            raw.get("collected_at") or normalized.get("collected_at")
                        )
                        or datetime.now(UTC),
                        status=raw.get("closed_state") or "UNKNOWN",
                    )
                    self.session.add(job)
                    counts["inserted"] += 1
                else:
                    counts["updated"] += 1
                self._apply(job, payload, company)
                self.session.flush()
                self._replace_children(job, payload)
                if index % batch_size == 0 and not dry_run:
                    self.session.commit()
            run.inserted, run.updated, run.skipped, run.failed = counts.values()
            run.finished_at = datetime.now(UTC)
            if dry_run:
                self.session.rollback()
            else:
                self.session.commit()
            return counts
        except Exception:
            self.session.rollback()
            raise

    def _apply(self, job: JobPosting, payload: dict[str, Any], company: Company | None) -> None:
        raw, normalized, enrichment = (
            payload.get("raw", {}),
            payload.get("normalized", {}),
            payload.get("enrichment", {}),
        )
        salary, experience = normalized.get("salary", {}), normalized.get("experience", {})
        location = enrichment.get("location", {})
        values = {
            "source_url": raw.get("source_url"),
            "title_raw": raw.get("title_raw"),
            "title_normalized": normalized.get("title_normalized"),
            "primary_category": normalized.get("primary_category"),
            "secondary_categories": normalized.get("secondary_categories", []),
            "company": company,
            "location_raw": raw.get("location_raw"),
            "city": location.get("city"),
            "province": location.get("province"),
            "country": location.get("country"),
            "work_mode": enrichment.get("work_mode", {}).get("work_mode"),
            "employment_type": enrichment.get("employment", {}).get("employment_type"),
            "seniority": normalized.get("seniority"),
            "experience_min_years": _decimal(experience.get("minimum_years")),
            "experience_max_years": _decimal(experience.get("maximum_years")),
            "salary_raw": raw.get("salary_raw"),
            "salary_min": _decimal(salary.get("minimum")),
            "salary_max": _decimal(salary.get("maximum")),
            "salary_currency": salary.get("currency"),
            "salary_period": salary.get("period"),
            "salary_type": salary.get("salary_type"),
            "salary_disclosed": bool(salary.get("disclosed")),
            "posted_at": _date(raw.get("posted_at_raw")),
            "expires_at": _date(raw.get("expires_at_raw")),
            "collected_at": _date(raw.get("collected_at") or normalized.get("collected_at"))
            or job.collected_at,
            "status": raw.get("closed_state") or "UNKNOWN",
            "content_hash": raw.get("content_hash"),
            "extractor_version": raw.get("extractor_version"),
            "normalization_version": "phase2.v1",
            "confidence_score": _decimal(normalized.get("confidence_score")),
            "description_raw": raw.get("description_raw"),
            "provenance": normalized.get("field_provenance", {}),
        }
        for key, value in values.items():
            setattr(job, key, value)

    def _replace_children(self, job: JobPosting, payload: dict[str, Any]) -> None:
        job.skills.clear()
        for match in payload.get("normalized", {}).get("skills", []):
            name = match.get("canonical_name")
            if not name:
                continue
            skill = self.session.scalar(select(Skill).where(Skill.canonical_name == name))
            if skill is None:
                skill = Skill(canonical_name=name, category=match.get("category"))
                self.session.add(skill)
                self.session.flush()
            job.skills.append(
                JobSkill(
                    skill=skill,
                    confidence=_decimal(match.get("confidence")),
                    evidence=str(match.get("evidence_span") or "") or None,
                )
            )
        self.session.query(DataQualityIssue).filter(DataQualityIssue.job_id == job.id).delete()
        for finding in payload.get("quality_issues", []) + payload.get("normalized", {}).get(
            "validation_issues", []
        ):
            self.session.add(
                DataQualityIssue(
                    job_id=job.id,
                    code=str(finding.get("code", "unknown")),
                    severity=str(finding.get("severity", "INFO")).upper(),
                    field_name=finding.get("field_name"),
                    message=str(finding.get("message", "")),
                )
            )
