// Acceptance runner using the installed browser, without downloading Chromium.
import base from './vite.config';
import { defineConfig } from 'vite';
import { playwright } from '@vitest/browser-playwright';
export default defineConfig(async (env) => {
 const config = await (base as any)(env);
 config.test.projects = config.test.projects.filter((project: any) => project.test.name !== 'ui');
 for (const project of config.test.projects) {
  if (project.test.browser) project.test.browser = {
   ...project.test.browser, headless: true,
   provider: playwright({launchOptions: {channel: 'chrome', args: ['--no-sandbox']}})
  };
 }
 return config;
});
