from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Company, JobPosting, JobSkill, Skill


class CompanyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[dict[str, Any]]:
        rows = self.session.execute(
            select(
                Company.id,
                Company.name,
                func.count(JobPosting.id),
                func.count(JobPosting.id).filter(JobPosting.status == "ACTIVE"),
            )
            .outerjoin(JobPosting)
            .group_by(Company.id)
            .order_by(Company.name, Company.id)
        )
        return [
            {"id": row[0], "name": row[1], "job_count": row[2], "active_job_count": row[3] or 0}
            for row in rows
        ]

    def get(self, company_id: int) -> dict[str, Any] | None:
        result = next((item for item in self.list() if item["id"] == company_id), None)
        if result is None:
            return None
        categories = self.session.execute(
            select(JobPosting.primary_category, func.count())
            .where(JobPosting.company_id == company_id)
            .group_by(JobPosting.primary_category)
            .order_by(func.count().desc(), JobPosting.primary_category)
        )
        skills = self.session.execute(
            select(Skill.canonical_name, func.count(JobSkill.job_id))
            .join(JobSkill)
            .join(JobPosting)
            .where(JobPosting.company_id == company_id)
            .group_by(Skill.id)
            .order_by(func.count(JobSkill.job_id).desc(), Skill.canonical_name)
        )
        return result | {
            "categories": [{"value": value, "count": count} for value, count in categories],
            "top_skills": [{"value": value, "count": count} for value, count in skills],
        }
