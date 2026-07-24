# Phase 1A Source Verification Report

**Verification date:** 2026-07-24 (Asia/Ho_Chi_Minh, UTC+07:00)  
**Status:** evidence-gathering only; no source is approved for production crawling by this report.  
**Legal disclaimer:** these are robots.txt, public-Terms and technical observations, not legal conclusions.

## 1. Objective

Verify the policy and technical claims made about ITviec, TopDev and Glints Vietnam before any source adapter is implemented. The Gemini feasibility report was treated as research input, not as evidence. This sprint does not authorize Phase 1B, bulk collection or production crawling.

## 2. Method and safety limits

- Read the Phase 0 product, schema, architecture, benchmark and agent-rule documents.
- Read the accessible Gemini DOCX report in `docs/research/`.
- Used `VietnamITLaborMarketIntelligence-SourceVerification/1.0 (low-volume public-source verification; no production crawling)` for direct HTTP checks.
- Used GET requests only, at least two seconds apart within each request sequence.
- Inspected robots.txt and public Terms before job details.
- Stopped ITviec and Glints before job-detail sampling when policy/access evidence required a stop.
- Inspected four unique TopDev job-detail URLs: three current sitemap entries and one historical URL.
- Retained only small sanitized JSON-LD/HTML fragments. Full pages, full descriptions, request headers, personal data and tracking data were not retained.
- Did not use login sessions, proxies, CAPTCHA handling, browser fingerprint evasion or employer interactions.

The job-detail sample is purposive and tiny. It demonstrates current technical behavior only; it does not establish long-term stability or field-coverage rates.

## 3. ITviec findings

### Robots.txt findings

- URL: `https://itviec.com/robots.txt`
- Accessed: 2026-07-24 13:24 +07:00
- HTTP: 200, `text/plain`
- `User-Agent: *` allows `/` and disallows `/subscriptions/new`.
- Declared sitemap: `https://itviec.com/dunggiatminh.xml`.

### Terms findings

- URL: `https://itviec.com/blog/terms-and-conditions/`
- Accessed: 2026-07-24T13:25:22.7824400+07:00
- HTTP: 200, `text/html; charset=UTF-8`
- Section 2.2 states that, beyond what is necessary for reasonable personal use, site content may not be retrieved, displayed, modified, copied, printed, sold, downloaded, reverse engineered or transmitted.
- This observation is not a legal conclusion. It creates a policy ambiguity for a research/analytics ingestion project and requires owner/legal review or written permission.

### Sitemap and technical findings

- `https://itviec.com/dunggiatminh.xml` returned HTTP 200 at 2026-07-24T13:25:26.2248444+07:00.
- It is a sitemap index with multiple child sitemaps and a current `lastmod`.
- Job-detail pages were **not inspected** after the Terms gate. Gemini claims about numeric job IDs, static HTML, JSON-LD, fields, pagination and closed-state behavior remain unverified in this sprint.

### Project recommendation

**MANUAL REVIEW REQUIRED.** Do not implement or operate an ITviec adapter until the intended collection, retention and analytics use is reviewed against the Terms and explicitly approved. Robots permission alone is not treated as sufficient authorization.

## 4. TopDev findings

### Robots.txt findings

- URL: `https://topdev.vn/robots.txt`
- Accessed: 2026-07-24 13:24 +07:00
- HTTP: 200, `text/plain; charset=utf-8`
- General `User-agent: *` allows `/` but disallows login, employer search, partner, apply, affiliate, challenge, academy and socket paths.
- Cloudflare content signals state `search=yes`, `ai-train=no`, `use=reference`.
- Declared sitemap: `https://topdev.vn/sitemap.xml`.
- These directives did not disallow the public listing/detail paths inspected. They do not independently grant project permission.

### Terms findings

- URL: `https://topdev.vn/term-of-services`
- Accessed: 2026-07-24T13:25:29.0531317+07:00
- HTTP: 200, `text/html; charset=utf-8`
- The inspected Terms contain broad intellectual-property and acceptable-use provisions. No explicit crawler/screen-scraping permission was found, and the keyword review did not find an explicit scraper prohibition.
- Absence of an explicit prohibition is not treated as permission; manual compliance review remains necessary.

### Listing, sitemap and pagination

