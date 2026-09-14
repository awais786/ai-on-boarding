// Shared by board-history (parses fingerprints left by earlier runs) and the
// writer (stamps a new one on every comment). Keeping both in one place
// means the format can never drift between reader and writer.
// Format: <!-- issue-reconciler: v1 run=<id> decision=<action> evidence=sha256:<hex> -->

const FINGERPRINT_RE = /<!--\s*issue-reconciler:\s*v1\s+run=(\S+)\s+decision=(\S+)\s+evidence=sha256:([0-9a-f]+)\s*-->/;

export type Fingerprint = {
  runId: string;
  decision: string;
  evidenceHash: string;
};

export function buildFingerprint(fp: Fingerprint): string {
  return `<!-- issue-reconciler: v1 run=${fp.runId} decision=${fp.decision} evidence=sha256:${fp.evidenceHash} -->`;
}

export function parseFingerprint(commentBody: string): Fingerprint | null {
  const match = FINGERPRINT_RE.exec(commentBody);
  if (!match) return null;
  const [, runId, decision, evidenceHash] = match;
  return { runId, decision, evidenceHash };
}
