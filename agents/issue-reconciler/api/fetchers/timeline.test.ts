import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createMockClient } from '../mock-client.ts';
import { fetchIssueComments } from './timeline.ts';

test('normalizes comments and batches multiple issues into one request', async () => {
  const { client, calls } = createMockClient([
    {
      repository: {
        issue_0: {
          comments: {
            nodes: [{ author: { login: 'alice' }, body: 'looks good', createdAt: '2026-09-14T00:00:00.000Z' }],
          },
        },
        issue_1: {
          comments: {
            nodes: [{ author: null, body: 'deleted user comment', createdAt: '2026-09-13T00:00:00.000Z' }],
          },
        },
      },
    },
  ]);

  const result = await fetchIssueComments(client, [1, 2]);

  assert.equal(calls.length, 1);
  assert.deepEqual(result.get(1), [
    { author: 'alice', body: 'looks good', createdAt: '2026-09-14T00:00:00.000Z' },
  ]);
  assert.deepEqual(result.get(2), [
    { author: null, body: 'deleted user comment', createdAt: '2026-09-13T00:00:00.000Z' },
  ]);
});
