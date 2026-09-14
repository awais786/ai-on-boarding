import type { GitHubClient } from '../client.ts';
import { MAX_TEXT_LENGTH, OPENSPEC_ARCHIVE_DIR, OPENSPEC_CHANGES_PATH, REPO_NAME, REPO_OWNER } from '../../config.ts';

export type OpenSpecChange = {
  name: string;
  proposalText: string;
};

const TREE_QUERY = `
  query OpenSpecChangesTree($owner: String!, $name: String!, $expression: String!) {
    repository(owner: $owner, name: $name) {
      object(expression: $expression) {
        ... on Tree {
          entries { name type }
        }
      }
    }
  }
`;

type TreeResponse = {
  repository: {
    object: { entries: Array<{ name: string; type: string }> } | null;
  } | null;
};

type ProposalsResponse = Record<string, { text: string } | null>;

function buildProposalsQuery(names: string[]): string {
  const aliases = names
    .map(
      (n, i) => `
    proposal_${i}: object(expression: "HEAD:${OPENSPEC_CHANGES_PATH}/${n}/proposal.md") {
      ... on Blob { text }
    }`,
    )
    .join('\n');

  return `query OpenSpecProposals($owner: String!, $name: String!) {
    repository(owner: $owner, name: $name) { ${aliases} }
  }`;
}

/**
 * Lists in-flight OpenSpec changes (excluding the archive) with their
 * proposal text, truncated. Correlating a proposal to a specific issue
 * number happens in the openspec-evidence spoke, not here - this fetcher
 * only normalizes what the repo contains.
 */
export async function fetchOpenSpecChanges(client: GitHubClient): Promise<OpenSpecChange[]> {
  const treeData = await client.query<TreeResponse>(TREE_QUERY, {
    owner: REPO_OWNER,
    name: REPO_NAME,
    expression: `HEAD:${OPENSPEC_CHANGES_PATH}`,
  });

  const dirs = (treeData.repository?.object?.entries ?? []).filter(
    (entry) => entry.type === 'tree' && entry.name !== OPENSPEC_ARCHIVE_DIR,
  );

  if (dirs.length === 0) return [];

  const query = buildProposalsQuery(dirs.map((d) => d.name));
  const proposalsData = await client.query<{ repository: ProposalsResponse | null }>(query, {
    owner: REPO_OWNER,
    name: REPO_NAME,
  });

  const repository = proposalsData.repository ?? {};

  return dirs.map((dir, i) => ({
    name: dir.name,
    proposalText: (repository[`proposal_${i}`]?.text ?? '').slice(0, MAX_TEXT_LENGTH),
  }));
}
