# Module 3 Journal

## Unit 7 — Issue selection

**Issue link:** https://github.com/codepath/pathreview-ai201-fa26-howard/issues/36

**Issue title:** `POST /reviews` endpoint has no test for when the profile has no ingested documents

**Tier:** [x] Tier 1  [ ] Tier 2  [ ] Tier 3

**Problem summary:**
The `POST /reviews` route in `api/routes/reviews.py` creates a pending review and hands
the work off to `process_review` as a background task, but nothing tests what happens
when the profile exists and has no ingested content (no parsed resume, README, or
chunks). Right now we don't know whether that case returns a clear error or crashes
somewhere in the RAG or agent pipeline with a generic 500, or a review that never
finishes. A good fix adds unit tests in `tests/unit/test_review_routes.py` that set up
that empty-profile case and check that the endpoint gives back a proper client-facing
error (or that the review ends up in a clear failed state) and doesn't crash. If the
tests show the current behavior is wrong, the fix also adds the missing guard.

**Selection notes — "Is this right for me?":**
- *Scope:* Small and well defined. The main work is one new test file, with maybe a
  small guard in the route or `core/services/review_service.py`. That fits the 2–3 hour
  estimate and the Tier 1 label.
- *Skills:* I need pytest, FastAPI's test client or dependency overrides, and mocking
  async DB sessions. I can learn these from the existing `tests/unit` files such as
  `test_review_service.py`.
- *Clarity:* The acceptance criterion is clear: the endpoint returns an appropriate
  error instead of crashing. One open question is which status code counts as
  "appropriate" (for example 400 or 422 vs. 404). I'll decide that from how the
  existing routes handle errors and explain my choice in the PR.
- *Risk:* Low. The change is mostly test code, so it's unlikely to break other
  features or conflict with other contributors' work.

**Branch name:** test/36-review-no-ingested-content

**Setup confirmation:** [ ] App runs locally at localhost:5173

**Cohort ledger:** [ ] Issue added to cohort ledger
