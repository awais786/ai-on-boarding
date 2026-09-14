const GRAPHQL_ENDPOINT = 'https://api.github.com/graphql';

const MAX_ATTEMPTS = 4;
const BASE_BACKOFF_MS = 500;

export type Transport = (url: string, init: RequestInit) => Promise<Response>;

export class GraphQLError extends Error {
  errors: unknown;
  constructor(message: string, errors: unknown) {
    super(message);
    this.name = 'GraphQLError';
    this.errors = errors;
  }
}

// A non-2xx response that isn't rate-limiting or a server error - retrying
// the same query won't change the outcome, so this must skip the generic
// catch block's retry-on-any-error path below.
class FatalHttpError extends Error {}

export type GitHubClientOptions = {
  token: string;
  fetchImpl?: Transport;
  maxAttempts?: number;
  baseBackoffMs?: number;
  sleep?: (ms: number) => Promise<void>;
};

/**
 * Thin GraphQL client: auth header, retry with jittered backoff on transient
 * failures (5xx, network errors, secondary rate limit), and no retry on
 * client errors (4xx other than 403 rate-limit) or GraphQL-level errors,
 * since those won't succeed by resending the same query.
 */
export class GitHubClient {
  private readonly token: string;
  private readonly fetchImpl: Transport;
  private readonly maxAttempts: number;
  private readonly baseBackoffMs: number;
  private readonly sleep: (ms: number) => Promise<void>;

  constructor(options: GitHubClientOptions) {
    this.token = options.token;
    this.fetchImpl = options.fetchImpl ?? ((url, init) => fetch(url, init));
    this.maxAttempts = options.maxAttempts ?? MAX_ATTEMPTS;
    this.baseBackoffMs = options.baseBackoffMs ?? BASE_BACKOFF_MS;
    this.sleep = options.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  }

  async query<T>(query: string, variables: Record<string, unknown> = {}): Promise<T> {
    let lastError: Error = new Error('unreachable');

    for (let attempt = 1; attempt <= this.maxAttempts; attempt++) {
      try {
        const response = await this.fetchImpl(GRAPHQL_ENDPOINT, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${this.token}`,
            'Content-Type': 'application/json',
            Accept: 'application/vnd.github+json',
          },
          body: JSON.stringify({ query, variables }),
        });

        if (response.status === 403 || response.status === 429) {
          const retryAfter = response.headers.get('retry-after');
          lastError = new Error(`rate limited (status ${response.status})`);
          await this.backoff(attempt, retryAfter ? Number(retryAfter) * 1000 : undefined);
          continue;
        }

        if (response.status >= 500) {
          lastError = new Error(`transient server error (status ${response.status})`);
          await this.backoff(attempt);
          continue;
        }

        if (!response.ok) {
          throw new FatalHttpError(`GitHub API request failed: ${response.status} ${response.statusText}`);
        }

        const body = (await response.json()) as { data?: T; errors?: unknown };

        if (body.errors) {
          if (isRetryableGraphQLError(body.errors)) {
            lastError = new GraphQLError('retryable GraphQL error', body.errors);
            await this.backoff(attempt);
            continue;
          }
          throw new GraphQLError('GraphQL request returned errors', body.errors);
        }

        return body.data as T;
      } catch (error) {
        if (error instanceof GraphQLError || error instanceof FatalHttpError) {
          throw error;
        }
        lastError = error instanceof Error ? error : new Error(String(error));
        if (attempt < this.maxAttempts) {
          await this.backoff(attempt);
        }
      }
    }

    throw lastError;
  }

  private async backoff(attempt: number, floorMs?: number): Promise<void> {
    const exponential = this.baseBackoffMs * 2 ** (attempt - 1);
    const jitter = Math.random() * this.baseBackoffMs;
    const delay = Math.max(floorMs ?? 0, exponential + jitter);
    await this.sleep(delay);
  }
}

function isRetryableGraphQLError(errors: unknown): boolean {
  if (!Array.isArray(errors)) return false;
  return errors.some((e) => e && typeof e === 'object' && (e as { type?: string }).type === 'RATE_LIMITED');
}
