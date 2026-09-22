# Provider Resilience v3.1

Provider routing uses portfolio-scoped circuit states: CLOSED, HALF_OPEN, OPEN. Transient HTTP failures (429, 5xx, timeout/network errors) use Retry-After aware exponential backoff. Terminal workflow failures are stored in a workflow dead-letter record.

Async HTTP video jobs are persisted with an idempotency key before long polling and can be recovered by the dedicated media recovery loop. Recovery is tenant scoped through portfolio_id and provider profile lookup.

Recommended operational signals: circuit OPEN count, recovery retry count, workflow dead-letter count, provider 429/5xx rate, and media-job age.
