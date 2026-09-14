import assert from 'node:assert/strict';
import { test } from 'node:test';

import Anthropic from '@anthropic-ai/sdk';
import { createRoutedMockClient, type MockRoute } from './api/mock-client.ts';
import { run } from './orchestrator.ts';
import { acquireLease } from './state/leases.ts';
import type { LeaseState } from './state/leases.ts';
import type { RunLogEntry } from './state/runlog.ts';

const NOW = new Date('2026-09-14T12:00:00.000Z');

function mockAnthropic(handler: (variables: unknown) => { matches: Array<{ prNumber: number; confidence: number }> } | { throws: Error }) {
  const client = new Anthropic({ apiKey: 'test-key' });
  let calls = 0;
  (client.messages as unknown as { parse: (params: unknown) => Promise<{ parsed_output: unknown }> }).parse = async (
    params: unknown,
  ) => {
    calls++;
    const outcome = handler(params);
    if ('throws' in outcome) throw outcome.throws;
    return { parsed_output: outcome };
  };
  return { client, callCount: () => calls };
}

function baseRoutes(overrides: Partial<Record<string, unknown>> = {}): MockRoute[] {
  return [
    {
      match: 'BoardItems',
      response: overrides.board ?? { node: { items: { pageInfo: { hasNextPage: false, endCursor: null }, nodes: [] } } },
    },
    {
      match: 'OpenIssues',
      response: overrides.issues ?? { repository: { issues: { pageInfo: { hasNextPage: false, endCursor: null }, nodes: [] } } },
    },
    { match: 'LinkedPRs', response: overrides.linkedPRs ?? { repository: {} } },
    { match: 'IssueComments', response: overrides.comments ?? { repository: {} } },
    { match: 'OpenSpecChangesTree', response: overrides.openSpecTree ?? { repository: { object: { entries: [] } } } },
    { match: 'OpenSpecProposals', response: overrides.openSpecProposals ?? { repository: {} } },
    {
      match: 'CandidatePRs',
      response: overrides.candidatePRs ?? { repository: { open: { nodes: [] }, merged: { nodes: [] } } },
    },
  ];
}

function boardWithOneItem(itemId: string, issueNumber: number, status: string | null) {
  return {
    node: {
      items: {
        pageInfo: { hasNextPage: false, endCursor: null },
        nodes: [{ id: itemId, status: status ? { name: status } : null, content: { __typename: 'Issue', number: issueNumber, repository: { name: 'ai-on-boarding' } } }],
      },
    },
  };
}

function openIssues(issues: Array<{ number: number; title: string; labels?: string[] }>) {
  return {
    repository: {
      issues: {
        pageInfo: { hasNextPage: false, endCursor: null },
        nodes: issues.map((i) => ({ number: i.number, title: i.title, labels: { nodes: (i.labels ?? []).map((name) => ({ name })) } })),
      },
    },
  };
}

const mergedPRFields = {
  __typename: 'PullRequest',
  number: 88,
  title: 'Fix bug',
  state: 'MERGED',
  merged: true,
  mergedAt: '2026-09-14T00:00:00.000Z',
  isDraft: false,
  headRefName: 'fix-bug',
};

test('happy path: explicit merged PR resolves to set_done and the lease is released', async () => {
  const { client } = createRoutedMockClient(
    baseRoutes({
      board: boardWithOneItem('PVTI_5', 5, 'In Progress'),
      issues: openIssues([{ number: 5, title: 'Fix bug' }]),
      linkedPRs: { repository: { issue_0: { timelineItems: { nodes: [{ __typename: 'ConnectedEvent', subject: mergedPRFields }] } } } },
    }),
  );
  const { client: anthropic } = mockAnthropic(() => ({ matches: [] }));

  const result = await run({
    githubClient: client,
    anthropicClient: anthropic,
    runId: 'run-1',
    leaseState: {},
    runLog: [],
    now: NOW,
  });

  assert.equal(result.processed.length, 1);
  assert.deepEqual(result.processed[0].decision, { action: 'set_done', reason: 'PR merged, none open' });
  assert.deepEqual(result.leaseState, {});
  assert.equal(result.runLog.length, 1);
  assert.equal(result.circuitBroken, false);
});

