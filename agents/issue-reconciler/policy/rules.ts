import type { Decision, Evidence, LinkedPR } from '../types.ts';

// Fingerprint prefix from HTML comments (see plan: "Commenting"). Any actor
// string equal to this is the agent's own write, not a human's.
export const AGENT_ACTOR = 'issue-reconciler';

export const DEFAULT_FUZZY_CONFIDENCE_THRESHOLD = 0.85;
export const HUMAN_OVERRIDE_WINDOW_MS = 24 * 60 * 60 * 1000;
export const FLAPPING_TRANSITION_COUNT = 3;

export type PolicyOptions = {
  fuzzyConfidenceThreshold?: number;
  now?: Date;
};

function isTrusted(pr: LinkedPR, threshold: number): boolean {
  return pr.matchSource === 'explicit' || pr.confidence >= threshold;
}

function isHumanActor(actor: string | null): boolean {
  return actor !== null && actor !== AGENT_ACTOR;
}

/**
 * Pure policy engine: evidence in, decision out. No I/O, no model call.
 * Rules are evaluated in order; the first match wins.
 */
export function decideAction(evidence: Evidence, options: PolicyOptions = {}): Decision {
  const threshold = options.fuzzyConfidenceThreshold ?? DEFAULT_FUZZY_CONFIDENCE_THRESHOLD;
  const now = options.now ?? new Date();

  // 1. Ignore label always wins.
  if (evidence.hasIgnoreLabel) {
    return { action: 'noop', reason: 'ignore label' };
  }

  // 2. A recent human status change is never overridden.
  if (isHumanActor(evidence.lastStatusActor) && evidence.lastStatusAt !== null) {
    const age = now.getTime() - new Date(evidence.lastStatusAt).getTime();
    if (age >= 0 && age < HUMAN_OVERRIDE_WINDOW_MS) {
      return { action: 'noop', reason: 'human override' };
    }
  }

  // 3. Repeated agent flips indicate flapping; hand off to a human.
  if (evidence.transitionCount >= FLAPPING_TRANSITION_COUNT) {
    return { action: 'flag', reason: 'flapping' };
  }

  const trustedPRs = evidence.linkedPRs.filter((pr) => isTrusted(pr, threshold));
  const trustedMerged = trustedPRs.filter((pr) => pr.merged);
  const trustedOpen = trustedPRs.filter((pr) => pr.state === 'OPEN');

  // 4. A merged PR with nothing still open closes the issue out.
  if (trustedMerged.length > 0 && trustedOpen.length === 0) {
    return { action: 'set_done', reason: 'PR merged, none open' };
  }

  // 5. A merged PR alongside a still-open PR is ambiguous - a human decides.
  if (trustedMerged.length > 0 && trustedOpen.length > 0) {
    return { action: 'flag', reason: 'mixed PR states' };
  }

  // 6. An open PR (including draft) means work is in flight.
  if (trustedOpen.length > 0) {
    return { action: 'set_in_progress', reason: 'PR open' };
  }

  // 7. An OpenSpec proposal is also work in flight, absent a PR yet.
  if (evidence.openSpecProposals.length > 0) {
    return { action: 'set_in_progress', reason: 'OpenSpec proposal in flight' };
  }

  // 8. Candidate PRs exist but none were trustworthy enough to act on.
  if (evidence.linkedPRs.length > 0 && trustedPRs.length === 0) {
    return { action: 'flag', reason: 'low confidence' };
  }

  // 9. No evidence of any work in flight.
  return { action: 'noop', reason: 'no evidence' };
}
