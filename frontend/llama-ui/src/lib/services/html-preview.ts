export function projectAssetPath(documentPath: string, reference: string): string | null {
 if (!reference || /^(?:[a-z][a-z0-9+.-]*:|[\\/#])/i.test(reference)) return null;
 let decoded: string;
 try { decoded = decodeURIComponent(reference.split(/[?#]/)[0]); } catch { return null; }
 if (decoded.startsWith('/') || /[\\\x00-\x1f:]/.test(decoded)) return null;
 const parts = documentPath.split('/').slice(0, -1);
 for (const part of decoded.split('/')) {
  if (part === '..') { if (!parts.length) return null; parts.pop(); }
  else if (part && part !== '.') parts.push(part);
 }
 return parts.join('/') || null;
}
export async function bundleHtmlPreview(html: string, documentPath: string, read: (path: string) => Promise<string>): Promise<string> {
 const document = new DOMParser().parseFromString(html, 'text/html');
 document.querySelectorAll('base, meta[http-equiv="Content-Security-Policy"]').forEach(node => node.remove());
 const nodes = Array.from(document.querySelectorAll('link[rel="stylesheet"][href],script[src]')).slice(0, 16);
 let budget = 1024 * 1024;
 for (const node of nodes) {
  const reference = node.getAttribute(node.tagName === 'LINK' ? 'href' : 'src') || '';
  const path = projectAssetPath(documentPath, reference);
  if (!path || !/\.(?:css|js|mjs)$/i.test(path)) continue;
  try {
   const content = await read(path);
   const bytes = new TextEncoder().encode(content);
   if (bytes.length > 256 * 1024 || bytes.length > budget) continue;
   budget -= bytes.length;
   let binary = ''; for (const byte of bytes) binary += String.fromCharCode(byte);
   node.setAttribute(node.tagName === 'LINK' ? 'href' : 'src', 'data:' + (node.tagName === 'LINK' ? 'text/css' : 'text/javascript') + ';base64,' + btoa(binary));
  } catch { /* Missing project assets stay blocked by CSP. */ }
 }
 const policy = document.createElement('meta'); policy.httpEquiv = 'Content-Security-Policy';
 policy.content = "default-src 'none'; style-src 'unsafe-inline' data:; script-src 'unsafe-inline' data:; img-src data:; connect-src 'none'; form-action 'none';";
 document.head.prepend(policy);
 return '<!doctype html>' + document.documentElement.outerHTML;
}
