# Source Decision Register

**Updated:** 2026-07-24  
**Scope:** Phase 1A and Phase 1A.1 verification decisions. These are project gates, not legal conclusions.

| Source | Decision | Evidence summary | Safe next action |
|---|---|---|---|
| TopDev | `CONDITIONAL_GO` | Technically verified on three active and one historical public detail page; compliance approval remains pending. | Compliance review and offline work with existing sanitized fixtures only. No production crawling. |
| ITviec | `HOLD` | Stopped at Terms gate; technical claims remain unverified. | Manual Terms/permission review only. |
| Glints Vietnam | `EXCLUDE_FROM_AUTOMATED_MVP` | Public Terms restrict screen scraping/data mining/robots without prior written consent; research request returned 403. | No automated evaluation. Reconsider only with prior written consent. |
| JobsGO | `HOLD_ACCESS_CONTROL` | robots.txt allows public root and declares job sitemaps, but the public Terms URL and declared sitemap index returned 403 to the descriptive research User-Agent. No detail pages inspected. | Manual permission/access clarification only; run a new bounded sprint only after approval. |
| CareerViet | `EXCLUDE_FROM_AUTOMATED_MVP` | Terms limit content use to a personal, noncommercial single copy and restrict HTML/content copying; robots disallow multiple job/API paths. No detail pages inspected. | No automated evaluation. Reconsider only with explicit permission for the project use. |

## Glints replacement decision

No replacement is approved yet. **JobsGO is the preferred replacement candidate for manual follow-up** because it publishes job-related sitemap declarations, but it remains on hold after 403 responses and cannot enter adapter development.

## Sources safe to continue evaluating

- **Offline technical evaluation:** TopDev, using only the existing sanitized fixtures, while compliance approval is pending.
- **Manual policy/permission evaluation:** ITviec and JobsGO.
- **Not safe for further automated evaluation under current evidence:** ITviec, Glints Vietnam, JobsGO and CareerViet.
- **No source is approved for production crawling.**

Phase 1B remains blocked pending explicit approval of at least one source's collection and retention policy.
