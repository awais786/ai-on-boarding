import assert from 'node:assert/strict';
import { test } from 'node:test';

import { summarizeHistory } from './board-history.ts';
import { buildFingerprint } from '../fingerprint.ts';
import { AGENT_ACTOR } from '../policy/rules.ts';
import type { IssueComment } from '../api/fetchers/timeline.ts';

const NOW = new Date('2026-09-14T12:00:00.000Z');

test('no comments means no known actor and no transitions', () => {
  const result = summarizeHistory([], NOW);
  assert.deepEqual(result, { lastStatusActor: null, lastStatusAt: null, transitionCount: 0 });
});

test('a plain human comment is treated as the last human touch', () => {
  const comments: IssueComment[] = [
    { author: 'alice', body: 'please hold off on this one', createdAt: '2026-09-14T10:00:00.000Z' },
  ];

  const result = summarizeHistory(comments, NOW);

  assert.deepEqual(result, {
    lastStatusActor: 'alice',
    lastStatusAt: '2026-09-14T10:00:00.000Z',
    transitionCount: 0,
  });
});

test('a fingerprinted comment is attributed to the agent, not the PAT owner', () => {
  const fp = buildFingerprint({ runId: 'run-1', decision: 'set_in_progress', evidenceHash: 'abc123' });
  const comments: IssueComment[] = [
    { author: 'a-human-owned-pat', body: `In progress - PR #5 open.\n${fp}`, createdAt: '2026-09-14T09:00:00.000Z' },
  ];

  const result = summarizeHistory(comments, NOW);

  assert.equal(result.lastStatusActor, AGENT_ACTOR);
  assert.equal(result.lastStatusAt, '2026-09-14T09:00:00.000Z');
  assert.equal(result.transitionCount, 1);
});

test('counts only transition decisions within the lookback window', () => {
  const inWindow = buildFingerprint({ runId: 'r1', decision: 'set_in_progress', evidenceHash: 'a' });
  const flagDecision = buildFingerprint({ runId: 'r2', decision: 'flag', evidenceHash: 'b' });
  const outsideWindow = buildFingerprint({ runId: 'r3', decision: 'set_done', evidenceHash: 'c' });

  const comments: IssueComment[] = [
    { author: 'bot', body: `old\n${outsideWindow}`, createdAt: '2026-09-01T00:00:00.000Z' },
    { author: 'bot', body: `flagged\n${flagDecision}`, createdAt: '2026-09-13T00:00:00.000Z' },
    { author: 'bot', body: `recent\n${inWindow}`, createdAt: '2026-09-14T00:00:00.000Z' },
  ];

  const result = summarizeHistory(comments, NOW);

  assert.equal(result.transitionCount, 1);
});

test('a human comment after the agent last wrote overrides the actor', () => {
  const fp = buildFingerprint({ runId: 'r1', decision: 'set_in_progress', evidenceHash: 'a' });
  const comments: IssueComment[] = [
    { author: 'bot', body: `automated\n${fp}`, createdAt: '2026-09-13T00:00:00.000Z' },
    { author: 'bob', body: 'actually I am handling this', createdAt: '2026-09-14T08:00:00.000Z' },
  ];

  const result = summarizeHistory(comments, NOW);

  assert.equal(result.lastStatusActor, 'bob');
  assert.equal(result.lastStatusAt, '2026-09-14T08:00:00.000Z');
});
