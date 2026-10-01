export function nextMatchIndex(index: number, direction: number, total: number) {
 return total > 0 ? (index + direction + total) % total : -1;
}
export function tableFindParams(q: string, matchCase: boolean, wholeCell: boolean, offset: number, sheet?: number) {
 const params = new URLSearchParams({ q, match_case: String(matchCase), whole_cell: String(wholeCell), offset: String(offset), limit: '200' });
 if (sheet !== undefined) params.set('sheet', String(sheet));
 return params;
}
export function workspaceDeletionBlocked(id: string, activeId: string | undefined, busy: boolean, dirty: boolean, staged: boolean) {
 return id === activeId && (busy || dirty || staged);
}

export function pendingFileChange<T extends { path: string; action: string }>(task: { state: string; publication_state?: string; changes?: T[] } | null | undefined, path: string): T | undefined {
 if (task?.state !== 'completed' || task.publication_state !== 'staged') return undefined;
 return task.changes?.find(change => change.path === path && !['mkdir', 'rmdir'].includes(change.action));
}
