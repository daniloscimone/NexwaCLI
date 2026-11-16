# Changelog

## 0.2.1 (2026-11-16)

- Preserve pending-refund API errors and the original purchase journal for manual same-key recovery; do not mark a rejected order as accepted.
- Retry read-only HTTP 429 responses at most twice, honoring Retry-After seconds/dates and bounded progressive waits. Print wait notices to stderr.
- Keep purchases and refill requests free of automatic retries. Clarify invalid/revoked/expired key and permission errors without claiming the server distinguishes them.
- Add regression tests for refund errors, request-key preservation and rate-limit handling. Existing commands remain compatible; no deprecations.
