import { readFile, writeFile } from 'node:fs/promises';

export type LeaseState = Record<number, string>; // issueNumber -> ISO expiresAt

export function isLeased(state: LeaseState, issueNumber: number, now: Date): boolean {
  const expiresAt = state[issueNumber];
  return expiresAt !== undefined && new Date(expiresAt).getTime() > now.getTime();
}

/** Returns null if already leased and unexpired; otherwise the updated state. */
export function acquireLease(state: LeaseState, issueNumber: number, ttlMs: number, now: Date): LeaseState | null {
  if (isLeased(state, issueNumber, now)) return null;
  return { ...state, [issueNumber]: new Date(now.getTime() + ttlMs).toISOString() };
}

export function releaseLease(state: LeaseState, issueNumber: number): LeaseState {
  const next = { ...state };
  delete next[issueNumber];
  return next;
}

export async function loadLeaseState(path: string): Promise<LeaseState> {
  try {
    return JSON.parse(await readFile(path, 'utf8'));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return {};
    throw error;
  }
}

export async function saveLeaseState(path: string, state: LeaseState): Promise<void> {
  await writeFile(path, JSON.stringify(state, null, 2));
}
