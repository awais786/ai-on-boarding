import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createMockClient } from '../api/mock-client.ts';
import { gatherOpenSpecProposals } from './openspec-evidence.ts';

test('maps a proposal to every issue it references', async () => {
  const { client } = createMockClient([
    {
      repository: {
        object: {
          entries: [
            { name: 'fix-9-and-10', type: 'tree' },
            { name: 'unrelated-change', type: 'tree' },
          ],
        },
      },
    },
    {
      repository: {
        proposal_0: { text: 'Fixes #9 and #10 in one pass.' },
        proposal_1: { text: 'No issue reference here.' },
      },
    },
  ]);

  const result = await gatherOpenSpecProposals(client);

  assert.deepEqual(result.get(9), ['fix-9-and-10']);
  assert.deepEqual(result.get(10), ['fix-9-and-10']);
  assert.equal(result.get(11), undefined);
});

test('does not duplicate an issue reference mentioned twice in the same proposal', async () => {
  const { client } = createMockClient([
    { repository: { object: { entries: [{ name: 'fix-9-twice', type: 'tree' }] } } },
    { repository: { proposal_0: { text: 'Fixes #9. See also #9 for context.' } } },
  ]);

  const result = await gatherOpenSpecProposals(client);

  assert.deepEqual(result.get(9), ['fix-9-twice']);
});
