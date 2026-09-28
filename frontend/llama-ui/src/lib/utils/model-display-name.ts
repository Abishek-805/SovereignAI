/** Presentation only. Runtime identifiers remain untouched. */
export function modelDisplayName(id:string) {
	return id.replace(/\.gguf$/i,'').replace(/[-_]Q\d.*$/i,'').replace(/[-_](Instruct|IT)(?:[-_]\d+)?$/i,'').replace(/[-_]/g,' ');
}
