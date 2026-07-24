from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import DataQualityIssue, JobPosting


class QualityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def summary(self) -> dict[str, Any]:
        rows = self.session.execute(
            select(DataQualityIssue.code, func.count())
            .group_by(DataQualityIssue.code)
            .order_by(DataQualityIssue.code)
        )
        return {
            "total_jobs": self.session.scalar(select(func.count(JobPosting.id))) or 0,
            "issues": [{"code": code, "count": count} for code, count in rows],
        }
