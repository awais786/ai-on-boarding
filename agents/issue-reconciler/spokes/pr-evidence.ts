import type { GitHubClient } from '../api/client.ts';
import { fetchLinkedPRs } from '../api/fetchers/prs.ts';
import type { LinkedPR } from '../types.ts';

/**
 * Read-only: returns evidence (explicit PR links per issue), never a
 * decision. The hub's policy engine is the only place that turns this into
 * an action.
 */
export async function gatherPRLinks(
  client: GitHubClient,
  issueNumbers: number[],
): Promise<Map<number, LinkedPR[]>> {
  return fetchLinkedPRs(client, issueNumbers);
}
