import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const DIST_DIR = resolve(__dirname, '../../dist');
const distExists = existsSync(DIST_DIR);

// PWA Build Output tests are integration tests that require a built dist/.
// CI builds first then runs these tests; local devs should run `npm run build` or use `npm run test:pwa`.
describe('PWA Build Output', () => {
	if (!distExists) {
		console.warn(`⚠ Skipping PWA Build Output tests - dist/ not found (run 'npm run build' first)`);
		it('skipped - dist/ not found', () => {});

		return;
	}

	const swContent = readFileSync(resolve(DIST_DIR, 'sw.js'), 'utf-8');
	const indexContent = readFileSync(resolve(DIST_DIR, 'index.html'), 'utf-8');
	const immutableAssets = readdirSync(resolve(DIST_DIR, '_app/immutable'), { recursive: true })
		.filter((name): name is string => typeof name === 'string')
		.map((name) => `_app/immutable/${name.replaceAll('\\', '/')}`);
	const scripts = immutableAssets.filter((name) => name.endsWith('.js'));
	const styles = immutableAssets.filter((name) => name.endsWith('.css'));
	const bootstrapImports = [...indexContent.matchAll(/import\("(?:\.\/|\/)(_app\/[^"\s]+\.js)"\)/g)]
		.map((match) => match[1]);

	describe('Core files exist', () => {
		it('service worker (sw.js) exists', () => {
			expect(existsSync(resolve(DIST_DIR, 'sw.js')), 'sw.js not found').toBeTruthy();
		});

		it('workbox library exists (hashed filename)', () => {
			// SvelteKit generates workbox-{hash}.js files
			const files = readdirSync(DIST_DIR).filter((f) => f.match(/^workbox-[^.]+\.js$/));

			expect(files.length).toBeGreaterThan(0);
		});

		it('manifest.webmanifest exists', () => {
			expect(
				existsSync(resolve(DIST_DIR, 'manifest.webmanifest')),
				'manifest.webmanifest not found'
			).toBeTruthy();
		});

		it('SvelteKit split start and app entries exist with content hashes', () => {
			for (const entry of ['start', 'app']) {
				expect(scripts.some((name) => new RegExp(`/entry/${entry}\\.[a-zA-Z0-9_-]+\\.js$`).test(name))).toBe(true);
			}
		});

		it('hashed SvelteKit styles exist for dynamically loaded workspaces', () => {
			expect(styles.length).toBeGreaterThan(0);
			for (const style of styles) expect(style).toMatch(/\/assets\/.+\.[a-zA-Z0-9_-]+\.css$/);
		});

		it('version.json exists in _app/', () => {
			// SvelteKit stores version.json in _app directory
			expect(
				existsSync(resolve(DIST_DIR, '_app', 'version.json')),
				'_app/version.json not found'
			).toBeTruthy();
		});
	});

	describe('version.json content', () => {
		it('has valid JSON with version field', () => {
			const content = readFileSync(resolve(DIST_DIR, '_app', 'version.json'), 'utf-8');
			const parsed = JSON.parse(content);

			expect(parsed).toHaveProperty('version');
			expect(typeof parsed.version).toBe('string');
			expect(parsed.version.length).toBeGreaterThan(0);
		});
	});

	describe('Service worker content', () => {
		it('service worker has minified self.define format', () => {
			expect(swContent).toBeTruthy();
			// SvelteKit's workbox-plugin-sveltekit produces a minified SW with self.define
			expect(swContent).toMatch(/if\(!self.define\)/);
		});

		it('references hashed workbox file (SvelteKit build output)', () => {
			expect(swContent).toBeTruthy();
			// SvelteKit's workbox-plugin-sveltekit references hashed workbox files
			expect(swContent).toMatch(/define\(\["\.\/workbox-[a-zA-Z0-9]+"\]/);
		});

		it('precache contains every split script, including lazy workspace chunks', () => {
			expect(scripts.length).toBeGreaterThan(0);
			for (const script of scripts) expect(swContent).toContain(JSON.stringify(script));
		});

		it('precache contains every dynamically loaded stylesheet', () => {
			for (const style of styles) expect(swContent).toContain(JSON.stringify(style));
		});

		it('precache contains _app/version.json', () => {
			expect(swContent).toBeTruthy();
			// SvelteKit stores version.json in _app directory
			expect(swContent).toMatch(/"_app\/version\.json"/);
		});

		it('precache contains manifest.webmanifest', () => {
			expect(swContent).toBeTruthy();
			expect(swContent).toMatch(/"manifest\.webmanifest"/);
		});

		it('no navigation route — API endpoints bypass PWA', () => {
			expect(swContent).toBeTruthy();
			// NavigationRoute is intentionally absent so direct browser
			// navigation to server API endpoints returns JSON, not HTML.
			expect(swContent).not.toMatch(/NavigationRoute/);
		});

		it('has runtime caching for API routes', () => {
			expect(swContent).toBeTruthy();
			expect(swContent).toMatch(/api-cache/);
			expect(swContent).toMatch(/NetworkFirst/);
		});
	});

	describe('index.html content', () => {
		it('every index bootstrap import resolves to an actual precached script', () => {
			expect(bootstrapImports.length).toBeGreaterThan(0);
			for (const entry of bootstrapImports) {
				expect(existsSync(resolve(DIST_DIR, entry))).toBe(true);
				expect(swContent).toContain(JSON.stringify(entry));
			}
		});

		it('styles referenced by index or split scripts resolve and are cached', () => {
			const scriptContents = scripts.map((name) => readFileSync(resolve(DIST_DIR, name), 'utf-8')).join('\n');
			expect(styles.some((style) => scriptContents.includes(style.split('/').at(-1)!))).toBe(true);
			for (const match of indexContent.matchAll(/href="(?:\.\/|\/)(_app\/[^"\s]+\.css)"/g)) {
				expect(existsSync(resolve(DIST_DIR, match[1]))).toBe(true);
				expect(swContent).toContain(JSON.stringify(match[1]));
			}
		});

		it('boots both split SvelteKit entries through dynamic import', () => {
			for (const entry of ['start', 'app']) expect(bootstrapImports.some((name) => name.includes(`/entry/${entry}.`))).toBe(true);
		});

		it('has __sveltekit__ variable (SvelteKit adds hash suffix)', () => {
			expect(indexContent).toBeTruthy();
			// SvelteKit 2.x uses __sveltekit__ as base with random suffix
			expect(indexContent).toMatch(/__sveltekit_[a-zA-Z0-9-]+/);
		});

		it('has PWA manifest link', () => {
			expect(indexContent).toBeTruthy();
			expect(indexContent).toMatch(/rel="manifest" href="(\.?\/)?manifest\.webmanifest"/);
		});

		it('has apple-touch-icon link', () => {
			expect(indexContent).toBeTruthy();
			expect(indexContent).toMatch(/rel="apple-touch-icon"/);
		});

		it('has _app paths for SvelteKit bundles', () => {
			expect(indexContent).toBeTruthy();
			// SvelteKit uses _app paths for hashed assets
			expect(indexContent).toMatch(/_app\//);
		});
	});

	describe('SvelteKit _app directory', () => {
		it('_app directory exists (SvelteKit uses it for hashed assets)', () => {
			expect(existsSync(resolve(DIST_DIR, '_app'))).toBeTruthy();
		});
	});

	describe('Hashed workbox files', () => {
		it('workbox-*.js files exist in dist root (SvelteKit build output)', () => {
			const files = readdirSync(DIST_DIR).filter((f) => f.match(/^workbox-[^.]+\.js$/));

			expect(files.length).toBeGreaterThan(0);
		});
	});

	describe('Static assets', () => {
		it('has favicon.ico', () => {
			expect(existsSync(resolve(DIST_DIR, 'favicon.ico'))).toBeTruthy();
		});

		it('has PWA icons', () => {
			expect(existsSync(resolve(DIST_DIR, 'pwa-64x64.png'))).toBeTruthy();
			expect(existsSync(resolve(DIST_DIR, 'pwa-192x192.png'))).toBeTruthy();
			expect(existsSync(resolve(DIST_DIR, 'pwa-512x512.png'))).toBeTruthy();
		});
	});
});
