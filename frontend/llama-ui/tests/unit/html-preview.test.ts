import { describe, it, expect } from 'vitest';
import { projectAssetPath } from '../../src/lib/services/html-preview';
describe('project preview asset paths',()=>{
 it('resolves sibling assets and bounded parent paths',()=>{
  expect(projectAssetPath('site/index.html','styles.css')).toBe('site/styles.css');
  expect(projectAssetPath('site/index.html','../app.js?v=1')).toBe('app.js');
 });
 it('rejects external, host and escaping paths',()=>{
  for(const reference of ['https://example.com/x.js','//host/x.js','C:/x.js','../../x.js','%2e%2e/%2e%2e/x.js','../%5cx.js','data:text/javascript,x','/x.js','%2fx.js'])expect(projectAssetPath('site/index.html',reference)).toBeNull();
 });
});
