"""Reproduction for #36: reviewing a profile that has no ingested content.

These tests only mock the database session (and the background task), not any
route-level helper. They therefore run unchanged against the code before and
after the fix, which makes them a faithful reproduction of the bug:

    git checkout 790d8c4 -- api/routes/reviews.py core/services/review_service.py
    .venv/Scripts/python -m pytest tests/unit/test_review_no_content_repro.py -v
    git checkout HEAD -- api/routes/reviews.py core/services/review_service.py

Observed before the fix (commit 790d8c4):
  * POST /reviews for an empty profile returns 200 with status "pending".
  * process_review() then marks that review "complete" with three hardcoded
    feedback sections and overall_score 0.81, even though nothing was ingested.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.middleware.auth import get_current_user
from core.database import get_db
from core.services.review_service import process_review


def _empty_profile():
    """A profile with no resume, GitHub username, or portfolio URL."""
    profile = Mock()
    profile.id = uuid4()
    profile.user_id = uuid4()
    profile.resume_text = None
    profile.resume_filename = None
    profile.github_username = None
    profile.portfolio_url = None
    return profile


def _result(first):
    """Mimic the object returned by `await db.execute(...)`."""
    result = Mock()
    result.scalars.return_value.first.return_value = first
    return result


def _pending_review(profile_id):
    now = datetime.now(UTC)
    review = Mock()
    review.id = uuid4()
    review.profile_id = profile_id
    review.status = "pending"
    review.sections = None
    review.overall_score = None
    review.error_message = None
    review.created_at = now
    review.updated_at = now
    return review


@pytest.mark.unit
def test_post_reviews_rejects_profile_with_no_ingested_content():
    """Repro, route level: an empty profile must not get a 200 "pending" review.

    Before the fix this returns 200 and schedules process_review.
    """
    profile = _empty_profile()
    user = Mock()
    user.id = profile.user_id

    db = AsyncMock()
    db.add = Mock()
    # Any SELECT returns the profile first, then "no ingested_sources rows".
    db.execute = AsyncMock(side_effect=[_result(profile), _result(None)])

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    try:
        with (
            patch(
                "api.routes.reviews.create_review",
                AsyncMock(return_value=_pending_review(profile.id)),
            ) as create_review,
            patch("api.routes.reviews.process_review", AsyncMock()) as process,
        ):
            response = TestClient(app, raise_server_exceptions=False).post(
                "/reviews", json={"profile_id": str(profile.id)}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422, (
        f"expected 422 for a profile with nothing to review, "
        f"got {response.status_code}: {response.json()}"
    )
    create_review.assert_not_awaited()
    process.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "#36: process_review() still marks an empty profile's review 'complete' "
        "with placeholder feedback. Remove this marker once the service guards it."
    ),
)
async def test_process_review_does_not_complete_review_for_empty_profile():
    """Repro, service level: the background job fakes a successful review.

    Observed: status == "complete", 3 hardcoded sections, overall_score == 0.81.
    """
    profile = _empty_profile()
    review = _pending_review(profile.id)

    db = AsyncMock()
    db.add = Mock()
    db.execute = AsyncMock(side_effect=[_result(review), _result(profile)])

    await process_review(db, review.id, profile.id)

    assert review.status != "complete", (
        f"review was marked complete with sections={review.sections!r} "
        f"overall_score={review.overall_score!r} although no content was ingested"
    )
