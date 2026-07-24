from __future__ import annotations

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import JobPosting, JobSkill, Skill


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, job_id: int) -> JobPosting | None:
        return self.session.scalar(
            select(JobPosting)
            .options(selectinload(JobPosting.skills).selectinload(JobSkill.skill))
            .where(JobPosting.id == job_id)
        )

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
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
        sort: str = "posted_at",
        order: str = "desc",
    ) -> tuple[list[JobPosting], int]:
        statement: Select[tuple[JobPosting]] = select(JobPosting).options(
            selectinload(JobPosting.company),
            selectinload(JobPosting.skills).selectinload(JobSkill.skill),
        )
        if category:
            statement = statement.where(JobPosting.primary_category == category)
        if city:
            statement = statement.where(JobPosting.city == city)
        if company_id:
            statement = statement.where(JobPosting.company_id == company_id)
        if employment_type:
            statement = statement.where(JobPosting.employment_type == employment_type)
        if work_mode:
            statement = statement.where(JobPosting.work_mode == work_mode)
        if status:
            statement = statement.where(JobPosting.status == status)
        if salary_disclosed is not None:
            statement = statement.where(JobPosting.salary_disclosed == salary_disclosed)
        if salary_min is not None:
            statement = statement.where(JobPosting.salary_max >= salary_min)
        if salary_max is not None:
            statement = statement.where(JobPosting.salary_min <= salary_max)
        if keyword:
            statement = statement.where(
                or_(
                    JobPosting.title_raw.ilike(f"%{keyword}%"),
                    JobPosting.title_normalized.ilike(f"%{keyword}%"),
                )
            )
        if skill:
            statement = statement.join(JobSkill).join(Skill).where(Skill.canonical_name == skill)
        count = (
            self.session.scalar(
                select(func.count()).select_from(statement.order_by(None).subquery())
            )
            or 0
        )
        sort_column = {
            "posted_at": JobPosting.posted_at,
            "collected_at": JobPosting.collected_at,
            "salary": JobPosting.salary_min,
        }[sort]
        ordering = sort_column.asc() if order == "asc" else sort_column.desc()
        items = list(
            self.session.scalars(
                statement.order_by(ordering, JobPosting.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).unique()
        )
        return items, count
