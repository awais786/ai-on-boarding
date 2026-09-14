import type Anthropic from '@anthropic-ai/sdk';
import type { GitHubClient } from './api/client.ts';
import { fetchBoardItems } from './api/fetchers/board.ts';
import { fetchOpenIssues, type OpenIssue } from './api/fetchers/issues.ts';
import { fetchCandidatePRs, type CandidatePR } from './api/fetchers/candidate-prs.ts';
import { gatherPRLinks } from './spokes/pr-evidence.ts';
import { gatherOpenSpecProposals } from './spokes/openspec-evidence.ts';
import { gatherBoardHistory } from './spokes/board-history.ts';
import { matchIssueToPRs } from './matcher/fuzzy.ts';
import { decideAction } from './policy/rules.ts';
import { hashEvidence } from './evidence-hash.ts';
import { acquireLease, releaseLease, type LeaseState } from './state/leases.ts';
import { appendEntry, findLatestForIssue, type RunLogEntry } from './state/runlog.ts';
import { IGNORE_LABEL, LEASE_TTL_MS, MAX_CONCURRENCY, MODEL_CALL_CAP_PER_RUN, PROJECT_ID } from './config.ts';
import type { Decision, Evidence, LinkedPR } from './types.ts';

export type ProcessedIssue = {
  issueNumber: number;
  decision: Decision;
  evidence: Evidence;
  evidenceHash: string;
  skipped?: 'leased' | 'unchanged-evidence';
};

export type FailedIssue = {
  issueNumber: number;
  error: string;
};

export type OrchestratorResult = {
  processed: ProcessedIssue[];
  failed: FailedIssue[];
  leaseState: LeaseState;
  runLog: RunLogEntry[];
  circuitBroken: boolean;
};

export type OrchestratorDeps = {
  githubClient: GitHubClient;
  anthropicClient: Anthropic;
  runId: string;
  leaseState: LeaseState;
  runLog: RunLogEntry[];
  now?: Date;
  fuzzyConfidenceThreshold?: number;
  maxConcurrency?: number;
  modelCallCap?: number;
  circuitBreakerErrorRate?: number;
};

type BoardValidationResponse = { node: { id: string } | null };

/**
 * Fails loudly if the configured project no longer resolves, rather than
 * silently processing zero issues (see plan Reliability: "Startup
 * validation").
 */
export async function validateBoardConfig(client: GitHubClient): Promise<void> {
  const data = await client.query<BoardValidationResponse>(
    `query ValidateProject($projectId: ID!) { node(id: $projectId) { id } }`,
    { projectId: PROJECT_ID },
  );
  if (!data.node) {
    throw new Error(`Configured PROJECT_ID ${PROJECT_ID} no longer resolves to a project`);
  }
}

function createLimiter(concurrency: number) {
  let active = 0;
  const queue: Array<() => void> = [];

  function next() {
    active--;
    const dequeued = queue.shift();
    if (dequeued) dequeued();
  }

  return async function run<T>(fn: () => Promise<T>): Promise<T> {
    if (active >= concurrency) {
      await new Promise<void>((resolve) => queue.push(resolve));
    }
    active++;
    try {
      return await fn();
    } finally {
      next();
    }
  };
}

function toLinkedPR(prNumber: number, confidence: number, candidatePool: CandidatePR[]): LinkedPR {
  // Fuzzy matching only ever runs against the candidate pool, so the source
  // record is guaranteed present - carry its real state through rather than
  // assuming OPEN, since the pool includes recently-merged PRs too and the
  // policy engine's set_done/set_in_progress rules depend on this being
  // accurate.
  const candidate = candidatePool.find((c) => c.number === prNumber)!;
  return {
    number: candidate.number,
    title: candidate.title,
    headRefName: candidate.headRefName,
    state: candidate.state,
    merged: candidate.merged,
    mergedAt: candidate.mergedAt,
    isDraft: candidate.isDraft,
    matchSource: 'fuzzy',
    confidence,
  };
}

/**
 * The hub: selects in-scope issues, fans out read-only evidence gathering,
 * runs the policy engine, and returns planned decisions. It never mutates
 * GitHub - see plan hard constraint #4, "one writer" (writers/board.ts,
 * Phase 5). This function is that boundary: everything before it is
 * read-only, everything after it (not built yet) is the sole write path.
 */
