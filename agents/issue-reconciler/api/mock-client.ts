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