- `https://topdev.vn/sitemap.xml`: HTTP 200; declares `https://topdev.vn/sitemap-jobs.xml`.
- `https://topdev.vn/sitemap-jobs.xml`: HTTP 200; it is an index of paged job sitemaps, not a flat job URL list.
- `https://topdev.vn/sitemap/jobs_desc_en_page_1.xml`: HTTP 200; supplied the three active sample URLs.
- `https://topdev.vn/viec-lam/tim-kiem`: HTTP 200 without login. The rendered listing showed both **Load more** and numbered navigation (`Previous`, pages, `Next`). Gemini's “traditional numbered pagination only” claim is false/incomplete.

### Active job-detail sample

All three active URLs returned HTTP 200 without login and retained their requested URL:

| URL job ID | Fetched at (+07:00) | JSON-LD | Selected direct structured evidence |
|---|---|---|---|
| `2121362` | 2026-07-24T13:28:28.5115239 | `JobPosting` | title, company, location, date posted, valid through, skills, 12 months experience, salary object |
| `2121361` | 2026-07-24T13:28:30.8342064 | `JobPosting` | title, company, location, date posted, valid through, skills, 24 months experience, salary object |
| `2121360` | 2026-07-24T13:28:33.1333680 | `JobPosting` | title, company, location, date posted, valid through, skills, 24 months experience, salary object |

Observed detail response sizes were about 333-421 KB. Each had two JSON-LD blocks, including a `JobPosting`. No `__NEXT_DATA__`, `__NUXT__` or `__NUXT_DATA__` marker was observed.

Important quality findings:

- The numeric job ID is present at the end of each sitemap/detail URL.
- `JobPosting.identifier.value` was `85784`, `95326` and `78272`, while URL job IDs were `2121362`, `2121361` and `2121360`. The JSON-LD identifier is therefore not the source job ID in these samples; it appears to identify the company.
- `employmentType` was `OTHER` in all three JSON-LD samples, so it cannot be accepted as a canonical full-time/part-time value without separate evidence.
- One negotiable sample emitted `currency=VND`, `unitText=MONTH`, and `value=Negotiable`. Canonical salary currency/period must remain null when no numeric salary is disclosed unless an explicit source statement supports those values.
- Numeric salary samples represented the range as one source string inside `value`, not as clean min/max numeric properties.
- JSON-LD did not expose a verified work-mode value in the sample (`jobLocationType` absent).
- Seniority and company size were not verified reliably in the retained active-detail evidence.
- Core structured extraction does not require JavaScript in the observed responses because JSON-LD was present in the initial HTML. Interactive rendering may still require JavaScript.

### Historical state

- URL ending `2086809` was inspected at 2026-07-24T13:29:02.1769182+07:00.
- It returned HTTP 200 at the same URL and exposed the visible state `Hết hạn`.
- This verifies one retained historical/closed state. It does not prove that all closed TopDev URLs behave this way.

### Project recommendation

**MANUAL REVIEW REQUIRED; TECHNICALLY PREFERRED CONDITIONAL PILOT.** TopDev is the only candidate with a completed technical sample in this sprint. If project ownership/compliance review approves the intended use, it should be the first adapter research target. JSON-LD should be primary evidence, with source-specific validation and tightly scoped HTML fallbacks.

## 5. Glints findings

### Robots.txt findings

- URL: `https://glints.com/robots.txt`
- Accessed: 2026-07-24 13:24 +07:00
- HTTP: 200, `text/plain; charset=utf-8`
- It disallows recommended/bookmarked jobs, settings, OAuth, password recovery, onboarding, preview, user and tracking paths, plus explore URLs with query strings.
- Declared sitemaps: `https://glints.com/sitemap_index.xml` and `https://glints.com/sitemaps/explore-page-id-sitemap.xml`.

### Terms findings

- Public Terms URL: `https://glints.com/vn/en/about/terms`.
- A direct low-volume research request returned HTTP 403 at 2026-07-24T13:25:34.7672417+07:00.
- The publicly indexed official Terms state that users are prohibited from using screen scraping, data mining, robots or similar gathering/extraction tools to establish, maintain, advance or reproduce site information on another website/publication without prior written consent.
- This is a policy observation, not a legal conclusion.

### Technical findings and recommendation

No listing, sitemap body or job-detail page was tested after the Terms/access gate. All Gemini technical claims about Next.js, `__NEXT_DATA__`, infinite scroll, fields and historical state remain unverified.

**EXCLUDE unless prior written consent is obtained.** The explicit Terms restriction and 403 response make further automated verification inappropriate in this sprint.

## 6. Field availability matrix

Classification describes the strongest evidence observed in this sprint, not a proposed canonical default.

### Required source comparison

