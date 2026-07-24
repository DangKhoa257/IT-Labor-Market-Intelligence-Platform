# Offline Processing Design

**Phase:** 1B-OFFLINE  
**Scope:** source-agnostic deterministic normalization only  
**Data constraint:** existing sanitized fixtures and records explicitly marked
`SYNTHETIC_TEST_DATA`; synthetic records are not labor-market observations.

This foundation performs no network access. It does not discover jobs, crawl pages, call an
external API or LLM, persist records, or produce market analytics. Source approval remains governed
by `SOURCE_DECISION.md`; this design does not change that policy.

## Module boundaries

| Module | Responsibility | Must not do |
|---|---|---|
| `domain` | Immutable typed input, output, evidence, and validation contracts | Parse source markup or apply source rules |
| `processing.salary` | Parse explicit numeric salary, currency, period, and gross/net evidence | Infer currency, period, gross/net, or exchange rates |
| `processing.experience` | Parse explicit Vietnamese and English year constraints | Infer experience from seniority or missing text |
| `processing.skills` | Load the Markdown seed and match canonical skills with boundaries and exclusions | Call an LLM/API or infer unmentioned skills |
| `processing.job_titles` | Normalize title display text and apply deterministic category rules | Claim statistical or ML accuracy |
| `processing.pipeline` | Compose the independent processors and collect provenance/issues | Fetch, store, schedule, or analyze records |

Each ruleset has an explicit version constant. Taxonomy changes should result in a new ruleset
version and regression tests rather than ad hoc output edits.

## Input and output contracts

`RawJobRecord` is the only pipeline input. A future source adapter must supply stable source
identity, `source_url`, raw title and description, and a timezone-aware `collected_at`. Optional raw
salary and experience regions remain nullable. `skills_raw=None` means the adapter did not expose a
dedicated skill region; an empty tuple means the region existed but contained no values.

`normalize_job_record(raw)` returns `NormalizedJobRecord`. Direct traceability fields are copied
without source-specific interpretation. Derived fields are represented by `Salary`,
`ExperienceRange`, `SkillMatch`, title/category values, a field-level provenance map, and
non-destructive `ValidationIssue` warnings.

The standalone parser contracts are:

- `parse_salary(str | None) -> Salary`
- `parse_experience(str | None) -> ExperienceRange`
- `load_skill_taxonomy(Path | None) -> tuple[SkillDefinition, ...]`
- `match_skills(str | None, taxonomy=None) -> tuple[SkillMatch, ...]`
- `normalize_job_title(str) -> TitleNormalization`

Results are immutable. Monetary amounts use `Decimal` base currency units; experience uses decimal
years. Evidence spans use Python half-open offsets `[start, end)` against NFC-normalized input. NFC
preserves character order, so ordinary Vietnamese and English input keeps usable offsets.

## Normalization rules

### Salary

- VND and USD are recognized only from explicit symbols or names.
- `triệu`/`trieu`/`million` scale by 1,000,000; `k`/`thousand` scale by 1,000.
- Two leading values form a range. `from`/`từ` forms an open upper range; `up to`/`tối đa` forms an
  open lower range; a bare single value sets both bounds to that value.
- Hour, month, and year are populated only from explicit English or Vietnamese period evidence.
- Gross and net are populated only when stated. Conflicting type evidence yields null.
- A negotiable phrase always produces `disclosed=false`, null numeric bounds, and type
  `negotiable`, even if unrelated numbers appear in the same raw region.
- `salary_raw` is preserved exactly. Currency conversion is outside this phase.

### Experience

- Explicit no-experience-required phrases produce the closed range `[0, 0]`.
- `under N`/`dưới N` produces an exclusive maximum with no invented minimum.
- `minimum N`, `at least N`, `N+`, `tối thiểu N`, and `từ N` produce an inclusive minimum.
- `N-M`, `N to M`, and `N đến M` produce an inclusive range.
- `more than N`, `over N`, `hơn N`, and `trên N` produce an exclusive minimum.
- Reversed and unrecognized ranges remain null and receive zero parse confidence.

### Skills

`docs/SKILL_TAXONOMY.md` is the seed registry for canonical names, aliases, categories, and
false-positive notes. Matching is case-insensitive and boundary-aware. Whitespace in aliases is
flexible; canonical results are deduplicated. Candidate matches sort by source offset, longest match,
then canonical name, making output repeatable.

Known ambiguous short/common aliases (for example `Go`, `React`, `Spring`, `JS`, and `TS`) require
nearby technical requirement context. Human languages require nearby proficiency/communication
context. Explicit exclusions cover incidental `.py`, chemical selenium, and the non-technical
occupation “playwright.” These rules are conservative and versioned, not semantic understanding.

### Titles and categories

Display normalization applies Unicode NFKC, whitespace cleanup, common backend/frontend/full-stack
alias normalization, title casing, and acronym restoration. Category rules are seeded from
`docs/JOB_TAXONOMY.md`. The earliest explicit role in a multi-role title is primary; other matched
roles are stable secondary categories. No match produces `Unclassified` with zero confidence.
Confidence is rule confidence only, not measured predictive accuracy.

## Null semantics

Null means “not stated, ambiguous, unavailable, or not safely parsed.” It never means zero. The only
experience zero is an explicit no-experience-required statement. Missing currency never defaults to
VND; missing gross/net never defaults to gross; missing pay period never defaults to month.

For collections, `None` at adapter input denotes an unavailable source region, while an empty tuple
denotes an observed region with no values. Matcher output is always a deterministic tuple and may be
empty. A `ValidationIssue` distinguishes important unparsed or ambiguous cases without inventing a
replacement value.

## Provenance model

Every derived field is registered in `NormalizedJobRecord.field_provenance`. `FieldProvenance`
requires:

- `source_field`: raw field used;
- `method`: deterministic transformation name;
- `rule_version`: parser or taxonomy version;
- `confidence`: bounded value from 0 through 1;
- `evidence_text` or `evidence_key`: inline evidence or a stable pointer to it.

Nested parser results also carry provenance, and every `SkillMatch` carries its exact evidence text
and span. Several fields may legitimately share one immutable provenance object when a single parse
produced them, such as salary bounds and currency.

## Limitations

- Rules cover the requested seed phrases, not every salary or experience convention.
- A raw region containing several unrelated monetary amounts can be ambiguous; the parser does not
  attempt semantic section analysis.
- No foreign-exchange, annualization, hourly conversion, or cost-of-living transformation occurs.
- Context windows reduce common skill false positives but cannot understand prose.
- Title classification uses title evidence only. Generic titles and responsibility-led distinctions
  remain `Unclassified`; no accuracy claim is made until a representative approved gold set exists.
- The Markdown loader is intentionally simple and expects the seed's four-column table structure.
- There is no production crawling, database, API, dashboard, scheduling, AI/LLM, or analytics in
  this phase.

## Future source adapters

A future adapter may be added only after its source is separately approved. It will transform
already-acquired, policy-compliant source evidence into `RawJobRecord`; it must not place source
conditionals in processing modules. The adapter then calls `normalize_job_record`, stores or
serializes the returned contract in a later approved phase, and retains the raw evidence referenced
by provenance keys. Adapter tests should use sanitized offline fixtures and cover missing/malformed
source fields. Adding an adapter does not authorize fetching, and this pipeline never initiates a
request itself.
