import { readFile, writeFile } from 'node:fs/promises';

export type RunLogEntry = {
  runId: string;
  issueNumber: number;
  decision: string;
  reason: string;
  evidenceHash: string;
  timestamp: string;
};

/**
 * Doubles as the write audit trail (every write has a corresponding entry)
 * and the idempotency source of truth (every run's evidence hash is
 * recorded here, not just runs that produced a write) - a noop needs a
 * comparison point too, or a steady-state issue would call the model and
 * recompute evidence every single run forever.
 */
export function appendEntry(log: RunLogEntry[], entry: RunLogEntry): RunLogEntry[] {
  return [...log, entry];
}

export function findLatestForIssue(log: RunLogEntry[], issueNumber: number): RunLogEntry | null {
  for (let i = log.length - 1; i >= 0; i--) {
    if (log[i].issueNumber === issueNumber) return log[i];
  }
  return null;
}

export async function loadRunLog(path: string): Promise<RunLogEntry[]> {
  try {
    return JSON.parse(await readFile(path, 'utf8'));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return [];
    throw error;
  }
}

export async function saveRunLog(path: string, log: RunLogEntry[]): Promise<void> {
  await writeFile(path, JSON.stringify(log, null, 2));
}
