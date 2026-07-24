# Deduplication Engine

The deduplication engine is deterministic and non-destructive. Exact clusters merge overlapping identity signals: `(source, source_job_id)`, canonical source URL, and content hash. Every cluster keeps member source, job ID, and URL and selects only a report representative.

Probable matching uses normalized company, title-token Jaccard score, city, employment type, disclosed salary range, and canonical skills. Scores at least `0.80` are `PROBABLE_DUPLICATE`; scores from `0.60` to `0.7999` are `POSSIBLE_DUPLICATE`. Lower scores are `DISTINCT`.

The output is advisory: probable and possible matches are never automatically removed. Missing evidence contributes no positive score, which keeps incomplete records from becoming duplicates solely through absent fields.
