import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createMockClient } from '../mock-client.ts';
import { fetchBoardItems } from './board.ts';

test('filters out items from other repositories and paginates', async () => {
  const { client, calls } = createMockClient([
    {
      node: {
        items: {
          pageInfo: { hasNextPage: true, endCursor: 'CURSOR_1' },
          nodes: [
            {
              id: 'item-1',
              status: { name: 'Todo' },
              content: { __typename: 'Issue', number: 1, repository: { name: 'ai-on-boarding' } },
            },
            {
              id: 'item-2',
              status: { name: 'Done' },
              content: { __typename: 'Issue', number: 2, repository: { name: 'some-other-repo' } },
            },
            { id: 'item-3', status: null, content: { __typename: 'PullRequest' } },
          ],
        },
      },
    },
    {
      node: {
        items: {
          pageInfo: { hasNextPage: false, endCursor: null },
          nodes: [
            {
              id: 'item-4',
              status: null,
              content: { __typename: 'Issue', number: 4, repository: { name: 'ai-on-boarding' } },
            },
          ],
        },
      },
    },
  ]);

  const items = await fetchBoardItems(client);

  assert.deepEqual(items, [
    { itemId: 'item-1', issueNumber: 1, status: 'Todo' },
    { itemId: 'item-4', issueNumber: 4, status: null },
  ]);
  assert.equal(calls.length, 2);
  assert.equal(calls[1].variables.cursor, 'CURSOR_1');
});
