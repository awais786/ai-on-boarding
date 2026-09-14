import type { GitHubClient } from '../client.ts';
import { REPO_NAME, REPO_OWNER } from '../../config.ts';
import type { LinkedPR } from '../../types.ts';

const BATCH_SIZE = 50;

type TimelinePR = {
  number: number;
  title: string;
  state: 'OPEN' | 'CLOSED' | 'MERGED';
  merged: boolean;
  mergedAt: string | null;
  isDraft: boolean;
  headRefName: string;
};

type TimelineNode =
  | { __typename: 'CrossReferencedEvent'; willCloseTarget: boolean; source: { __typename: string } & Partial<TimelinePR> }
  | { __typename: 'ConnectedEvent'; subject: { __typename: string } & Partial<TimelinePR> }
  | { __typename: string };

type RawResponse = {
  repository: Record<
    string,
    {
      timelineItems: {
        nodes: TimelineNode[];
      };
    } | null
  > | null;
};

const PR_FIELDS = `
  __typename
  ... on PullRequest {
    number
    title
    state
    merged
    mergedAt
    isDraft
    headRefName
  }
`;

function buildQuery(issueNumbers: number[]): string {
  const aliases = issueNumbers
    .map(
      (n, i) => `
    issue_${i}: issue(number: ${n}) {
      timelineItems(first: 50, itemTypes: [CROSS_REFERENCED_EVENT, CONNECTED_EVENT]) {
        nodes {
          __typename
          ... on CrossReferencedEvent {
            willCloseTarget
            source { ${PR_FIELDS} }
          }
          ... on ConnectedEvent {
            subject { ${PR_FIELDS} }
          }
        }
      }
    }`,
    )
    .join('\n');

  return `query LinkedPRs($owner: String!, $name: String!) {
    repository(owner: $owner, name: $name) { ${aliases} }
  }`;
}

function toLinkedPR(pr: Partial<TimelinePR>): LinkedPR | null {
  if (pr.number === undefined) return null;
  return {
    number: pr.number,
    title: pr.title ?? '',
    state: pr.state ?? 'OPEN',
    merged: pr.merged ?? false,
    mergedAt: pr.mergedAt ?? null,
    isDraft: pr.isDraft ?? false,
    headRefName: pr.headRefName ?? '',
    matchSource: 'explicit',
    confidence: 1.0,
  };
}

/**
 * Fetches explicit PR references (closing keywords, manually linked) for a
 * batch of issues in a single request via aliased sub-queries, per the plan's
 * "single GraphQL query per issue batch, not per issue" constraint. Fuzzy
 * matching for issues with no explicit reference happens later, in the
 * Phase 3 matcher, over PRs this fetcher does not return.
 */
export async function fetchLinkedPRs(
  client: GitHubClient,
  issueNumbers: number[],
): Promise<Map<number, LinkedPR[]>> {
  const result = new Map<number, LinkedPR[]>();

  for (let i = 0; i < issueNumbers.length; i += BATCH_SIZE) {
    const batch = issueNumbers.slice(i, i + BATCH_SIZE);
    const query = buildQuery(batch);
    const data = await client.query<RawResponse>(query, {
      owner: REPO_OWNER,
      name: REPO_NAME,
    });

    batch.forEach((issueNumber, index) => {
      const node = data.repository?.[`issue_${index}`];
      const prs: LinkedPR[] = [];
      const seen = new Set<number>();

      for (const item of node?.timelineItems.nodes ?? []) {
        let raw: Partial<TimelinePR> | undefined;
        if (item.__typename === 'CrossReferencedEvent' && 'willCloseTarget' in item) {
          if (!item.willCloseTarget || item.source.__typename !== 'PullRequest') continue;
          raw = item.source;
        } else if (item.__typename === 'ConnectedEvent' && 'subject' in item) {
          if (item.subject.__typename !== 'PullRequest') continue;
          raw = item.subject;
        }

        const pr = raw && toLinkedPR(raw);
        if (pr && !seen.has(pr.number)) {
          seen.add(pr.number);
          prs.push(pr);
        }
      }

      result.set(issueNumber, prs);
    });
  }

  return result;
}
