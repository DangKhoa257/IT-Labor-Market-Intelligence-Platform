"""Idempotent import of advisory duplicate-report clusters."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import DuplicateCluster, DuplicateClusterMember, JobPosting, Source


class DuplicateReportImporter:
    def __init__(self, session: Session) -> None:
        self.session = session

    def import_path(self, path: Path, *, dry_run: bool = False) -> dict[str, int]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("clusters"), list):
            raise ValueError("Duplicate report must contain a clusters array")
        method_version = payload.get("method_version")
        if not isinstance(method_version, str) or not method_version:
            raise ValueError("Duplicate report method_version is required")

        counts = {"inserted": 0, "updated": 0, "skipped": 0, "deleted": 0}
        existing = list(
            self.session.scalars(
                select(DuplicateCluster).where(DuplicateCluster.method_version == method_version)
            )
        )
        existing_by_members = {self._member_ids(cluster.id): cluster for cluster in existing}
        retained_ids: set[int] = set()

        try:
            for raw_cluster in cast(list[Any], payload["clusters"]):
                if not isinstance(raw_cluster, dict):
                    raise ValueError("Duplicate cluster entries must be objects")
                member_jobs, representative_job_id = self._resolve_members(raw_cluster)
                signature = frozenset(job.id for job in member_jobs)
                if len(signature) < 2:
                    raise ValueError("Duplicate clusters require at least two resolved jobs")
                classification = raw_cluster.get("classification")
                decision = raw_cluster.get("decision", {})
                if not isinstance(classification, str) or not isinstance(decision, dict):
                    raise ValueError("Duplicate classification and decision are required")
                raw_score = decision.get("score")
                score = Decimal(str(raw_score)) if raw_score is not None else None
                cluster = existing_by_members.get(signature)
                if cluster is None:
                    cluster = DuplicateCluster(
                        classification=classification,
                        score=score,
                        method_version=method_version,
                    )
                    self.session.add(cluster)
                    self.session.flush()
                    self._replace_members(cluster.id, member_jobs, representative_job_id)
                    counts["inserted"] += 1
                elif self._is_unchanged(cluster, classification, score, representative_job_id):
                    counts["skipped"] += 1
                else:
                    cluster.classification = classification
                    cluster.score = score
                    self._replace_members(cluster.id, member_jobs, representative_job_id)
                    counts["updated"] += 1
                retained_ids.add(cluster.id)

            for cluster in existing:
                if cluster.id in retained_ids:
                    continue
                self.session.execute(
                    delete(DuplicateClusterMember).where(
                        DuplicateClusterMember.cluster_id == cluster.id
                    )
                )
                self.session.delete(cluster)
                counts["deleted"] += 1
            if dry_run:
                self.session.rollback()
            else:
                self.session.commit()
            return counts
        except Exception:
            self.session.rollback()
            raise

    def _member_ids(self, cluster_id: int) -> frozenset[int]:
        return frozenset(
            self.session.scalars(
                select(DuplicateClusterMember.job_id).where(
                    DuplicateClusterMember.cluster_id == cluster_id
                )
            )
        )

    def _resolve_members(self, raw_cluster: dict[str, Any]) -> tuple[list[JobPosting], int]:
        references = raw_cluster.get("members")
        member_indices = raw_cluster.get("member_indices")
        representative_index = raw_cluster.get("representative_index")
        if not isinstance(references, list) or not isinstance(member_indices, list):
            raise ValueError("Duplicate cluster members and member_indices are required")
        jobs: list[JobPosting] = []
        representative_job_id: int | None = None
        for position, reference in enumerate(references):
            if not isinstance(reference, dict):
                raise ValueError("Duplicate member references must be objects")
            source_name = reference.get("source")
            source_job_id = reference.get("source_job_id")
            if not isinstance(source_name, str) or not isinstance(source_job_id, str):
                raise ValueError("Duplicate member source identity is required")
            job = self.session.scalar(
                select(JobPosting)
                .join(Source)
                .where(
                    Source.name == source_name,
                    JobPosting.source_job_id == source_job_id,
                )
            )
            if job is None:
                raise ValueError(f"Duplicate member not found: {source_name}/{source_job_id}")
            jobs.append(job)
            if position < len(member_indices) and member_indices[position] == representative_index:
                representative_job_id = job.id
        return jobs, representative_job_id or jobs[0].id

    def _replace_members(
        self, cluster_id: int, jobs: list[JobPosting], representative_job_id: int
    ) -> None:
        self.session.execute(
            delete(DuplicateClusterMember).where(DuplicateClusterMember.cluster_id == cluster_id)
        )
        self.session.add_all(
            DuplicateClusterMember(
                cluster_id=cluster_id,
                job_id=job.id,
                representative=job.id == representative_job_id,
            )
            for job in jobs
        )

    def _is_unchanged(
        self,
        cluster: DuplicateCluster,
        classification: str,
        score: Decimal | None,
        representative_job_id: int,
    ) -> bool:
        current_representative = self.session.scalar(
            select(DuplicateClusterMember.job_id).where(
                DuplicateClusterMember.cluster_id == cluster.id,
                DuplicateClusterMember.representative.is_(True),
            )
        )
        return (
            cluster.classification == classification
            and cluster.score == score
            and current_representative == representative_job_id
        )
