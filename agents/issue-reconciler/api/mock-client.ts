import { GitHubClient } from './client.ts';

// Test-only helper: a GitHubClient whose transport returns canned GraphQL
// responses in sequence instead of hitting the network, so fetchers and
// spokes can be unit tested without live credentials.
export function createMockClient(responses: unknown[]): {
  client: GitHubClient;
  calls: Array<{ query: string; variables: Record<string, unknown> }>;
} {
  const calls: Array<{ query: string; variables: Record<string, unknown> }> = [];
  let callIndex = 0;

  const client = new GitHubClient({
    token: 'test-token',
    sleep: async () => {},
    fetchImpl: async (_url, init) => {
      const { query, variables } = JSON.parse(init.body as string);
      calls.push({ query, variables });
      const data = responses[callIndex++];
      return new Response(JSON.stringify({ data }), { status: 200 });
    },
  });

  return { client, calls };
}

export type MockRoute = { match: string; response: unknown | ((variables: Record<string, unknown>) => unknown) };

/**
 * Test-only helper for code that fans out several GraphQL queries in
 * parallel (the orchestrator): routes by a substring of the query text (each
 * query in this codebase has a distinct operation name) rather than by call
 * order, since concurrent fetchers' relative invocation order is an
 * implementation detail, not something a test should have to predict.
 */
export function createRoutedMockClient(routes: MockRoute[]): {
  client: GitHubClient;
  calls: Array<{ query: string; variables: Record<string, unknown> }>;
} {
  const calls: Array<{ query: string; variables: Record<string, unknown> }> = [];

  const client = new GitHubClient({
    token: 'test-token',
    sleep: async () => {},
    fetchImpl: async (_url, init) => {
      const { query, variables } = JSON.parse(init.body as string);
      calls.push({ query, variables });
      const route = routes.find((r) => query.includes(r.match));
      if (!route) {
        throw new Error(`createRoutedMockClient: no route matched query:\n${query}`);
      }
      const data = typeof route.response === 'function' ? route.response(variables) : route.response;
      return new Response(JSON.stringify({ data }), { status: 200 });
    },
  });

  return { client, calls };
}
