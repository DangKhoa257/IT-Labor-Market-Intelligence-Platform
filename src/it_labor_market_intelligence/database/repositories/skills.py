from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Company, JobPosting, JobSkill, Skill


class SkillRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[dict[str, Any]]:
        rows = self.session.execute(
            select(Skill.id, Skill.canonical_name, Skill.category, func.count(JobSkill.job_id))
            .outerjoin(JobSkill)
            .group_by(Skill.id)
            .order_by(func.count(JobSkill.job_id).desc(), Skill.canonical_name)
        )
        result = []
        for row in rows:
            categories = self.session.execute(
                select(JobPosting.primary_category)
                .join(JobSkill)
                .where(JobSkill.skill_id == row[0])
                .distinct()
                .order_by(JobPosting.primary_category)
            )
            companies = self.session.execute(
                select(Company.id, Company.name)
                .join(JobPosting)
                .join(JobSkill)
                .where(JobSkill.skill_id == row[0])
                .distinct()
                .order_by(Company.name, Company.id)
            )
            result.append(
                {
                    "id": row[0],
                    "canonical_name": row[1],
                    "category": row[2],
                    "job_count": row[3],
                    "categories": [value for (value,) in categories],
                    "companies": [{"id": item[0], "name": item[1]} for item in companies],
                }
            )
        return result