test('an already-leased issue is skipped and its lease is left untouched', async () => {
  const { client } = createRoutedMockClient(
    baseRoutes({
      board: boardWithOneItem('PVTI_5', 5, 'Todo'),
      issues: openIssues([{ number: 5, title: 'Fix bug' }]),
    }),
  );
  const { client: anthropic, callCount } = mockAnthropic(() => ({ matches: [] }));

  const preLeased: LeaseState = acquireLease({}, 5, 5 * 60 * 1000, NOW)!;

  const result = await run({
    githubClient: client,
    anthropicClient: anthropic,
    runId: 'run-1',
    leaseState: preLeased,
    runLog: [],
    now: NOW,
  });

  assert.equal(result.processed[0].skipped, 'leased');
  assert.deepEqual(result.leaseState, preLeased);
  assert.equal(result.runLog.length, 0);
  assert.equal(callCount(), 0);
});

test('unchanged evidence since the last run is skipped with no model call and no new run-log entry', async () => {
  const routes = baseRoutes({
    board: boardWithOneItem('PVTI_5', 5, 'In Progress'),
    issues: openIssues([{ number: 5, title: 'Fix bug' }]),
    linkedPRs: { repository: { issue_0: { timelineItems: { nodes: [{ __typename: 'ConnectedEvent', subject: mergedPRFields }] } } } },
  });

  const first = await run({
    githubClient: createRoutedMockClient(routes).client,
    anthropicClient: mockAnthropic(() => ({ matches: [] })).client,
    runId: 'run-1',
    leaseState: {},
    runLog: [],
    now: NOW,
  });

  const { client: anthropic2, callCount } = mockAnthropic(() => ({ matches: [] }));
  const second = await run({
    githubClient: createRoutedMockClient(routes).client,
    anthropicClient: anthropic2,
    runId: 'run-2',
    leaseState: {},
    runLog: first.runLog,
    now: new Date(NOW.getTime() + 60_000),
  });

  assert.equal(second.processed[0].skipped, 'unchanged-evidence');
  assert.equal(second.runLog.length, first.runLog.length);
  assert.equal(callCount(), 0);
});

test('an issue with no explicit PR reference is fuzzy-matched against the candidate pool', async () => {
  const { client } = createRoutedMockClient(
    baseRoutes({
      board: boardWithOneItem('PVTI_5', 5, 'Todo'),
      issues: openIssues([{ number: 5, title: 'Add retries' }]),
      candidatePRs: {
        repository: {
          open: { nodes: [] },
          merged: { nodes: [{ number: 91, title: 'Add retries to client', headRefName: 'add-retries', state: 'MERGED', isDraft: false, mergedAt: NOW.toISOString() }] },
        },
      },
    }),
  );
  const { client: anthropic, callCount } = mockAnthropic(() => ({ matches: [{ prNumber: 91, confidence: 0.9 }] }));

  const result = await run({
    githubClient: client,
    anthropicClient: anthropic,
    runId: 'run-1',
    leaseState: {},
    runLog: [],
    now: NOW,
  });

  assert.equal(callCount(), 1);
  assert.deepEqual(result.processed[0].decision, { action: 'set_done', reason: 'PR merged, none open' });
  assert.equal(result.processed[0].evidence.linkedPRs[0].matchSource, 'fuzzy');
});

test('an ignored issue never reaches the model', async () => {
  const { client } = createRoutedMockClient(
    baseRoutes({
      board: boardWithOneItem('PVTI_5', 5, 'Todo'),
      issues: openIssues([{ number: 5, title: 'Add retries', labels: ['agent:ignore'] }]),
      candidatePRs: {
        repository: { open: { nodes: [{ number: 91, title: 'Add retries', headRefName: 'add-retries', state: 'OPEN', isDraft: false, mergedAt: null }] }, merged: { nodes: [] } },
      },
    }),
  );
  const { client: anthropic, callCount } = mockAnthropic(() => ({ matches: [] }));

  const result = await run({
    githubClient: client,
    anthropicClient: anthropic,
    runId: 'run-1',
    leaseState: {},
    runLog: [],
    now: NOW,
  });

  assert.deepEqual(result.processed[0].decision, { action: 'noop', reason: 'ignore label' });
  assert.equal(callCount(), 0);
});

