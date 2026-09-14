import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createMockClient } from '../mock-client.ts';
import { fetchOpenIssues } from './issues.ts';

test('normalizes open issues with their labels', async () => {
  const { client } = createMockClient([
    {
      repository: {
        issues: {
          pageInfo: { hasNextPage: false, endCursor: null },
          nodes: [
            {
              number: 1,
              title: 'Fix the thing',
              labels: { nodes: [{ name: 'bug' }, { name: 'agent:ignore' }] },
            },
            { number: 2, title: 'Add the other thing', labels: { nodes: [] } },
          ],
        },
      },
    },
  ]);

  const issues = await fetchOpenIssues(client);

  assert.deepEqual(issues, [
    { number: 1, title: 'Fix the thing', labels: ['bug', 'agent:ignore'] },
    { number: 2, title: 'Add the other thing', labels: [] },
  ]);
});
