import { createHash } from 'node:crypto';
import type { Evidence } from './types.ts';

// Object.keys order follows insertion order, not a canonical order, so a
// plain JSON.stringify(evidence) would change hash on a harmless field
// reorder. This sorts keys at every level (arrays keep their order - element
// order in linkedPRs/openSpecProposals is itself evidence).
function stableStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(',')}]`;
  }
  if (value !== null && typeof value === 'object') {
    const entries = Object.keys(value as Record<string, unknown>)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify((value as Record<string, unknown>)[key])}`);
    return `{${entries.join(',')}}`;
  }
  return JSON.stringify(value);
}

/** The idempotency key: hash(issueNumber + evidence), per the plan. */
export function hashEvidence(evidence: Evidence): string {
  return createHash('sha256').update(stableStringify(evidence)).digest('hex');
}
