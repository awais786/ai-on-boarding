import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createMockClient } from '../mock-client.ts';
import { fetchLinkedPRs } from './prs.ts';

const mergedPR = {
  __typename: 'PullRequest',
  number: 10,
  title: 'Fix issue 1',
  state: 'MERGED',
  merged: true,
  mergedAt: '2026-09-14T00:00:00.000Z',
  isDraft: false,
  headRefName: 'fix-1',
};

test('includes a PR only when the cross-reference will close the issue', async () => {
  const { client } = createMockClient([
    {
      repository: {
        issue_0: {
          timelineItems: {
            nodes: [
              { __typename: 'CrossReferencedEvent', willCloseTarget: true, source: mergedPR },
              {
                __typename: 'CrossReferencedEvent',
                willCloseTarget: false,
                source: { ...mergedPR, number: 11 },
              },
            ],
          },
        },
      },
    },
  ]);

  const result = await fetchLinkedPRs(client, [1]);

  assert.deepEqual(result.get(1), [
    {
      number: 10,
      title: 'Fix issue 1',
      state: 'MERGED',
      merged: true,
      mergedAt: '2026-09-14T00:00:00.000Z',
      isDraft: false,
      headRefName: 'fix-1',
      matchSource: 'explicit',
      confidence: 1.0,
    },
  ]);
});

test('includes a manually connected PR and ignores non-PR sources', async () => {
  const { client } = createMockClient([
    {
      repository: {
        issue_0: {
          timelineItems: {
            nodes: [
              { __typename: 'ConnectedEvent', subject: { ...mergedPR, number: 20 } },
              { __typename: 'ConnectedEvent', subject: { __typename: 'Issue' } },
            ],
          },
        },
      },
    },
  ]);

  const result = await fetchLinkedPRs(client, [1]);

  assert.equal(result.get(1)?.length, 1);
  assert.equal(result.get(1)?.[0].number, 20);
});

test('deduplicates a PR referenced by multiple timeline events', async () => {
  const { client } = createMockClient([
    {
      repository: {
        issue_0: {
          timelineItems: {
            nodes: [
              { __typename: 'CrossReferencedEvent', willCloseTarget: true, source: mergedPR },
              { __typename: 'ConnectedEvent', subject: mergedPR },
            ],
          },
        },
      },
    },
  ]);

  const result = await fetchLinkedPRs(client, [1]);

  assert.equal(result.get(1)?.length, 1);
});

test('batches multiple issues into one request via aliases', async () => {
  const { client, calls } = createMockClient([
    {
      repository: {
        issue_0: { timelineItems: { nodes: [] } },
        issue_1: { timelineItems: { nodes: [{ __typename: 'ConnectedEvent', subject: { ...mergedPR, number: 30 } }] } },
      },
    },
  ]);

  const result = await fetchLinkedPRs(client, [5, 8]);

  assert.equal(calls.length, 1);
  assert.deepEqual(result.get(5), []);
  assert.equal(result.get(8)?.[0].number, 30);
});
