import type { GitHubClient } from '../api/client.ts';
import { fetchOpenSpecChanges } from '../api/fetchers/repo.ts';

const ISSUE_REF_RE = /#(\d+)/g;

/**
 * Correlates each in-flight OpenSpec proposal to the issue number(s) it
 * references (e.g. "Closes #12"), returning issue number -> change names.
 * One repo-wide fetch, not one per issue - the proposal list is small and
 * shared across the whole batch.
 */
export async function gatherOpenSpecProposals(client: GitHubClient): Promise<Map<number, string[]>> {
  const changes = await fetchOpenSpecChanges(client);
  const byIssue = new Map<number, string[]>();

  for (const change of changes) {
    const referenced = new Set<number>();
    for (const match of change.proposalText.matchAll(ISSUE_REF_RE)) {
      referenced.add(Number(match[1]));
    }

    for (const issueNumber of referenced) {
      const existing = byIssue.get(issueNumber) ?? [];
      existing.push(change.name);
      byIssue.set(issueNumber, existing);
    }
  }

  return byIssue;
}