export async function run(deps: OrchestratorDeps): Promise<OrchestratorResult> {
  const now = deps.now ?? new Date();
  const maxConcurrency = deps.maxConcurrency ?? MAX_CONCURRENCY;
  const modelCallCap = deps.modelCallCap ?? MODEL_CALL_CAP_PER_RUN;

  const [boardItems, openIssues] = await Promise.all([
    fetchBoardItems(deps.githubClient),
    fetchOpenIssues(deps.githubClient),
  ]);

  const issuesByNumber = new Map<number, OpenIssue>(openIssues.map((i) => [i.number, i]));
  const inScope = boardItems.filter((item) => issuesByNumber.has(item.issueNumber));
  const issueNumbers = inScope.map((item) => item.issueNumber);

  const [linkedPRsByIssue, boardHistoryByIssue, openSpecByIssue, candidatePool] = await Promise.all([
    gatherPRLinks(deps.githubClient, issueNumbers),
    gatherBoardHistory(deps.githubClient, issueNumbers, now),
    gatherOpenSpecProposals(deps.githubClient),
    fetchCandidatePRs(deps.githubClient, now),
  ]);

  let leaseState = deps.leaseState;
  let runLog = deps.runLog;
  let modelCallsMade = 0;
  let circuitBroken = false;

  const processed: ProcessedIssue[] = [];
  const failed: FailedIssue[] = [];
  const limit = createLimiter(maxConcurrency);

  await Promise.all(
    inScope.map((item) =>
      limit(async () => {
        if (circuitBroken) return;

        const issueNumber = item.issueNumber;
        const leased = acquireLease(leaseState, issueNumber, LEASE_TTL_MS, now);
        if (!leased) {
          processed.push({
            issueNumber,
            decision: { action: 'noop', reason: 'already leased' },
            evidence: null as unknown as Evidence,
            evidenceHash: '',
            skipped: 'leased',
          });
          return;
        }
        leaseState = leased;

        try {
          const issueMeta = issuesByNumber.get(issueNumber)!;
          const history = boardHistoryByIssue.get(issueNumber);
          let linkedPRs = linkedPRsByIssue.get(issueNumber) ?? [];

          const evidence: Evidence = {
            issueNumber,
            itemId: item.itemId,
            currentStatus: item.status,
            hasIgnoreLabel: issueMeta.labels.includes(IGNORE_LABEL),
            linkedPRs,
            openSpecProposals: openSpecByIssue.get(issueNumber) ?? [],
            lastStatusActor: history?.lastStatusActor ?? null,
            lastStatusAt: history?.lastStatusAt ?? null,
            transitionCount: history?.transitionCount ?? 0,
          };

          const hashBeforeMatching = hashEvidence(evidence);
          const latest = findLatestForIssue(runLog, issueNumber);
          if (latest?.evidenceHash === hashBeforeMatching) {
            processed.push({
              issueNumber,
              decision: { action: 'noop', reason: 'unchanged evidence' },
              evidence,
              evidenceHash: hashBeforeMatching,
              skipped: 'unchanged-evidence',
            });
            return;
          }

          // Fuzzy matching only runs when there is no explicit reference -
          // an ignored issue skips it too, since its decision is 'noop'
          // regardless of what the matcher would say.
          if (linkedPRs.length === 0 && !evidence.hasIgnoreLabel && candidatePool.length > 0) {
            if (modelCallsMade >= modelCallCap) {
              circuitBroken = true;
              return;
            }
            modelCallsMade++;
            const matches = await matchIssueToPRs(
              deps.anthropicClient,
              { number: issueNumber, title: issueMeta.title },
              candidatePool,
            );
            linkedPRs = matches.map((m) => toLinkedPR(m.prNumber, m.confidence, candidatePool));
            evidence.linkedPRs = linkedPRs;
          }

          const evidenceHash = hashEvidence(evidence);
          const decision = decideAction(evidence, {
            fuzzyConfidenceThreshold: deps.fuzzyConfidenceThreshold,
            now,
          });

          runLog = appendEntry(runLog, {
            runId: deps.runId,
            issueNumber,
            decision: decision.action,
            reason: decision.reason,
            evidenceHash,
            timestamp: now.toISOString(),
          });

          processed.push({ issueNumber, decision, evidence, evidenceHash });
        } catch (error) {
          failed.push({ issueNumber, error: error instanceof Error ? error.message : String(error) });
          const errorRate = failed.length / inScope.length;
          if (errorRate > (deps.circuitBreakerErrorRate ?? 0.2)) {
            circuitBroken = true;
          }
        } finally {
          leaseState = releaseLease(leaseState, issueNumber);
        }
      }),
    ),
  );

  return { processed, failed, leaseState, runLog, circuitBroken };
}
