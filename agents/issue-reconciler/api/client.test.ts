import assert from 'node:assert/strict';
import { test } from 'node:test';

import { GitHubClient, GraphQLError } from './client.ts';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), { status: 200, ...init });
}

test('returns data on a successful response', async () => {
  const client = new GitHubClient({
    token: 't',
    sleep: async () => {},
    fetchImpl: async () => jsonResponse({ data: { hello: 'world' } }),
  });

  const result = await client.query<{ hello: string }>('query { hello }');
  assert.deepEqual(result, { hello: 'world' });
});

test('retries transient 5xx responses and eventually succeeds', async () => {
  let calls = 0;
  const client = new GitHubClient({
    token: 't',
    sleep: async () => {},
    fetchImpl: async () => {
      calls++;
      if (calls < 3) return new Response('boom', { status: 502 });
      return jsonResponse({ data: { ok: true } });
    },
  });

  const result = await client.query<{ ok: boolean }>('query { ok }');
  assert.deepEqual(result, { ok: true });
  assert.equal(calls, 3);
});

test('retries a rate-limited response honoring Retry-After', async () => {
  let calls = 0;
  const sleeps: number[] = [];
  const client = new GitHubClient({
    token: 't',
    sleep: async (ms) => {
      sleeps.push(ms);
    },
    fetchImpl: async () => {
      calls++;
      if (calls === 1) {
        return new Response('rate limited', { status: 403, headers: { 'retry-after': '2' } });
      }
      return jsonResponse({ data: { ok: true } });
    },
  });

  await client.query('query { ok }');
  assert.equal(calls, 2);
  assert.ok(sleeps[0] >= 2000, `expected first backoff to honor retry-after, got ${sleeps[0]}`);
});

test('gives up after maxAttempts and surfaces the last error', async () => {
  const client = new GitHubClient({
    token: 't',
    maxAttempts: 2,
    sleep: async () => {},
    fetchImpl: async () => new Response('boom', { status: 500 }),
  });

  await assert.rejects(() => client.query('query { ok }'), /transient server error/);
});

test('does not retry a non-retryable GraphQL error', async () => {
  let calls = 0;
  const client = new GitHubClient({
    token: 't',
    sleep: async () => {},
    fetchImpl: async () => {
      calls++;
      return jsonResponse({ errors: [{ type: 'NOT_FOUND', message: 'no such field' }] });
    },
  });

  await assert.rejects(() => client.query('query { ok }'), GraphQLError);
  assert.equal(calls, 1);
});

test('retries a RATE_LIMITED GraphQL-level error', async () => {
  let calls = 0;
  const client = new GitHubClient({
    token: 't',
    sleep: async () => {},
    fetchImpl: async () => {
      calls++;
      if (calls === 1) {
        return jsonResponse({ errors: [{ type: 'RATE_LIMITED', message: 'slow down' }] });
      }
      return jsonResponse({ data: { ok: true } });
    },
  });

  const result = await client.query<{ ok: boolean }>('query { ok }');
  assert.deepEqual(result, { ok: true });
  assert.equal(calls, 2);
});

test('does not retry a plain 4xx client error', async () => {
  let calls = 0;
  const client = new GitHubClient({
    token: 't',
    sleep: async () => {},
    fetchImpl: async () => {
      calls++;
      return new Response('bad request', { status: 400 });
    },
  });

  await assert.rejects(() => client.query('query { ok }'), /400/);
  assert.equal(calls, 1);
});
