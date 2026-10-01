<script lang="ts" module>
	import { AI_TUTORIAL_MD } from './fixtures/ai-tutorial.js';
	import { API_DOCS_MD } from './fixtures/api-docs.js';
	import { BLOG_POST_MD } from './fixtures/blog-post.js';
	import { DATA_ANALYSIS_MD } from './fixtures/data-analysis.js';
	import { EMPTY_MD } from './fixtures/empty.js';
	import { MATH_FORMULAS_MD } from './fixtures/math-formulas.js';
	import { README_MD } from './fixtures/readme.js';
	import { defineMeta } from '@storybook/addon-svelte-csf';
	import { MarkdownContent } from '$lib/components/app';
	import { expect } from 'storybook/test';

	const { Story } = defineMeta({
		component: MarkdownContent,
		parameters: {
			layout: 'centered'
		},
		title: 'Components/MarkdownContent'
	});

	// Keep the complete formula fixture while bounding each render and accessibility scan.
	// The original single story can take longer than the browser test timeout on Windows.
	const mathFormulaParts = MATH_FORMULAS_MD.split(
		/(?=\n## (?:Statistics and Probability|Advanced Topics|Further Bracket Styles and Amounts|Formulas in a Table))/
	);
	function mathFormulaPart(index: number): string {
		if (mathFormulaParts.length !== 5 || !mathFormulaParts[index]) {
			throw new Error('Math formula fixture sections changed; update the story boundaries.');
		}
		return mathFormulaParts[index];
	}
</script>

<Story args={{ class: 'max-w-[56rem] w-[calc(100vw-2rem)]', content: EMPTY_MD }} name="Empty" />

<Story
	args={{ class: 'max-w-[56rem] w-[calc(100vw-2rem)]', content: AI_TUTORIAL_MD }}
	name="AI Tutorial"
/>

<Story
	args={{ class: 'max-w-[56rem] w-[calc(100vw-2rem)]', content: API_DOCS_MD }}
	name="API Documentation"
/>

<Story
	args={{ class: 'max-w-[56rem] w-[calc(100vw-2rem)]', content: BLOG_POST_MD }}
	name="Technical Blog"
/>

<Story
	args={{ class: 'max-w-[56rem] w-[calc(100vw-2rem)]', content: DATA_ANALYSIS_MD }}
	name="Data Analysis"
/>

<Story
	args={{ class: 'max-w-[56rem] w-[calc(100vw-2rem)]', content: README_MD }}
	name="README file"
/>

<Story args={{ class: 'max-w-[56rem] w-[calc(100vw-2rem)]', content: mathFormulaPart(0) }} name="Math Formulas — Arithmetic, Algebra, Calculus" />
<Story args={{ class: 'max-w-[56rem] w-[calc(100vw-2rem)]', content: mathFormulaPart(1) }} name="Math Formulas — Statistics through Set Theory" />
<Story args={{ class: 'max-w-[56rem] w-[calc(100vw-2rem)]', content: mathFormulaPart(2) }} name="Math Formulas — Advanced and Inline" />
<Story args={{ class: 'max-w-[56rem] w-[calc(100vw-2rem)]', content: mathFormulaPart(3) }} name="Math Formulas — Brackets and Amounts" />
<Story args={{ class: 'max-w-[56rem] w-[calc(100vw-2rem)]', content: mathFormulaPart(4) }} name="Math Formulas — Tables and Chemistry" />

<Story
	args={{
		class: 'max-w-[56rem] w-[calc(100vw-2rem)]',
		content: `# URL Links Test

Here are some example URLs that should open in new tabs:

- [Hugging Face Homepage](https://huggingface.co)
- [GitHub Repository](https://github.com/ggml-org/llama.cpp)
- [OpenAI Website](https://openai.com)
- [Google Search](https://www.google.com)

You can also test inline links like https://example.com or https://docs.python.org.

All links should have \`target="_blank"\` and \`rel="noopener noreferrer"\` attributes for security.`
	}}
	name="URL Links"
	play={async (context) => {
		const { canvasElement } = context;

		// Wait for component to render
		await new Promise((resolve) => setTimeout(resolve, 100));

		// Find all links in the rendered content
		const links = (canvasElement as HTMLElement).querySelectorAll(
			'a[href]'
		) as NodeListOf<HTMLAnchorElement>;
		const linkList = Array.from(links) as HTMLAnchorElement[];

		// Test that we have the expected number of links
		expect(links.length).toBeGreaterThan(0);

		// Test each link for proper attributes
		links.forEach((link: HTMLAnchorElement) => {
			const href = link.getAttribute('href');

			// Test that external links have proper security attributes
			if (href && (href.startsWith('http://') || href.startsWith('https://'))) {
				expect(link.getAttribute('target')).toBe('_blank');
				expect(link.getAttribute('rel')).toBe('noopener noreferrer');
			}
		});

		// Test specific links exist
		const hugginFaceLink = linkList.find(
			(link) => link.getAttribute('href') === 'https://huggingface.co'
		);

		expect(hugginFaceLink).toBeTruthy();
		expect(hugginFaceLink?.textContent).toBe('Hugging Face Homepage');

		const githubLink = linkList.find(
			(link) => link.getAttribute('href') === 'https://github.com/ggml-org/llama.cpp'
		);

		expect(githubLink).toBeTruthy();
		expect(githubLink?.textContent).toBe('GitHub Repository');

		const openaiLink = linkList.find((link) => link.getAttribute('href') === 'https://openai.com');

		expect(openaiLink).toBeTruthy();
		expect(openaiLink?.textContent).toBe('OpenAI Website');

		const googleLink = linkList.find(
			(link) => link.getAttribute('href') === 'https://www.google.com'
		);

		expect(googleLink).toBeTruthy();
		expect(googleLink?.textContent).toBe('Google Search');

		// Test inline links (auto-linked URLs)
		const exampleLink = linkList.find(
			(link) => link.getAttribute('href') === 'https://example.com'
		);

		expect(exampleLink).toBeTruthy();

		const pythonDocsLink = linkList.find(
			(link) => link.getAttribute('href') === 'https://docs.python.org'
		);

		expect(pythonDocsLink).toBeTruthy();

		console.log(`✅ URL Links test passed - Found ${links.length} links with proper attributes`);
	}}
/>
