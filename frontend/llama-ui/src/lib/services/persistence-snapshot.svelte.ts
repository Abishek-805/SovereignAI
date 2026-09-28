/** Strip Svelte state proxies before passing records to IndexedDB's structured clone. */
export function persistenceSnapshot<T>(record: T): T {
	return $state.snapshot(record) as T;
}
