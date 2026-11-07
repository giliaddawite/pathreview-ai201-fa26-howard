# Module 3 Journal

## Unit 7 — Issue selection

**Issue link:** https://github.com/codepath/pathreview-ai201-fa26-howard/issues/36

**Issue title:** `POST /reviews` endpoint has no test for when the profile has no ingested documents

**Tier:** [x] Tier 1  [ ] Tier 2  [ ] Tier 3

**Problem summary:**
The review endpoint (`POST /reviews` in `api/routes/reviews.py`) never checks whether a
profile has anything to review before it starts a review, and no test covers that case.
When I traced the code, I found that a profile with no ingested content and no resume,
GitHub username, or portfolio URL still gets a 200 "pending" response. The background
job in `core/services/review_service.py` then marks the review "complete" using
placeholder feedback, so the user gets a "successful" review of nothing instead of an
error. A good fix rejects this case up front with a clear 4xx error and adds unit tests
in `tests/unit/test_review_routes.py` that prove it, while making sure profiles that do
have content can still be reviewed.

**Selection notes — "Is this right for me?":**
- *Scope:* Small and well defined. The work is one new test file plus a small guard in
  the route and `core/services/review_service.py`. That fits the 2–3 hour estimate and
  the Tier 1 label.
- *Skills:* I need pytest, FastAPI's `TestClient` with dependency overrides, and mocking
  async DB sessions. I can learn these from existing files in `tests/unit`, such as
  `test_review_service.py`.
- *Clarity:* The acceptance criterion is clear: the endpoint returns an appropriate
  error instead of crashing or faking success. To choose the status code, I followed
  the existing convention in `api/routes/profiles.py`: 422 when the profile content
  can't be processed, and 404 when the profile doesn't exist.
- *Defining "no ingested content":* Checking only the `ingested_sources` table would
  block every first review, because ingestion runs inside the background job after the
  review is created. So "no content" means no ingested sources *and* nothing that could
  be ingested.
- *Risk:* Low. The change is small and covered by tests, and no integration tests or
  frontend code depend on the old behavior.

**Branch name:** test/36-review-no-ingested-content

**Setup confirmation:** [x] App runs locally at localhost:5173

**Cohort ledger:** [ ] Issue added to cohort ledger
