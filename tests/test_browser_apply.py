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
