import type { GitHubClient } from '../api/client.ts';
import { fetchIssueComments, type IssueComment } from '../api/fetchers/timeline.ts';
import { AGENT_ACTOR } from '../policy/rules.ts';
import { parseFingerprint } from '../fingerprint.ts';
import { TRANSITION_LOOKBACK_DAYS } from '../config.ts';

const LOOKBACK_MS = TRANSITION_LOOKBACK_DAYS * 24 * 60 * 60 * 1000;
const TRANSITION_DECISIONS = new Set(['set_done', 'set_in_progress']);

export type BoardHistoryEntry = {
  lastStatusActor: string | null;
  lastStatusAt: string | null;
  transitionCount: number;
};

/**
 * The GitHub API exposes no history of Projects v2 field-value changes, so
 * this reconstructs "who last touched status, and when" from the agent's own
 * fingerprinted comments (see fingerprint.ts) plus ordinary human comments as
 * a proxy for recent human attention. The PAT backing the agent's writes
 * belongs to a human account, so author login alone can't tell the two
 * apart - the fingerprint is what does.
 */
export function summarizeHistory(comments: IssueComment[], now: Date): BoardHistoryEntry {
  let transitionCount = 0;
  for (const comment of comments) {
    const fp = parseFingerprint(comment.body);
    if (!fp || !TRANSITION_DECISIONS.has(fp.decision)) continue;
    if (now.getTime() - new Date(comment.createdAt).getTime() < LOOKBACK_MS) {
      transitionCount++;
    }
  }

  const last = comments.at(-1);
  if (!last) {
    return { lastStatusActor: null, lastStatusAt: null, transitionCount };
  }

  const lastFingerprint = parseFingerprint(last.body);
  return {
    lastStatusActor: lastFingerprint ? AGENT_ACTOR : last.author,
    lastStatusAt: last.createdAt,
    transitionCount,
  };
}

export async function gatherBoardHistory(
  client: GitHubClient,
  issueNumbers: number[],
  now: Date = new Date(),
): Promise<Map<number, BoardHistoryEntry>> {
  const commentsByIssue = await fetchIssueComments(client, issueNumbers);
  const result = new Map<number, BoardHistoryEntry>();

  for (const issueNumber of issueNumbers) {
    result.set(issueNumber, summarizeHistory(commentsByIssue.get(issueNumber) ?? [], now));
  }

  return result;
}
