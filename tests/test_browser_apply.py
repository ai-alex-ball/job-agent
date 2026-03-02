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


class TestGreenhouseFiller:
    """
    Test _apply_greenhouse() with a mocked Playwright Page.

    Greenhouse form field selectors:
      First name : input#first_name
      Last name  : input#last_name
      Email      : input#email
      Phone      : input#phone
      Resume     : input[type="file"]
      Cover text : textarea (first textarea on page)
      LinkedIn   : input[aria-label*='LinkedIn'], input[placeholder*='LinkedIn']
      Submit     : input[type="submit"] or button[type="submit"]
    """

    def _make_page(self, has_resume_field=True, has_cover_textarea=True, has_linkedin=False):
        page = MagicMock()
        _cache = {}
        def locator_side_effect(selector):
            if selector in _cache:
                return _cache[selector]
            loc = MagicMock()
            if selector == 'input[type="file"]':
                loc.count.return_value = 1 if has_resume_field else 0
            elif selector == "textarea":
                loc.count.return_value = 1 if has_cover_textarea else 0
                loc.first = MagicMock()
            elif "LinkedIn" in selector:
                loc.count.return_value = 1 if has_linkedin else 0
            else:
                loc.count.return_value = 1
            _cache[selector] = loc
            return loc
        page.locator.side_effect = locator_side_effect
        page.wait_for_selector.return_value = MagicMock()
        return page

    def _make_job(self, cv_path=None):
        return {
            "id": 1,
            "title": "Innovation Director",
            "company": "Acme",
            "url": "https://boards.greenhouse.io/acme/jobs/1",
            "cover_letter": "I am very excited to apply for this role.",
            "cv_path": cv_path,
        }

    def test_fills_required_fields(self):
        applier = BrowserApplier()
        page = self._make_page()
        job = self._make_job()
        with patch("builtins.input", return_value="y"):
            applier._apply_greenhouse(page, job)
        page.locator("input#first_name").fill.assert_called_once_with("Jane")
        page.locator("input#last_name").fill.assert_called_once_with("Ball")
        page.locator("input#email").fill.assert_called_once_with("jane.doe@example.com")
        page.locator("input#phone").fill.assert_called_once_with("07700 900123")

    def test_uploads_cv_when_path_exists(self, tmp_path):
        applier = BrowserApplier()
        cv_file = tmp_path / "outputs" / "cv.docx"
        cv_file.parent.mkdir(parents=True)
        cv_file.write_bytes(b"fake docx content")
        rel_path = str(Path("outputs") / "cv.docx")
        with patch("browser_apply.BASE_DIR", tmp_path):
            page = self._make_page(has_resume_field=True)
            job = self._make_job(cv_path=rel_path)
            with patch("builtins.input", return_value="y"):
                applier._apply_greenhouse(page, job)
        page.locator('input[type="file"]').set_input_files.assert_called_once()

    def test_skips_upload_when_no_cv_path(self):
        applier = BrowserApplier()
        page = self._make_page(has_resume_field=True)
        job = self._make_job(cv_path=None)
        with patch("builtins.input", return_value="y"):
            applier._apply_greenhouse(page, job)
        page.locator('input[type="file"]').set_input_files.assert_not_called()

    def test_fills_cover_letter_textarea(self):
        applier = BrowserApplier()
        page = self._make_page(has_cover_textarea=True)
        job = self._make_job()
        with patch("builtins.input", return_value="y"):
            applier._apply_greenhouse(page, job)
        page.locator("textarea").first.fill.assert_called_once_with(job["cover_letter"])

    def test_user_confirmation_yes_clicks_submit(self):
        """When user types 'y', submit is clicked."""
        applier = BrowserApplier()
        page = self._make_page()
        job = self._make_job()
        with patch("builtins.input", return_value="y"):
            success, msg = applier._apply_greenhouse(page, job)
        assert success is True
        # submit was clicked (either selector)
        submit_clicked = (
            page.locator("input[type='submit']").click.called
            or page.locator('input[type="submit"]').click.called
            or page.locator("button[type='submit']").click.called
            or page.locator('button[type="submit"]').click.called
        )
        assert submit_clicked

    def test_user_confirmation_no_returns_cancelled(self):
        """When user types anything other than y/yes, returns (False, 'cancelled by user')."""
        applier = BrowserApplier()
        page = self._make_page()
        job = self._make_job()
        with patch("builtins.input", return_value="n"):
            success, msg = applier._apply_greenhouse(page, job)
        assert success is False
        assert "cancel" in msg.lower()

    def test_user_confirmation_yes_case_insensitive(self):
        """'YES', 'Yes', 'Y' should all be accepted."""
        applier = BrowserApplier()
        page = self._make_page()
        job = self._make_job()
        with patch("builtins.input", return_value="YES"):
            success, msg = applier._apply_greenhouse(page, job)
        assert success is True


