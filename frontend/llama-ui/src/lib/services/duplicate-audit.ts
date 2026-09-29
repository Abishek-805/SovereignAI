export type DuplicateGroup = { kept: { document_id: string; display_name: string }; removed: { document_id: string; display_name: string }[] };
export function removedDuplicateGroups(operations: unknown): DuplicateGroup[] {
 if (!Array.isArray(operations)) return [];
 const groups: DuplicateGroup[] = [];
 for (const operation of operations) {
  if (operation?.tool !== 'document_deduplicate' || !Array.isArray(operation.result?.groups) || !(operation.result.removed_count > 0)) continue;
  for (const group of operation.result.groups) {
   const valid = (item: any) => item && typeof item.document_id === 'string' && typeof item.display_name === 'string';
   if (!valid(group?.kept) || !Array.isArray(group.duplicates)) continue;
   const removed = group.duplicates.filter(valid).map((item: any) => ({document_id:item.document_id,display_name:item.display_name}));
   if (removed.length) groups.push({kept:{document_id:group.kept.document_id,display_name:group.kept.display_name}, removed});
  }
 }
 return groups;
}
