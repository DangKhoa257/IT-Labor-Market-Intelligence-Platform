"""Exact identity clustering."""

from __future__ import annotations

from collections import defaultdict

from .fingerprints import canonical_url, content_hash, identity_key


def exact_clusters(records: list[dict]) -> list[list[int]]:
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        for kind, value in (
            ("identity", identity_key(record)),
            ("url", canonical_url(record)),
            ("hash", content_hash(record)),
        ):
            if value and value != (None, None):
                groups[(kind, str(value))].append(index)
    candidate_groups = [
        set(indices) for _, indices in sorted(groups.items()) if len(set(indices)) > 1
    ]
    merged: list[set[int]] = []
    for candidate in candidate_groups:
        overlapping = [group for group in merged if group & candidate]
        if overlapping:
            for group in overlapping:
                candidate.update(group)
                merged.remove(group)
        merged.append(candidate)
    return [sorted(group) for group in sorted(merged, key=lambda group: min(group))]
