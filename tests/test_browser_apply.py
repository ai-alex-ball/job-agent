import pytest
from unittest.mock import MagicMock, patch, call
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from browser_apply import detect_portal


class TestDetectPortal:
    def test_greenhouse_boards_url(self):
        assert detect_portal("https://boards.greenhouse.io/acme/jobs/12345") == "greenhouse"

    def test_greenhouse_app_url(self):
        assert detect_portal("https://app.greenhouse.io/applications/prose?for=acme") == "greenhouse"

    def test_lever_url(self):
        assert detect_portal("https://jobs.lever.co/stripe/abc-def") == "lever"

    def test_lever_apply_url(self):
        assert detect_portal("https://jobs.lever.co/openai/xyz/apply") == "lever"

    def test_workday_myworkday_url(self):
        assert detect_portal("https://hsbc.wd3.myworkday.com/hsbc/job/London/Innovation-Director_R123") == "workday"

    def test_workday_workdayjobs_url(self):
        assert detect_portal("https://acme.workdayjobs.com/en-US/careers/job/R123") == "workday"

    def test_generic_for_unknown(self):
        assert detect_portal("https://careers.acme.com/jobs/innovation-director") == "generic"

    def test_generic_for_reed(self):
        assert detect_portal("https://www.reed.co.uk/jobs/innovation-director/12345") == "generic"

    def test_empty_url(self):
        assert detect_portal("") == "generic"

    def test_none_url(self):
        assert detect_portal(None) == "generic"


from browser_apply import BrowserApplier


class TestBrowserApplierProfileLoad:
    def test_loads_name(self):
        applier = BrowserApplier()
        assert applier.profile["name"] == "Jane Doe"

    def test_loads_email(self):
        applier = BrowserApplier()
        assert applier.profile["email"] == "jane.doe@example.com"

    def test_loads_phone(self):
        applier = BrowserApplier()
        assert applier.profile["phone"] == "07700 900123"

    def test_loads_linkedin(self):
        applier = BrowserApplier()
        assert "linkedin.com/in/jane-doe-example" in applier.profile["linkedin"]

    def test_name_splits_to_first_last(self):
        applier = BrowserApplier()
        assert applier.profile["first_name"] == "Jane"
        assert applier.profile["last_name"] == "Ball"


class TestBrowserApplierDispatch:
    """Test that apply() routes to the correct filler based on portal."""

    def _make_job(self, url, status="manual_required"):
        return {
            "id": 1,
            "title": "Innovation Director",
            "company": "Acme Corp",
            "url": url,
            "cover_letter": "I am excited to apply.",
            "tailored_cv": "Jane Doe CV text.",
            "cv_path": None,
            "status": status,
        }

    def test_routes_greenhouse(self):
        from unittest.mock import patch
        applier = BrowserApplier()
        job = self._make_job("https://boards.greenhouse.io/acme/jobs/1")
        with patch.object(applier, "_apply_greenhouse", return_value=(True, "Applied")) as m:
            with patch("browser_apply.sync_playwright"):
                success, msg = applier.apply(job)
        m.assert_called_once()
        assert success is True
        assert msg == "Applied"

    def test_routes_lever(self):
        from unittest.mock import patch
        applier = BrowserApplier()
        job = self._make_job("https://jobs.lever.co/acme/abc")
        with patch.object(applier, "_apply_lever", return_value=(True, "Applied")) as m:
            with patch("browser_apply.sync_playwright"):
                success, msg = applier.apply(job)
        m.assert_called_once()
        assert success is True
        assert msg == "Applied"

    def test_workday_returns_unsupported(self):
        applier = BrowserApplier()
        job = self._make_job("https://acme.myworkday.com/acme/job/R1")
        success, msg = applier.apply(job)
        assert success is False
        assert "unsupported" in msg.lower()

    def test_generic_routes_to_generic_filler(self):
        from unittest.mock import patch
        applier = BrowserApplier()
        job = self._make_job("https://careers.acme.com/jobs/123")
        with patch.object(applier, "_apply_generic", return_value=(False, "Partial")) as m:
            with patch("browser_apply.sync_playwright"):
                success, msg = applier.apply(job)
        m.assert_called_once()
        assert success is False
        assert msg == "Partial"
