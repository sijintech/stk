// Unit tests of the viewer's pure modules (payload decoding, colour mapping, labels, camera) run in Node and need
// no browser. workbench-navigation.spec.ts drives the built app in Chromium against a mocked hub; it is skipped
// until `npm run build` has produced dist/ (or STK_WEB_DIST names a build). `npm test`.
import {defineConfig} from '@playwright/test';

export default defineConfig({testDir: 'tests', fullyParallel: true, reporter: 'list'});
