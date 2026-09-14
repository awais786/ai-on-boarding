import type { GitHubClient } from '../client.ts';
import { PROJECT_ID, REPO_NAME } from '../../config.ts';

export type BoardItem = {
  itemId: string;
  issueNumber: number;
  status: string | null;
};

const QUERY = `
  query BoardItems($projectId: ID!, $cursor: String) {
    node(id: $projectId) {
      ... on ProjectV2 {
        items(first: 100, after: $cursor) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id
            status: fieldValueByName(name: "Status") {
              ... on ProjectV2ItemFieldSingleSelectValue { name }
            }
            content {
              __typename
              ... on Issue {
                number
                repository { name }
              }
            }
          }
        }
      }
    }
  }
`;

type RawResponse = {
  node: {
    items: {
      pageInfo: { hasNextPage: boolean; endCursor: string | null };
      nodes: Array<{
        id: string;
        status: { name: string } | null;
        content: {
          __typename: string;
          number?: number;
          repository?: { name: string };
        } | null;
      }>;
    };
  } | null;
};

/**
 * Fetches every board item, paginated, filtered to this repo's issues. The
 * board is user-level and may hold items from other repos - never touch
 * those (see plan "Board scope warning").
 */
export async function fetchBoardItems(client: GitHubClient): Promise<BoardItem[]> {
  const items: BoardItem[] = [];
  let cursor: string | null = null;

  do {
    const data: RawResponse = await client.query<RawResponse>(QUERY, {
      projectId: PROJECT_ID,
      cursor,
    });

    const page = data.node?.items;
    if (!page) break;

    for (const node of page.nodes) {
      if (node.content?.__typename !== 'Issue') continue;
      if (node.content.repository?.name !== REPO_NAME) continue;
      if (node.content.number === undefined) continue;

      items.push({
        itemId: node.id,
        issueNumber: node.content.number,
        status: node.status?.name ?? null,
      });
    }

    cursor = page.pageInfo.hasNextPage ? page.pageInfo.endCursor : null;
  } while (cursor);

  return items;
}
