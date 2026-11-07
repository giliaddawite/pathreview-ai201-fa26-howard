"""Tests for the POST /reviews route (api/routes/reviews.py)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.middleware.auth import get_current_user
from core.database import get_db


def _make_profile(**fields):
    """Build a profile stand-in with every ingestible source empty by default."""
    profile = Mock()
    profile.id = str(uuid4())
    profile.user_id = str(uuid4())
    profile.resume_text = fields.get("resume_text")
    profile.github_username = fields.get("github_username")
    profile.portfolio_url = fields.get("portfolio_url")
    return profile


def _execute_result(first):
    """Mimic the object returned by `await db.execute(...)`."""
    result = Mock()
    result.scalars.return_value.first.return_value = first
    return result


@pytest.mark.unit
class TestCreateReviewRoute:
    """POST /reviews behaviour around profile content."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.add = Mock()
        # Default: the profile has no rows in ingested_sources.
        db.execute = AsyncMock(return_value=_execute_result(None))
        return db

    @pytest.fixture
    def client(self, mock_db):
        user = Mock()
        user.id = str(uuid4())
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        yield TestClient(app, raise_server_exceptions=False)
        app.dependency_overrides.clear()

    def test_profile_with_no_ingested_content_returns_422(self, client, mock_db):
        """A profile with no ingested sources and nothing to ingest is rejected cleanly."""
        profile = _make_profile()

        with (
            patch("api.routes.reviews.get_profile", AsyncMock(return_value=profile)),
            patch("api.routes.reviews.create_review", AsyncMock()) as create_review,
            patch("api.routes.reviews.process_review", AsyncMock()) as process_review,
        ):
            response = client.post("/reviews", json={"profile_id": profile.id})

        assert response.status_code == 422
        assert "no ingested content" in response.json()["detail"]
        create_review.assert_not_awaited()
        process_review.assert_not_called()
        # The route actually consulted ingested_sources rather than short-circuiting.
        mock_db.execute.assert_awaited_once()

    def test_missing_profile_returns_404(self, client):
        """A profile that doesn't exist (or isn't the user's) returns 404, not 500."""
        with (
            patch("api.routes.reviews.get_profile", AsyncMock(return_value=None)),
            patch("api.routes.reviews.create_review", AsyncMock()) as create_review,
        ):
            response = client.post("/reviews", json={"profile_id": str(uuid4())})

        assert response.status_code == 404
        create_review.assert_not_awaited()

    @pytest.mark.parametrize(
        "fields",
        [
            {"resume_text": "Jane Doe, Software Engineer"},
            {"github_username": "janedoe"},
            {"portfolio_url": "https://janedoe.dev"},
        ],
    )
    def test_profile_with_ingestible_source_creates_review(self, client, fields):
        """The guard must not block profiles that have something to ingest."""
        profile = _make_profile(**fields)
        review = _make_review(profile.id)

        with (
            patch("api.routes.reviews.get_profile", AsyncMock(return_value=profile)),
            patch("api.routes.reviews.create_review", AsyncMock(return_value=review)),
            patch("api.routes.reviews.process_review", AsyncMock()) as process_review,
        ):
            response = client.post("/reviews", json={"profile_id": profile.id})

        assert response.status_code == 200
        assert response.json()["status"] == "pending"
        process_review.assert_awaited_once()

    def test_profile_with_previously_ingested_sources_creates_review(self, client, mock_db):
        """Existing ingested_sources rows count as content even if profile fields are empty."""
        profile = _make_profile()
        review = _make_review(profile.id)
        mock_db.execute = AsyncMock(return_value=_execute_result(str(uuid4())))

        with (
            patch("api.routes.reviews.get_profile", AsyncMock(return_value=profile)),
            patch("api.routes.reviews.create_review", AsyncMock(return_value=review)),
            patch("api.routes.reviews.process_review", AsyncMock()),
        ):
            response = client.post("/reviews", json={"profile_id": profile.id})

        assert response.status_code == 200


def _make_review(profile_id):
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