| Source | Sample size | Public access | Job ID | Stable URL | HTML | JSON-LD | `__NEXT_DATA__` | JS required | Salary | Skills | Posted date | Experience | Work mode | Historical state | Compliance status | Technical difficulty | Recommendation |
|---|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ITviec | 0 detail pages | Policy resources public; details not tested | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | Manual review required | Not assessed | Pause pending policy approval |
| TopDev | 4 detail pages (3 active, 1 historical) | Yes, HTTP 200 without login | Numeric URL suffix observed | Four sampled URLs returned 200 without redirect; long-term stability unproven | Initial HTML contains structured evidence; no H1 established in raw sample | Yes, `JobPosting` on 3/3 active pages | Not observed | No for verified JSON-LD fields | Present with semantic caveats | Present | Present | Present in months | UNVERIFIED | One expired URL retained with `Hết hạn` | Manual review required | Medium | Preferred conditional pilot after approval |
| Glints | 0 detail pages | Terms request returned 403; details not tested | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | Exclude absent written consent | Not assessed | Exclude under current evidence |

### Canonical field evidence

| Field/claim | ITviec (n=0) | TopDev (3 active + 1 historical) | Glints (n=0) |
|---|---|---|---|
| Stable source job ID | UNVERIFIED | DIRECT_STRUCTURED — numeric URL suffix; long-term reuse still unverified | UNVERIFIED |
| Stable public detail URL | UNVERIFIED | DIRECT_STRUCTURED — four URLs returned 200 without redirect | UNVERIFIED |
| Title | UNVERIFIED | DIRECT_STRUCTURED — JSON-LD | UNVERIFIED |
| Company | UNVERIFIED | DIRECT_STRUCTURED — JSON-LD | UNVERIFIED |
| Location | UNVERIFIED | DIRECT_STRUCTURED — JSON-LD address | UNVERIFIED |
| Salary | UNVERIFIED | DIRECT_STRUCTURED — JSON-LD, but range/negotiable semantics require validation | UNVERIFIED |
| Posted date | UNVERIFIED | DIRECT_STRUCTURED — `datePosted` | UNVERIFIED |
| Expiry date | UNVERIFIED | DIRECT_STRUCTURED — `validThrough` | UNVERIFIED |
| Experience | UNVERIFIED | DIRECT_STRUCTURED — `monthsOfExperience` | UNVERIFIED |
| Seniority | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| Employment type | UNVERIFIED | DIRECT_STRUCTURED — observed only as low-information `OTHER` | UNVERIFIED |
| Work mode | UNVERIFIED | UNVERIFIED — no `jobLocationType`; must not default to onsite | UNVERIFIED |
| Skill tags | UNVERIFIED | DIRECT_STRUCTURED — JSON-LD `skills` source string | UNVERIFIED |
| Description | UNVERIFIED | DIRECT_STRUCTURED — JSON-LD present; full value not retained | UNVERIFIED |
| Company size | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| Closed-job state | UNVERIFIED | DIRECT_HTML — one historical page showed `Hết hạn` | UNVERIFIED |

No field in the table is classified as `INFERRED`; inference was intentionally not performed. No missing field was converted to a default.

## 7. Rendering and extraction strategy matrix

| Source | Discovery | Detail rendering | Primary evidence | Fallback | JS needed for verified fields | Strategy status |
|---|---|---|---|---|---|---|
| ITviec | Sitemap index observed | Not tested | UNVERIFIED | None proposed | UNVERIFIED | Stop pending manual policy review |
| TopDev | Sitemap index -> paged job sitemap; listing has load-more and numbered controls | Initial HTML contains JSON-LD; no H1 or Next/Nuxt marker was established in the raw sample | JSON-LD `JobPosting` plus URL suffix | Small, tested HTML selectors only for fields missing/invalid in JSON-LD | No for verified JSON-LD fields | Conditional parser research only after approval |
| Glints | Sitemap declarations observed in robots only | Not tested | UNVERIFIED | None proposed | UNVERIFIED | Exclude absent written consent |

## 8. Robots.txt and Terms observations

| Source | Robots observation | Terms observation | Access-control observation | Compliance status |
|---|---|---|---|---|
| ITviec | Job paths not disallowed; sitemap declared | Retrieval/copy restriction beyond reasonable personal use | No access-control response encountered in policy checks | Manual review required |
| TopDev | Public detail paths not disallowed; content signal reserves AI training; sitemap declared | Broad IP/use provisions; no explicit scraper rule found in inspected page | Public listing/details returned 200 without login | Manual review required |
| Glints | Some job/account/tracking paths disallowed; sitemaps declared | Explicit prior-written-consent requirement for screen scraping/data mining/robots | Terms request with research User-Agent returned 403 | Exclude absent consent |

