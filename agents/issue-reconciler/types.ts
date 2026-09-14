export type LinkedPR = {
  number: number;
  title: string;
  state: 'OPEN' | 'CLOSED' | 'MERGED';
  merged: boolean;
  mergedAt: string | null;
  isDraft: boolean;
  headRefName: string;
  matchSource: 'explicit' | 'fuzzy';
  confidence: number; // 1.0 for explicit
};

export type Evidence = {
  issueNumber: number;
  itemId: string; // project item ID
  currentStatus: string | null;
  hasIgnoreLabel: boolean;
  linkedPRs: LinkedPR[];
  openSpecProposals: string[];
  lastStatusActor: string | null;
  lastStatusAt: string | null;
  transitionCount: number; // agent flips in last 7 days
};

export type Decision =
  | { action: 'set_done'; reason: string }
  | { action: 'set_in_progress'; reason: string }
  | { action: 'flag'; reason: string }
  | { action: 'noop'; reason: string };
