// Unit tests of the viewer's pure modules (payload decoding, colour mapping, labels, camera); they run in Node
// and need no browser. `npm test`.
import {defineConfig} from '@playwright/test';

export default defineConfig({testDir: 'tests', fullyParallel: true, reporter: 'list'});
