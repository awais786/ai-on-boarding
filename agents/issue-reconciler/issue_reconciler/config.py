from __future__ import annotations

REPO_OWNER = "awais786"
REPO_NAME = "ai-on-boarding"

# See plan "Verified environment" - resolved once against the live board.
# Startup validation (orchestrator.validate_board_config) re-checks these
# still exist before any write.
PROJECT_ID = "PVT_kwHOA4V_f84AGZiK"
STATUS_FIELD_ID = "PVTSSF_lAHOA4V_f84AGZiKzgDsBxo"

STATUS_OPTIONS = {
    "Todo": "f75ad846",
    "In Progress": "47fc9ee4",
    "Done": "98236657",
}

OPENSPEC_CHANGES_PATH = "openspec/changes"
OPENSPEC_ARCHIVE_DIR = "archive"

IGNORE_LABEL = "agent:ignore"
NEEDS_TRIAGE_LABEL = "needs-triage"

# Body/title fields fetched from GitHub are truncated to this length before
# they ever reach normalized Evidence, per the "code fetches, model only
# sees normalized JSON" constraint - keeps prompts small and bounds cost.
MAX_TEXT_LENGTH = 500

TRANSITION_LOOKBACK_DAYS = 7

# Fuzzy-match candidate pool: bounds cost of the repo-wide PR scan the
# matcher searches over when an issue has no explicit reference.
FUZZY_CANDIDATE_LOOKBACK_DAYS = 7
FUZZY_CANDIDATE_LIMIT = 50

LEASE_TTL_SECONDS = 5 * 60
MAX_CONCURRENCY = 5
CIRCUIT_BREAKER_ERROR_RATE = 0.2
MODEL_CALL_CAP_PER_RUN = 100
