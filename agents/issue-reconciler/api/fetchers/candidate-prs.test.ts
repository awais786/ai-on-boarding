import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createMockClient } from '../mock-client.ts';
import { fetchCandidatePRs } from './candidate-prs.ts';

const NOW = new Date('2026-09-14T12:00:00.000Z');

function pr(overrides: Partial<{ number: number; title: string; headRefName: string; state: 'OPEN' | 'MERGED'; isDraft: boolean; mergedAt: string | null }>) {
  return {
    number: 1,
    title: 'PR',
    headRefName: 'branch',
    state: 'OPEN' as const,
    isDraft: false,
    mergedAt: null,
    ...overrides,
  };
}

test('includes open PRs and merges within the lookback window, excluding older merges', async () => {
  const { client } = createMockClient([
    {
      repository: {
        open: { nodes: [pr({ number: 1, title: 'WIP feature', headRefName: 'wip-feature' })] },
        merged: {
          nodes: [
            pr({ number: 2, title: 'Recent fix', headRefName: 'recent-fix', state: 'MERGED', mergedAt: '2026-09-10T00:00:00.000Z' }),
            pr({ number: 3, title: 'Old fix', headRefName: 'old-fix', state: 'MERGED', mergedAt: '2026-08-01T00:00:00.000Z' }),
          ],
        },
      },
    },
  ]);

  const result = await fetchCandidatePRs(client, NOW);

  assert.deepEqual(
    result.map((c) => c.number),
    [1, 2],
  );
  assert.equal(result[0].merged, false);
  assert.equal(result[1].merged, true);
});

test('deduplicates a PR that appears in both the open and merged pages', async () => {
  const { client } = createMockClient([
    {
      repository: {
        open: { nodes: [pr({ number: 1, title: 'Feature', headRefName: 'feature' })] },
        merged: {
          nodes: [pr({ number: 1, title: 'Feature', headRefName: 'feature', state: 'MERGED', mergedAt: '2026-09-13T00:00:00.000Z' })],
        },
      },
    },
  ]);

  const result = await fetchCandidatePRs(client, NOW);

  assert.equal(result.length, 1);
});
