from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DuplicateCluster, DuplicateClusterMember, JobPosting, Source


class DuplicateRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[dict[str, Any]]:
        clusters = list(
            self.session.scalars(select(DuplicateCluster).order_by(DuplicateCluster.id))
        )
        results: list[dict[str, Any]] = []
        for cluster in clusters:
            members = self.session.execute(
                select(
                    JobPosting.id,
                    Source.name,
                    JobPosting.source_job_id,
                    JobPosting.source_url,
                    DuplicateClusterMember.representative,
                )
                .join(JobPosting, JobPosting.id == DuplicateClusterMember.job_id)
                .join(Source, Source.id == JobPosting.source_id)
                .where(DuplicateClusterMember.cluster_id == cluster.id)
                .order_by(DuplicateClusterMember.representative.desc(), JobPosting.id)
            )
            member_values = [
                {
                    "job_id": row[0],
                    "source": row[1],
                    "source_job_id": row[2],
                    "source_url": row[3],
                    "representative": row[4],
                }
                for row in members
            ]
            results.append(
                {
                    "id": cluster.id,
                    "classification": cluster.classification,
                    "score": float(cluster.score) if cluster.score is not None else None,
                    "member_count": len(member_values),
                    "method_version": cluster.method_version,
                    "members": member_values,
                }
            )
        return results
