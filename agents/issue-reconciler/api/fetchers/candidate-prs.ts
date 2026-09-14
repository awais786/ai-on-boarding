import type { GitHubClient } from '../client.ts';
import { FUZZY_CANDIDATE_LIMIT, FUZZY_CANDIDATE_LOOKBACK_DAYS, REPO_NAME, REPO_OWNER } from '../../config.ts';

export type CandidatePR = {
  number: number;
  title: string;
  headRefName: string;
  state: 'OPEN' | 'MERGED';
  merged: boolean;
  mergedAt: string | null;
  isDraft: boolean;
};

const PR_FIELDS = `number title headRefName state isDraft mergedAt`;

const QUERY = `
  query CandidatePRs($owner: String!, $name: String!, $limit: Int!) {
    repository(owner: $owner, name: $name) {
      open: pullRequests(states: [OPEN], first: $limit, orderBy: { field: UPDATED_AT, direction: DESC }) {
        nodes { ${PR_FIELDS} }
      }
      merged: pullRequests(states: [MERGED], first: $limit, orderBy: { field: UPDATED_AT, direction: DESC }) {
        nodes { ${PR_FIELDS} }
      }
    }
  }
`;

type RawPR = { number: number; title: string; headRefName: string; state: 'OPEN' | 'MERGED'; isDraft: boolean; mergedAt: string | null };

type RawResponse = {
  repository: {
    open: { nodes: RawPR[] };
    merged: { nodes: RawPR[] };
  } | null;
};

function toCandidatePR(pr: RawPR): CandidatePR {
  return {
    number: pr.number,
    title: pr.title,
    headRefName: pr.headRefName,
    state: pr.state,
    merged: pr.state === 'MERGED',
    mergedAt: pr.mergedAt,
    isDraft: pr.isDraft,
  };
}

/**
 * A bounded, repo-wide pool of open PRs plus PRs merged in the last
 * FUZZY_CANDIDATE_LOOKBACK_DAYS days - one query per run, not per issue. This
 * is the search space the fuzzy matcher (matcher/fuzzy.ts) compares each
 * unmatched issue against; it is not itself evidence for any one issue.
 * Carries full PR state (not just title/branch) so a fuzzy match to a merged
 * PR is distinguishable from a match to one still open.
 */
export async function fetchCandidatePRs(client: GitHubClient, now: Date = new Date()): Promise<CandidatePR[]> {
  const data = await client.query<RawResponse>(QUERY, {
    owner: REPO_OWNER,
    name: REPO_NAME,
    limit: FUZZY_CANDIDATE_LIMIT,
  });

  const repository = data.repository;
  if (!repository) return [];

  const cutoff = now.getTime() - FUZZY_CANDIDATE_LOOKBACK_DAYS * 24 * 60 * 60 * 1000;
  const recentlyMerged = repository.merged.nodes.filter(
    (pr) => pr.mergedAt !== null && new Date(pr.mergedAt).getTime() >= cutoff,
  );

  const candidates = [...repository.open.nodes, ...recentlyMerged].map(toCandidatePR);
  const seen = new Set<number>();
  return candidates.filter((pr) => {
    if (seen.has(pr.number)) return false;
    seen.add(pr.number);
    return true;
  });
}
