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
