from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import DuplicateCluster, DuplicateClusterMember


class DuplicateRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[dict]:
        rows = self.session.execute(
            select(
                DuplicateCluster.id,
                DuplicateCluster.classification,
                DuplicateCluster.score,
                func.count(DuplicateClusterMember.id),
            )
            .outerjoin(DuplicateClusterMember)
            .group_by(DuplicateCluster.id)
            .order_by(DuplicateCluster.id)
        )
        return [
            {
                "id": row[0],
                "classification": row[1],
                "score": float(row[2]) if row[2] is not None else None,
                "member_count": row[3],
            }
            for row in rows
        ]
