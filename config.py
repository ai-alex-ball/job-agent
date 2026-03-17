import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent
PROFILE_PATH = BASE_DIR / "profile.json"
PROMPTS_DIR = BASE_DIR / "prompts"
DB_PATH = BASE_DIR / "jobs.db"

# API Keys
REED_API_KEY = os.environ.get("REED_API_KEY", "")
JSEARCH_API_KEY = os.environ.get("JSEARCH_API_KEY", "")  # RapidAPI key
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Claude
CLAUDE_MODEL = "claude-sonnet-4-6"
MIN_SCORE_THRESHOLD = 75

# Gmail
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
DIGEST_RECIPIENT = os.environ.get("DIGEST_RECIPIENT", "jane.doe@example.com")
DEFAULT_APPLICATION_EMAIL = os.environ.get("DEFAULT_APPLICATION_EMAIL", "")

# Phase 3 — approval webhook
FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))
APPROVAL_BASE_URL = os.environ.get("APPROVAL_BASE_URL", f"http://localhost:{FLASK_PORT}")

# Phase 4 — browser automation
PLAYWRIGHT_HEADLESS = os.environ.get("PLAYWRIGHT_HEADLESS", "true").lower() != "false"
SCREENSHOTS_DIR = BASE_DIR / "outputs" / "screenshots"


# Job search
TARGET_ROLES = [
    "Programme Director",
    "Innovation Lead",
    "Innovation Director",
    "Head of Innovation",
    "Startup Programme Lead",
    "Venture Programme Director",
    "Strategic Partnerships Director",
    "Chief Innovation Officer",
    "VP Innovation",
    "Accelerator Lead",
    "Head of Ventures",
    "Chief of Staff",
    "Ecosystem Lead",
    "Head of Ecosystem",
    "Portfolio Director",
    "Venture Studio Lead",
    "Developer Relations",
    "Head of Developer Relations",
    "Community Director",
    "AI Strategy Lead",
    "Head of AI",
    "Transformation Director",
    "Managing Director",
    "Head of Partnerships",
    "Entrepreneur in Residence",
    "Venture Partner",
]

# Reduced role list for JSearch (RapidAPI free tier = 200 req/month; 6 terms × 30 days = 180)
JSEARCH_ROLES = [
    "Programme Director",
    "Innovation Lead",
    "Head of Innovation",
    "Startup Partnerships",
    "Venture Lead",
    "AI Programme Director",
]

LOCATION = "London"
REED_DISTANCE_MILES = 15
RESULTS_PER_QUERY = 10
MAX_JOBS_PER_RUN = 30
DREAM_EMPLOYER_MIN_SCORE = 60
DREAM_ALERT_RECIPIENT = "jobseeker@example.com"

DREAM_EMPLOYERS = [
    # AI labs
    "Anthropic", "DeepMind", "Google DeepMind", "Microsoft", "Cohere", "Mistral",
    # Banks
    "HSBC", "Lloyds", "Barclays", "NatWest", "Santander",
    # Consulting
    "KPMG", "Deloitte", "McKinsey", "BCG", "Accenture",
    # VC / accelerators
    "Entrepreneur First", "Seedcamp", "Techstars", "Wayra", "Octopus Ventures",
    # Innovation bodies
    "Innovate UK", "UKRI", "Nesta",
    # Big tech
    "Amazon", "Meta", "Apple", "Salesforce",
]

# Title must contain at least one of these (case-insensitive) to pass pre-filter.
# Cuts API costs by ~80% by dropping irrelevant roles before hitting Claude.
TITLE_INCLUDE_KEYWORDS = [
    "innovation",
    "incubat",             # incubator, incubation
    "accelerat",           # accelerator, acceleration
    "ecosystem",
    "venture",
    "startup",
    "start-up",
    "programme director",
    "program director",
    "fintech",
    "partnerships director",
    "strategic partnerships",
    "head of ventures",
    "developer relations",
    "transformation",
    "entrepreneur",
    "venture partner",
    "chief of staff",
    "portfolio director",
]

# Title must NOT contain any of these (case-insensitive) — hard reject before Claude.
# Add terms freely; each entry is a substring match.
TITLE_EXCLUDE_KEYWORDS = [
    "erp",
    "sap",
    "procurement",
    "clinical",
    "nursing",
    "teaching",
    "education",
    "audiology",
    "radiography",
    "physiotherapy",
    "construction",
    "civil engineering",
    "nuclear",
    "defence",
    "legal",
    "solicitor",
    "conveyancing",
    "social worker",
    "care worker",
]
