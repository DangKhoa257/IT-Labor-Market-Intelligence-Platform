"""Duplicate clusters retain all original records and choose no destructive action."""

from __future__ import annotations

from typing import Any

from .exact import exact_clusters
from .similarity import compare_records


def deduplicate_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    clusters: list[dict[str, Any]] = []
    seen: set[tuple[int, ...]] = set()
    for indices in exact_clusters(records):
        key = tuple(indices)
        if key in seen:
            continue
        seen.add(key)
        clusters.append(
            {
                "classification": "EXACT_DUPLICATE",
                "representative_index": indices[0],
                "member_indices": indices,
                "members": [_member_identity(records[index]) for index in indices],
                "decision": {"score": 1.0, "method_version": "dedup.v1", "confidence": 1.0},
            }
        )
    for left in range(len(records)):
        for right in range(left + 1, len(records)):
            comparison = compare_records(records[left], records[right])
            if comparison["classification"] != "DISTINCT":
                clusters.append(
                    {
                        "classification": comparison["classification"],
                        "representative_index": left,
                        "member_indices": [left, right],
                        "members": [
                            _member_identity(records[left]),
                            _member_identity(records[right]),
                        ],
                        "decision": comparison,
                    }
                )
    return {"method_version": "dedup.v1", "cluster_count": len(clusters), "clusters": clusters}


def _member_identity(record: dict[str, Any]) -> dict[str, Any]:
    raw = record.get("raw", {})
    return {
        "source": raw.get("source"),
        "source_job_id": raw.get("source_job_id"),
        "source_url": raw.get("source_url"),
    }
