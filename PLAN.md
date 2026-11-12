# Solution plan

**Issue:** [`POST /reviews` endpoint has no test for when the profile has no ingested documents (#36)](https://github.com/codepath/pathreview-ai201-fa26-howard/issues/36)

**Branch:** `test/36-review-no-ingested-content`

> Status note: I wrote a first-draft route guard (`df78fcf`) before formally reproducing
> the issue. Reproducing the issue (`dd1d247`) showed that this draft is incomplete:
> it fixes the endpoint, but the background job still fakes success. This plan covers
> the remaining work for Unit 9. It's a living document.

## Understand

**Root cause.** Nothing in the review flow checks that a profile has something to review.

1. `create_review_endpoint` in `api/routes/reviews.py` (pre-fix, `790d8c4`) never loads the
   profile. It calls `create_review()` right away, which also skips the ownership check (it
   ignores `user_id`). It then schedules `process_review` as a background task.
2. `process_review` in `core/services/review_service.py` calls `_run_ingestion_pipeline()`.
   For an empty profile that returns `[]`, but nothing checks the result.
   `_run_agent_orchestration()` and `_run_rag_retrieval_generation()` are placeholders that
   ignore their input and return hardcoded sections. `_run_safety_checks()` approves them.

**Expected:** the API rejects an empty profile with a clear 4xx error. No review row is
created and no background job runs. If the job runs anyway, it marks the review `failed`
with an `error_message` instead of inventing feedback.

**Actual (reproduced, see `tests/unit/test_review_no_content_repro.py`):**
- `POST /reviews` → `200 {"status": "pending", ...}`
- The background job → `status="complete"`, 3 hardcoded sections, `overall_score=0.81`
- A `profile_id` that doesn't exist → `create_review` hits a FK error → generic `500`
- A profile owned by another user → a review is created against it

## Map

| File | Function / area | Change |
|---|---|---|
| `api/routes/reviews.py` | `create_review_endpoint` | Load profile with ownership check → 404. Run content guard → 422. *(Drafted in `df78fcf`.)* |
| `core/services/review_service.py` | `profile_has_reviewable_content` (new) | Treat whitespace-only fields as empty. *(Drafted; needs the edge-case fix.)* |
| `core/services/review_service.py` | `process_review` | If ingestion returns nothing and no `ingested_sources` rows exist, set `status="failed"` and `error_message`, then return. |
| `core/services/profile_service.py` | `get_profile` | Reuse as-is (ownership-scoped lookup). No change expected. |
| `tests/unit/test_review_no_content_repro.py` | repro tests | Remove the `xfail` marker once `process_review` is guarded. |
| `tests/unit/test_review_routes.py` | route tests | Add whitespace/blank-PDF cases. Keep 404/422/200 coverage. |
| `frontend/src/pages/NewProfilePage.tsx` | `handleProfileCreated` | *Stretch / maybe a follow-up issue:* show the 422 `detail` instead of silently redirecting. |

## Plan

1. **Finish the route guard** (`api/routes/reviews.py`, `review_service.py`).
   `profile_has_reviewable_content` should use `.strip()` on `resume_text`,
   `github_username`, and `portfolio_url`, so `"   "` or a blank PDF's `"\n\n"` doesn't count
   as content. Keep 404 for missing or not-owned profiles and 422 for empty ones.
   Replace the deprecated `status.HTTP_422_UNPROCESSABLE_ENTITY` with a constant that works
   on our Starlette version (1.10.0) without a deprecation warning.
2. **Guard the background job** (`process_review`). After `_run_ingestion_pipeline`, if
   `ingestion_results` is empty and the profile has no `ingested_sources` rows, set
   `review.status = "failed"` and `review.error_message = "No ingested content to review"`,
   commit, log `review_no_content`, and return before agent/RAG/safety run. This also
   covers profiles whose content is removed between `POST` and the job running.
3. **Flip the reproduction to a regression test.** Remove the `xfail` from
   `test_process_review_does_not_complete_review_for_empty_profile` and also assert that
   `status == "failed"` and that `error_message` is set. Because of `strict=True`, the test
   fails (XPASS) if I forget to remove the marker.
4. **Extend route tests** (`tests/unit/test_review_routes.py`). Parametrize the 422 case
   over `None`, `""`, `"   "`, and `"\n\n"` for each field. Keep the 200 cases for each real
   source and for existing `ingested_sources` rows.
5. **Verify.** Run `make test-unit` (382 passed / 54 xfailed today; that count must not
   drop), plus `ruff`/`black`/`mypy` via pre-commit. If Docker is up, manually
   `POST /reviews` against a fresh empty profile at `localhost:8000` and confirm the 422.

## Inputs & outputs

- **Input:** `POST /reviews` with body `{"profile_id": "<uuid>"}` and a bearer token. The
  guard reads the `Profile` row (`resume_text`, `github_username`, `portfolio_url`) and
  checks whether any `ingested_sources` row exists for that `profile_id`.
- **Output:**
  - Profile has content → `200`, `ReviewResponse` with `status="pending"` (unchanged).
  - Profile has no content → `422 {"detail": "Profile has no ingested content to review. ..."}`.
    No review row is created and no background task runs.
  - Profile missing or not owned → `404 {"detail": "Profile not found"}`.
  - Background job finds nothing to ingest → review row is `status="failed"`, `error_message` set.

## Risks & unknowns

- **Defining "no content."** Checking only `ingested_sources` would block every first
  review, because ingestion happens inside `process_review`. I chose "no rows **and**
  nothing ingestible". I need to confirm the maintainers agree, or ask in Slack.
- **The tests depend on implementation details.** `tests/unit/test_review_routes.py`
  patches `api.routes.reviews.get_profile`. Against the pre-fix code all 6 tests error with
  `AttributeError` instead of failing on behavior. That's fine for regression tests, but the
  repro file is the real evidence. Don't delete it.
- **The 404 is a behavior change.** Before, a non-owned profile got a review (an
  authorization gap) and a missing one got a 500. I should check that nothing (frontend,
  `tests/integration`, `scripts/seed_db.py`) relies on the old behavior.
- **The frontend hides the error.** `NewProfilePage.handleProfileCreated` catches the
  error, logs it to the console, and redirects to `/dashboard`, so the user never sees the
  422 message. A fix may be out of scope for a Tier 1 backend issue. I may file a follow-up.
- **The 422 constant.** `HTTP_422_UNPROCESSABLE_ENTITY` warns on Starlette 1.10. I need
  to check that `HTTP_422_UNPROCESSABLE_CONTENT` exists at the minimum version
  `pyproject.toml` allows (`fastapi>=0.109.0`). If it doesn't, use the literal `422`.
- **Extra DB query.** The guard adds one `SELECT ... LIMIT 1` per review request, which
  should be negligible.
- **Race window.** Content could be removed after the route check but before the job
  runs. Step 2 covers this.

## Edge cases

- All three source fields are `None` and there are no `ingested_sources` rows → 422
- Fields are empty strings `""` (the form sends blanks) → 422
- Whitespace-only `github_username`/`portfolio_url` (`"  "`) → 422 *(currently passes; fix in step 1)*
- Scanned/image-only PDF, so `resume_text == "\n\n\n"` → 422 *(currently passes; fix in step 1)*
- Empty fields but previously ingested `ingested_sources` rows → 200 (re-review allowed)
- Only one source present (just a resume, just GitHub, or just a portfolio) → 200
- `profile_id` doesn't exist → 404 (was 500)
- `profile_id` belongs to another user → 404, without revealing that it exists (was 200)
- Malformed `profile_id` (not a UUID) → 422 from Pydantic validation (unchanged)
- Job runs on a profile whose content was cleared after `POST` → review `failed`, not `complete`