class TestLeverFiller:
    """
    Lever form selectors:
      Name          : input[name="name"]
      Email         : input[name="email"]
      Phone         : input[name="phone"]
      LinkedIn      : input[name="urls[LinkedIn]"]
      Org (company) : input[name="org"]
      Resume upload : input[type="file"]
      Cover letter  : textarea[name="comments"]
      Submit        : button[type="submit"]
    """

    def _make_page(self):
        page = MagicMock()
        _cache = {}
        def locator_side_effect(selector):
            if selector not in _cache:
                loc = MagicMock()
                loc.count.return_value = 1
                loc.first = MagicMock()
                _cache[selector] = loc
            return _cache[selector]
        page.locator.side_effect = locator_side_effect
        page.wait_for_selector.return_value = MagicMock()
        return page

    def _make_job(self, cv_path=None):
        return {
            "id": 2,
            "title": "Innovation Director",
            "company": "Stripe",
            "url": "https://jobs.lever.co/stripe/abc/apply",
            "cover_letter": "Dear Hiring Team, I am delighted to apply.",
            "cv_path": cv_path,
        }

    def test_fills_name_email_phone(self):
        applier = BrowserApplier()
        page = self._make_page()
        with patch("builtins.input", return_value="y"):
            applier._apply_lever(page, self._make_job())
        page.locator('input[name="name"]').fill.assert_called_once_with("Jane Doe")
        page.locator('input[name="email"]').fill.assert_called_once_with("jane.doe@example.com")
        page.locator('input[name="phone"]').fill.assert_called_once_with("07700 900123")

    def test_fills_linkedin_url(self):
        applier = BrowserApplier()
        page = self._make_page()
        with patch("builtins.input", return_value="y"):
            applier._apply_lever(page, self._make_job())
        page.locator('input[name="urls[LinkedIn]"]').fill.assert_called_once_with(
            applier.profile["linkedin"]
        )

    def test_fills_cover_letter(self):
        applier = BrowserApplier()
        page = self._make_page()
        job = self._make_job()
        with patch("builtins.input", return_value="y"):
            applier._apply_lever(page, job)
        page.locator('textarea[name="comments"]').fill.assert_called_once_with(
            job["cover_letter"]
        )

    def test_user_confirmation_yes_clicks_submit(self):
        applier = BrowserApplier()
        page = self._make_page()
        with patch("builtins.input", return_value="y"):
            success, msg = applier._apply_lever(page, self._make_job())
        assert success is True
        page.locator('button[type="submit"]').click.assert_called_once()

    def test_user_confirmation_no_returns_cancelled(self):
        applier = BrowserApplier()
        page = self._make_page()
        with patch("builtins.input", return_value="n"):
            success, msg = applier._apply_lever(page, self._make_job())
        assert success is False
        assert "cancel" in msg.lower()
        page.locator('button[type="submit"]').click.assert_not_called()

    def test_user_confirmation_yes_case_insensitive(self):
        applier = BrowserApplier()
        page = self._make_page()
        with patch("builtins.input", return_value="YES"):
            success, msg = applier._apply_lever(page, self._make_job())
        assert success is True