Robots.txt and Terms answer different questions. This report does not interpret either as a legal grant.

## 9. Risks and unresolved questions

- TopDev permission for recurring analytics ingestion is not explicit.
- TopDev JSON-LD identifier semantics conflict with the Gemini assumption and require source-specific ID rules.
- TopDev structured employment type and negotiable salary metadata can be semantically misleading.
- Long-term URL stability, field coverage and DOM/JSON-LD stability cannot be inferred from four pages on one day.
- Closed-state behavior was observed once; 404, redirect and hidden variants remain unknown.
- Work mode, seniority and company size need approved follow-up sampling before parser design.
- ITviec technical suitability remains unknown because the policy gate stopped detail testing.
- Glints technical suitability remains unknown and should not be tested automatically without written consent.
- Sitemap removal alone must not mark a posting inactive; a failure or indexing change is not proof of closure.
- Any raw-description retention requires a source-specific copyright/retention decision.

## 10. Final source recommendation

1. **TopDev — manual review required; technically preferred conditional MVP candidate.** Proceed only after approval of the intended use and retention model.
2. **ITviec — manual review required.** Seek clarification/permission before technical sampling or adapter work.
3. **Glints — exclude absent prior written consent.** Do not continue automated verification under the current Terms/access response.

No source is declared fully approved for production crawling.

## 11. Proposed order for adapter development

1. TopDev, only after compliance owner approval: start with an offline parser over the sanitized JSON-LD fixtures; do not schedule network crawling.
2. ITviec, only after manual review/permission and a new bounded verification sprint.
3. Glints is not in the adapter queue unless prior written consent changes the policy gate.

Phase 1B should **not begin yet**. The prerequisite is an explicit project decision approving at least one source and its collection/retention policy.

## 12. Changes required in DATA_SCHEMA.md

Do not change the canonical schema during Phase 1A. The audit in `DATA_SCHEMA_AUDIT.md` proposes:

- field-level provenance and evidence method, not only record-level source/confidence;
- separate inference method and confidence for inferred values;
- explicit company visibility/unknown state;
- possible primary and secondary job categories;
- source-specific ID evidence rules;
- multi-location support;
- explicit unknown/undisclosed salary semantics;
- no defaults for work mode, currency, salary type or experience;
- source raw value retention for semantically weak structured values such as TopDev `employmentType=OTHER`.

These proposals require a versioned schema decision plus synchronized updates to the gold template and tests.

# Phase 1A.1 — Backup Source Verification

**Verification date:** 2026-07-24 (Asia/Ho_Chi_Minh, UTC+07:00)
**Candidates:** JobsGO and CareerViet
**Outcome:** both sources stopped at the policy/access gate; zero job-detail pages inspected.

## Objective and method

Evaluate JobsGO and CareerViet as possible replacements for Glints without implementing a crawler. Direct requests used `VietnamITLaborMarketIntelligence-SourceVerification/1.1 (low-volume public-source verification; no production crawling)`, GET only, with at least two seconds between requests in each sequence.

The same stop rules as Phase 1A applied. Robots permission was not treated as a Terms grant, and an HTTP 403 was treated as an access-control signal rather than something to work around.

## JobsGO findings

### Robots.txt

- URL: `https://jobsgo.vn/robots.txt`
- Accessed: 2026-07-24T13:57:56.1415991+07:00
- HTTP: 200, `text/plain; charset=utf-8`
- General user agents are allowed at `/`.
- Disallowed paths include candidate/account, access, phone, search, WordPress and AJAX paths.
- Declared sitemaps include:
  - `https://jobsgo.vn/sitemap-job-place.xml`
  - `https://jobsgo.vn/sitemap-job-type-place.xml`
  - `https://jobsgo.vn/sitemap-job-type.xml`
  - `https://jobsgo.vn/sitemap-job-search.xml`
  - `https://jobsgo.vn/sitemap-employer.xml`
  - `https://jobsgo.vn/sitemap-research-salary.xml`
  - `https://jobsgo.vn/sitemap_index.xml`

### Terms and server response

- Public Terms URL: `https://jobsgo.vn/site/term-of-service`.
- Direct access with the descriptive research User-Agent returned HTTP 403 at 2026-07-24T13:58:34.0658941+07:00.
- The sitemap index declared in robots.txt also returned HTTP 403 at 2026-07-24T13:58:36.2697725+07:00.
- The publicly indexed official Terms describe site data/content, including job information and data structures, as protected assets and state that exploitation, storage and sharing must comply with law, the Terms and privacy rules.
- No attempt was made to alter headers, use a browser session, retry through another IP or evade the response.

