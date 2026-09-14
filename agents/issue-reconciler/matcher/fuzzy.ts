import Anthropic from '@anthropic-ai/sdk';
import { zodOutputFormat } from '@anthropic-ai/sdk/helpers/zod';
import { z } from 'zod';

// Haiku per plan: this is a narrow title/branch-similarity judgment, not a
// task that needs a frontier model. It is also the ONE model call in this
// system - see plan hard constraint #1: the model never touches the GitHub
// API, only normalized JSON in, a verdict out.
const MODEL = 'claude-haiku-4-5';
const MAX_REPAIR_ATTEMPTS = 2;

const MatchSchema = z.object({
  matches: z.array(
    z.object({
      prNumber: z.number(),
      confidence: z.number().min(0).max(1),
    }),
  ),
});

export type FuzzyCandidate = {
  number: number;
  title: string;
  headRefName: string;
};

export type FuzzyMatch = {
  prNumber: number;
  confidence: number;
};

function buildPrompt(issue: { number: number; title: string }, candidates: FuzzyCandidate[]): string {
  return `An issue has no explicit closing reference from any pull request. Judge whether any of
the candidate PRs below likely resolve it, based only on title and branch name similarity.

Issue: ${JSON.stringify({ number: issue.number, title: issue.title })}

Candidate PRs: ${JSON.stringify(candidates)}

For every candidate, return a confidence between 0 and 1 that it resolves this issue.
Return 0 for candidates with no plausible relationship. Do not guess based on PR number
proximity alone - only title and branch name similarity count as evidence.`;
}

/**
 * The only model call in the system. Never called when an explicit PR
 * reference exists. On an unparseable response, retries once with the same
 * prompt; a second failure is treated as no match rather than surfaced as an
 * error, since a missed fuzzy match degrades to "flag: low confidence"
 * downstream rather than corrupting the batch.
 */
export async function matchIssueToPRs(
  client: Anthropic,
  issue: { number: number; title: string },
  candidates: FuzzyCandidate[],
): Promise<FuzzyMatch[]> {
  if (candidates.length === 0) return [];

  const prompt = buildPrompt(issue, candidates);
  const validNumbers = new Set(candidates.map((c) => c.number));

  for (let attempt = 1; attempt <= MAX_REPAIR_ATTEMPTS; attempt++) {
    try {
      const response = await client.messages.parse({
        model: MODEL,
        max_tokens: 1024,
        messages: [{ role: 'user', content: prompt }],
        output_config: { format: zodOutputFormat(MatchSchema) },
      });

      if (response.parsed_output) {
        return response.parsed_output.matches.filter((m) => validNumbers.has(m.prNumber));
      }
      // No text block to parse - same "unparseable" case as a schema
      // mismatch, so fall through and let the retry loop handle it.
    } catch (error) {
      // zodOutputFormat's parse() throws a bare AnthropicError (not an
      // APIError subclass) on invalid JSON or a schema mismatch - that's the
      // one case this function treats as retryable-then-give-up. A real
      // APIError (rate limit, auth, 5xx) is a transport failure, not a
      // format failure, and must propagate for the orchestrator's own
      // retry/circuit-breaker handling rather than silently becoming "no
      // match".
      if (error instanceof Anthropic.APIError || !(error instanceof Anthropic.AnthropicError)) {
        throw error;
      }
    }

    if (attempt === MAX_REPAIR_ATTEMPTS) {
      return [];
    }
  }

  return [];
}