test('a board item whose issue is not open is excluded from processing', async () => {
  const { client } = createRoutedMockClient(
    baseRoutes({
      board: boardWithOneItem('PVTI_9', 9, 'Todo'),
      issues: openIssues([{ number: 5, title: 'A different, still-open issue' }]),
    }),
  );
  const { client: anthropic } = mockAnthropic(() => ({ matches: [] }));

  const result = await run({
    githubClient: client,
    anthropicClient: anthropic,
    runId: 'run-1',
    leaseState: {},
    runLog: [],
    now: NOW,
  });

  assert.equal(result.processed.length, 0);
});

test('the model-call cap trips the circuit breaker before exhausting the batch', async () => {
  const board = {
    node: {
      items: {
        pageInfo: { hasNextPage: false, endCursor: null },
        nodes: [
          { id: 'PVTI_1', status: null, content: { __typename: 'Issue', number: 1, repository: { name: 'ai-on-boarding' } } },
          { id: 'PVTI_2', status: null, content: { __typename: 'Issue', number: 2, repository: { name: 'ai-on-boarding' } } },
        ],
      },
    },
  };
  const { client } = createRoutedMockClient(
    baseRoutes({
      board,
      issues: openIssues([{ number: 1, title: 'Issue one' }, { number: 2, title: 'Issue two' }]),
      linkedPRs: { repository: { issue_0: { timelineItems: { nodes: [] } }, issue_1: { timelineItems: { nodes: [] } } } },
      comments: { repository: { issue_0: { comments: { nodes: [] } }, issue_1: { comments: { nodes: [] } } } },
      candidatePRs: {
        repository: { open: { nodes: [{ number: 50, title: 'Some PR', headRefName: 'x', state: 'OPEN', isDraft: false, mergedAt: null }] }, merged: { nodes: [] } },
      },
    }),
  );
  const { client: anthropic } = mockAnthropic(() => ({ matches: [] }));

  const result = await run({
    githubClient: client,
    anthropicClient: anthropic,
    runId: 'run-1',
    leaseState: {},
    runLog: [],
    now: NOW,
    maxConcurrency: 1,
    modelCallCap: 1,
  });

  assert.equal(result.circuitBroken, true);
  assert.equal(result.processed.length, 1);
});

test('a failure rate above the circuit-breaker threshold halts the rest of the batch', async () => {
  const issues = [1, 2, 3, 4, 5].map((n) => ({ number: n, title: `Issue ${n}` }));
  const board = {
    node: {
      items: {
        pageInfo: { hasNextPage: false, endCursor: null },
        nodes: issues.map((i) => ({ id: `PVTI_${i.number}`, status: null, content: { __typename: 'Issue', number: i.number, repository: { name: 'ai-on-boarding' } } })),
      },
    },
  };
  const linkedPRsResponse = { repository: Object.fromEntries(issues.map((_, i) => [`issue_${i}`, { timelineItems: { nodes: [] } }])) };
  const commentsResponse = { repository: Object.fromEntries(issues.map((_, i) => [`issue_${i}`, { comments: { nodes: [] } }])) };

  const { client } = createRoutedMockClient(
    baseRoutes({
      board,
      issues: openIssues(issues),
      linkedPRs: linkedPRsResponse,
      comments: commentsResponse,
      candidatePRs: {
        repository: { open: { nodes: [{ number: 50, title: 'Some PR', headRefName: 'x', state: 'OPEN', isDraft: false, mergedAt: null }] }, merged: { nodes: [] } },
      },
    }),
  );
  const { client: anthropic } = mockAnthropic(() => ({ throws: new Anthropic.APIConnectionError({ message: 'model outage' }) }));

  const result = await run({
    githubClient: client,
    anthropicClient: anthropic,
    runId: 'run-1',
    leaseState: {},
    runLog: [],
    now: NOW,
    maxConcurrency: 1,
  });

  assert.equal(result.circuitBroken, true);
  assert.equal(result.failed.length, 2);
  assert.equal(result.processed.length, 0);
});
