export const REPO_OWNER = 'awais786';
export const REPO_NAME = 'ai-on-boarding';

// See plan "Verified environment" - resolved once against the live board.
// Startup validation (Phase 4) re-checks these still exist before any write.
export const PROJECT_ID = 'PVT_kwHOA4V_f84AGZiK';
export const STATUS_FIELD_ID = 'PVTSSF_lAHOA4V_f84AGZiKzgDsBxo';

export const STATUS_OPTIONS = {
  Todo: 'f75ad846',
  'In Progress': '47fc9ee4',
  Done: '98236657',
} as const;

export const OPENSPEC_CHANGES_PATH = 'openspec/changes';
export const OPENSPEC_ARCHIVE_DIR = 'archive';

export const IGNORE_LABEL = 'agent:ignore';
export const NEEDS_TRIAGE_LABEL = 'needs-triage';

// Body/title fields fetched from GitHub are truncated to this length before
// they ever reach normalized Evidence, per the "code fetches, model only
// sees normalized JSON" constraint - keeps prompts small and bounds cost.
export const MAX_TEXT_LENGTH = 500;

export const TRANSITION_LOOKBACK_DAYS = 7;

// Fuzzy-match candidate pool: bounds cost of the repo-wide PR scan the
// matcher searches over when an issue has no explicit reference.
export const FUZZY_CANDIDATE_LOOKBACK_DAYS = 7;
export const FUZZY_CANDIDATE_LIMIT = 50;

export const LEASE_TTL_MS = 5 * 60 * 1000;
export const MAX_CONCURRENCY = 5;
export const CIRCUIT_BREAKER_ERROR_RATE = 0.2;
export const MODEL_CALL_CAP_PER_RUN = 100;
