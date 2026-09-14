import type { GitHubClient } from '../client.ts';
import { REPO_NAME, REPO_OWNER } from '../../config.ts';

export type OpenIssue = {
  number: number;
  title: string;
  labels: string[];
};

const QUERY = `
  query OpenIssues($owner: String!, $name: String!, $cursor: String) {
    repository(owner: $owner, name: $name) {
      issues(first: 100, after: $cursor, states: [OPEN]) {
        pageInfo { hasNextPage endCursor }
        nodes {
          number
          title
          labels(first: 20) { nodes { name } }
        }
      }
    }
  }
`;

type RawResponse = {
  repository: {
    issues: {
      pageInfo: { hasNextPage: boolean; endCursor: string | null };
      nodes: Array<{
        number: number;
        title: string;
        labels: { nodes: Array<{ name: string }> };
      }>;
    };
  } | null;
};

export async function fetchOpenIssues(client: GitHubClient): Promise<OpenIssue[]> {
  const issues: OpenIssue[] = [];
  let cursor: string | null = null;

  do {
    const data: RawResponse = await client.query<RawResponse>(QUERY, {
      owner: REPO_OWNER,
      name: REPO_NAME,
      cursor,
    });

    const page = data.repository?.issues;
    if (!page) break;

    for (const node of page.nodes) {
      issues.push({
        number: node.number,
        title: node.title,
        labels: node.labels.nodes.map((l) => l.name),
      });
    }

    cursor = page.pageInfo.hasNextPage ? page.pageInfo.endCursor : null;
  } while (cursor);

  return issues;
}
