import type { GitHubClient } from '../client.ts';
import { REPO_NAME, REPO_OWNER } from '../../config.ts';

const BATCH_SIZE = 50;
const COMMENTS_PER_ISSUE = 20;

export type IssueComment = {
  author: string | null;
  body: string;
  createdAt: string;
};

type RawResponse = {
  repository: Record<
    string,
    {
      comments: {
        nodes: Array<{ author: { login: string } | null; body: string; createdAt: string }>;
      };
    } | null
  > | null;
};

function buildQuery(issueNumbers: number[]): string {
  const aliases = issueNumbers
    .map(
      (n, i) => `
    issue_${i}: issue(number: ${n}) {
      comments(last: ${COMMENTS_PER_ISSUE}) {
        nodes {
          author { login }
          body
          createdAt
        }
      }
    }`,
    )
    .join('\n');

  return `query IssueComments($owner: String!, $name: String!) {
    repository(owner: $owner, name: $name) { ${aliases} }
  }`;
}

/**
 * Fetches each issue's most recent comments, batched in one request. This is
 * how board-history recovers status-change actor/timestamp: the agent's own
 * writes carry a fingerprint (see plan "Commenting"), and this is the only
 * audit trail available since Projects v2 field changes aren't exposed on
 * the issue timeline.
 */
export async function fetchIssueComments(
  client: GitHubClient,
  issueNumbers: number[],
): Promise<Map<number, IssueComment[]>> {
  const result = new Map<number, IssueComment[]>();

  for (let i = 0; i < issueNumbers.length; i += BATCH_SIZE) {
    const batch = issueNumbers.slice(i, i + BATCH_SIZE);
    const data = await client.query<RawResponse>(buildQuery(batch), {
      owner: REPO_OWNER,
      name: REPO_NAME,
    });

    batch.forEach((issueNumber, index) => {
      const node = data.repository?.[`issue_${index}`];
      const comments = (node?.comments.nodes ?? []).map((c) => ({
        author: c.author?.login ?? null,
        body: c.body,
        createdAt: c.createdAt,
      }));
      result.set(issueNumber, comments);
    });
  }

  return result;
}
