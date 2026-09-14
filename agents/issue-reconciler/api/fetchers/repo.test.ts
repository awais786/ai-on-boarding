import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createMockClient } from '../mock-client.ts';
import { fetchOpenSpecChanges } from './repo.ts';

test('excludes the archive directory and non-tree entries', async () => {
  const { client, calls } = createMockClient([
    {
      repository: {
        object: {
          entries: [
            { name: 'add-issue-9-fix', type: 'tree' },
            { name: 'archive', type: 'tree' },
            { name: 'README.md', type: 'blob' },
          ],
        },
      },
    },
    {
      repository: {
        proposal_0: { text: 'Closes #9. Adds the fix.' },
      },
    },
  ]);

  const changes = await fetchOpenSpecChanges(client);

  assert.deepEqual(changes, [{ name: 'add-issue-9-fix', proposalText: 'Closes #9. Adds the fix.' }]);
  assert.equal(calls.length, 2);
});

test('truncates a proposal body longer than MAX_TEXT_LENGTH', async () => {
  const longText = 'x'.repeat(2000);
  const { client } = createMockClient([
    { repository: { object: { entries: [{ name: 'big-change', type: 'tree' }] } } },
    { repository: { proposal_0: { text: longText } } },
  ]);

  const changes = await fetchOpenSpecChanges(client);

  assert.equal(changes[0].proposalText.length, 500);
});

test('returns an empty list without a second request when there are no changes', async () => {
  const { client, calls } = createMockClient([{ repository: { object: { entries: [] } } }]);

  const changes = await fetchOpenSpecChanges(client);

  assert.deepEqual(changes, []);
  assert.equal(calls.length, 1);
});