### Technical inspection

Testing stopped before listing or job-detail access. Sample size is zero, so URL patterns, source IDs, rendering, structured data, pagination and job fields remain unverified.

### JobsGO result

**HOLD_ACCESS_CONTROL.** JobsGO is the preferred backup candidate for manual outreach because its robots.txt openly declares job-related sitemaps, but it is not safe to continue automated technical evaluation while the descriptive research client receives 403 responses.

## CareerViet findings

### Robots.txt

- URL: `https://careerviet.vn/robots.txt`
- Accessed: 2026-07-24T13:57:58.2367527+07:00
- HTTP: 200, `text/plain; charset=UTF-8`
- Several named search/AI agents are explicitly allowed, while some named archival/data agents are disallowed.
- General user-agent rules disallow multiple candidate, matching, export, resume, API and job paths, including `/api/*`, `/vi/jobs/*`, `/en/jobs/*` and `/en/tim-viec-lam/*`.
- No sitemap declaration was present in the inspected robots.txt.

### Terms

- URL: `https://careerviet.vn/vi/jobseekers/use`
- Accessed: 2026-07-24T13:59:00.3354487+07:00
- HTTP: 200, `text/html; charset=utf-8`
- The public Terms authorize viewing/accessing a single copy of site content solely for personal, noncommercial use.
- They restrict selling, modifying, reproducing, displaying or distributing site content for public/commercial purposes and state that users shall not copy or adapt the HTML code used to generate CareerViet pages.
- These are policy observations, not legal conclusions.

### Technical inspection

Testing stopped at the Terms gate. No sitemap body, listing or job-detail page was requested. Sample size is zero; all technical and field claims remain unverified.

### CareerViet result

**EXCLUDE_FROM_AUTOMATED_MVP.** Do not continue automated evaluation unless CareerViet provides permission that covers the intended collection, retention and analytics use.

## Backup comparison

| Source | Detail sample | robots.txt | Sitemap | Terms/access gate | Public URL | Job ID | HTML | JSON-LD/embedded JSON | JS required | Pagination | Historical state | Result |
|---|---:|---|---|---|---|---|---|---|---|---|---|---|
| JobsGO | 0 | General allow with scoped disallows | Seven declarations; requested index returned 403 | Terms URL returned 403 | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | `HOLD_ACCESS_CONTROL` |
| CareerViet | 0 | Multiple job/API paths disallowed | No declaration observed | Personal/noncommercial single-copy use; HTML copying restricted | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | `EXCLUDE_FROM_AUTOMATED_MVP` |

## Backup field classification

Because both sources stopped before job-detail sampling, no missing field may be converted into a source default.

| Field | JobsGO | CareerViet |
|---|---|---|
| Public detail URL | UNVERIFIED | UNVERIFIED |
| Source job ID | UNVERIFIED | UNVERIFIED |
| Title | UNVERIFIED | UNVERIFIED |
| Company | UNVERIFIED | UNVERIFIED |
| Location | UNVERIFIED | UNVERIFIED |
| Salary | UNVERIFIED | UNVERIFIED |
| Posted date | UNVERIFIED | UNVERIFIED |
| Expiry date | UNVERIFIED | UNVERIFIED |
| Experience | UNVERIFIED | UNVERIFIED |
| Seniority | UNVERIFIED | UNVERIFIED |
| Employment type | UNVERIFIED | UNVERIFIED |
| Work mode | UNVERIFIED | UNVERIFIED |
| Skill tags | UNVERIFIED | UNVERIFIED |
| Historical/expired state | UNVERIFIED | UNVERIFIED |

Rendering/transport claims are also `UNVERIFIED`: server-rendered HTML availability, JSON-LD, embedded JSON, JavaScript requirement and pagination style.

## Replacement recommendation and next gate

There is **no technically and operationally verified replacement for Glints** from Phase 1A.1.

JobsGO is the recommended **replacement candidate for manual follow-up**, not an approved automated source. The next safe action is to ask JobsGO for permission/clarification and, if access is explicitly approved, run a new bounded verification sprint. CareerViet should not be considered for the automated MVP under the current Terms evidence.

No backup source is safe for additional automated HTTP evaluation now:

- JobsGO: manual compliance/permission outreach only.
- CareerViet: permission outreach only; otherwise stop.

Do not begin Phase 1B based on these backup results, and do not modify `DATA_SCHEMA.md`.
