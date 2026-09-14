import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createRoutedMockClient } from './api/mock-client.ts';
import { validateBoardConfig } from './orchestrator.ts';

test('resolves quietly when the configured project still exists', async () => {
  const { client } = createRoutedMockClient([{ match: 'ValidateProject', response: { node: { id: 'PVT_kwHOA4V_f84AGZiK' } } }]);
  await assert.doesNotReject(() => validateBoardConfig(client));
});

test('fails loudly when the configured project no longer resolves', async () => {
  const { client } = createRoutedMockClient([{ match: 'ValidateProject', response: { node: null } }]);
  await assert.rejects(() => validateBoardConfig(client), /no longer resolves/);
});
