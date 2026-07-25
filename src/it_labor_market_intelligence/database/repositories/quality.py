from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import DataQualityIssue, JobPosting


class QualityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def summary(self) -> dict[str, Any]:
        rows = self.session.execute(
            select(DataQualityIssue.code, DataQualityIssue.severity, func.count())
            .group_by(DataQualityIssue.code, DataQualityIssue.severity)
            .order_by(DataQualityIssue.severity, DataQualityIssue.code)
        )
        total = self.session.scalar(select(func.count(JobPosting.id))) or 0
        rejected = (
            self.session.scalar(
                select(func.count(func.distinct(DataQualityIssue.job_id))).where(
                    DataQualityIssue.severity == "REJECT"
                )
            )
            or 0
        )
        info = (
            self.session.scalar(
                select(func.count(func.distinct(DataQualityIssue.job_id))).where(
                    DataQualityIssue.severity == "INFO"
                )
            )
            or 0
        )
        warning_or_error = (
            self.session.scalar(
                select(func.count(func.distinct(DataQualityIssue.job_id))).where(
                    DataQualityIssue.severity.in_(("WARNING", "ERROR"))
                )
            )
            or 0
        )
        classified = (
            self.session.scalar(
                select(func.count(JobPosting.id)).where(
                    JobPosting.primary_category.is_not(None),
                    JobPosting.primary_category != "Unclassified",
                )
            )
            or 0
        )
        return {
            "total_jobs": total,
            "accepted_records": total - rejected,
            "rejected_records": rejected,
            "records_with_info_notices": info,
            "records_with_warning_or_error_issues": warning_or_error,
            "title_classified_records": classified,
            "title_classification_coverage": round(classified / total, 4) if total else 0.0,
            "issues": [
                {"code": code, "severity": severity, "count": count}
                for code, severity, count in rows
            ],
        }
