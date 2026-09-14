import assert from 'node:assert/strict';
import { test } from 'node:test';

import Anthropic from '@anthropic-ai/sdk';
import { matchIssueToPRs } from './fuzzy.ts';

type MockOutcome = { parsed_output: unknown } | { throws: Error };

function mockClient(outcomes: MockOutcome[]): { client: Anthropic; callCount: () => number } {
  const client = new Anthropic({ apiKey: 'test-key' });
  let calls = 0;
  (client.messages as unknown as { parse: (params: unknown) => Promise<{ parsed_output: unknown }> }).parse =
    async () => {
      const outcome = outcomes[calls];
      calls++;
      if ('throws' in outcome) throw outcome.throws;
      return { parsed_output: outcome.parsed_output };
    };
  return { client, callCount: () => calls };
}

const ISSUE = { number: 9, title: 'Add retry logic to the API client' };
const CANDIDATES = [
  { number: 91, title: 'Add retries to api client', headRefName: 'add-retries' },
  { number: 92, title: 'Update README', headRefName: 'docs-update' },
];

test('returns no matches without calling the model when there are no candidates', async () => {
  const { client, callCount } = mockClient([]);
  const result = await matchIssueToPRs(client, ISSUE, []);
  assert.deepEqual(result, []);
  assert.equal(callCount(), 0);
});

test('returns the parsed matches on a valid first response', async () => {
  const { client, callCount } = mockClient([
    { parsed_output: { matches: [{ prNumber: 91, confidence: 0.92 }, { prNumber: 92, confidence: 0.02 }] } },
  ]);

  const result = await matchIssueToPRs(client, ISSUE, CANDIDATES);

  assert.deepEqual(result, [
    { prNumber: 91, confidence: 0.92 },
    { prNumber: 92, confidence: 0.02 },
  ]);
  assert.equal(callCount(), 1);
});

test('retries once when the schema parse throws, then uses the repaired result', async () => {
  const { client, callCount } = mockClient([
    { throws: new Anthropic.AnthropicError('Failed to parse structured output: bad JSON') },
    { parsed_output: { matches: [{ prNumber: 91, confidence: 0.8 }] } },
  ]);

  const result = await matchIssueToPRs(client, ISSUE, CANDIDATES);

  assert.deepEqual(result, [{ prNumber: 91, confidence: 0.8 }]);
  assert.equal(callCount(), 2);
});

test('treats two consecutive schema-parse failures as no match', async () => {
  const err = () => ({ throws: new Anthropic.AnthropicError('Failed to parse structured output: bad JSON') });
  const { client, callCount } = mockClient([err(), err()]);

  const result = await matchIssueToPRs(client, ISSUE, CANDIDATES);

  assert.deepEqual(result, []);
  assert.equal(callCount(), 2);
});

test('propagates a genuine API error instead of treating it as no match', async () => {
  const { client, callCount } = mockClient([{ throws: new Anthropic.APIConnectionError({ message: 'network down' }) }]);

  await assert.rejects(() => matchIssueToPRs(client, ISSUE, CANDIDATES), /network down/);
  assert.equal(callCount(), 1);
});

test('drops a match for a PR number the model hallucinated outside the candidate set', async () => {
  const { client } = mockClient([
    { parsed_output: { matches: [{ prNumber: 999, confidence: 0.9 }, { prNumber: 91, confidence: 0.7 }] } },
  ]);

  const result = await matchIssueToPRs(client, ISSUE, CANDIDATES);

  assert.deepEqual(result, [{ prNumber: 91, confidence: 0.7 }]);
});
