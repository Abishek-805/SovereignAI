/** Leaving a read-only diff must use the persisted modified file, not the
 * editor draft that existed before the agent wrote it. Accept never writes. */
export function acceptedEditorContent(input: {
 reviewing: boolean;
 draft: string;
 saved: string | undefined;
 disk: string;
}): { content: string; baseline: string } {
 return {
  content: !input.reviewing && input.saved !== undefined && input.draft !== input.saved
   ? input.draft : input.disk,
  baseline: input.disk
 };
}
