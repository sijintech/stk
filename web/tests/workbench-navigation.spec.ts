// Browser regression for the Hub Web section navigation (工作台 / 任务 / 结果): the explicit 结果 / 读取日志
// shortcuts in Tasks open 结果 in one click with their target in view, and a late result never moves the user.
// It drives the built app (`npm run build` first, or STK_WEB_DIST=<dir>) in Chromium; page.route serves the
// files and a mocked hub, so no server, model or network is used. Without a build these tests are skipped.
import {expect, test, type Locator, type Page, type Request, type Route} from '@playwright/test';
import {existsSync, readFileSync, writeFileSync} from 'node:fs';
import {extname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const DIST = process.env.STK_WEB_DIST || fileURLToPath(new URL('../dist/', import.meta.url));
test.skip(!existsSync(join(DIST, 'index.html')), `no built app in ${DIST}: run npm run build or set STK_WEB_DIST`);
test.use({serviceWorkers: 'block', launchOptions: {args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader']}});

const ORIGIN = 'http://localhost:47883'; // secure context for crypto.randomUUID; page.route answers before any socket
const node = 'a'.repeat(32), ws = 'b'.repeat(32), task = 'c'.repeat(32);
const row = {id: task, workspace_id: ws, name: '解析场验证', state: 'succeeded', updated_at: '2026-11-10T12:00:00.000000Z'};
const device = {id: node, role: 'node', name: '节点甲', online: true, revoked: false, last_seen: 1794830400,
  snapshot: {tasks: [row], workspaces: [{id: ws, name: '项目一'}], features: ['read', 'task.get', 'task.artifacts', 'task.events']}};
const scene = {manifest: {version: 1, field: 'phi', units: 'V', value_range: [0, 1], render_origin: [0, 0, 0], display_reduced: false},
  mesh: {positions: [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0.5]], values: [0, 0.3, 0.6, 1], indices: [0, 1, 2, 1, 3, 2]}};
const LOG = Array.from({length: 40}, (_, i) => `step ${i + 1} converged`).join('\n') + '\n'; // taller than the pane
// 图谱 fixtures: one preset with a task binding and a step, answered by graph.evaluate with the payload v2 example
// (its buffers are served as hub blobs). The result reports the step it was computed for and the choices.
const EXAMPLE = fileURLToPath(new URL('../../docs/specs/examples/payload-v2/', import.meta.url));
const PRESET = {id: 'field-view', name: '场视图', bindings: [{name: 'field'}], parameters: [{name: 'step', type: 'step', default: 'latest'}]};
const STEPS = [0, 500, 1000];
const types: Record<string, string> = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.webmanifest': 'application/manifest+json'};

// Mocked hub. `later` switches task.artifacts to a longer list, so a click-time read is distinguishable from the
// read made on task selection; `hold(kind)` keeps that request pending until released.
// Conversations, as suan/control/app.py has them: `rows` is the saved list and `saved` the stored transcripts, with
// Hub creation times. A history read answers with the transcript as it was when the request arrived, and only the
// Hub's own 404 says "Session not found" (`historyFault` gives a proxy page or a Hub without the read-only route).
// A send creates the session and records the user message at once, publishing sessions.changed, before the reply:
// the same message ID again is not recorded twice, and once its reply exists the send returns the session as it is
// without another reply (`replies` counts the mock model's replies). `sendFail` fails it before the Hub
// ('before'), after the user message ('recorded', the Hub's 502) or after the reply as a lost connection ('lost').
// `holdNext` holds only the next such request: 'history <id>', 'send' / 'send <id>' before the Hub sees it,
// 'recorded' after the user message, 'replied' after the reply with the answer already taken. `calls` records every
// conversation request except the list, including any legacy `GET sessions/{id}`, which this hub refuses because it
// would create a session; `messages` records each sent body.
type Said = {id: string; role: string; content: string; created: number};
let clock = 1794900000;
const say = (id: string, role: string, content: string): Said => ({id, role, content, created: ++clock});
class Hub {
  rows: {id: string; name: string; created: number; label?: string}[] = [];
  readonly saved = new Map<string, Said[]>();
  readonly calls: string[] = [];
  readonly messages: {session: string; id: string; content: string}[] = [];
  replies = 0;
  sendFail: false | 'before' | 'recorded' | 'lost' = false;
  historyFault: null | 'route' | 'proxy' = null;
  private readonly streams: Route[] = [];
  private event = 0;
  // sessions.changed on the event stream: the open stream answers one event, and the app refreshes the list.
  publish() {
    for (const stream of this.streams.splice(0)) {
      void stream.fulfill({status: 200, contentType: 'text/event-stream',
        body: `id: ${++this.event}\nevent: sessions.changed\ndata: {}\n\n`}).catch(() => undefined);
    }
  }
  private readonly once = new Map<string, Promise<void>>();
  holdNext(key: string) {
    let release!: () => void;
    this.once.set(key, new Promise<void>(resolve => { release = resolve; }));
    return () => release();
  }
  private async gateOnce(...keys: string[]) {
    for (const key of keys) {
      const held = this.once.get(key);
      if (held) { this.once.delete(key); this.reached.add(key); await held; return; }
    }
  }
  later = false;
  // When set, task.artifacts lists exactly these paths instead of scalar-0.vti (and scalar-1.vti once `later`).
  artifactPaths?: string[];
  field = 'phi';
  // 任务: `device` is the node the hub lists; `down` makes every hub call fail as an unreachable control service;
  // `review` sends a task.submit to execution review, which GET actions then lists until it is approved or refused.
  device: typeof device = device;
  // Further nodes the hub lists (no node reads are answered for them).
  others: Record<string, any>[] = [];
  down = false;
  review = false;
  readonly actionRows: Record<string, any>[] = [];
  logsFail = false;
  readonly viewErrors = new Map<string, string>();
  reportedViewSource?: {task_id: string; path: string} | 'omit';
  // Payloads of the view.build and view.probe actions, in order: which task and artifact each one asked for.
  readonly builds: Record<string, any>[] = [];
  readonly probes: Record<string, any>[] = [];
  // 图谱: the presets GET graphs/presets lists (none by default) and the graph.evaluate payloads, in order.
  presets: unknown[] = [];
  readonly evaluations: Record<string, any>[] = [];
  // `queueGraph`: graph.evaluate is queued on the node; GET actions/{id} answers queued until it is cleared, then the
  // result; `hold('poll')` holds the next poll, which then answers as `queueGraph` is on release. `queuePolls` counts
  // those polls. `graphChunk` holds the lazy 图谱 module until it resolves.
  queueGraph = false;
  queuePolls = 0;
  private readonly queuedResults = new Map<string, unknown>();
  graphChunk?: Promise<void>;
  readonly pending = new Map<string, Promise<void>>();
  readonly reached = new Set<string>();
  hold(kind: string) {
    let release!: () => void;
    this.pending.set(kind, new Promise<void>(resolve => { release = resolve; }));
    return () => { this.pending.delete(kind); release(); };
  }
  private async gate(kind: string) {
    const held = this.pending.get(kind);
    if (held) { this.reached.add(kind); await held; }
  }
  async install(page: Page) {
    await page.addInitScript(() => sessionStorage.setItem('stk-token', 'abcdefghijklmnopqrstu'));
    // An aborted read cannot be fulfilled any more; that is expected and ignored.
    await page.route(`${ORIGIN}/**`, route => this.answer(route).catch(() => undefined));
  }
  private async answer(route: Route) {
    const request = route.request(), url = new URL(request.url());
    if (!url.pathname.startsWith('/api/v1/')) {
      if (this.graphChunk && /^\/assets\/GraphPanel-[^/]+\.js$/.test(url.pathname)) await this.graphChunk;
      const file = join(DIST, url.pathname === '/' ? 'index.html' : url.pathname);
      if (!existsSync(file)) return route.fulfill({status: 404, body: ''});
      return route.fulfill({status: 200, contentType: types[extname(file)] || 'application/octet-stream', body: readFileSync(file)});
    }
    const path = url.pathname.slice('/api/v1/'.length);
    const json = (body: unknown, status = 200) => route.fulfill({status, contentType: 'application/json', body: JSON.stringify(body)});
    if (this.down) return json({detail: '控制服务不可用'}, 503);
    if (path === 'events') { this.streams.push(route); return; } // open and silent until the hub publishes
    if (path === 'devices') return json([this.device, ...this.others]);
    if (path === 'actions' && request.method() === 'GET') return json(this.actionRows);
    const reviewed = /^actions\/([^/]+)\/review$/.exec(path);
    if (reviewed && request.method() === 'POST') {
      const item = this.actionRows.find(a => a.id === reviewed[1]);
      if (!item) return json({detail: 'Action not found'}, 404);
      item.state = request.postDataJSON().approved ? 'succeeded' : 'rejected';
      return json(item);
    }
    const polled = /^actions\/([^/]+)$/.exec(path);
    if (polled && request.method() === 'GET' && this.queuedResults.has(polled[1])) {
      this.queuePolls++;
      await this.gate('poll');
      return json(this.queueGraph ? {id: polled[1], state: 'queued'} : {id: polled[1], state: 'succeeded', result: this.queuedResults.get(polled[1])});
    }
    if (path === 'sessions') return json(this.rows);
    if (path === 'policy') return json({read_kinds: ['task.get', 'task.artifacts', 'task.events']});
    if (path === 'graphs/presets') return json(this.presets);
    const stored = /^blobs\/([0-9a-f]{64})$/.exec(path);
    if (stored) {
      const file = join(EXAMPLE, `${stored[1]}.bin`);
      return existsSync(file) ? route.fulfill({status: 200, contentType: 'application/octet-stream', body: readFileSync(file)}) : json({detail: 'no blob'}, 404);
    }
    const conversation = /^sessions\/([^/]+)(\/history|\/messages)?$/.exec(path);
    if (conversation) {
      const [, id, tail] = conversation;
      if (!tail) { this.calls.push(`legacy ${id}`); return json({detail: 'legacy GET would create a session'}, 500); }
      if (tail === '/history' && request.method() === 'GET') {
        this.calls.push(`history ${id}`);
        const messages = this.saved.get(id), fault = this.historyFault;
        const snapshot = messages ? {id, messages: [...messages]} : null;
        await this.gateOnce(`history ${id}`);
        if (fault === 'route') return json({detail: 'Not Found'}, 404);
        if (fault === 'proxy') return route.fulfill({status: 404, contentType: 'text/html', body: '<html>404 Not Found</html>'});
        return snapshot ? json(snapshot) : json({detail: 'Session not found'}, 404);
      }
      if (tail === '/messages' && request.method() === 'POST') {
        const body = request.postDataJSON(), fail = this.sendFail;
        this.calls.push(`send ${id}`);
        this.messages.push({session: id, id: body.id, content: body.content});
        await this.gateOnce(`send ${id}`, 'send');
        if (fail === 'before') return json({detail: '模型暂不可用'}, 502);
        // get_session creates the session; the user message is recorded once and published before the reply.
        if (!this.saved.has(id)) this.saved.set(id, []);
        if (!this.rows.some(row => row.id === id)) this.rows.unshift({id, name: '新会话', created: ++clock});
        const messages = this.saved.get(id)!;
        const old = messages.find(m => m.id === body.id);
        if (old && old.content !== body.content) return json({detail: 'Message ID reused with different content'}, 409);
        if (!messages.some(m => m.id === `${body.id}r`)) {
          if (!old) messages.push(say(body.id, 'user', body.content));
          this.publish();
          await this.gateOnce('recorded');
          if (fail === 'recorded') return json({detail: 'Model request failed; retry this message'}, 502);
          this.replies += 1;
          messages.push(say(`${body.id}r`, 'assistant', `回复：${body.content}`));
          this.publish();
        }
        const answer = {id, messages: [...messages]};
        await this.gateOnce('replied');
        if (fail === 'lost') return route.abort('connectionreset');
        return json(answer);
      }
    }
    if (path === `nodes/${node}/read`) {
      const {kind} = request.postDataJSON();
      // The node's own row for the asked task, as the Runtime has it.
      if (kind === 'task.get') {
        const id = request.postDataJSON().payload?.task_id;
        return json({result: this.device.snapshot.tasks.find(t => t.id === id) ?? row});
      }
      // The running task's event log: no new events yet.
      if (kind === 'task.events') return json({result: {events: [], next_offset: 0, size: 0, terminal: false}});
      if (kind === 'task.artifacts') {
        const later = this.later;
        await this.gate(kind);
        if (this.artifactPaths) return json({result: this.artifactPaths.map(path => ({path, size: 10}))});
        return json({result: [{path: 'scalar-0.vti', size: 10}, ...(later ? [{path: 'scalar-1.vti', size: 10}] : [])]});
      }
    }
    if (path === 'actions' && request.method() === 'POST') {
      const body = request.postDataJSON();
      if (body.kind === 'view.build') this.builds.push(body.payload);
      if (body.kind === 'view.probe') this.probes.push(body.payload);
      if (body.kind === 'graph.evaluate') this.evaluations.push(body.payload);
      const viewError = this.viewErrors.get(body.kind);
      await this.gate(body.kind);
      if (viewError) return json({detail: viewError}, 502);
      if (body.kind === 'view.build') {
        const field = this.field;
        const source = this.reportedViewSource ?? {task_id: body.payload.task_id, path: body.payload.path};
        return json({id: body.id, state: 'succeeded',
          result: {...scene, manifest: {...scene.manifest, field, ...(source === 'omit' ? {} : {source})}}});
      }
      if (body.kind === 'view.probe') {
        return json({id: body.id, state: 'succeeded', result: {position: body.payload.position, values: [0.5], units: 'V'}});
      }
      if (body.kind === 'task.submit') {
        if (!this.review) return json({id: body.id, state: 'succeeded', result: {id: task}});
        const item = {id: body.id, state: 'review', review_reason: '新命令需要执行复核', request: {kind: body.kind, payload: body.payload}};
        this.actionRows.unshift(item);
        return json(item);
      }
      if (body.kind === 'graph.evaluate') {
        const asked = body.payload.parameters?.step, step = typeof asked === 'number' ? asked : STEPS[STEPS.length - 1];
        const result = {outputs: {main: {manifest: JSON.parse(readFileSync(join(EXAMPLE, 'manifest.json'), 'utf8'))}},
          parameters: {step: {value: step, choices: STEPS}}};
        if (this.queueGraph) { this.queuedResults.set(body.id, result); return json({id: body.id, state: 'queued'}); }
        return json({id: body.id, state: 'succeeded', result});
      }
      if (body.kind === 'task.logs') return json(this.logsFail ? {id: body.id, state: 'failed', error: '日志暂不可读'} :
        {id: body.id, state: 'succeeded', result: {data: Buffer.from(LOG).toString('base64')}});
    }
    return json({detail: `unmocked ${path}`}, 500);
  }
}

const nav = (page: Page) => page.getByRole('navigation', {name: '工作区'});
const go = (page: Page, label: string) => nav(page).getByRole('button', {name: label, exact: true}).click();
const shortcut = (page: Page, label: '结果' | '读取日志') => page.locator('aside.tasks .inline').getByRole('button', {name: label, exact: true});
const surfaces = {工作台: 'aside.chat', 任务: 'aside.tasks', 结果: 'section.analysis'} as const;
const footer = (page: Page) => page.locator('footer');
// 任务 keeps the run environment and the new task form in disclosures under the queue.
const project = (page: Page) => page.locator('aside.tasks label', {hasText: /^项目/}).locator('select');
const disclosure = (page: Page, name: '运行环境' | '新建任务') => page.locator('aside.tasks details.setting > summary', {hasText: name});

// covered: the compact history is open over the active section, which then stays shown but takes no input.
async function expectActive(page: Page, label: keyof typeof surfaces, {covered = false} = {}) {
  for (const [name, selector] of Object.entries(surfaces)) {
    const active = name === label;
    const button = nav(page).getByRole('button', {name, exact: true});
    if (active) await expect(button).toHaveAttribute('aria-current', 'page'); else await expect(button).not.toHaveAttribute('aria-current');
    if (active) await expect(page.locator(selector)).toBeVisible(); else await expect(page.locator(selector)).toBeHidden();
    expect(await page.locator(selector).evaluate(el => (el as HTMLElement).inert)).toBe(!active || covered);
  }
}

// Records the hub writes and node reads (POST); refreshes and polls are GETs.
function posts(page: Page) {
  const seen: string[] = [];
  const listener = (request: Request) => {
    if (request.method() !== 'POST' || !request.url().includes('/api/v1/')) return;
    seen.push(`${new URL(request.url()).pathname.replace(node, '{node}')} ${request.postDataJSON()?.kind}`);
  };
  page.on('request', listener);
  return {seen, stop: () => page.off('request', listener)};
}

// Paired app with the task selected in 任务 (a list click stays in 任务), drafts in 工作台 and 任务,
// a loaded scene with a moved camera and a probe input in 结果. Ends in 任务.
async function setup(page: Page, hub: Hub, {scene: withScene = true} = {}) {
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.clock.install();
  await hub.install(page);
  await page.goto(ORIGIN + '/');
  await expectActive(page, '工作台');
  await page.getByLabel('对话内容').fill('未发送的草稿：分析 phi 场');
  await go(page, '任务');
  await page.getByLabel('执行节点').selectOption(node);
  await project(page).selectOption(ws);
  await page.getByRole('button', {name: /解析场验证/}).click();
  await expectActive(page, '任务');
  await expect(page.getByRole('region', {name: '所选任务状态'})).toContainText('已读取 Runtime 状态');
  await disclosure(page, '新建任务').click();
  await page.getByLabel('TaskSpec').fill('{"argv":["python3","draft.py"],"outputs":[]}');
  if (withScene) {
    await go(page, '结果');
    await page.getByLabel('结果文件').selectOption('scalar-0.vti');
    await page.getByRole('button', {name: '加载视图'}).click();
    await expect(page.locator('section.analysis .viewport canvas')).toHaveCount(1);
    await expect(page.locator('section.analysis .legend')).toContainText('V');
    const box = (await page.locator('section.analysis .viewport').boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2 + 30, {steps: 8});
    await page.mouse.up();
    await page.getByLabel('探针X').fill('0.25');
    await page.locator('section.analysis .viewport canvas').evaluate(el => { (el as any).__marker = 'same-canvas'; });
    await go(page, '任务');
  }
  await expect(footer(page)).toContainText('就绪');
  return errors;
}

// Freeze timers so periodic hub polls cannot add requests while one explicit click is counted.
async function freeze(page: Page) {
  await page.clock.pauseAt(await page.evaluate(() => Date.now()) + 20);
  await page.waitForTimeout(300);
}

// Viewer pixels at a fixed scroll offset of 结果, so a different scroll position cannot pass for a camera change.
async function viewerShot(page: Page, name: string) {
  await page.locator('section.analysis').evaluate(el => { el.scrollTop = 0; });
  const shot = await page.locator('section.analysis .viewport').screenshot({path: test.info().outputPath(`viewer-${name}.png`)});
  return shot;
}

// Scroll offset of 结果 and the log pane's box: equal before and after a late log means nothing moved.
async function logLayout(page: Page) {
  return page.locator('section.analysis').evaluate(el => {
    const r = el.querySelector('details.logs')!.getBoundingClientRect();
    return {scrollTop: el.scrollTop, pane: [r.top, r.height].map(Math.round)};
  });
}

async function state(page: Page) {
  return {
    draft: await page.getByLabel('对话内容').inputValue(),
    node: await page.getByLabel('执行节点').inputValue(),
    workspace: await project(page).inputValue(),
    selected: (await page.locator('aside.tasks .task.selected').allTextContents()).join(),
    spec: await page.getByLabel('TaskSpec').inputValue(),
    analysis: await page.locator('section.analysis [role=tab][aria-selected=true]').textContent(),
    file: await page.getByLabel('结果文件').inputValue(),
    title: await page.locator('section.analysis .view-title h1').textContent(),
    probe: await page.getByLabel('探针X').inputValue(),
    canvas: await page.locator('section.analysis .viewport canvas').evaluate(el => (el as any).__marker ?? null),
  };
}

const viewports = [{name: 'wide', width: 1440, height: 900}, {name: 'narrow', width: 390, height: 844}];

for (const viewport of viewports) {
  test.describe(viewport.name, () => {
    test.use({viewport: {width: viewport.width, height: viewport.height}});

    test('Tasks 结果 opens 结果 in one click and shows the files it reads', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub);
      const fileList = page.getByLabel('结果文件');
      await go(page, '结果');
      await freeze(page);
      const viewer = await viewerShot(page, 'before');
      // 结果 is left scrolled to the bottom; on the narrow page that puts the file list out of view.
      await page.locator('section.analysis').evaluate(el => { el.scrollTop = el.scrollHeight; });
      if (viewport.name === 'narrow') await expect(fileList).not.toBeInViewport();
      await go(page, '任务');
      const before = await state(page);
      expect(before).toMatchObject({draft: '未发送的草稿：分析 phi 场', node, workspace: ws, analysis: '结果文件',
        file: 'scalar-0.vti', title: 'phi', probe: '0.25', canvas: 'same-canvas'});
      await expect(fileList.locator('option', {hasText: 'scalar-1.vti'})).toHaveCount(0);
      hub.later = true;
      const release = hub.hold('task.artifacts');
      const sent = posts(page);
      await shortcut(page, '结果').click();
      // One click: 结果 is open and the file list is in view while the read is still pending.
      await expectActive(page, '结果');
      await expect(fileList).toBeInViewport();
      await expect(fileList).toBeFocused();
      await expect(footer(page)).toContainText('正在处理请求');
      await expect.poll(() => hub.reached.has('task.artifacts')).toBe(true);
      release();
      await expect(fileList.locator('option', {hasText: 'scalar-1.vti'})).toHaveCount(1);
      await expect(footer(page)).toContainText('就绪');
      await expectActive(page, '结果');
      await page.waitForTimeout(300);
      sent.stop();
      expect(sent.seen).toEqual(['/api/v1/nodes/{node}/read task.artifacts']);
      expect(await state(page)).toEqual(before);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-files-shortcut.png`)});
      expect((await viewerShot(page, 'after')).equals(viewer)).toBe(true);
      expect(errors).toEqual([]);
    });

    test('Tasks 读取日志 opens 结果 with the log in view', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub);
      const pane = page.locator('section.analysis details.logs');
      await go(page, '结果');
      await freeze(page);
      const viewer = await viewerShot(page, 'before');
      // The log pane is collapsed and 结果 scrolled to the top; on the narrow page the pane is then out of view.
      await page.locator('section.analysis summary', {hasText: '日志 / 探针结果'}).click();
      expect(await pane.evaluate(el => (el as HTMLDetailsElement).open)).toBe(false);
      await page.locator('section.analysis').evaluate(el => { el.scrollTop = 0; });
      if (viewport.name === 'narrow') await expect(pane).not.toBeInViewport();
      await go(page, '任务');
      const before = await state(page);
      const release = hub.hold('task.logs');
      const sent = posts(page);
      await shortcut(page, '读取日志').click();
      await expectActive(page, '结果');
      expect(await pane.evaluate(el => (el as HTMLDetailsElement).open)).toBe(true);
      // The pane gets its full bounded height at the click, so it is wholly in view before any text arrives
      // (0.99: fractional layout at 390 px leaves ~0.1 px).
      await expect(pane).toBeInViewport({ratio: 0.99});
      await expect(pane.locator('summary')).toBeFocused();
      await expect(footer(page)).toContainText('正在处理请求');
      await expect.poll(() => hub.reached.has('task.logs')).toBe(true);
      const held = await logLayout(page);
      release();
      await expect(pane.locator('pre')).toHaveText(LOG);
      // The 40-line log scrolls inside the pane: 结果 neither scrolled nor reflowed.
      expect(await logLayout(page)).toEqual(held);
      await expect(pane).toBeInViewport({ratio: 0.99});
      await expect(footer(page)).toContainText('就绪');
      await expectActive(page, '结果');
      await page.waitForTimeout(300);
      sent.stop();
      expect(sent.seen).toEqual(['/api/v1/actions task.logs']);
      expect(await state(page)).toEqual(before);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-logs-shortcut.png`)});
      expect((await viewerShot(page, 'after')).equals(viewer)).toBe(true);
      expect(errors).toEqual([]);
    });

    test('a failed 读取日志 reports the error in 结果', async ({page}) => {
      const hub = new Hub();
      hub.logsFail = true;
      const errors = await setup(page, hub, {scene: false});
      await freeze(page);
      const sent = posts(page);
      await shortcut(page, '读取日志').click();
      await expectActive(page, '结果');
      await expect(page.getByRole('alert')).toContainText('日志暂不可读');
      await expect(page.getByRole('alert')).toBeInViewport();
      await expect(page.locator('section.analysis details.logs pre')).toHaveText('选择任务读取日志，或在三维视图中选取一个位置。');
      await expect(footer(page)).toContainText('就绪');
      sent.stop();
      expect(sent.seen).toEqual(['/api/v1/actions task.logs']);
      expect(errors).toEqual([]);
    });

    test('a held 加载视图 completes in place and keeps the newer page choice', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub, {scene: false});
      const title = page.locator('section.analysis .view-title h1');
      await go(page, '结果');
      await page.getByLabel('结果文件').selectOption('scalar-0.vti');
      expect(await title.textContent()).toBe('科学结果');
      // Leave for 任务 with the first build held, then for 工作台 with a second build of another field.
      for (const [away, field] of [['任务', 'phi'], ['工作台', 'psi']] as const) {
        await go(page, '结果');
        hub.field = field;
        const release = hub.hold('view.build');
        hub.reached.clear();
        await page.getByRole('button', {name: '加载视图'}).click();
        await expect.poll(() => hub.reached.has('view.build')).toBe(true);
        await go(page, away);
        await expectActive(page, away);
        release();
        // The late result updates the same bound result while the user stays where they went.
        await expect.poll(() => title.textContent()).toBe(field);
        await expect(page.locator('section.analysis .legend')).toHaveCount(1);
        await expect(footer(page)).toContainText('就绪');
        await page.waitForTimeout(300);
        await expectActive(page, away);
      }
      await go(page, '结果');
      await expect(page.locator('section.analysis .viewport canvas')).toHaveCount(1);
      await expect(page.locator('section.analysis .legend')).toBeVisible();
      expect(errors).toEqual([]);
    });

    test('a held shortcut read completes without moving the user', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub, {scene: false});
      const fileList = page.getByLabel('结果文件'), log = page.locator('section.analysis details.logs pre');
      for (const [label, kind, away] of [['结果', 'task.artifacts', '任务'], ['读取日志', 'task.logs', '工作台']] as const) {
        await go(page, '任务');
        hub.later = true;
        const release = hub.hold(kind);
        hub.reached.clear();
        await shortcut(page, label).click();
        await expectActive(page, '结果');
        await expect.poll(() => hub.reached.has(kind)).toBe(true);
        await go(page, away);
        release();
        await expect(footer(page)).toContainText('就绪');
        // The late read fills 结果 for the same task while the user stays in the section they chose.
        if (kind === 'task.artifacts') await expect(fileList.locator('option', {hasText: 'scalar-1.vti'})).toHaveCount(1);
        else await expect.poll(() => log.textContent()).toBe(LOG);
        await page.waitForTimeout(300);
        await expectActive(page, away);
      }
      expect(errors).toEqual([]);
    });

    for (const scrolled of [false, true]) {
      test(`a held 读取日志 after leaving and returning to 结果${scrolled ? ' scrolled to the top' : ''} moves nothing`, async ({page}) => {
        const hub = new Hub();
        const errors = await setup(page, hub);
        const pane = page.locator('section.analysis details.logs');
        const release = hub.hold('task.logs');
        await shortcut(page, '读取日志').click();
        await expectActive(page, '结果');
        await expect.poll(() => hub.reached.has('task.logs')).toBe(true);
        await go(page, '任务');
        await go(page, '结果');
        await expectActive(page, '结果');
        if (scrolled) await page.locator('section.analysis').evaluate(el => { el.scrollTop = 0; });
        if (!scrolled) await expect(pane).toBeInViewport({ratio: 0.99});
        const held = await logLayout(page);
        release();
        await expect(pane.locator('pre')).toHaveText(LOG);
        await expect(footer(page)).toContainText('就绪');
        await page.waitForTimeout(300);
        // The late text neither grows the pane nor scrolls 结果, whether the user left it at the pane or moved away.
        expect(await logLayout(page)).toEqual(held);
        if (!scrolled) await expect(pane).toBeInViewport({ratio: 0.99});
        await expectActive(page, '结果');
        await page.screenshot({path: test.info().outputPath(`${viewport.name}-aba${scrolled ? '-top' : ''}.png`)});
        expect(errors).toEqual([]);
      });
    }

    test('Tasks 结果 keeps the chosen 图谱 mode and its panel', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub, {scene: false});
      await go(page, '结果');
      // The mode switch keeps its height when 结果 overflows (it collapsed to 2 px in a height-limited column).
      expect((await page.getByRole('tab', {name: '图谱'}).boundingBox())!.height).toBeGreaterThan(24);
      await page.getByRole('tab', {name: '图谱'}).click();
      const graph = page.locator('section.analysis .graph-panel');
      await expect(graph).toHaveCount(1);
      await graph.evaluate(el => { (el as any).__marker = 'same-graph'; });
      await go(page, '任务');
      await freeze(page);
      hub.later = true;
      const sent = posts(page);
      await shortcut(page, '结果').click();
      await expectActive(page, '结果');
      const tab = page.getByRole('tab', {name: '图谱'});
      await expect(tab).toHaveAttribute('aria-selected', 'true');
      await expect(tab).toBeFocused();
      await expect(tab).toBeInViewport();
      await expect(footer(page)).toContainText('就绪');
      expect(await graph.evaluate(el => (el as any).__marker ?? null)).toBe('same-graph');
      sent.stop();
      expect(sent.seen).toEqual(['/api/v1/nodes/{node}/read task.artifacts']);
      expect(errors).toEqual([]);
    });
  });
}

// 任务 as the native focused Tasks page: the queue and the selected task come first, the run environment (node and
// project) and the new task form are one-click disclosures under it, and only their explicit buttons submit.
const queue = (page: Page) => page.getByRole('region', {name: '任务队列'});
const status = (page: Page) => page.getByRole('region', {name: '所选任务状态'});
const settings = (page: Page, name: '运行环境' | '新建任务') => disclosure(page, name).locator('..');
// Node reads (task.get, task.artifacts) are POSTs too; everything else POSTed is a write.
const writes = (seen: string[]) => seen.filter(s => !s.startsWith('/api/v1/nodes/{node}/read '));
const top = async (target: Locator) => (await target.boundingBox())!.y;
// Counts the measured clicks and <select> choices of one route, apart from its setup, and keeps them as evidence.
function route(page: Page, name: string) {
  const record = {route: name, clicks: 0, selects: 0, steps: [] as string[]};
  return {
    record,
    click: async (target: Locator, step: string) => { record.clicks++; record.steps.push(`click ${step}`); await target.click(); },
    select: async (target: Locator, value: string, step: string) => { record.selects++; record.steps.push(`select ${step}`); await target.selectOption(value); },
    save: () => writeFileSync(test.info().outputPath(`route-${name}.json`), JSON.stringify(record, null, 2)),
  };
}
async function start(page: Page, hub: Hub) {
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.clock.install();
  await hub.install(page);
  await page.goto(ORIGIN + '/');
  await expectActive(page, '工作台');
  return errors;
}

for (const viewport of viewports) {
  test.describe(`${viewport.name} queue-first 任务`, () => {
    test.use({viewport: {width: viewport.width, height: viewport.height}});

    test('from a fresh connected start the queue comes first and the open 运行环境 chooses its scope', async ({page}) => {
      const hub = new Hub();
      const errors = await start(page, hub);
      await expect(footer(page)).toContainText('就绪');
      const sent = posts(page);
      const r = route(page, `${viewport.name}-connected`);
      await r.click(nav(page).getByRole('button', {name: '任务', exact: true}), '任务');
      await expectActive(page, '任务');
      await expect(queue(page)).toContainText('在下方「运行环境」中选择执行节点和项目，这里显示任务队列。');
      await expect(settings(page, '运行环境')).toHaveAttribute('open', '');
      await expect(settings(page, '新建任务')).not.toHaveAttribute('open', '');
      await expect(disclosure(page, '运行环境')).toHaveText('运行环境 · 未选择节点');
      await expect(disclosure(page, '新建任务')).toHaveText('新建任务 · 先选择项目');
      await expect(page.getByLabel('执行节点')).toBeInViewport({ratio: 1});
      expect(await top(queue(page))).toBeLessThan(await top(disclosure(page, '运行环境')));
      expect(await top(disclosure(page, '运行环境'))).toBeLessThan(await top(disclosure(page, '新建任务')));
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-connected-start.png`)});
      await r.select(page.getByLabel('执行节点'), node, '执行节点');
      await expect(queue(page).locator('.queue-head')).toHaveText('任务队列节点甲 · 在线 · 全部项目');
      await expect(project(page)).toBeInViewport({ratio: 1});
      await r.select(project(page), ws, '项目');
      await expect(queue(page).locator('.queue-head')).toHaveText('任务队列节点甲 · 在线 · 项目一');
      await expect(disclosure(page, '运行环境')).toHaveText('运行环境 · 节点甲 · 项目一');
      await expect(disclosure(page, '新建任务')).toHaveText('新建任务 · 项目一');
      const row = queue(page).getByRole('button', {name: /解析场验证/});
      await expect(row).toBeInViewport({ratio: 1});
      await r.click(row, '任务行');
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      await expect(page.locator('aside.tasks .task-scope')).toHaveText('所选任务 · 节点甲 · 项目一');
      await expect(shortcut(page, '结果')).toBeInViewport({ratio: 1});
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-connected-selected.png`)});
      // One click folds the environment to its readable summary; the queue and the selected task do not move.
      const at = [await top(queue(page)), await top(status(page))];
      await r.click(disclosure(page, '运行环境'), '收起运行环境');
      await expect(page.getByLabel('执行节点')).toBeHidden();
      expect([await top(queue(page)), await top(status(page))]).toEqual(at);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-connected-folded.png`)});
      await r.click(disclosure(page, '运行环境'), '展开运行环境');
      await expect(page.getByLabel('执行节点')).toHaveValue(node);
      await expect(project(page)).toHaveValue(ws);
      await r.click(disclosure(page, '新建任务'), '展开新建任务');
      await expect(page.getByRole('button', {name: '运行解析场示例'})).toBeEnabled();
      await expect(page.getByLabel('TaskSpec')).toBeVisible();
      await expect(page.locator('aside.tasks .task.selected')).toHaveText(/解析场验证/);
      sent.stop();
      expect(writes(sent.seen)).toEqual([]);
      expect([...new Set(sent.seen)].sort()).toEqual(['/api/v1/nodes/{node}/read task.artifacts', '/api/v1/nodes/{node}/read task.get']);
      expect(hub.calls).toEqual([]);
      expect(r.record).toMatchObject({clicks: 5, selects: 2});
      r.save();
      expect(errors).toEqual([]);
    });

    test('an established 任务 keeps the queue first and its drafts, scope and Viewer with the disclosures folded', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub);
      await go(page, '结果');
      const viewer = await viewerShot(page, 'before');
      await go(page, '任务');
      await page.locator('aside.tasks').evaluate(el => { el.scrollTop = 0; });
      const before = await state(page);
      expect(before).toMatchObject({node, workspace: ws, selected: '解析场验证succeeded', spec: '{"argv":["python3","draft.py"],"outputs":[]}'});
      const sent = posts(page);
      const r = route(page, `${viewport.name}-established`);
      // Zero clicks: the queue row, the selected task's status and its shortcuts are in view above both disclosures.
      await expect(queue(page).getByRole('button', {name: /解析场验证/})).toBeInViewport({ratio: 1});
      await expect(status(page)).toBeInViewport({ratio: 1});
      await expect(shortcut(page, '读取日志')).toBeInViewport({ratio: 1});
      expect(await top(status(page))).toBeLessThan(await top(disclosure(page, '运行环境')));
      await r.click(disclosure(page, '运行环境'), '收起运行环境');
      await r.click(disclosure(page, '新建任务'), '收起新建任务');
      await expect(page.getByLabel('TaskSpec')).toBeHidden();
      await expect(disclosure(page, '运行环境')).toHaveText('运行环境 · 节点甲 · 项目一');
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-established-folded.png`)});
      await r.click(nav(page).getByRole('button', {name: '结果', exact: true}), '结果');
      await expectActive(page, '结果');
      expect((await viewerShot(page, 'folded')).equals(viewer)).toBe(true);
      await r.click(nav(page).getByRole('button', {name: '工作台', exact: true}), '工作台');
      await expect(draft(page)).toHaveValue('未发送的草稿：分析 phi 场');
      await r.click(nav(page).getByRole('button', {name: '任务', exact: true}), '任务');
      await expectActive(page, '任务');
      await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
      await expect(settings(page, '新建任务')).not.toHaveAttribute('open', '');
      expect(await state(page)).toEqual(before);
      // One click each opens them again with the same choices and the same unsubmitted TaskSpec.
      await r.click(disclosure(page, '运行环境'), '展开运行环境');
      await expect(page.getByLabel('执行节点')).toBeVisible();
      await r.click(disclosure(page, '新建任务'), '展开新建任务');
      await expect(page.getByLabel('TaskSpec')).toHaveValue('{"argv":["python3","draft.py"],"outputs":[]}');
      expect(await state(page)).toEqual(before);
      sent.stop();
      expect(writes(sent.seen)).toEqual([]);
      expect(r.record).toMatchObject({clicks: 7, selects: 0});
      r.save();
      await go(page, '结果');
      expect((await viewerShot(page, 'after')).equals(viewer)).toBe(true);
      expect(errors).toEqual([]);
    });

    test('from a disconnected start 任务 says the Hub is unreachable and offers no submission', async ({page}) => {
      const hub = new Hub();
      hub.down = true;
      const errors = await start(page, hub);
      await expect(page.locator('header .connection')).toHaveText('连接中断 · 显示最近状态');
      const sent = posts(page);
      const r = route(page, `${viewport.name}-disconnected`);
      await r.click(nav(page).getByRole('button', {name: '任务', exact: true}), '任务');
      await expectActive(page, '任务');
      await expect(queue(page)).toContainText('控制服务未连接。恢复连接后，这里显示执行节点的任务队列。');
      await expect(disclosure(page, '运行环境')).toHaveText('运行环境 · 未选择节点');
      await expect(page.getByLabel('执行节点').locator('option')).toHaveText(['选择节点']);
      await expect(page.locator('aside.tasks .inline').getByRole('button', {name: '新建', exact: true})).toBeDisabled();
      await r.click(disclosure(page, '新建任务'), '展开新建任务');
      await expect(page.getByRole('button', {name: '运行解析场示例'})).toBeDisabled();
      await expect(page.getByRole('button', {name: '提交复核'})).toBeDisabled();
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-disconnected.png`)});
      // An explicit 刷新 after the Hub is back lists the node; still nothing is chosen or written.
      hub.down = false;
      await r.click(page.locator('aside.tasks .section-title').getByRole('button', {name: '刷新'}), '刷新');
      await expect(page.locator('header .connection')).toHaveText('控制服务已连接');
      await expect(queue(page)).toContainText('在下方「运行环境」中选择执行节点和项目');
      await expect(page.getByLabel('执行节点')).toHaveValue('');
      sent.stop();
      expect(sent.seen).toEqual([]);
      expect(r.record).toMatchObject({clicks: 3, selects: 0});
      r.save();
      expect(unexpected(errors, 503)).toEqual([]);
    });

    test('the queue names an offline node and a project without tasks', async ({page}) => {
      const hub = new Hub();
      const other = 'd'.repeat(32);
      hub.device = {...device, online: false, snapshot: {...device.snapshot, workspaces: [...device.snapshot.workspaces, {id: other, name: '项目二'}]}};
      const errors = await start(page, hub);
      await go(page, '任务');
      await page.getByLabel('执行节点').selectOption(node);
      await expect(queue(page).locator('.queue-head')).toHaveText('任务队列节点甲 · 离线 · 全部项目');
      // The whole node is listed while no project is chosen; the selected task shows its own project.
      await queue(page).getByRole('button', {name: /解析场验证/}).click();
      await expect(page.locator('aside.tasks .task-scope')).toHaveText('所选任务 · 节点甲 · 项目一');
      await expect(status(page)).toContainText('暂时无法读取 Runtime 状态');
      await project(page).selectOption(other);
      await expect(queue(page)).toContainText('项目二 中暂无任务，可在下方「新建任务」中提交。');
      await expect(page.locator('aside.tasks .task')).toHaveCount(0);
      await expect(disclosure(page, '运行环境')).toHaveText('运行环境 · 节点甲 · 项目二');
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-offline-empty-project.png`)});
      expect(errors).toEqual([]);
    });

    test('a long queue keeps the selected task and run environment within reach', async ({page}) => {
      const hub = new Hub();
      const more = Array.from({length: 199}, (_, index) => ({
        ...row, id: (index + 1).toString(16).padStart(32, '0'), name: `额外任务 ${index + 1}`,
      }));
      hub.device = {...device, snapshot: {...device.snapshot, tasks: [row, ...more]}};
      const errors = await start(page, hub);
      await go(page, '任务');
      await page.getByLabel('执行节点').selectOption(node);
      await project(page).selectOption(ws);
      const list = queue(page).locator('.task-list');
      const rows = list.getByRole('button');
      await expect(rows).toHaveCount(200);
      expect(await list.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true);

      const sent = posts(page);
      await rows.first().click();
      await expect(status(page)).toBeInViewport();
      await expect(disclosure(page, '运行环境')).toBeInViewport();
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-long-queue.png`)});
      await rows.last().focus();
      await expect(rows.last()).toBeInViewport();
      await expect(rows.last()).toBeFocused();
      await expect(rows.first()).toHaveClass(/selected/);
      sent.stop();
      expect(writes(sent.seen)).toEqual([]);
      expect(errors).toEqual([]);
    });

    test('only the explicit buttons in 新建任务 submit; a pending review is approved in place', async ({page}) => {
      const hub = new Hub();
      hub.review = true;
      const errors = await setup(page, hub, {scene: false});
      const sent = posts(page);
      for (const name of ['运行环境', '新建任务', '运行环境', '新建任务'] as const) await disclosure(page, name).click();
      await go(page, '结果');
      await go(page, '任务');
      await expect(footer(page)).toContainText('就绪');
      expect(writes(sent.seen)).toEqual([]);
      await page.getByRole('button', {name: '运行解析场示例'}).click();
      const card = page.locator('aside.tasks article.review');
      await expect(card).toHaveCount(1);
      await expect(footer(page)).toContainText('就绪');
      expect(writes(sent.seen)).toEqual(['/api/v1/actions task.submit']);
      expect(hub.actionRows[0].request.payload).toMatchObject({template: 'demo-field', spec: {workspace_id: ws, name: '解析场验证'}});
      // The review sits with the selected task, above the folded settings, and needs no disclosure to approve.
      for (const name of ['运行环境', '新建任务'] as const) await disclosure(page, name).click();
      expect(await card.evaluate(el => el.closest('details'))).toBeNull();
      expect(await top(card)).toBeLessThan(await top(disclosure(page, '运行环境')));
      await expect(card).toContainText('新命令需要执行复核');
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-review.png`)});
      await card.getByRole('button', {name: '批准执行'}).click();
      await expect(card).toHaveCount(0);
      expect(writes(sent.seen)).toEqual(['/api/v1/actions task.submit', `/api/v1/actions/${hub.actionRows[0].id}/review undefined`]);
      expect(hub.actionRows[0].state).toBe('succeeded');
      // The custom TaskSpec is sent once, by 提交复核, with the draft that was kept while folded.
      await disclosure(page, '新建任务').click();
      await page.getByRole('button', {name: '提交复核'}).click();
      await expect(card).toHaveCount(1);
      sent.stop();
      expect(writes(sent.seen).slice(2)).toEqual(['/api/v1/actions task.submit']);
      expect(hub.actionRows[0].request.payload).toEqual({spec: {workspace_id: ws, argv: ['python3', 'draft.py'], outputs: []}});
      expect(errors).toEqual([]);
    });
  });
}

// 结果 names its source in one line under the title: the selected task's node, project and name, then the artifact
// the Viewer shows. The shown scene stays bound to the task and file of the view.build that made it, so another
// file choice is shown as chosen but not loaded, 查询原始值 asks for the shown file, and a late reply for another
// task or an older scene is dropped. Only 加载视图 and 查询原始值 send anything.
const task2 = 'd'.repeat(32);
const row2 = {...row, id: task2, name: '对照任务', state: 'succeeded'};
const twoTasks = {...device, snapshot: {...device.snapshot, tasks: [row, row2]}};
const source = (page: Page) => page.getByLabel('结果来源');
const title = (page: Page) => page.locator('section.analysis .view-title h1');
const canvasMarker = (page: Page) => page.locator('section.analysis .viewport canvas').evaluate(el => (el as any).__marker ?? null);
const probeLog = (page: Page) => page.locator('section.analysis details.logs pre');
const taskRow = (page: Page, name: string) => queue(page).getByRole('button', {name: new RegExp(name)});
const shown = (file: string, name = '解析场验证') => `节点甲 · 项目一 · ${name}，${file}`;
const pending = (file: string) => `已选 ${file}，加载视图后显示`;
// 来源 beside the source line opens the full source of 结果 over the page: label and value of each row, and the
// selectable values (IDs and paths) alone.
const sourceToggle = (page: Page) => page.locator('section.analysis .view-title').getByRole('button', {name: '来源', exact: true});
const sourcePanel = (page: Page) => page.getByRole('region', {name: '来源详情'});
const detailRows = (page: Page) => sourcePanel(page).locator('dl').evaluate(dl =>
  [...dl.querySelectorAll('dt')].map(dt => [dt.textContent, dt.nextElementSibling!.textContent]));
const detailValues = (page: Page) => sourcePanel(page).locator('.source-value').allTextContents();
const selectedText = (page: Page) => page.evaluate(() => getSelection()!.toString());
// Where 结果 and its Viewer are: equal before, while and after the details are open means nothing moved.
const resultLayout = (page: Page) => page.locator('section.analysis').evaluate(el => {
  const box = (selector: string) => { const r = el.querySelector(selector)!.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; };
  return {scrollTop: el.scrollTop, scrollHeight: el.scrollHeight, viewport: box('.viewport'), title: box('.view-title'), controls: box('.view-controls')};
});
// Every request of the page (GETs, POSTs and files alike), for a check that an action sends nothing at all.
function everything(page: Page) {
  const seen: string[] = [];
  const listener = (request: Request) => seen.push(`${request.method()} ${new URL(request.url()).pathname}`);
  page.on('request', listener);
  return {seen, stop: () => page.off('request', listener)};
}
// Counts every use of the clipboard API, execCommand and copy/cut/paste events in the page.
async function spyClipboard(page: Page) {
  await page.addInitScript(() => {
    const w = window as any, clipboard = navigator.clipboard as any;
    w.__clipboard = [];
    if (clipboard) for (const name of ['writeText', 'write', 'readText', 'read']) {
      const original = clipboard[name]?.bind(clipboard);
      clipboard[name] = (...args: unknown[]) => { w.__clipboard.push(name); return original?.(...args); };
    }
    const exec = document.execCommand.bind(document);
    document.execCommand = (command: string, ...rest: any[]) => { w.__clipboard.push(`exec ${command}`); return exec(command, ...rest); };
    for (const type of ['copy', 'cut', 'paste']) document.addEventListener(type, () => w.__clipboard.push(`event ${type}`), true);
  });
}
const clipboardUses = (page: Page) => page.evaluate(() => (window as any).__clipboard);

for (const viewport of viewports) {
  test.describe(`${viewport.name} 结果 source`, () => {
    test.use({viewport: {width: viewport.width, height: viewport.height}});

    test('结果 names the shown task and file; another choice stays chosen until 加载视图, and 查询原始值 asks for the shown file', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub);
      const fileList = page.getByLabel('结果文件');
      await go(page, '结果');
      await freeze(page);
      const viewer = await viewerShot(page, 'source-before');
      await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
      await expect(source(page)).toBeInViewport();
      await expect(page.locator('section.analysis')).not.toContainText('RESULT EXPLORER');
      await go(page, '任务');
      hub.later = true;
      const sent = posts(page);
      const r = route(page, `${viewport.name}-result-source`);
      // The existing one-click shortcut: 结果 opens with the list it reads, and the source line already in view.
      await r.click(shortcut(page, '结果'), 'Tasks 结果');
      await expectActive(page, '结果');
      await expect(source(page)).toBeInViewport();
      await expect(fileList.locator('option', {hasText: 'scalar-1.vti'})).toHaveCount(1);
      await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
      const viewportBox = () => page.locator('section.analysis .viewport').boundingBox();
      const placed = await viewportBox();
      await r.select(fileList, 'scalar-1.vti', '结果文件 scalar-1.vti');
      // Chosen, not loaded: the line keeps the shown file and names the choice; the canvas and its camera stay.
      await expect(source(page)).toHaveText(`${shown('显示 scalar-0.vti')}${pending('scalar-1.vti')}`);
      expect(await title(page).textContent()).toBe('phi');
      expect(await canvasMarker(page)).toBe('same-canvas');
      expect((await viewerShot(page, 'source-chosen')).equals(viewer)).toBe(true);
      // The note is one line, cut short rather than wrapped: the Viewer does not move.
      expect(await viewportBox()).toEqual(placed);
      // Ordinary navigation away and back sends nothing and keeps the same canvas and line.
      await r.click(nav(page).getByRole('button', {name: '工作台', exact: true}), '工作台');
      await r.click(nav(page).getByRole('button', {name: '结果', exact: true}), '结果');
      await expect(source(page)).toHaveText(`${shown('显示 scalar-0.vti')}${pending('scalar-1.vti')}`);
      expect(await canvasMarker(page)).toBe('same-canvas');
      expect(await page.getByLabel('对话内容').inputValue()).toBe('未发送的草稿：分析 phi 场');
      await page.waitForTimeout(300);
      expect(sent.seen).toEqual(['/api/v1/nodes/{node}/read task.artifacts']);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-source-chosen.png`)});
      // 查询原始值 reads the file the Viewer shows, not the newer choice.
      await r.click(page.getByRole('button', {name: '查询原始值'}), '查询原始值 (shown scalar-0)');
      await expect(probeLog(page)).toContainText('"values"');
      expect(hub.probes).toHaveLength(1);
      expect(hub.probes[0]).toMatchObject({task_id: task, path: 'scalar-0.vti'});
      expect(hub.probes[0].position[0]).toBe(0.25);
      // 加载视图 shows the chosen file; from then on the line and the probe follow it.
      hub.field = 'psi';
      await r.click(page.getByRole('button', {name: '加载视图'}), '加载视图 scalar-1');
      await expect(source(page)).toHaveText(shown('显示 scalar-1.vti'));
      await expect(title(page)).toHaveText('psi');
      await expect(probeLog(page)).not.toContainText('"values"');
      expect(hub.builds.map(b => [b.task_id, b.path])).toEqual([[task, 'scalar-0.vti'], [task, 'scalar-1.vti']]);
      await r.click(page.getByRole('button', {name: '查询原始值'}), '查询原始值 (shown scalar-1)');
      await expect.poll(() => hub.probes.length).toBe(2);
      expect(hub.probes[1]).toMatchObject({task_id: task, path: 'scalar-1.vti'});
      await expect(footer(page)).toContainText('就绪');
      await page.waitForTimeout(300);
      sent.stop();
      expect(sent.seen).toEqual(['/api/v1/nodes/{node}/read task.artifacts', '/api/v1/actions view.probe',
        '/api/v1/actions view.build', '/api/v1/actions view.probe']);
      // 图谱 names the task only: its data sources are bound in the graph panel.
      await page.getByRole('tab', {name: '图谱'}).click();
      await expect(source(page)).toHaveText('节点甲 · 项目一 · 解析场验证，图谱数据源在下方绑定');
      await expect(source(page)).not.toHaveAttribute('title', /scalar-1\.vti/);
      await expect(probeLog(page)).not.toContainText('"values"');
      await expect(page.locator('section.analysis .view-title h1')).toHaveText('图谱视图');
      r.save();
      writeFileSync(test.info().outputPath('source-requests.json'), JSON.stringify({posts: sent.seen, builds: hub.builds, probes: hub.probes}, null, 2));
      expect(errors).toEqual([]);
    });

    test('expired result failures stay with their source and a new scene restores task logs', async ({page}) => {
      const hub = new Hub();
      hub.device = twoTasks;
      hub.later = true;
      const errors = await setup(page, hub);
      await go(page, '任务');
      await shortcut(page, '读取日志').click();
      await expect(probeLog(page)).toContainText('step 1 converged');
      await expect(footer(page)).toContainText('就绪');
      await page.getByRole('button', {name: '查询原始值'}).click();
      await expect(probeLog(page)).toContainText('"values"');
      const file = page.getByLabel('结果文件');
      const load = page.getByRole('button', {name: '加载视图'});
      const alert = page.getByRole('alert');

      hub.viewErrors.set('view.build', '文件读取失败');
      const releaseBuild = hub.hold('view.build');
      await load.click();
      await expect.poll(() => hub.reached.has('view.build')).toBe(true);
      await file.selectOption('scalar-1.vti');
      releaseBuild();
      await expect(footer(page)).toContainText('就绪');
      await expect(alert).toHaveCount(0);
      await expect(probeLog(page)).toContainText('"values"');

      await load.click();
      await expect(alert).toContainText('文件读取失败');
      await file.selectOption('scalar-0.vti');
      await expect(alert).toHaveCount(0);
      hub.viewErrors.delete('view.build');
      await file.selectOption('scalar-1.vti');
      hub.reportedViewSource = {task_id: task, path: 'scalar-0.vti'};
      await load.click();
      await expect(alert).toContainText('返回的结果来源与所选文件不符');
      await expect(source(page)).toContainText('显示 scalar-0.vti');
      hub.reportedViewSource = 'omit';
      await load.click();
      await expect(source(page)).toHaveText(shown('显示 scalar-1.vti'));
      await expect(probeLog(page)).toContainText('step 1 converged');
      await expect(probeLog(page)).not.toContainText('"values"');

      hub.viewErrors.set('view.probe', '旧探针失败');
      const releaseProbe = hub.hold('view.probe');
      await page.getByRole('button', {name: '查询原始值'}).click();
      await expect.poll(() => hub.reached.has('view.probe')).toBe(true);
      await go(page, '任务');
      await taskRow(page, '对照任务').click();
      releaseProbe();
      await expect(footer(page)).toContainText('就绪');
      await go(page, '结果');
      await expect(source(page)).toHaveText(shown('尚未加载结果文件', '对照任务'));
      await expect(alert).toHaveCount(0);
      expect(unexpected(errors, 502)).toEqual([]);
    });

    test('held replies are dropped after another task is chosen, even after coming back to the first', async ({page}) => {
      const hub = new Hub();
      hub.device = twoTasks;
      const errors = await setup(page, hub, {scene: false});
      const sent = posts(page);
      const r = route(page, `${viewport.name}-held-scope`);
      // A held 加载视图 for 解析场验证, then 对照任务 and back to 解析场验证 before it completes.
      await go(page, '结果');
      await r.select(page.getByLabel('结果文件'), 'scalar-0.vti', '结果文件 scalar-0.vti');
      await expect(source(page)).toHaveText(`${shown('尚未加载结果文件')}${pending('scalar-0.vti')}`);
      let release = hub.hold('view.build');
      await r.click(page.getByRole('button', {name: '加载视图'}), '加载视图 (held)');
      await expect.poll(() => hub.reached.has('view.build')).toBe(true);
      await r.click(nav(page).getByRole('button', {name: '任务', exact: true}), '任务');
      await r.click(taskRow(page, '对照任务'), '对照任务');
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      await r.click(taskRow(page, '解析场验证'), '解析场验证');
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      release();
      await expect(footer(page)).toContainText('就绪');
      await page.waitForTimeout(300);
      await r.click(nav(page).getByRole('button', {name: '结果', exact: true}), '结果');
      await expect(page.locator('section.analysis .viewport canvas')).toHaveCount(0);
      await expect(title(page)).toHaveText('科学结果');
      await expect(source(page)).toHaveText(shown('尚未加载结果文件'));
      // A shown scene, then a held 查询原始值 and another task before it answers.
      await r.select(page.getByLabel('结果文件'), 'scalar-0.vti', '结果文件 scalar-0.vti');
      await r.click(page.getByRole('button', {name: '加载视图'}), '加载视图');
      await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
      await expect(page.locator('section.analysis .viewport canvas')).toHaveCount(1);
      hub.reached.clear();
      release = hub.hold('view.probe');
      await r.click(page.getByRole('button', {name: '查询原始值'}), '查询原始值 (held)');
      await expect.poll(() => hub.reached.has('view.probe')).toBe(true);
      await r.click(nav(page).getByRole('button', {name: '任务', exact: true}), '任务');
      await r.click(taskRow(page, '对照任务'), '对照任务');
      release();
      await expect(footer(page)).toContainText('就绪');
      await page.waitForTimeout(300);
      await r.click(nav(page).getByRole('button', {name: '结果', exact: true}), '结果');
      await expect(probeLog(page)).toHaveText('选择任务读取日志，或在三维视图中选取一个位置。');
      await expect(source(page)).toHaveText(shown('尚未加载结果文件', '对照任务'));
      await expect(page.locator('section.analysis .viewport canvas')).toHaveCount(0);
      sent.stop();
      expect(writes(sent.seen)).toEqual(['/api/v1/actions view.build', '/api/v1/actions view.build', '/api/v1/actions view.probe']);
      expect(hub.builds.map(b => b.task_id)).toEqual([task, task]);
      expect(hub.probes.map(p => [p.task_id, p.path])).toEqual([[task, 'scalar-0.vti']]);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-held-scope.png`)});
      r.save();
      writeFileSync(test.info().outputPath('held-scope-requests.json'), JSON.stringify({posts: sent.seen, builds: hub.builds, probes: hub.probes}, null, 2));
      expect(errors).toEqual([]);
    });

    test('a held 查询原始值 keeps its reply across a file choice; a held 加载视图 for an older choice is dropped', async ({page}) => {
      const hub = new Hub();
      hub.later = true;
      const errors = await setup(page, hub);
      await go(page, '结果');
      const fileList = page.getByLabel('结果文件');
      await expect(fileList.locator('option', {hasText: 'scalar-1.vti'})).toHaveCount(1);
      // The probe was asked for the shown scalar-0; changing the choice does not change what it reads.
      let release = hub.hold('view.probe');
      await page.getByRole('button', {name: '查询原始值'}).click();
      await expect.poll(() => hub.reached.has('view.probe')).toBe(true);
      await fileList.selectOption('scalar-1.vti');
      release();
      await expect(probeLog(page)).toContainText('"values"');
      expect(hub.probes.map(p => p.path)).toEqual(['scalar-0.vti']);
      await expect(source(page)).toHaveText(`${shown('显示 scalar-0.vti')}${pending('scalar-1.vti')}`);
      // A build of scalar-1 held while the choice goes back to scalar-0: its late scene is not shown.
      hub.reached.clear();
      hub.field = 'psi';
      release = hub.hold('view.build');
      await page.getByRole('button', {name: '加载视图'}).click();
      await expect.poll(() => hub.reached.has('view.build')).toBe(true);
      await fileList.selectOption('scalar-0.vti');
      release();
      await expect(footer(page)).toContainText('就绪');
      await page.waitForTimeout(300);
      await expect(title(page)).toHaveText('phi');
      await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
      expect(await canvasMarker(page)).toBe('same-canvas');
      expect(hub.builds.map(b => b.path)).toEqual(['scalar-0.vti', 'scalar-1.vti']);
      expect(errors).toEqual([]);
    });

    test('the line names the task\'s own project while the queue shows all projects; choosing a project drops a held probe', async ({page}) => {
      const hub = new Hub();
      const ws2 = 'e'.repeat(32), task3 = 'f'.repeat(32);
      const row3 = {...row, id: task3, workspace_id: ws2, name: '项目二任务'};
      hub.device = {...device, snapshot: {...device.snapshot, tasks: [row, row3], workspaces: [{id: ws, name: '项目一'}, {id: ws2, name: '项目二'}]}};
      const errors = await start(page, hub);
      await go(page, '任务');
      await page.getByLabel('执行节点').selectOption(node);
      await expect(queue(page).locator('.queue-head')).toHaveText('任务队列节点甲 · 在线 · 全部项目');
      await taskRow(page, '项目二任务').click();
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      await go(page, '结果');
      await expect(source(page)).toHaveText('节点甲 · 项目二 · 项目二任务，尚未加载结果文件');
      await page.getByLabel('结果文件').selectOption('scalar-0.vti');
      await page.getByRole('button', {name: '加载视图'}).click();
      await expect(source(page)).toHaveText('节点甲 · 项目二 · 项目二任务，显示 scalar-0.vti');
      await page.getByRole('button', {name: '查询原始值'}).click();
      await expect(probeLog(page)).toContainText('"values"');
      expect(hub.builds.map(b => [b.task_id, b.path])).toEqual([[task3, 'scalar-0.vti']]);
      expect(hub.probes.map(p => [p.task_id, p.path])).toEqual([[task3, 'scalar-0.vti']]);
      // A held probe, then a project chosen in 运行环境 (which clears the selected task) before it answers.
      const release = hub.hold('view.probe');
      await page.getByRole('button', {name: '查询原始值'}).click();
      await expect.poll(() => hub.reached.has('view.probe')).toBe(true);
      await go(page, '任务');
      await project(page).selectOption(ws);
      release();
      await expect(footer(page)).toContainText('就绪');
      await page.waitForTimeout(300);
      await go(page, '结果');
      await expect(probeLog(page)).toHaveText('选择任务读取日志，或在三维视图中选取一个位置。');
      await expect(source(page)).toHaveText('未选择任务，在「任务」中选择任务');
      await expect(title(page)).toHaveText('科学结果');
      await expect(page.locator('section.analysis .viewport canvas')).toHaveCount(0);
      expect(hub.probes.map(p => p.task_id)).toEqual([task3, task3]);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-other-project.png`)});
      expect(errors).toEqual([]);
    });

    test('long node, project and task names wrap in the source line', async ({page}) => {
      const hub = new Hub();
      const long = (word: string) => word.repeat(60 / word.length);
      const longRow = {...row, name: long('任务名')};
      hub.device = {...device, name: long('节点'), snapshot: {...device.snapshot, tasks: [longRow], workspaces: [{id: ws, name: long('项目')}]}};
      const errors: string[] = [];
      page.on('pageerror', e => errors.push(String(e)));
      await hub.install(page);
      await page.goto(ORIGIN + '/');
      await go(page, '任务');
      await page.getByLabel('执行节点').selectOption(node);
      await project(page).selectOption(ws);
      await taskRow(page, '任务名').click();
      await go(page, '结果');
      await page.getByLabel('结果文件').selectOption('scalar-0.vti');
      await page.getByRole('button', {name: '加载视图'}).click();
      await expect(source(page)).toHaveText(`${long('节点')} · ${long('项目')} · ${long('任务名')}，显示 scalar-0.vti`);
      const analysis = page.locator('section.analysis');
      const widths = await analysis.evaluate(el => [el.scrollWidth, el.clientWidth]);
      expect(widths[0]).toBeLessThanOrEqual(widths[1]);
      const box = (await source(page).boundingBox())!;
      expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-source-long.png`)});
      expect(errors).toEqual([]);
    });

    test('来源 opens the full source over 结果 in one click and closes back to its toggle; nothing is sent and nothing moves', async ({page}) => {
      const hub = new Hub();
      hub.later = true;
      conversations(hub);
      await spyClipboard(page);
      const errors = await setup(page, hub);
      const fileList = page.getByLabel('结果文件');
      // The task's log is read and shown in 结果 first, so the log pane's text and place are compared too.
      await shortcut(page, '读取日志').click();
      await expect(probeLog(page)).toContainText('step 40 converged');
      await go(page, '任务');
      const r = route(page, `${viewport.name}-source-details`);
      // The existing one-click shortcut is unchanged: 结果 with its file list focused and the summary line in view.
      await r.click(shortcut(page, '结果'), 'Tasks 结果');
      await expectActive(page, '结果');
      await expect(fileList).toBeFocused();
      await expect(fileList.locator('option', {hasText: 'scalar-1.vti'})).toHaveCount(1);
      await r.select(fileList, 'scalar-1.vti', '结果文件 scalar-1.vti');
      await expect(source(page)).toHaveText(`${shown('显示 scalar-0.vti')}${pending('scalar-1.vti')}`);
      await expect(footer(page)).toContainText('就绪');
      await freeze(page);
      const before = await state(page);
      const viewer = await viewerShot(page, 'details-before');
      const placed = await resultLayout(page);
      const logText = await probeLog(page).textContent(), logPlace = await logLayout(page);
      expect(logText).toBe(LOG);
      // Closed by default: one 来源 button in the source row, in view, and no details.
      await expect(sourceToggle(page)).toHaveAttribute('aria-expanded', 'false');
      await expect(sourceToggle(page)).toBeInViewport();
      await expect(sourcePanel(page)).toHaveCount(0);
      const sourceBox = (await source(page).boundingBox())!, toggleBox = (await sourceToggle(page).boundingBox())!;
      expect(toggleBox.y).toBeGreaterThanOrEqual(sourceBox.y);
      expect(toggleBox.y + toggleBox.height).toBeLessThanOrEqual(sourceBox.y + sourceBox.height);
      expect(toggleBox.height).toBeGreaterThanOrEqual(24);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-details-closed.png`)});
      const sent = everything(page);
      // One click: the full node, project and task, the shown file and, apart from it, the chosen one.
      await r.click(sourceToggle(page), '来源');
      await expect(sourcePanel(page)).toBeVisible();
      await expect(sourcePanel(page)).toBeInViewport();
      await expect(sourceToggle(page)).toHaveAttribute('aria-expanded', 'true');
      await expect(sourceToggle(page)).toHaveAttribute('aria-controls', 'result-source-details');
      await expect(sourcePanel(page)).toHaveAttribute('id', 'result-source-details');
      await expect(sourceToggle(page)).toBeFocused();
      expect(await detailRows(page)).toEqual([['节点', `节点甲${node}`], ['项目', `项目一${ws}`], ['任务', `解析场验证${task}`],
        ['显示的文件', 'scalar-0.vti'], ['已选文件', 'scalar-1.vti尚未加载，点「加载视图」后显示']]);
      expect(await detailValues(page)).toEqual([node, ws, task, 'scalar-0.vti', 'scalar-1.vti']);
      expect(await sourcePanel(page).evaluate(el => [el.scrollWidth <= el.clientWidth, el.getBoundingClientRect().right <= innerWidth])).toEqual([true, true]);
      expect(await resultLayout(page)).toEqual(placed);
      expect(await canvasMarker(page)).toBe('same-canvas');
      await expect(page.locator('section.analysis h2, section.analysis h3')).toHaveCount(0);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-details-open.png`)});
      await r.click(sourcePanel(page).getByRole('button', {name: '收起', exact: true}), '收起');
      await expect(sourcePanel(page)).toHaveCount(0);
      await expect(sourceToggle(page)).toBeFocused();
      await expect(sourceToggle(page)).toHaveAttribute('aria-expanded', 'false');
      expect(await resultLayout(page)).toEqual(placed);
      expect((await viewerShot(page, 'details-closed')).equals(viewer)).toBe(true);
      expect(await state(page)).toEqual(before);
      // Keyboard: Enter opens with the focus kept on 来源, Tab reaches each ID and path, which then selects itself;
      // Escape closes from the toggle or from inside and gives the focus back to 来源; Space opens again.
      await page.keyboard.press('Enter');
      await expect(sourcePanel(page)).toBeVisible();
      await expect(sourceToggle(page)).toBeFocused();
      await page.keyboard.press('Tab');
      await expect(sourcePanel(page).locator('.source-value').first()).toBeFocused();
      expect(await selectedText(page)).toBe(node);
      for (let i = 0; i < 3; i++) await page.keyboard.press('Tab');
      await expect(sourcePanel(page).locator('.source-value', {hasText: 'scalar-0.vti'})).toBeFocused();
      expect(await selectedText(page)).toBe('scalar-0.vti');
      await page.keyboard.press('Tab');
      expect(await selectedText(page)).toBe('scalar-1.vti');
      await page.keyboard.press('Escape');
      await expect(sourcePanel(page)).toHaveCount(0);
      await expect(sourceToggle(page)).toBeFocused();
      await page.keyboard.press('Space');
      await expect(sourcePanel(page)).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(sourcePanel(page)).toHaveCount(0);
      await expect(sourceToggle(page)).toBeFocused();
      expect(await resultLayout(page)).toEqual(placed);
      // Tab past 收起 closes the details: the next control (the analysis mode) takes the focus, nothing under them.
      await page.keyboard.press('Enter');
      await expect(sourcePanel(page)).toBeVisible();
      for (let i = 0; i < 6; i++) await page.keyboard.press('Tab');
      await expect(sourcePanel(page).getByRole('button', {name: '收起', exact: true})).toBeFocused();
      expect(await selectedText(page)).toBe('');
      await page.keyboard.press('Tab');
      await expect(sourcePanel(page)).toHaveCount(0);
      await expect(page.getByRole('tab', {name: '结果文件'})).toBeFocused();
      await expect(sourceToggle(page)).toHaveAttribute('aria-expanded', 'false');
      // Shift+Tab back to 来源 and before it (the source line has no focusable part): the details close the same way.
      await page.keyboard.press('Shift+Tab');
      await expect(sourceToggle(page)).toBeFocused();
      await page.keyboard.press('Enter');
      await expect(sourcePanel(page)).toBeVisible();
      await page.keyboard.press('Shift+Tab');
      await expect(sourcePanel(page)).toHaveCount(0);
      expect(await resultLayout(page)).toEqual(placed);
      // The same at a scrolled 结果 (来源 still in view): opening, moving through, closing by Escape and by 收起
      // keep the scroll offset.
      const scrolled = await page.locator('section.analysis').evaluate(el => { el.scrollTop = 40; return el.scrollTop; });
      expect(scrolled).toBe(40);
      await expect(sourceToggle(page)).toBeInViewport({ratio: 1});
      const at = await resultLayout(page);
      const offset = () => page.locator('section.analysis').evaluate(el => el.scrollTop);
      await sourceToggle(page).focus();
      await page.keyboard.press('Enter');
      await expect(sourcePanel(page)).toBeVisible();
      await page.keyboard.press('Tab');
      expect(await offset()).toBe(40);
      await page.keyboard.press('Escape');
      await expect(sourceToggle(page)).toBeFocused();
      expect(await resultLayout(page)).toEqual(at);
      await page.keyboard.press('Enter');
      await sourcePanel(page).getByRole('button', {name: '收起', exact: true}).click();
      await expect(sourceToggle(page)).toBeFocused();
      expect(await resultLayout(page)).toEqual(at);
      await page.locator('section.analysis').evaluate((el, top) => { el.scrollTop = top; }, placed.scrollTop);
      expect(await resultLayout(page)).toEqual(placed);
      expect(await probeLog(page).textContent()).toBe(logText);
      expect(await logLayout(page)).toEqual(logPlace);
      if (isNarrow(page)) {
        await page.keyboard.press('Enter');
        await expect(sourcePanel(page)).toBeVisible();
        await historyToggle(page).focus();
        await page.keyboard.press('Enter');
        await expect(historyToggle(page)).toHaveAttribute('aria-expanded', 'true');
        await page.keyboard.press('Escape');
        await expect(historyToggle(page)).toBeFocused();
        await expect(sourcePanel(page)).toHaveCount(0);
      }
      await page.waitForTimeout(300);
      sent.stop();
      expect(sent.seen).toEqual([]);
      expect(await clipboardUses(page)).toEqual([]);
      expect(await state(page)).toEqual(before);
      // Open, then a press outside: the details close and the press reaches its target (工作台), then 结果 again.
      await r.click(sourceToggle(page), '来源');
      await r.click(nav(page).getByRole('button', {name: '工作台', exact: true}), '工作台');
      await expectActive(page, '工作台');
      await r.click(nav(page).getByRole('button', {name: '结果', exact: true}), '结果');
      await expect(sourcePanel(page)).toHaveCount(0);
      expect(await state(page)).toEqual(before);
      // Open, then a conversation from the history and back: the conversation opens, 结果 is as it was, details closed.
      await r.click(sourceToggle(page), '来源');
      if (isNarrow(page)) await r.click(historyToggle(page), '历史');
      await r.click(item(page, /相场参数讨论/), '相场参数讨论');
      await shows(page, ['A 的问题', 'A 的回答']);
      await r.click(nav(page).getByRole('button', {name: '结果', exact: true}), '结果');
      await expect(sourcePanel(page)).toHaveCount(0);
      const {draft: _, ...kept} = before;
      expect(await work(page)).toEqual(kept);
      expect(await probeLog(page).textContent()).toBe(logText);
      expect((await viewerShot(page, 'details-returned')).equals(viewer)).toBe(true);
      // 图谱 keeps its source at task level: its data sources are bound in the graph panel.
      await r.click(page.getByRole('tab', {name: '图谱'}), '图谱');
      await r.click(sourceToggle(page), '来源');
      expect(await detailRows(page)).toEqual([['节点', `节点甲${node}`], ['项目', `项目一${ws}`], ['任务', `解析场验证${task}`],
        ['数据源', '在下方图谱面板中绑定']]);
      await expect(sourcePanel(page)).not.toContainText('scalar');
      await page.keyboard.press('Escape');
      await expect(sourcePanel(page)).toHaveCount(0);
      expect(hub.calls).toEqual([`history ${A}`]);
      expect(hub.builds).toHaveLength(1);
      expect(hub.probes).toHaveLength(0);
      expect(hub.replies).toBe(0);
      expect(await clipboardUses(page)).toEqual([]);
      r.save();
      writeFileSync(test.info().outputPath('details-requests.json'), JSON.stringify({openClose: sent.seen, conversationCalls: hub.calls, builds: hub.builds}, null, 2));
      expect(errors).toEqual([]);
    });

    test('来源 shows long and pathological names and paths exactly, as plain text, inside the page', async ({page}) => {
      const hub = new Hub();
      const shownPath = 'runs/' + 'step-0000/'.repeat(80) + 'scalar-0.vti';
      const chosenPath = 'x'.repeat(360) + '\\..\\ · ，<em>原始结果</em>&amp;.vti';
      const nodeName = '节点'.repeat(80), wsName = '项目 · 一，二 · 三'.repeat(20);
      const taskBase = '解析 · 场，'.repeat(24) + '<em>原始结果</em>';
      const taskName = taskBase + '\u202E原始\u200B';
      hub.artifactPaths = [shownPath, chosenPath];
      hub.device = {...device, name: nodeName, snapshot: {...device.snapshot, tasks: [{...row, name: taskName}], workspaces: [{id: ws, name: wsName}]}};
      const errors = await start(page, hub);
      await go(page, '任务');
      await page.getByLabel('执行节点').selectOption(node);
      await project(page).selectOption(ws);
      await taskRow(page, '解析').click();
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      await go(page, '结果');
      const fileList = page.getByLabel('结果文件');
      await fileList.selectOption(shownPath);
      await page.getByRole('button', {name: '加载视图'}).click();
      await expect(source(page)).toContainText(`显示 ${shownPath}`);
      await fileList.selectOption(chosenPath);
      await expect(source(page)).toContainText(pending(chosenPath));
      await expect(source(page)).toHaveAttribute('title', `节点 ${node}\n项目 ${ws}\n任务 ${task}\n文件 ${shownPath}`);
      await expect(footer(page)).toContainText('就绪');
      const placed = await resultLayout(page);
      await sourceToggle(page).click();
      await expect(sourcePanel(page)).toBeVisible();
      // Exact text, nothing interpreted as markup, each value in its own row whatever separators it contains.
      const capturedValues = await detailValues(page);
      expect(capturedValues).toEqual([node, ws, task, shownPath, chosenPath]);
      expect(await sourcePanel(page).locator('.source-name').allTextContents()).toEqual([nodeName, wsName, taskName]);
      expect(await sourcePanel(page).locator('.source-escaped').allTextContents()).toEqual(
        [`含不可见字符：${taskBase}\\u{202E}原始\\u{200B}`]);
      expect(await page.locator('section.analysis .source-details em').count()).toBe(0);
      // Wrapped within the page and scrolled inside the details: no sideways overflow, and 结果 has not moved.
      const fit = await sourcePanel(page).evaluate(el => ({wide: el.scrollWidth <= el.clientWidth, right: el.getBoundingClientRect().right <= innerWidth,
        bottom: el.getBoundingClientRect().bottom <= innerHeight, scrolls: el.scrollHeight > el.clientHeight}));
      expect(fit).toMatchObject({wide: true, right: true, bottom: true});
      expect(await page.locator('section.analysis').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
      expect(await resultLayout(page)).toEqual(placed);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-details-long.png`)});
      // A click or tap selects a whole path; the keyboard focus on the last one selects it and brings it into view.
      const values = sourcePanel(page).locator('.source-value');
      await values.nth(3).click();
      expect(await selectedText(page)).toBe(shownPath);
      await values.nth(4).focus();
      expect(await selectedText(page)).toBe(chosenPath);
      await expect(values.nth(4)).toBeInViewport();
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-details-long-end.png`)});
      await page.keyboard.press('Escape');
      await expect(sourcePanel(page)).toHaveCount(0);
      await expect(sourceToggle(page)).toBeFocused();
      expect(await resultLayout(page)).toEqual(placed);
      writeFileSync(test.info().outputPath('details-long.json'), JSON.stringify({fit, values: capturedValues}, null, 2));
      expect(errors).toEqual([]);
    });
  });
}

test('the analysis mode switch keeps its height on a short wide page', async ({page}) => {
  await page.setViewportSize({width: 1440, height: 700});
  const hub = new Hub();
  await hub.install(page);
  await page.goto(ORIGIN + '/');
  await go(page, '结果');
  for (const name of ['结果文件', '图谱']) expect((await page.getByRole('tab', {name}).boundingBox())!.height).toBeGreaterThan(24);
  await page.getByRole('tab', {name: '图谱'}).click();
  await expect(page.getByRole('tab', {name: '图谱'})).toHaveAttribute('aria-selected', 'true');
});

// Conversation history in the common navigation: a left column beside the rail on a wide page, on demand from the
// strip on a narrow one. Choosing a conversation is read-only (history GET only); only 发送 writes.
const A = '1'.repeat(32), B = '2'.repeat(32), X = '3'.repeat(32);
function conversations(hub: Hub, {listMissing = false} = {}) {
  hub.rows = [{id: A, name: '相场参数讨论', created: 1794830500}, {id: B, name: '铁电回线分析', created: 1794830400},
    ...(listMissing ? [{id: X, name: '旧列表中的对话', created: 1794830300}] : [])];
  hub.saved.set(A, [say('a1', 'user', 'A 的问题'), say('a2', 'assistant', 'A 的回答')]);
  hub.saved.set(B, [say('b1', 'user', 'B 的问题')]);
}
// The history element itself, so its hidden and inert state can be read while it is closed on a narrow page.
const historyPanel = (page: Page) => page.locator('#conversation-history');
const historyToggle = (page: Page) => nav(page).getByRole('button', {name: '对话历史', exact: true});
const item = (page: Page, name: string | RegExp) => historyPanel(page).getByRole('button', {name, includeHidden: true});
const transcript = (page: Page) => page.locator('aside.chat .messages article p').allTextContents();
// Waits for the transcript to show; for a check that something did not change, read `transcript` after settling.
const shows = (page: Page, expected: string[]) => expect.poll(() => transcript(page)).toEqual(expected);
const draft = (page: Page) => page.getByLabel('对话内容');
const sendButton = (page: Page) => page.locator('aside.chat form').getByRole('button', {name: '发送', exact: true});
const resendButton = (page: Page) => page.locator('aside.chat .send-failure').getByRole('button', {name: '重新发送', exact: true});
const label = (page: Page) => page.locator('aside.chat .conversation-name');
const entries = (page: Page) => historyPanel(page).locator('.history-list li');
test('history distinguishes generic saved conversations with their first question', async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  const hub = new Hub();
  hub.rows = [
    {id: A, name: '新会话', created: clock, label: '比较 300 K 的极化结果'},
    {id: B, name: '材料复核', created: clock + 1, label: 'A preview must not override an explicit name'},
  ];
  hub.saved.set(A, [say('title-question', 'user', '比较 300 K 的极化结果')]);
  hub.saved.set(B, []);
  await hub.install(page);
  const requested = page.waitForRequest(request => new URL(request.url()).pathname === '/api/v1/sessions');
  await page.goto(ORIGIN + '/');
  expect(new URL((await requested).url()).searchParams.get('include_labels')).toBe('true');
  await expect(item(page, /材料复核/)).toBeVisible();
  await expect(item(page, /A preview must not/)).toHaveCount(0);
  await item(page, /比较 300 K 的极化结果/).click();
  await expect(label(page)).toContainText('比较 300 K 的极化结果');
  await shows(page, ['比较 300 K 的极化结果']);
  expect(hub.calls.filter(call => call.startsWith('POST sessions/'))).toEqual([]);
});
const box = async (page: Page, selector: string) => (await page.locator(selector).boundingBox())!;
// Up to 1050 px (the app's compact width) the history is opened from the navigation on demand.
const isNarrow = (page: Page) => page.viewportSize()!.width <= 1050;
// One explicit action in the history; on a narrow page the history is opened first.
async function choose(page: Page, name: string | RegExp) {
  if (isNarrow(page)) await historyToggle(page).click();
  await item(page, name).click();
}
// Except for the conversation draft: what 任务 and 结果 hold, which a conversation change must leave alone.
async function work(page: Page) {
  const {draft: _, ...rest} = await state(page);
  return rest;
}
// Console resource errors for the statuses a test provokes on purpose (404 history, failed send, lost connection).
const unexpected = (errors: string[], ...statuses: (number | string)[]) =>
  errors.filter(e => !statuses.some(status => e.includes(typeof status === 'number' ? `status of ${status}` : status)));

for (const viewport of viewports) {
  test.describe(`${viewport.name} conversations`, () => {
    test.use({viewport: {width: viewport.width, height: viewport.height}});

    test('history sits in the navigation without moving the active section', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const errors = await setup(page, hub);
      const before = await state(page);
      for (const section of ['结果', '工作台'] as const) {
        await go(page, section);
        const surface = surfaces[section];
        const held = await box(page, surface);
        if (viewport.name === 'wide') {
          // Rail, readable history column, then the active section.
          await expect(page.getByRole('region', {name: '对话历史'})).toBeVisible();
          expect(await historyPanel(page).evaluate(el => (el as HTMLElement).inert)).toBe(false);
          await expect(historyToggle(page)).toHaveCount(0);
          const rail = (await nav(page).boundingBox())!, column = (await historyPanel(page).boundingBox())!;
          expect([rail.x, rail.width, column.x, column.width]).toEqual([0, 76, 76, 248]);
          expect(held.x).toBeGreaterThanOrEqual(column.x + column.width);
          for (const name of ['相场参数讨论', '铁电回线分析']) {
            await expect(item(page, new RegExp(name))).toBeInViewport({ratio: 1});
            expect(await item(page, new RegExp(name)).evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
          }
          await page.screenshot({path: test.info().outputPath(`wide-history-${section}.png`)});
        } else {
          await expect(historyPanel(page)).toBeHidden();
          expect(await historyPanel(page).evaluate(el => (el as HTMLElement).inert)).toBe(true);
          await historyToggle(page).click();
          await expect(historyToggle(page)).toHaveAttribute('aria-expanded', 'true');
          await expect(page.getByRole('region', {name: '对话历史'})).toBeVisible();
          await expect(historyPanel(page)).toBeInViewport({ratio: 1});
          await expect(item(page, /新对话.*未保存/)).toBeFocused();
          // The history covers the section on demand; the section keeps its box and stays the active one, but
          // takes no input until the history closes.
          expect(await box(page, surface)).toEqual(held);
          await expectActive(page, section, {covered: true});
          await page.screenshot({path: test.info().outputPath(`narrow-history-open-${section}.png`)});
          await page.keyboard.press('Escape');
          await expect(historyPanel(page)).toBeHidden();
          await expect(historyToggle(page)).toBeFocused();
          await expect(historyToggle(page)).toHaveAttribute('aria-expanded', 'false');
          await expectActive(page, section);
          expect(await box(page, surface)).toEqual(held);
          await page.screenshot({path: test.info().outputPath(`narrow-history-closed-${section}.png`)});
        }
      }
      expect(await state(page)).toEqual(before);
      expect(hub.calls).toEqual([]);
      expect(errors).toEqual([]);
    });

    test('a saved conversation opens 工作台 in one action; 新对话 stays local until 发送', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const errors = await setup(page, hub);
      const before = await work(page);
      const sent = posts(page);
      await choose(page, /相场参数讨论/);
      await expectActive(page, '工作台');
      await shows(page, ['A 的问题', 'A 的回答']);
      await expect(item(page, /相场参数讨论/)).toHaveAttribute('aria-current', 'true');
      await expect(page.locator('aside.chat .conversation-name')).toHaveText(`相场参数讨论 · ${A.slice(0, 6)}`);
      await expect(draft(page)).toHaveValue('');
      expect(await page.evaluate(() => sessionStorage.getItem('stk-session'))).toBe(A);
      if (viewport.name === 'narrow') await expect(historyPanel(page)).toBeHidden();
      // 新对话 is a local conversation with no request at all; the earlier unsent draft keeps its own entry.
      if (isNarrow(page)) await historyToggle(page).click();
      await historyPanel(page).getByRole('button', {name: '新对话', exact: true}).click();
      await expectActive(page, '工作台');
      await expect(draft(page)).toBeFocused();
      await expect(page.locator('aside.chat .chat-intro')).toContainText('从一个科学问题开始');
      await expect(page.locator('aside.chat .conversation-name')).toHaveText('新对话 · 未保存');
      expect(await page.evaluate(() => sessionStorage.getItem('stk-session'))).toBeNull();
      await choose(page, /新对话.*有草稿/);
      await expect(draft(page)).toHaveValue('未发送的草稿：分析 phi 场');
      await page.waitForTimeout(300);
      sent.stop();
      expect(sent.seen).toEqual([]);
      expect(hub.calls).toEqual([`history ${A}`]);
      expect(hub.saved.size).toBe(2);
      expect(await work(page)).toEqual(before);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-conversation-local-draft.png`)});
      expect(errors).toEqual([]);
    });

    test('delayed reads and a late send stay with their own conversation', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const errors = await setup(page, hub, {scene: false});
      const settled = async () => { await expect(footer(page)).toContainText('就绪'); await page.waitForTimeout(300); };
      // A's read is held while the user moves on to B; A's late answer does not replace B.
      let release = hub.holdNext(`history ${A}`);
      await choose(page, /相场参数讨论/);
      await expect(page.locator('aside.chat .messages')).toContainText('正在读取对话');
      await expect.poll(() => hub.reached.has(`history ${A}`)).toBe(true);
      await choose(page, /铁电回线分析/);
      await shows(page, ['B 的问题']);
      release();
      await settled();
      expect(await transcript(page)).toEqual(['B 的问题']);
      await expect(item(page, /铁电回线分析/)).toHaveAttribute('aria-current', 'true');
      // A send from A answers after the user moved to B: B is unchanged, and A keeps the answer.
      await choose(page, /相场参数讨论/);
      await shows(page, ['A 的问题', 'A 的回答']);
      await draft(page).fill('A 追问');
      release = hub.holdNext(`send ${A}`);
      await sendButton(page).click();
      await expect(draft(page)).toHaveValue('');
      await expect(page.locator('aside.chat .pending')).toContainText('A 追问');
      await expect.poll(() => hub.reached.has(`send ${A}`)).toBe(true);
      await choose(page, /铁电回线分析/);
      await shows(page, ['B 的问题']);
      release();
      await settled();
      expect(await transcript(page)).toEqual(['B 的问题']);
      release = hub.holdNext(`history ${A}`);
      await choose(page, /相场参数讨论/);
      await shows(page, ['A 的问题', 'A 的回答', 'A 追问', '回复：A 追问']); // before the read answers
      release();
      await settled();
      expect(await transcript(page)).toEqual(['A 的问题', 'A 的回答', 'A 追问', '回复：A 追问']);
      // A read that started before a newer send answers after it: the older transcript is not shown again.
      release = hub.holdNext(`history ${A}`);
      await choose(page, /相场参数讨论/);
      await expect.poll(() => hub.reached.has(`history ${A}`)).toBe(true);
      await draft(page).fill('A 再问');
      await sendButton(page).click();
      await expect(page.locator('aside.chat .messages')).toContainText('回复：A 再问');
      release();
      await settled();
      expect(await transcript(page)).toEqual(['A 的问题', 'A 的回答', 'A 追问', '回复：A 追问', 'A 再问', '回复：A 再问']);
      expect(hub.calls.filter(call => call.startsWith('send'))).toEqual([`send ${A}`, `send ${A}`]);
      expect(hub.calls.filter(call => call.startsWith('legacy'))).toEqual([]);
      expect(errors).toEqual([]);
    });

    test('a stale read of the same conversation never replaces a newer one', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const errors = await setup(page, hub, {scene: false});
      const later = (n: number) => say(`a${n}`, 'assistant', `另一设备 ${n}`);
      // A, B, then A again: the first A read answers last with what A held before.
      let release = hub.holdNext(`history ${A}`);
      await choose(page, /相场参数讨论/);
      await expect.poll(() => hub.reached.has(`history ${A}`)).toBe(true);
      await choose(page, /铁电回线分析/);
      hub.saved.get(A)!.push(later(3));
      await choose(page, /相场参数讨论/);
      await expect(page.locator('aside.chat .messages')).toContainText('另一设备 3');
      release();
      await page.waitForTimeout(300);
      expect(await transcript(page)).toEqual(['A 的问题', 'A 的回答', '另一设备 3']);
      // Choosing A again while its read is held: the newer read wins whatever order they answer in.
      hub.reached.clear();
      release = hub.holdNext(`history ${A}`);
      await choose(page, /相场参数讨论/);
      await expect.poll(() => hub.reached.has(`history ${A}`)).toBe(true);
      hub.saved.get(A)!.push(later(4));
      await choose(page, /相场参数讨论/);
      await expect(page.locator('aside.chat .messages')).toContainText('另一设备 4');
      release();
      await page.waitForTimeout(300);
      expect(await transcript(page)).toEqual(['A 的问题', 'A 的回答', '另一设备 3', '另一设备 4']);
      expect(hub.calls).toEqual([`history ${A}`, `history ${B}`, `history ${A}`, `history ${A}`, `history ${A}`]);
      expect(errors).toEqual([]);
    });

    test('a conversation the hub no longer has is never created', async ({page}) => {
      const hub = new Hub();
      conversations(hub, {listMissing: true});
      const errors = await setup(page, hub, {scene: false});
      const sent = posts(page), send = sendButton(page);
      // A listed row is not enough to send while its read is pending; its late 404 leaves B as it is.
      const release = hub.holdNext(`history ${X}`);
      await choose(page, /旧列表中的对话/);
      await expect.poll(() => hub.reached.has(`history ${X}`)).toBe(true);
      await draft(page).fill('不会被发送');
      await expect(send).toBeDisabled();
      await choose(page, /铁电回线分析/);
      await shows(page, ['B 的问题']);
      release();
      await page.waitForTimeout(300);
      expect(await transcript(page)).toEqual(['B 的问题']);
      await expect(page.locator('aside.chat .conversation-name')).toHaveText(`铁电回线分析 · ${B.slice(0, 6)}`);
      await expect(page.locator('aside.chat .chat-intro')).toHaveCount(0);
      // Chosen again, the read answers 404: the conversation is reported missing and keeps its unsent draft.
      await choose(page, /旧列表中的对话/);
      await expectActive(page, '工作台');
      await expect(page.locator('aside.chat .chat-intro')).toContainText('这个对话已不存在');
      await expect(page.locator('aside.chat .conversation-name')).toHaveText(`已不存在 · ${X.slice(0, 6)}`);
      await expect(draft(page)).toHaveValue('不会被发送');
      await expect(send).toBeDisabled();
      await page.getByLabel('对话内容').press('Control+Enter');
      // The history keeps the missing conversation while it holds the unsent draft, so the text stays reachable.
      if (isNarrow(page)) await historyToggle(page).click();
      await expect(item(page, /旧列表中的对话.*已不存在.*有草稿/)).toHaveCount(1);
      if (isNarrow(page)) await page.keyboard.press('Escape');
      await choose(page, /铁电回线分析/);
      await shows(page, ['B 的问题']);
      await choose(page, /旧列表中的对话.*已不存在.*有草稿/);
      await expect(draft(page)).toHaveValue('不会被发送');
      await expect(page.locator('aside.chat .chat-intro')).toContainText('这个对话已不存在');
      await expect(send).toBeDisabled();
      await page.waitForTimeout(300);
      sent.stop();
      expect(sent.seen).toEqual([]);
      expect(hub.calls).toEqual([`history ${X}`, `history ${B}`, `history ${X}`, `history ${B}`, `history ${X}`]);
      expect(hub.saved.has(X)).toBe(false);
      expect(await page.evaluate(() => sessionStorage.getItem('stk-session'))).toBeNull();
      expect(unexpected(errors, 404)).toEqual([]);
    });

    for (const stored of ['missing', 'saved'] as const) {
      test(`a stored ${stored} conversation is ${stored === 'saved' ? 'restored from its history' : 'dropped for a local draft'}`, async ({page}) => {
        const hub = new Hub();
        conversations(hub);
        const errors: string[] = [];
        page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
        const id = stored === 'saved' ? B : X;
        await page.addInitScript(choice => sessionStorage.setItem('stk-session', choice), id);
        await hub.install(page);
        await page.goto(ORIGIN + '/');
        await expectActive(page, '工作台');
        if (stored === 'saved') {
          await expect.poll(() => transcript(page)).toEqual(['B 的问题']);
          await expect(page.locator('aside.chat .conversation-name')).toHaveText(`铁电回线分析 · ${B.slice(0, 6)}`);
        } else {
          await expect(page.locator('aside.chat .conversation-name')).toHaveText('新对话 · 未保存');
          await expect(page.locator('aside.chat .chat-intro')).toContainText('从一个科学问题开始');
          await expect.poll(() => page.evaluate(() => sessionStorage.getItem('stk-session'))).toBeNull();
        }
        await page.waitForTimeout(300);
        expect(hub.calls).toEqual([`history ${id}`]);
        expect(hub.saved.has(X)).toBe(false);
        expect(unexpected(errors, 404)).toEqual([]);
      });
    }

    test('only 发送 writes; a failed send keeps the draft and never overwrites newer text', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const errors = await setup(page, hub, {scene: false});
      await go(page, '工作台');
      const send = sendButton(page), failure = page.locator('aside.chat .send-failure');
      const sends = () => hub.calls.filter(call => call.startsWith('send'));
      hub.sendFail = 'before';
      // The user types again while the failing send is held: the newer text is kept.
      let release = hub.holdNext('send');
      await send.click();
      await expect(draft(page)).toHaveValue('');
      await expect.poll(() => hub.reached.has('send')).toBe(true);
      await draft(page).fill('更新的输入');
      release();
      await expect(failure).toContainText('草稿已保留');
      await expect(draft(page)).toHaveValue('更新的输入');
      await expect(failure.locator('.failed-text')).toHaveText('未发送：未发送的草稿：分析 phi 场');
      // A different draft cannot replace an ambiguous failed send; the explicit retry still works.
      await expect(send).toBeDisabled();
      await resendButton(page).click();
      await expect(failure).toContainText('模型暂不可用');
      await expect(draft(page)).toHaveValue('更新的输入');
      await expect(failure.locator('.failed-text')).toHaveText('未发送：未发送的草稿：分析 phi 场');
      await page.waitForTimeout(600);
      const local = hub.calls[0].slice('send '.length);
      expect(hub.calls).toEqual([`send ${local}`, `send ${local}`]);
      // A failure answered after the user moved to A stays with the local conversation.
      release = hub.holdNext('send');
      await resendButton(page).click();
      await expect.poll(() => hub.reached.has('send')).toBe(true);
      await choose(page, /相场参数讨论/);
      await shows(page, ['A 的问题', 'A 的回答']);
      release();
      await expect(footer(page)).toContainText('就绪');
      await page.waitForTimeout(300);
      await expect(failure).toHaveCount(0);
      await expect(draft(page)).toHaveValue('');
      expect(await transcript(page)).toEqual(['A 的问题', 'A 的回答']);
      await choose(page, /新对话.*有草稿/);
      await expect(draft(page)).toHaveValue('更新的输入');
      await expect(failure).toContainText('模型暂不可用');
      expect(sends()).toEqual([`send ${local}`, `send ${local}`, `send ${local}`]);
      expect(hub.saved.has(local)).toBe(false);
      await expect(page.locator('aside.chat .conversation-name')).toHaveText('新对话 · 未保存');
      // Retrying the original message saves the local conversation and keeps the other draft.
      hub.sendFail = false;
      await resendButton(page).click();
      await shows(page, ['未发送的草稿：分析 phi 场', '回复：未发送的草稿：分析 phi 场']);
      await expect(draft(page)).toHaveValue('更新的输入');
      await send.click();
      await shows(page, ['未发送的草稿：分析 phi 场', '回复：未发送的草稿：分析 phi 场', '更新的输入', '回复：更新的输入']);
      await expect(failure).toHaveCount(0);
      await expect(page.locator('aside.chat .conversation-name')).toHaveText(`新会话 · ${local.slice(0, 6)}`);
      expect(await page.evaluate(() => sessionStorage.getItem('stk-session'))).toBe(local);
      if (isNarrow(page)) await historyToggle(page).click();
      await expect(item(page, new RegExp(local.slice(0, 6)))).toHaveAttribute('aria-current', 'true');
      await expect(item(page, /新对话.*未保存/)).toHaveCount(0);
      expect(sends()).toEqual(Array(5).fill(`send ${local}`));
      expect(hub.messages.slice(0, 4).map(m => m.id)).toEqual(Array(4).fill(hub.messages[0].id));
      expect(hub.messages[4].id).not.toBe(hub.messages[0].id);
      // Coming back to the local conversation after its failed sends reads what the Hub recorded of it: nothing.
      expect(hub.calls.filter(call => !call.startsWith('send'))).toEqual([`history ${A}`, `history ${local}`]);
      expect(unexpected(errors, 502, 404)).toEqual([]);
    });

    test('each conversation keeps its draft through the Tasks shortcuts and 结果', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const errors = await setup(page, hub);
      const before = await work(page);
      // 任务 and 结果 are left scrolled to the bottom; choosing conversations keeps both offsets.
      const scroll = () => page.evaluate(() => ['aside.tasks', 'section.analysis'].map(s => Math.round(document.querySelector(s)!.scrollTop)));
      await page.evaluate(() => { for (const s of ['aside.tasks', 'section.analysis']) { const el = document.querySelector(s)!; el.scrollTop = el.scrollHeight; } });
      const offsets = await scroll();
      if (viewport.name === 'narrow') expect(Math.min(...offsets)).toBeGreaterThan(0);
      await choose(page, /相场参数讨论/);
      await draft(page).fill('A 的草稿');
      await choose(page, /铁电回线分析/);
      await expect(draft(page)).toHaveValue('');
      await draft(page).fill('B 的草稿');
      expect(await scroll()).toEqual(offsets);
      await go(page, '任务');
      await shortcut(page, '结果').click();
      await expectActive(page, '结果');
      await go(page, '任务');
      await shortcut(page, '读取日志').click();
      await expectActive(page, '结果');
      await expect(page.locator('section.analysis details.logs pre')).toHaveText(LOG);
      await go(page, '工作台');
      await expect(draft(page)).toHaveValue('B 的草稿');
      await shows(page, ['B 的问题']);
      await choose(page, /相场参数讨论.*有草稿/);
      await expect(draft(page)).toHaveValue('A 的草稿');
      await choose(page, /新对话.*有草稿/);
      await expect(draft(page)).toHaveValue('未发送的草稿：分析 phi 场');
      await go(page, '任务');
      await expect(footer(page)).toContainText('就绪');
      expect(await work(page)).toEqual(before);
      // The same 图谱 panel stays mounted while conversations change.
      await go(page, '结果');
      await page.getByRole('tab', {name: '图谱'}).click();
      const graph = page.locator('section.analysis .graph-panel');
      await graph.evaluate(el => { (el as any).__marker = 'same-graph'; });
      await choose(page, /铁电回线分析/);
      await expect(draft(page)).toHaveValue('B 的草稿');
      await go(page, '结果');
      expect(await graph.evaluate(el => (el as any).__marker ?? null)).toBe('same-graph');
      expect(hub.calls).toEqual([`history ${A}`, `history ${B}`, `history ${A}`, `history ${B}`]);
      expect(errors).toEqual([]);
    });

    // 1. A stored or listed ID is shown at once, but 发送 waits for its own read-only history.
    test('a stored conversation sends only after its own history; a held definitive 404 never creates it', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const errors: string[] = [];
      page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
      await page.addInitScript(choice => sessionStorage.setItem('stk-session', choice), X);
      const release = hub.holdNext(`history ${X}`);
      await hub.install(page);
      await page.goto(ORIGIN + '/');
      await expect.poll(() => hub.reached.has(`history ${X}`)).toBe(true);
      await expect(label(page)).toHaveText(`正在确认 · ${X.slice(0, 6)}`);
      await expect(item(page, /未确认的对话.*正在确认/)).toHaveAttribute('aria-current', 'true');
      await draft(page).fill('给旧对话的草稿');
      await expect(sendButton(page)).toBeDisabled();
      // Neither a disabled click nor a direct form submit sends while the read is held.
      await page.locator('aside.chat form').evaluate(form => (form as HTMLFormElement).requestSubmit());
      release();
      // The Hub's own 404: the stored choice is dropped for a new local conversation that takes the draft along.
      await expect(label(page)).toHaveText('新对话 · 未保存');
      await expect(draft(page)).toHaveValue('给旧对话的草稿');
      await expect(page.locator('aside.chat .chat-intro')).toContainText('从一个科学问题开始');
      await expect(item(page, /未确认的对话|已不存在/)).toHaveCount(0);
      expect(await page.evaluate(() => sessionStorage.getItem('stk-session'))).toBeNull();
      expect(hub.calls).toEqual([`history ${X}`]);
      await sendButton(page).click();
      await shows(page, ['给旧对话的草稿', '回复：给旧对话的草稿']);
      expect(hub.messages.map(m => m.session)).not.toContain(X);
      expect(hub.saved.has(X)).toBe(false);
      expect(hub.calls.filter(call => call.startsWith('legacy'))).toEqual([]);
      expect(unexpected(errors, 404)).toEqual([]);
    });

    test('a vanished conversation keeps its draft reachable and can move it to a new conversation', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const errors: string[] = [];
      page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
      await page.addInitScript(choice => sessionStorage.setItem('stk-session', choice), X);
      const release = hub.holdNext(`history ${X}`);
      await hub.install(page);
      await page.goto(ORIGIN + '/');
      await expect.poll(() => hub.reached.has(`history ${X}`)).toBe(true);
      await draft(page).fill('留给 X 的草稿');
      // Leaving X abandons its held read; X stays listed with its draft, still unconfirmed and not sendable.
      await choose(page, /铁电回线分析/);
      await shows(page, ['B 的问题']);
      release();
      await expect(item(page, /未确认的对话.*正在确认.*有草稿/)).toHaveCount(1);
      await choose(page, /未确认的对话/);
      await expect(page.locator('aside.chat .chat-intro')).toContainText('这个对话已不存在');
      await expect(label(page)).toHaveText(`已不存在 · ${X.slice(0, 6)}`);
      await expect(draft(page)).toHaveValue('留给 X 的草稿');
      await expect(sendButton(page)).toBeDisabled();
      await choose(page, /相场参数讨论/);
      await shows(page, ['A 的问题', 'A 的回答']);
      await expect(item(page, /已不存在的对话.*有草稿/)).toHaveCount(1);
      await choose(page, /已不存在的对话/);
      await expect(draft(page)).toHaveValue('留给 X 的草稿');
      await expect(page.getByRole('button', {name: '移到新对话', exact: true})).toBeVisible();
      await page.screenshot({path: test.info().outputPath(`${isNarrow(page) ? 'narrow' : 'wide'}-missing-draft.png`)});
      // An explicit move: the text goes to a new local conversation, which 发送 then creates under a new ID.
      await page.getByRole('button', {name: '移到新对话', exact: true}).click();
      await expect(label(page)).toHaveText('新对话 · 未保存');
      await expect(draft(page)).toHaveValue('留给 X 的草稿');
      await expect(draft(page)).toBeFocused();
      await expect(item(page, /已不存在/)).toHaveCount(0);
      await sendButton(page).click();
      await shows(page, ['留给 X 的草稿', '回复：留给 X 的草稿']);
      expect(hub.messages).toHaveLength(1);
      expect(hub.messages[0].session).not.toBe(X);
      expect(hub.calls.filter(call => !call.startsWith('send'))).toEqual([`history ${X}`, `history ${B}`, `history ${X}`, `history ${A}`, `history ${X}`]);
      expect(hub.saved.has(X)).toBe(false);
      expect(unexpected(errors, 404)).toEqual([]);
    });

    test('a conversation created here cannot be recreated after a definitive missing read', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const errors = await setup(page, hub, {scene: false});
      await go(page, '工作台');
      await sendButton(page).click();
      await expect(footer(page)).toContainText('就绪');
      const id = hub.messages[0].session, short = id.slice(0, 6);
      await expect(label(page)).toHaveText(`新会话 · ${short}`);
      await draft(page).fill('已保存对话的后续草稿');
      await choose(page, /铁电回线分析/);
      await shows(page, ['B 的问题']);
      hub.saved.delete(id); // The already-listed row is stale.
      await choose(page, new RegExp(short));
      await expect(label(page)).toHaveText(`已不存在 · ${short}`);
      await expect(draft(page)).toHaveValue('已保存对话的后续草稿');
      await expect(sendButton(page)).toBeDisabled();
      await page.locator('aside.chat form').dispatchEvent('submit', {cancelable: true});
      await expect(page.getByRole('button', {name: '移到新对话', exact: true})).toBeVisible();
      expect(hub.messages).toHaveLength(1);
      expect(hub.saved.has(id)).toBe(false);
      expect(unexpected(errors, 404)).toEqual([]);
    });

    test('only the Hub\'s own not-found marks a conversation missing; other 404s can be read again', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const errors: string[] = [];
      page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
      const failed = page.locator('aside.chat .messages', {hasText: '读取对话失败'});
      // A Hub without the read-only history answers FastAPI's plain 404 for a stored choice: kept, not sendable.
      hub.historyFault = 'route';
      await page.addInitScript(choice => sessionStorage.setItem('stk-session', choice), B);
      await hub.install(page);
      await page.goto(ORIGIN + '/');
      await expect(failed).toContainText('没有提供只读对话历史（Not Found）');
      await expect(page.locator('aside.chat .chat-intro')).toHaveCount(0);
      await expect(sendButton(page)).toBeDisabled();
      await draft(page).fill('B 的草稿');
      expect(await page.evaluate(() => sessionStorage.getItem('stk-session'))).toBe(B);
      hub.historyFault = null;
      await page.getByRole('button', {name: '重新读取', exact: true}).click();
      await shows(page, ['B 的问题']);
      await expect(label(page)).toHaveText(`铁电回线分析 · ${B.slice(0, 6)}`);
      await expect(sendButton(page)).toBeEnabled();
      await expect(draft(page)).toHaveValue('B 的草稿');
      // A proxy's 404 page for a listed conversation: a read failure with 重新读取, and A is not sendable yet.
      hub.historyFault = 'proxy';
      await choose(page, /相场参数讨论/);
      await expect(failed).toContainText('请求失败 (404)');
      await expect(label(page)).toHaveText(`相场参数讨论 · ${A.slice(0, 6)}`);
      await draft(page).fill('A 的草稿');
      await expect(sendButton(page)).toBeDisabled();
      hub.historyFault = null;
      await page.getByRole('button', {name: '重新读取', exact: true}).click();
      await shows(page, ['A 的问题', 'A 的回答']);
      await expect(sendButton(page)).toBeEnabled();
      await page.waitForTimeout(300);
      expect(hub.calls).toEqual([`history ${B}`, `history ${B}`, `history ${A}`, `history ${A}`]);
      expect(hub.saved.size).toBe(2);
      expect(unexpected(errors, 404)).toEqual([]);
    });

    test('a later history that finds a conversation clears its earlier not-found', async ({page}) => {
      const hub = new Hub();
      conversations(hub, {listMissing: true});
      const errors = await setup(page, hub, {scene: false});
      await choose(page, /旧列表中的对话/);
      await expect(label(page)).toHaveText(`已不存在 · ${X.slice(0, 6)}`);
      await draft(page).fill('等它回来');
      // The Hub has it again (a restored database, say): the next read of the same ID is the newer observation.
      hub.saved.set(X, [say('x1', 'user', 'X 的问题')]);
      await choose(page, /铁电回线分析/);
      await shows(page, ['B 的问题']);
      await choose(page, /旧列表中的对话.*有草稿/);
      await shows(page, ['X 的问题']);
      await expect(label(page)).toHaveText(`旧列表中的对话 · ${X.slice(0, 6)}`);
      await expect(page.locator('aside.chat .messages')).not.toContainText('已不存在');
      await expect(sendButton(page)).toBeEnabled();
      await sendButton(page).click();
      await shows(page, ['X 的问题', '等它回来', '回复：等它回来']);
      expect(hub.calls).toEqual([`history ${X}`, `history ${B}`, `history ${X}`, `send ${X}`]);
      expect(unexpected(errors, 404)).toEqual([]);
    });

    // 2. The Hub lists a new conversation as soon as its POST has recorded the user message.
    test('a new conversation the Hub lists before its reply appears once and keeps its draft', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const errors = await setup(page, hub, {scene: false});
      await go(page, '工作台');
      const release = hub.holdNext('recorded');
      await sendButton(page).click();
      await expect.poll(() => hub.reached.has('recorded')).toBe(true);
      const N = hub.messages[0].session, short = N.slice(0, 6);
      // sessions.changed refreshed the list while the POST is held: N is listed once, as the Hub names it.
      await expect(item(page, new RegExp(`${short}.*发送中`))).toHaveCount(1, {timeout: 10_000});
      await expect(item(page, /新对话.*未保存/)).toHaveCount(0);
      await expect(entries(page)).toHaveCount(3);
      await expect(label(page)).toHaveText(`新会话 · ${short}`);
      await expect(page.locator('aside.chat .pending')).toContainText('未发送的草稿：分析 phi 场');
      await draft(page).fill('N 的新草稿');
      // Away and back: N's read shows the recorded message once, with the newer draft.
      await choose(page, /相场参数讨论/);
      await shows(page, ['A 的问题', 'A 的回答']);
      await choose(page, new RegExp(short));
      await shows(page, ['未发送的草稿：分析 phi 场']);
      await expect(page.locator('aside.chat .pending')).toHaveCount(0);
      await expect(draft(page)).toHaveValue('N 的新草稿');
      release();
      await shows(page, ['未发送的草稿：分析 phi 场', '回复：未发送的草稿：分析 phi 场']);
      await expect(footer(page)).toContainText('就绪');
      await expect(draft(page)).toHaveValue('N 的新草稿');
      await expect(item(page, new RegExp(short))).toHaveCount(1);
      await expect(entries(page)).toHaveCount(3);
      expect(hub.replies).toBe(1);
      expect(hub.calls.filter(call => call.startsWith('send'))).toEqual([`send ${N}`]);
      expect(errors).toEqual([]);
    });

    test('a send acknowledgement outranks a not-found read of the new conversation, in either order', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const errors = await setup(page, hub, {scene: false});
      await go(page, '工作台');
      const intro = page.locator('aside.chat .chat-intro');
      // The POST is held before the Hub sees it and then fails; meanwhile N's read finds nothing.
      hub.sendFail = 'before';
      let release = hub.holdNext('send');
      await sendButton(page).click();
      await expect.poll(() => hub.reached.has('send')).toBe(true);
      const N = hub.messages[0].session;
      await choose(page, /铁电回线分析/);
      await shows(page, ['B 的问题']);
      await choose(page, /新对话.*发送中/);
      await expect.poll(() => hub.calls).toContain(`history ${N}`);
      await expect(page.locator('aside.chat .pending')).toContainText('未发送的草稿：分析 phi 场');
      await page.waitForTimeout(300);
      // Not on the Hub (yet) is not "no longer exists" for this page's own conversation.
      await expect(page.locator('aside.chat .messages')).not.toContainText('已不存在');
      await expect(label(page)).toHaveText('新对话 · 未保存');
      release();
      await expect(page.locator('aside.chat .send-failure')).toContainText('模型暂不可用');
      await expect(draft(page)).toHaveValue('未发送的草稿：分析 phi 场');
      await expect(sendButton(page)).toBeEnabled();
      // The retry is the same message under the same ID, and its acknowledgement saves N.
      hub.sendFail = false;
      await resendButton(page).click();
      await shows(page, ['未发送的草稿：分析 phi 场', '回复：未发送的草稿：分析 phi 场']);
      await expect(label(page)).toHaveText(`新会话 · ${N.slice(0, 6)}`);
      await expect(draft(page)).toHaveValue('');
      // The other order: a new conversation's read that found nothing answers after its send's acknowledgement.
      if (isNarrow(page)) await historyToggle(page).click();
      await historyPanel(page).getByRole('button', {name: '新对话', exact: true}).click();
      await draft(page).fill('第二个对话');
      release = hub.holdNext('send');
      await sendButton(page).click();
      await expect.poll(() => hub.reached.has('send')).toBe(true);
      const M = hub.messages[2].session;
      expect(M).not.toBe(N);
      await choose(page, /铁电回线分析/);
      await shows(page, ['B 的问题']);
      const late = hub.holdNext(`history ${M}`);
      await choose(page, /新对话.*发送中/);
      await expect.poll(() => hub.reached.has(`history ${M}`)).toBe(true);
      release();
      await shows(page, ['第二个对话', '回复：第二个对话']);
      await expect(label(page)).toHaveText(`新会话 · ${M.slice(0, 6)}`);
      late();
      await expect(footer(page)).toContainText('就绪');
      await page.waitForTimeout(300);
      expect(await transcript(page)).toEqual(['第二个对话', '回复：第二个对话']);
      await expect(label(page)).toHaveText(`新会话 · ${M.slice(0, 6)}`);
      await expect(intro).toHaveCount(0);
      await expect(sendButton(page)).toBeDisabled(); // only for want of text
      await draft(page).fill('第二个对话的追问');
      await expect(sendButton(page)).toBeEnabled();
      await expect(item(page, new RegExp(M.slice(0, 6)))).toHaveCount(1);
      await expect(item(page, /已不存在/)).toHaveCount(0);
      expect(hub.messages.map(m => [m.session, m.id])).toEqual([
        [N, hub.messages[0].id], [N, hub.messages[0].id], [M, hub.messages[2].id]]);
      expect(unexpected(errors, 404, 502)).toEqual([]);
    });

    for (const order of ['history first', 'send first'] as const) {
      test(`a newer history merges with an older send response arriving ${order}`, async ({page}) => {
        const hub = new Hub();
        conversations(hub);
        const errors = await setup(page, hub, {scene: false});
        await choose(page, /相场参数讨论/);
        await shows(page, ['A 的问题', 'A 的回答']);
        await draft(page).fill('A 追问');
        // The POST reply snapshot was taken before the later message from another device.
        const releaseSend = hub.holdNext('replied');
        await sendButton(page).click();
        await expect.poll(() => hub.reached.has('replied')).toBe(true);
        hub.saved.get(A)!.push(say('a9', 'assistant', '另一设备 9'));
        await choose(page, /铁电回线分析/);
        await shows(page, ['B 的问题']);
        const releaseHistory = order === 'send first' ? hub.holdNext(`history ${A}`) : undefined;
        await choose(page, /相场参数讨论/);
        const newer = ['A 的问题', 'A 的回答', 'A 追问', '回复：A 追问', '另一设备 9'];
        if (releaseHistory) {
          await expect.poll(() => hub.reached.has(`history ${A}`)).toBe(true);
          releaseSend();
          await shows(page, newer.slice(0, -1));
          releaseHistory();
        } else {
          await shows(page, newer);
          releaseSend();
        }
        await expect(footer(page)).toContainText('就绪');
        await shows(page, newer);
        await expect(page.locator('aside.chat .pending')).toHaveCount(0);
        expect(hub.replies).toBe(1);
        expect(errors).toEqual([]);
      });
    }

    // 3. Retries reuse the message ID, which the Hub records once.
    test('a retry after a 502 or a lost answer reuses the message ID; other text is a new message', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const errors = await setup(page, hub, {scene: false});
      await go(page, '工作台');
      const failure = page.locator('aside.chat .send-failure');
      const first = '未发送的草稿：分析 phi 场';
      // The Hub records the session and the user message, then its model fails: 502.
      hub.sendFail = 'recorded';
      await sendButton(page).click();
      await expect(failure).toContainText('Model request failed; retry this message');
      await expect(failure).toContainText('发送未完成，草稿已保留');
      await expect(draft(page)).toHaveValue(first);
      const N = hub.messages[0].session, short = N.slice(0, 6);
      await expect(item(page, new RegExp(`${short}.*有草稿.*发送失败`))).toHaveCount(1, {timeout: 10_000});
      await expect(item(page, /新对话.*未保存/)).toHaveCount(0);
      // A newer, independently typed draft, then away and back: N's read shows the message was recorded.
      await draft(page).fill('第二条');
      await choose(page, /相场参数讨论/);
      await shows(page, ['A 的问题', 'A 的回答']);
      await choose(page, new RegExp(short));
      await shows(page, [first]);
      await expect(sendButton(page)).toBeDisabled();
      await expect(failure).toContainText('消息已记录，回复尚未确认');
      await expect(failure.locator('.failed-text')).toHaveCount(0);
      await expect(draft(page)).toHaveValue('第二条');
      await page.screenshot({path: test.info().outputPath(`${isNarrow(page) ? 'narrow' : 'wide'}-recorded-retry.png`)});
      await expect(resendButton(page)).toBeEnabled();
      await page.locator('aside.chat form').dispatchEvent('submit', {cancelable: true});
      expect(hub.messages).toHaveLength(1);
      // 重新发送 sends the failed message under its ID and leaves the newer draft alone.
      hub.sendFail = false;
      await resendButton(page).click();
      await shows(page, [first, `回复：${first}`]);
      await expect(failure).toHaveCount(0);
      await expect(draft(page)).toHaveValue('第二条');
      // The newer text is another message with a new ID. Its reply is committed, then the connection drops.
      hub.sendFail = 'lost';
      await sendButton(page).click();
      await expect(failure).toContainText('发送未完成');
      await expect(draft(page)).toHaveValue('第二条');
      // The same text again from the composer: the same ID, and the Hub answers with what it has, no new reply.
      hub.sendFail = false;
      await sendButton(page).click();
      await shows(page, [first, `回复：${first}`, '第二条', '回复：第二条']);
      await expect(failure).toHaveCount(0);
      await expect(draft(page)).toHaveValue('');
      const ids = hub.messages.map(m => m.id);
      expect(hub.messages.every(m => m.session === N)).toBe(true);
      expect(ids).toEqual([ids[0], ids[0], ids[2], ids[2]]);
      expect(ids[2]).not.toBe(ids[0]);
      expect(hub.saved.get(N)!.map(m => m.content)).toEqual([first, `回复：${first}`, '第二条', '回复：第二条']);
      expect(hub.replies).toBe(2);
      expect(unexpected(errors, 502, 'ERR_CONNECTION_RESET')).toEqual([]);
    });

    test('an oversized draft remains editable before any send', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const errors = await setup(page, hub, {scene: false});
      await go(page, '工作台');
      await draft(page).fill('🧪'.repeat(12_001));
      await expect(sendButton(page)).toBeDisabled();
      await page.locator('aside.chat form').dispatchEvent('submit', {cancelable: true});
      expect(hub.messages).toHaveLength(0);
      const valid = '🧪'.repeat(12_000);
      await draft(page).fill(valid);
      await expect(sendButton(page)).toBeEnabled();
      await sendButton(page).click();
      await expect(footer(page)).toContainText('就绪');
      expect(hub.messages).toHaveLength(1);
      expect(hub.messages[0].content).toBe(valid);
      expect(errors).toEqual([]);
    });

    test('one draft is sent once even when it is submitted twice at once', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const errors = await setup(page, hub, {scene: false});
      await choose(page, /相场参数讨论/);
      await shows(page, ['A 的问题', 'A 的回答']);
      await draft(page).fill('只发一次');
      // Two submits and a click in the same task, before React renders the disabled button.
      hub.sendFail = 'before';
      await page.locator('aside.chat form').evaluate(form => {
        const f = form as HTMLFormElement;
        f.requestSubmit(); f.requestSubmit(); f.querySelector('button')!.click();
      });
      await expect(page.locator('aside.chat .send-failure')).toContainText('模型暂不可用');
      expect(hub.messages).toHaveLength(1);
      // The same for 重新发送: one retry, under the first ID.
      hub.sendFail = false;
      await resendButton(page).evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click(); });
      await shows(page, ['A 的问题', 'A 的回答', '只发一次', '回复：只发一次']);
      await page.waitForTimeout(300);
      expect(hub.messages.map(m => m.id)).toEqual([hub.messages[0].id, hub.messages[0].id]);
      expect(hub.replies).toBe(1);
      expect(unexpected(errors, 502)).toEqual([]);
    });

    // 4. A late reply moves nothing in 任务 or 结果, and 工作台 shows it on return.
    test('a late reply leaves 任务 and 结果 in place and is there on return', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const errors = await setup(page, hub);
      const before = await work(page);
      await choose(page, /相场参数讨论/);
      await shows(page, ['A 的问题', 'A 的回答']);
      await draft(page).fill('A 追问');
      const release = hub.holdNext('send');
      await sendButton(page).click();
      await expect.poll(() => hub.reached.has('send')).toBe(true);
      await go(page, '结果');
      await page.locator('section.analysis').evaluate(el => { el.scrollTop = Math.round(el.scrollHeight / 3); });
      const viewer = await viewerShot(page, 'late-before');
      await page.locator('section.analysis').evaluate(el => { el.scrollTop = Math.round(el.scrollHeight / 3); });
      const held = await logLayout(page), surface = await box(page, 'section.analysis');
      release();
      await expect(footer(page)).toContainText('就绪');
      await page.waitForTimeout(300);
      expect(await logLayout(page)).toEqual(held);
      expect(await box(page, 'section.analysis')).toEqual(surface);
      await expectActive(page, '结果');
      if (isNarrow(page)) {
        // The history opens on the selected conversation; Escape returns to the toggle and 结果 is unchanged.
        await historyToggle(page).click();
        await expect(item(page, /相场参数讨论/)).toBeFocused();
        await expect(item(page, /相场参数讨论/)).toHaveAttribute('aria-current', 'true');
        await page.keyboard.press('Escape');
        await expect(historyToggle(page)).toBeFocused();
        expect(await logLayout(page)).toEqual(held);
      }
      await choose(page, /相场参数讨论/);
      await expectActive(page, '工作台');
      await shows(page, ['A 的问题', 'A 的回答', 'A 追问', '回复：A 追问']);
      await expect(draft(page)).toHaveValue('');
      await go(page, '结果');
      expect(await logLayout(page)).toEqual(held);
      expect((await viewerShot(page, 'late-after')).equals(viewer)).toBe(true);
      expect(await work(page)).toEqual(before);
      expect(errors).toEqual([]);
    });
  });
}

// The compact history overlay from the keyboard: it opens on the selected conversation, keeps input away from the
// section under it, closes with Escape from anywhere, and keeps the focus in the history across the compact width.
test('the compact history overlay is keyboard reachable, blocks the section under it and survives a width change', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  const hub = new Hub();
  conversations(hub);
  const errors = await setup(page, hub, {scene: false});
  await choose(page, /铁电回线分析/);
  await shows(page, ['B 的问题']);
  await go(page, '任务');
  await page.locator('aside.tasks').evaluate(el => { el.scrollTop = el.scrollHeight; });
  const inPanel = () => page.evaluate(() => !!document.activeElement?.closest('#conversation-history'));
  const inSurface = () => page.evaluate(() => !!document.activeElement?.closest('.surface'));
  await historyToggle(page).focus();
  await page.keyboard.press('Enter');
  await expect(historyToggle(page)).toHaveAttribute('aria-expanded', 'true');
  await expect(item(page, /铁电回线分析/)).toBeFocused();
  await expectActive(page, '任务', {covered: true});
  // Tab and Shift+Tab never reach the covered section.
  for (const key of [...Array(8).fill('Tab'), ...Array(8).fill('Shift+Tab')]) {
    await page.keyboard.press(key);
    expect(await inSurface()).toBe(false);
  }
  // A pointer on the covered section reaches the backdrop, which closes the history; nothing in 任务 is pressed.
  await page.locator('aside.tasks').evaluate(el => { (el as any).__clicks = 0; el.addEventListener('click', () => { (el as any).__clicks++; }); });
  const backdrop = await box(page, '.history-backdrop'), overlay = await box(page, '#conversation-history');
  const y = backdrop.y + backdrop.height - 8;
  expect(y).toBeGreaterThan(overlay.y + overlay.height);
  await page.mouse.click(backdrop.x + backdrop.width / 2, y);
  await expect(historyPanel(page)).toBeHidden();
  await expect(historyToggle(page)).toBeFocused();
  expect(await page.locator('aside.tasks').evaluate(el => (el as any).__clicks)).toBe(0);
  await expectActive(page, '任务');
  // Escape closes it from a navigation button as well, back to the toggle.
  await page.keyboard.press('Enter');
  await expect(item(page, /铁电回线分析/)).toBeFocused();
  await nav(page).getByRole('button', {name: '结果', exact: true}).focus();
  await page.keyboard.press('Escape');
  await expect(historyPanel(page)).toBeHidden();
  await expect(historyToggle(page)).toBeFocused();
  await expectActive(page, '任务');
  // Widening with the history open makes it the column, with the focus still on the same entry.
  await page.keyboard.press('Enter');
  await expect(item(page, /铁电回线分析/)).toBeFocused();
  await page.setViewportSize({width: 1440, height: 900});
  await expect(historyToggle(page)).toHaveCount(0);
  await expect(item(page, /铁电回线分析/)).toBeFocused();
  await expectActive(page, '任务');
  // Narrowing with the focus elsewhere: the history is closed, it does not come back open from before.
  await nav(page).getByRole('button', {name: '任务', exact: true}).focus();
  await page.setViewportSize({width: 390, height: 844});
  await expect(historyPanel(page)).toBeHidden();
  await expect(historyToggle(page)).toHaveAttribute('aria-expanded', 'false');
  await expectActive(page, '任务');
  // Widening with the focus on the toggle, which the wide page does not have, moves it into the column.
  await historyToggle(page).focus();
  await page.setViewportSize({width: 1440, height: 900});
  await expect(item(page, /铁电回线分析/)).toBeFocused();
  expect(await inPanel()).toBe(true);
  // Narrowing with the focus in the column opens the history as the overlay instead of hiding the focus.
  await page.setViewportSize({width: 390, height: 844});
  await expect(historyToggle(page)).toHaveAttribute('aria-expanded', 'true');
  await expect(item(page, /铁电回线分析/)).toBeFocused();
  await expectActive(page, '任务', {covered: true});
  await page.keyboard.press('Escape');
  await expect(historyToggle(page)).toBeFocused();
  await expectActive(page, '任务');
  // Choosing the selected conversation from the keyboard returns to 工作台 with it; 任务 keeps its scroll (taken
  // again here, since the width changes may have clamped it).
  const scroll = await page.locator('aside.tasks').evaluate(el => el.scrollTop);
  expect(scroll).toBeGreaterThan(0);
  await historyToggle(page).focus();
  await page.keyboard.press('Enter');
  await page.keyboard.press('Enter');
  await expectActive(page, '工作台');
  await shows(page, ['B 的问题']);
  await expect(page.locator('aside.chat .messages')).toBeFocused();
  await go(page, '任务');
  expect(await page.locator('aside.tasks').evaluate(el => el.scrollTop)).toBe(scroll);
  await page.screenshot({path: test.info().outputPath('narrow-overlay-keyboard.png')});
  expect(errors).toEqual([]);
});

test('the compact history scrolls a restored selection into view on keyboard open', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  const hub = new Hub();
  conversations(hub);
  for (let i = 0; i < 30; i++) {
    hub.rows.push({id: (0x100 + i).toString(16).padStart(32, '0'), name: `较新的对话 ${i}`, created: 1794830600 + i});
  }
  await page.addInitScript(id => sessionStorage.setItem('stk-session', id), B);
  const errors = await setup(page, hub, {scene: false});
  await expect(entries(page)).toHaveCount(32);
  await historyToggle(page).focus();
  await page.keyboard.press('Enter');
  const restored = item(page, /铁电回线分析/);
  await expect(restored).toBeFocused();
  const panel = (await historyPanel(page).boundingBox())!, row = (await restored.boundingBox())!;
  expect(row.y).toBeGreaterThanOrEqual(panel.y);
  expect(row.y + row.height).toBeLessThanOrEqual(panel.y + panel.height);
  expect(await historyPanel(page).evaluate(el => el.scrollTop)).toBeGreaterThan(0);
  expect(hub.messages).toHaveLength(0);
  expect(errors).toEqual([]);
});

// 结果 analysis modes: once shown, the file Viewer and the 图谱 panel both stay mounted; the mode not shown keeps its
// Viewer size and camera but takes no space, focus or pointer. 图谱 is first mounted (and reads its presets) when it
// is first opened, and only for the node it was opened under. A switch sends nothing; a changed task, project or node
// still drops what either mode shows.
const filePane = (page: Page) => page.locator('section.analysis .mode-pane.file-mode');
const graphPane = (page: Page) => page.locator('section.analysis .mode-pane.graph-mode');
const modeTab = (page: Page, name: '结果文件' | '图谱') => page.getByRole('tab', {name, exact: true});
// The vtk.js canvas of a mode's Viewer (a 图谱 payload also draws its legends on canvases of their own).
const vtkCanvas = (pane: Locator) => pane.locator('.viewport > canvas, .viewport > .vtk-host > canvas');
const marker = (pane: Locator) => vtkCanvas(pane).evaluate(el => (el as any).__marker ?? null);
const step = (page: Page) => graphPane(page).locator('.scrubber strong');
const node2 = 'e'.repeat(32);
// As freeze, with room for a loaded machine: pauseAt cannot go back to a time the page clock has already passed.
async function pause(page: Page) {
  await page.clock.pauseAt(await page.evaluate(() => Date.now()) + 1000);
  await page.waitForTimeout(300);
}
// Viewer pixels of one mode at a fixed scroll offset of 结果.
async function paneShot(page: Page, pane: Locator, name: string) {
  await page.locator('section.analysis').evaluate(el => { el.scrollTop = 0; });
  return pane.locator('.viewport').screenshot({path: test.info().outputPath(`${name}.png`)});
}
async function drag(page: Page, pane: Locator) {
  const box = (await pane.locator('.viewport').boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 - 60, box.y + box.height / 2 + 40, {steps: 8});
  await page.mouse.up();
}
// Every hub request except the periodic refresh (devices, actions list, sessions, policy, event stream) and the
// selected task's own 5 s task.get, which 任务 runs whatever the 结果 mode is.
function traffic(page: Page) {
  const seen: string[] = [];
  const listener = (request: Request) => {
    const url = new URL(request.url());
    if (!url.pathname.startsWith('/api/v1/')) return;
    const path = url.pathname.slice('/api/v1/'.length).replaceAll(node, '{node}');
    if (request.method() === 'GET' && /^(devices|actions|sessions|policy|events)$/.test(path)) return;
    if (path === 'nodes/{node}/read' && request.postDataJSON()?.kind === 'task.get') return;
    seen.push(request.method() === 'POST' ? `POST ${path} ${request.postDataJSON()?.kind ?? ''}`.trim() : `GET ${path.startsWith('blobs/') ? 'blobs/…' : path}`);
  };
  page.on('request', listener);
  return {seen, take: () => seen.splice(0), stop: () => page.off('request', listener)};
}
// The shown mode is visible and takes input; the other, when mounted, is hidden, inert and 0 px high, while its
// Viewer keeps a real size (no resize, so a scene accepted while hidden is framed as if shown).
async function expectMode(page: Page, mode: '结果文件' | '图谱') {
  const [shown, hidden] = mode === '结果文件' ? [filePane(page), graphPane(page)] : [graphPane(page), filePane(page)];
  await expect(modeTab(page, mode)).toHaveAttribute('aria-selected', 'true');
  await expect(shown).toBeVisible();
  expect(await shown.evaluate(el => (el as HTMLElement).inert)).toBe(false);
  if (!await hidden.count()) return;
  await expect(hidden).toBeHidden();
  expect(await hidden.evaluate(el => [(el as HTMLElement).inert, el.getBoundingClientRect().height])).toEqual([true, 0]);
  const size = await hidden.locator('.viewport').evaluate(el => [el.clientWidth, el.clientHeight]);
  expect(Math.min(...size)).toBeGreaterThan(100);
}
// From the shown mode tab, the keyboard never reaches the hidden mode.
async function tabWalk(page: Page, mode: '结果文件' | '图谱') {
  await modeTab(page, mode).focus();
  const hidden = mode === '结果文件' ? '.graph-mode' : '.file-mode';
  const reached: boolean[] = [];
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press('Tab');
    reached.push(await page.evaluate(selector => !!document.activeElement?.closest(`section.analysis ${selector}`), hidden));
  }
  return reached.some(Boolean);
}
async function computeGraph(page: Page, hub: Hub) {
  const count = hub.evaluations.length;
  await graphPane(page).getByRole('button', {name: '计算图谱'}).click();
  await expect(vtkCanvas(graphPane(page))).toHaveCount(1);
  await expect(step(page)).toHaveText('1000');
  expect(hub.evaluations).toHaveLength(count + 1);
}

for (const viewport of viewports) {
  test.describe(`${viewport.name} 结果 modes`, () => {
    test.use({viewport: {width: viewport.width, height: viewport.height}});

    test('结果文件 → 图谱 → 结果文件 and back keep each Viewer, camera, probe and source; switching sends nothing', async ({page}) => {
      const hub = new Hub();
      hub.presets = [PRESET];
      const sent = traffic(page);
      const errors = await setup(page, hub);
      // 图谱 is lazy: nothing of it is mounted or read before it is first opened.
      expect(sent.seen.filter(s => /graph/.test(s))).toEqual([]);
      await expect(graphPane(page)).toHaveCount(0);
      await go(page, '结果');
      await filePane(page).getByRole('button', {name: '查询原始值'}).click();
      await expect(probeLog(page)).toContainText('"values"');
      await expect(footer(page)).toContainText('就绪');
      const fileLog = await probeLog(page).textContent();
      const fileSource = [await source(page).textContent(), await source(page).getAttribute('title')];
      const fileShot = await paneShot(page, filePane(page), `${viewport.name}-file-before`);
      const fileLayout = {scroll: await page.locator('section.analysis').evaluate(el => el.scrollHeight), log: await logLayout(page)};
      sent.take();
      const r = route(page, `${viewport.name}-result-modes`);
      await r.click(modeTab(page, '图谱'), '图谱 (first opening)');
      await expectMode(page, '图谱');
      await expect(graphPane(page).getByLabel('图谱预设')).toHaveValue('field-view');
      await expect.poll(() => [...sent.seen]).toEqual(['GET graphs/presets']);
      expect(await marker(filePane(page))).toBe('same-canvas');
      // An explicit 计算图谱; then the graph camera is moved and a probe position typed.
      await computeGraph(page, hub);
      await page.waitForTimeout(300);
      await drag(page, graphPane(page));
      await graphPane(page).getByLabel('探针X').fill('1.5');
      await vtkCanvas(graphPane(page)).evaluate(el => { (el as any).__marker = 'same-graph'; });
      await expect(footer(page)).toContainText('就绪');
      await pause(page);
      const graphShot = await paneShot(page, graphPane(page), `${viewport.name}-graph-before`);
      const graphSource = [await source(page).textContent(), await source(page).getAttribute('title')];
      expect(graphSource[0]).toBe('节点甲 · 项目一 · 解析场验证，图谱数据源在下方绑定');
      expect(await tabWalk(page, '图谱')).toBe(false);
      sent.take();
      // 图谱 → 结果文件: the same canvas, camera pixels, probe, file, title, log and source; nothing moved.
      await r.click(modeTab(page, '结果文件'), '结果文件');
      await expectMode(page, '结果文件');
      expect(await marker(filePane(page))).toBe('same-canvas');
      expect((await paneShot(page, filePane(page), `${viewport.name}-file-returned`)).equals(fileShot)).toBe(true);
      expect(await filePane(page).getByLabel('探针X').inputValue()).toBe('0.25');
      expect(await page.getByLabel('结果文件').inputValue()).toBe('scalar-0.vti');
      expect(await title(page).textContent()).toBe('phi');
      expect(await probeLog(page).textContent()).toBe(fileLog);
      expect([await source(page).textContent(), await source(page).getAttribute('title')]).toEqual(fileSource);
      expect({scroll: await page.locator('section.analysis').evaluate(el => el.scrollHeight), log: await logLayout(page)}).toEqual(fileLayout);
      expect(await marker(graphPane(page))).toBe('same-graph');
      expect(await tabWalk(page, '结果文件')).toBe(false);
      // 结果文件 → 图谱: the same graph canvas, camera pixels, probe position and step.
      await r.click(modeTab(page, '图谱'), '图谱 (return)');
      await expectMode(page, '图谱');
      expect(await marker(graphPane(page))).toBe('same-graph');
      expect((await paneShot(page, graphPane(page), `${viewport.name}-graph-returned`)).equals(graphShot)).toBe(true);
      expect(await graphPane(page).getByLabel('探针X').inputValue()).toBe('1.5');
      await expect(step(page)).toHaveText('1000');
      expect([await source(page).textContent(), await source(page).getAttribute('title')]).toEqual(graphSource);
      // Section navigation keeps the mode and both Viewers too.
      await r.click(nav(page).getByRole('button', {name: '任务', exact: true}), '任务');
      await r.click(nav(page).getByRole('button', {name: '结果', exact: true}), '结果');
      await expectMode(page, '图谱');
      expect(await marker(graphPane(page))).toBe('same-graph');
      await r.click(modeTab(page, '结果文件'), '结果文件 (again)');
      expect(await marker(filePane(page))).toBe('same-canvas');
      expect((await paneShot(page, filePane(page), `${viewport.name}-file-again`)).equals(fileShot)).toBe(true);
      // Nothing follows later either (timers run on for a minute).
      await page.clock.runFor(60000);
      await page.waitForTimeout(300);
      expect(sent.seen).toEqual([]);
      expect(await page.getByLabel('对话内容').inputValue()).toBe('未发送的草稿：分析 phi 场');
      expect(await page.getByLabel('TaskSpec').inputValue()).toBe('{"argv":["python3","draft.py"],"outputs":[]}');
      expect([hub.builds.length, hub.probes.length, hub.evaluations.length, hub.replies]).toEqual([1, 1, 1, 0]);
      expect(r.record.clicks).toBe(6);
      r.save();
      sent.stop();
      expect(errors).toEqual([]);
    });

    test('来源 details stay exact for each mode across switches', async ({page}) => {
      const hub = new Hub();
      hub.presets = [PRESET];
      const errors = await setup(page, hub);
      await go(page, '结果');
      const rows = async () => { await sourceToggle(page).click(); const value = await detailRows(page); await page.keyboard.press('Escape');
        await expect(sourcePanel(page)).toHaveCount(0); return value; };
      const fileRows = [['节点', `节点甲${node}`], ['项目', `项目一${ws}`], ['任务', `解析场验证${task}`], ['显示的文件', 'scalar-0.vti']];
      const graphRows = [...fileRows.slice(0, 3), ['数据源', '在下方图谱面板中绑定']];
      expect(await rows()).toEqual(fileRows);
      await modeTab(page, '图谱').click();
      await computeGraph(page, hub);
      expect(await rows()).toEqual(graphRows);
      await modeTab(page, '结果文件').click();
      expect(await rows()).toEqual(fileRows);
      await modeTab(page, '图谱').click();
      expect(await rows()).toEqual(graphRows);
      expect(errors).toEqual([]);
    });

    test('work already sent completes in its hidden mode; a scrub not yet sent is dropped by the switch', async ({page}) => {
      const hub = new Hub();
      hub.presets = [PRESET];
      hub.later = true;
      const sent = traffic(page);
      const errors = await setup(page, hub);
      await go(page, '结果');
      // A held 加载视图 finishes while 图谱 is shown and is there, framed as if built in view, on return.
      await page.getByLabel('结果文件').selectOption('scalar-1.vti');
      hub.field = 'psi';
      const build = hub.hold('view.build');
      await filePane(page).getByRole('button', {name: '加载视图'}).click();
      await expect.poll(() => hub.reached.has('view.build')).toBe(true);
      await modeTab(page, '图谱').click();
      await expectMode(page, '图谱');
      build();
      await expect(footer(page)).toContainText('就绪');
      await expect(title(page)).toHaveText('图谱视图');
      await expect(filePane(page).locator('.legend')).toBeAttached();
      await modeTab(page, '结果文件').click();
      await expectMode(page, '结果文件');
      await expect(title(page)).toHaveText('psi');
      await expect(source(page)).toHaveText(shown('显示 scalar-1.vti'));
      await page.waitForTimeout(300);
      const hiddenBuilt = await paneShot(page, filePane(page), `${viewport.name}-built-hidden`);
      await filePane(page).getByRole('button', {name: '加载视图'}).click();
      await expect.poll(() => hub.builds.length).toBe(3);
      await expect(footer(page)).toContainText('就绪');
      await page.waitForTimeout(300);
      expect((await paneShot(page, filePane(page), `${viewport.name}-built-shown`)).equals(hiddenBuilt)).toBe(true);
      // A held 计算图谱 finishes while 结果文件 is shown and is there on return.
      await modeTab(page, '图谱').click();
      const evaluation = hub.hold('graph.evaluate');
      await graphPane(page).getByRole('button', {name: '计算图谱'}).click();
      await expect.poll(() => hub.reached.has('graph.evaluate')).toBe(true);
      await modeTab(page, '结果文件').click();
      sent.take();
      evaluation();
      await expect(vtkCanvas(graphPane(page))).toHaveCount(1);
      await expect(graphPane(page).locator('.status-line')).toHaveCount(0);
      await expectMode(page, '结果文件');
      await modeTab(page, '图谱').click();
      await expect(step(page)).toHaveText('1000');
      // Only the evaluation's own render data was read; then a scrub, debounced, is dropped by leaving 图谱.
      await pause(page);
      expect(sent.take().filter(s => s !== 'GET blobs/…')).toEqual([]);
      await graphPane(page).getByRole('button', {name: '上一步'}).click();
      await expect(step(page)).toHaveText('500');
      await modeTab(page, '结果文件').click();
      await page.clock.runFor(1000);
      await modeTab(page, '图谱').click();
      await expect(step(page)).toHaveText('1000');
      await page.clock.runFor(1000);
      expect(hub.evaluations).toHaveLength(1);
      expect(sent.take()).toEqual([]);
      // A scrub left in view is sent once, after its pause.
      await graphPane(page).getByRole('button', {name: '上一步'}).click();
      await page.clock.runFor(400);
      await expect.poll(() => hub.evaluations.length).toBe(2);
      expect(hub.evaluations[1].parameters).toEqual({step: 500});
      await expect(step(page)).toHaveText('500');
      writeFileSync(test.info().outputPath('in-flight-requests.json'), JSON.stringify({builds: hub.builds, evaluations: hub.evaluations}, null, 2));
      sent.stop();
      expect(errors).toEqual([]);
    });

    test('a 计算图谱 still running when the task or node changes in the hidden 图谱 is dropped', async ({page}) => {
      const hub = new Hub();
      hub.presets = [PRESET];
      hub.device = {...device, snapshot: {...device.snapshot, tasks: [row, row2]}};
      hub.others = [{...device, id: node2, name: '节点乙', snapshot: {...device.snapshot, tasks: [], workspaces: []}}];
      const errors = await setup(page, hub, {scene: false});
      const choose = async (name: RegExp) => { await go(page, '任务'); await page.locator('aside.tasks .task-list').getByRole('button', {name}).click(); };
      const dropped = async () => {
        await expect(vtkCanvas(graphPane(page))).toHaveCount(0);
        await expect(graphPane(page).getByRole('button', {name: '计算图谱'})).toBeEnabled();
        await expect(graphPane(page).locator('.status-line')).toHaveCount(0);
      };
      // Held, then the task changes while 结果文件 is shown; the late result is not shown for either task.
      await go(page, '结果');
      await modeTab(page, '图谱').click();
      let release = hub.hold('graph.evaluate');
      await graphPane(page).getByRole('button', {name: '计算图谱'}).click();
      await expect.poll(() => hub.reached.has('graph.evaluate')).toBe(true);
      await expect(graphPane(page).getByRole('button', {name: '计算中…'})).toBeDisabled();
      await modeTab(page, '结果文件').click();
      await choose(/对照任务/);
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      release();
      await page.waitForTimeout(500);
      await go(page, '结果');
      await expect(source(page)).toHaveText('节点甲 · 项目一 · 对照任务，尚未加载结果文件');
      await modeTab(page, '图谱').click();
      await dropped();
      await choose(/解析场验证/);
      await go(page, '结果');
      await dropped();
      // Held, then another node while 结果文件 is shown: the panel is dropped; back on the first node nothing returns.
      hub.reached.clear();
      release = hub.hold('graph.evaluate');
      await graphPane(page).getByRole('button', {name: '计算图谱'}).click();
      await expect.poll(() => hub.reached.has('graph.evaluate')).toBe(true);
      await modeTab(page, '结果文件').click();
      await go(page, '任务');
      await page.getByLabel('执行节点').selectOption(node2);
      await expect(graphPane(page)).toHaveCount(0);
      release();
      await page.waitForTimeout(500);
      await page.getByLabel('执行节点').selectOption(node);
      await project(page).selectOption(ws);
      await choose(/解析场验证/);
      await go(page, '结果');
      await expect(graphPane(page)).toHaveCount(0);
      await modeTab(page, '图谱').click();
      await expect(graphPane(page).getByLabel('图谱预设')).toHaveValue('field-view');
      await dropped();
      expect(hub.evaluations).toHaveLength(2);
      expect(errors).toEqual([]);
    });

    test('a running task\'s progress is read only while 图谱 is shown', async ({page}) => {
      const hub = new Hub();
      hub.presets = [PRESET];
      hub.device = {...device, snapshot: {...device.snapshot, tasks: [{...row, state: 'running'}]}};
      const sent = traffic(page);
      const errors = await setup(page, hub, {scene: false});
      const polls = () => sent.seen.filter(s => s === 'POST nodes/{node}/read task.events').length;
      await go(page, '结果');
      await page.waitForTimeout(500);
      expect(polls()).toBe(0);
      // (The clock is paused only once the panel is shown: a paused clock also holds the Suspense reveal.)
      await modeTab(page, '图谱').click();
      await expect(graphPane(page).getByLabel('图谱预设')).toHaveValue('field-view');
      await expect.poll(polls).toBe(1);
      await pause(page);
      await page.clock.runFor(60000);
      // (Each count waits for the requests the run timers started to be reported.)
      await page.waitForTimeout(500);
      const shown = polls();
      expect(shown).toBeGreaterThan(1);
      // Hidden, 图谱 stops reading; shown again, it reads at once and goes on.
      await modeTab(page, '结果文件').click();
      await page.clock.runFor(120000);
      await page.waitForTimeout(500);
      expect(polls()).toBe(shown);
      await modeTab(page, '图谱').click();
      await expect.poll(polls).toBe(shown + 1);
      expect(hub.evaluations).toHaveLength(0);
      sent.stop();
      expect(errors).toEqual([]);
    });

    test('a changed task, project or node drops both modes\' results; nothing old returns and 图谱 is read only when opened', async ({page}) => {
      const hub = new Hub();
      hub.presets = [PRESET];
      hub.device = {...device, snapshot: {...device.snapshot, tasks: [row, row2]}};
      hub.others = [{...device, id: node2, name: '节点乙', snapshot: {...device.snapshot, tasks: [], workspaces: []}}];
      const sent = traffic(page);
      const errors = await setup(page, hub);
      const firstTask = () => page.locator('aside.tasks .task-list').getByRole('button', {name: /解析场验证/});
      const empty = async () => {
        await expect(vtkCanvas(filePane(page))).toHaveCount(0);
        await expect(filePane(page).locator('.legend')).toHaveCount(0);
        if (await graphPane(page).count()) await expect(vtkCanvas(graphPane(page))).toHaveCount(0);
      };
      const both = async () => {
        await go(page, '结果');
        if (!await vtkCanvas(filePane(page)).count()) {
          await page.getByLabel('结果文件').selectOption('scalar-0.vti');
          await filePane(page).getByRole('button', {name: '加载视图'}).click();
          await expect(vtkCanvas(filePane(page))).toHaveCount(1);
        }
        await modeTab(page, '图谱').click();
        await computeGraph(page, hub);
        await modeTab(page, '结果文件').click();
        await expectMode(page, '结果文件');
        await expect(footer(page)).toContainText('就绪');
      };
      await both();
      const graphReads = () => sent.seen.filter(s => s === 'GET graphs/presets').length;
      expect(graphReads()).toBe(1);
      // Another task while 图谱 is hidden: neither mode shows the old result, then or after choosing the first again.
      await go(page, '任务');
      await page.locator('aside.tasks .task-list').getByRole('button', {name: /对照任务/}).click();
      await go(page, '结果');
      await expect(source(page)).toHaveText('节点甲 · 项目一 · 对照任务，尚未加载结果文件');
      await empty();
      await modeTab(page, '图谱').click();
      await empty();
      await expect(graphPane(page).locator('.graph-controls select').nth(1)).toHaveValue(task2);
      await modeTab(page, '结果文件').click();
      await go(page, '任务');
      await firstTask().click();
      await go(page, '结果');
      await expect(source(page)).toHaveText(shown('尚未加载结果文件'));
      await empty();
      await modeTab(page, '图谱').click();
      await empty();
      expect(graphReads()).toBe(1);
      // Another project (and back), with both results shown again first.
      await modeTab(page, '结果文件').click();
      await both();
      await go(page, '任务');
      await project(page).selectOption('');
      await project(page).selectOption(ws);
      await firstTask().click();
      await go(page, '结果');
      await empty();
      await modeTab(page, '图谱').click();
      await empty();
      expect(graphReads()).toBe(1);
      // Another node drops the hidden 图谱 panel; coming back to the first node does not mount it again hidden.
      await modeTab(page, '结果文件').click();
      await both();
      await go(page, '任务');
      await page.getByLabel('执行节点').selectOption(node2);
      await expect(graphPane(page)).toHaveCount(0);
      await page.getByLabel('执行节点').selectOption(node);
      await project(page).selectOption(ws);
      await firstTask().click();
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      await go(page, '结果');
      await expectMode(page, '结果文件');
      await empty();
      await expect(graphPane(page)).toHaveCount(0);
      await page.waitForTimeout(300);
      expect(graphReads()).toBe(1);
      // Opening 图谱 again mounts it fresh and reads its presets once.
      await modeTab(page, '图谱').click();
      await expectMode(page, '图谱');
      await expect(graphPane(page).getByLabel('图谱预设')).toHaveValue('field-view');
      await empty();
      expect(graphReads()).toBe(2);
      expect(hub.evaluations).toHaveLength(3);
      expect(sent.seen.filter(s => s.startsWith('POST') && !s.startsWith('POST nodes/{node}/read'))).toEqual([
        'POST actions view.build', 'POST actions graph.evaluate', 'POST actions view.build', 'POST actions graph.evaluate',
        'POST actions view.build', 'POST actions graph.evaluate']);
      writeFileSync(test.info().outputPath('scope-requests.json'), JSON.stringify(sent.seen, null, 2));
      sent.stop();
      expect(errors).toEqual([]);
    });
  });
}

// 图谱 scope and visibility. The panel works in the page's project and task scope, also at one node with no task
// selected (a local data package, a manually bound task), and is in view only in 结果, in 图谱 mode, with no compact
// history over it: out of view it reads no progress, drops a scrub not yet sent and reads no presets.
const ws2 = 'e'.repeat(32);
const twoProjects = {...device, snapshot: {...device.snapshot, workspaces: [{id: ws, name: '项目一'}, {id: ws2, name: '项目二'}]}};
const STKP = join(EXAMPLE, 'example.stkp'); // the public synthetic payload v2 package
const binding = (page: Page) => graphPane(page).getByLabel('数据源 field');
const localNote = (page: Page) => graphPane(page).locator('p.muted', {hasText: /^本地数据包 /});
const presetReads = (seen: string[]) => seen.filter(s => s === 'GET graphs/presets').length;
async function showGraph(page: Page) {
  await go(page, '结果');
  await modeTab(page, '图谱').click();
  await expectMode(page, '图谱');
  await expect(graphPane(page).getByLabel('图谱预设')).toHaveValue('field-view');
}
async function openPackage(page: Page) {
  await graphPane(page).locator('details.graph-extra > summary').click();
  await graphPane(page).locator('input[type=file]').setInputFiles(STKP);
  await expect(vtkCanvas(graphPane(page))).toHaveCount(1);
  await expect(localNote(page)).toHaveText('本地数据包 example.stkp · 无法查询原始值');
}
// Nothing of an earlier scope is in the panel: no canvas, package, status line or running evaluation.
async function graphEmpty(page: Page) {
  await expect(vtkCanvas(graphPane(page))).toHaveCount(0);
  await expect(localNote(page)).toHaveCount(0);
  await expect(graphPane(page).locator('.status-line')).toHaveCount(0);
  await expect(graphPane(page).getByRole('button', {name: '计算图谱'})).toBeEnabled();
}
// Pixels that differ between two screenshots of the same size, and the largest channel difference. Two renders of
// the payload v2 volume differ slightly inside the volume even in view; a framing change moves edges by far more.
async function pixelDiff(page: Page, a: Buffer, b: Buffer) {
  return page.evaluate(async ([a, b]) => {
    const load = async (data: string) => {
      const image = new Image();
      image.src = `data:image/png;base64,${data}`;
      await image.decode();
      const canvas = document.createElement('canvas');
      canvas.width = image.width; canvas.height = image.height;
      const context = canvas.getContext('2d')!;
      context.drawImage(image, 0, 0);
      return context.getImageData(0, 0, canvas.width, canvas.height);
    };
    const [x, y] = [await load(a), await load(b)];
    if (x.width !== y.width || x.height !== y.height) return {pixels: -1, max: 255};
    let pixels = 0, max = 0;
    for (let i = 0; i < x.data.length; i += 4) {
      const d = Math.max(...[0, 1, 2].map(k => Math.abs(x.data[i + k] - y.data[i + k])));
      if (d) { pixels++; max = Math.max(max, d); }
    }
    return {pixels, max};
  }, [a.toString('base64'), b.toString('base64')] as const);
}
async function chooseProject(page: Page, id: string) {
  await go(page, '任务');
  await project(page).selectOption(id);
}

for (const viewport of viewports) {
  test.describe(`${viewport.name} 图谱 scope and visibility`, () => {
    test.use({viewport: {width: viewport.width, height: viewport.height}});

    test('with no task selected at one node, a queued evaluation completing after a project change shows nothing', async ({page}) => {
      const hub = new Hub();
      hub.presets = [PRESET];
      hub.device = twoProjects;
      hub.queueGraph = true;
      const sent = traffic(page);
      const errors = await start(page, hub);
      await go(page, '任务');
      await page.getByLabel('执行节点').selectOption(node);
      await project(page).selectOption(ws);
      // In 项目一, no task selected: a task bound by hand in 图谱 and computed; the node queues it.
      await showGraph(page);
      await expect(source(page)).toHaveText('未选择任务，图谱数据源在下方绑定');
      await binding(page).selectOption(task);
      await graphPane(page).getByRole('button', {name: '计算图谱'}).click();
      await expect.poll(() => hub.queuePolls).toBeGreaterThan(0);
      await expect(graphPane(page).getByRole('button', {name: '计算中…'})).toBeDisabled();
      // 结果文件 is shown and a poll is in flight when the project changes in 任务; that poll then reports success.
      await modeTab(page, '结果文件').click();
      const poll = hub.hold('poll');
      await expect.poll(() => hub.reached.has('poll')).toBe(true);
      await chooseProject(page, ws2);
      hub.queueGraph = false;
      poll();
      await page.waitForTimeout(500);
      const polls = hub.queuePolls;
      await page.waitForTimeout(1500);
      expect(hub.queuePolls).toBe(polls);
      await expect(page.getByRole('alert')).toHaveCount(0);
      await go(page, '结果');
      await expectMode(page, '结果文件');
      await expect(page.getByRole('alert')).toHaveCount(0);
      await modeTab(page, '图谱').click();
      await graphEmpty(page);
      await expect(binding(page)).toHaveValue('');
      // Only the old evaluation's own polls were made: no render data was read for it.
      expect(sent.seen.filter(s => s === 'GET blobs/…')).toEqual([]);
      expect(presetReads(sent.seen)).toBe(1);
      expect(hub.evaluations).toEqual([expect.objectContaining({preset: 'field-view', bindings: {field: {task_id: task}}})]);
      expect(sent.seen.filter(s => s.startsWith('POST') && !s.startsWith('POST nodes/{node}/read'))).toEqual(['POST actions graph.evaluate']);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-queued-project-fence.png`)});
      writeFileSync(test.info().outputPath('queued-project-fence-requests.json'), JSON.stringify(sent.seen, null, 2));
      sent.stop();
      expect(errors).toEqual([]);
    });

    test('with no task selected at one node, a local package is kept across navigation and stays with its project', async ({page}) => {
      const hub = new Hub();
      hub.presets = [PRESET];
      hub.device = twoProjects;
      const sent = traffic(page);
      const errors = await start(page, hub);
      await go(page, '任务');
      await page.getByLabel('执行节点').selectOption(node);
      await project(page).selectOption(ws2);
      await showGraph(page);
      await openPackage(page);
      await vtkCanvas(graphPane(page)).evaluate(el => { (el as any).__marker = 'local-package'; });
      // A mode switch and section navigation keep the package, its canvas and its note.
      await modeTab(page, '结果文件').click();
      await go(page, '任务');
      await go(page, '工作台');
      await go(page, '结果');
      await modeTab(page, '图谱').click();
      expect(await marker(graphPane(page))).toBe('local-package');
      await expect(localNote(page)).toHaveText('本地数据包 example.stkp · 无法查询原始值');
      // Another project while 结果文件 is shown: the package is not shown there, nor after coming back to 项目二.
      const packageInput = graphPane(page).locator('input[type=file]');
      await modeTab(page, '结果文件').click();
      await chooseProject(page, ws);
      await go(page, '结果');
      await modeTab(page, '图谱').click();
      await graphEmpty(page);
      await expect(packageInput).toHaveValue('');
      await modeTab(page, '结果文件').click();
      await chooseProject(page, ws2);
      await go(page, '结果');
      await modeTab(page, '图谱').click();
      await graphEmpty(page);
      await expect(packageInput).toHaveValue('');
      await packageInput.setInputFiles(STKP);
      await expect(localNote(page)).toHaveText('本地数据包 example.stkp · 无法查询原始值');
      expect(presetReads(sent.seen)).toBe(1);
      expect(sent.seen.filter(s => s.startsWith('POST') && !s.startsWith('POST nodes/{node}/read'))).toEqual([]);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-package-project-fence.png`)});
      sent.stop();
      expect(errors).toEqual([]);
    });

    test('a late 图谱 error stays with its project; one raised while 图谱 is hidden waits for 图谱', async ({page}) => {
      const hub = new Hub();
      hub.presets = [PRESET];
      hub.device = twoProjects;
      hub.viewErrors.set('graph.evaluate', '节点拒绝：图谱数据不可读');
      const errors = await start(page, hub);
      await go(page, '任务');
      await page.getByLabel('执行节点').selectOption(node);
      await project(page).selectOption(ws);
      await showGraph(page);
      await binding(page).selectOption(task);
      let release = hub.hold('graph.evaluate');
      await graphPane(page).getByRole('button', {name: '计算图谱'}).click();
      await expect.poll(() => hub.reached.has('graph.evaluate')).toBe(true);
      await modeTab(page, '结果文件').click();
      await chooseProject(page, ws2);
      release();
      await page.waitForTimeout(500);
      await expect(page.getByRole('alert')).toHaveCount(0);
      await go(page, '结果');
      await expect(page.getByRole('alert')).toHaveCount(0);
      await modeTab(page, '图谱').click();
      await graphEmpty(page);
      await expect(page.getByRole('alert')).toHaveCount(0);
      // The same failure in the current project while 结果文件 is shown: not over 结果文件, but on 图谱's return.
      hub.reached.clear();
      await binding(page).selectOption(task);
      release = hub.hold('graph.evaluate');
      await graphPane(page).getByRole('button', {name: '计算图谱'}).click();
      await expect.poll(() => hub.reached.has('graph.evaluate')).toBe(true);
      await modeTab(page, '结果文件').click();
      release();
      await expect(graphPane(page).locator('.graph-controls button.primary')).toHaveText('计算图谱');
      await page.waitForTimeout(300);
      await expect(page.getByRole('alert')).toHaveCount(0);
      await go(page, '任务');
      await expect(page.getByRole('alert')).toHaveCount(0);
      await go(page, '结果');
      await expect(page.getByRole('alert')).toHaveCount(0);
      await modeTab(page, '图谱').click();
      await expect(page.getByRole('alert')).toContainText('节点拒绝：图谱数据不可读');
      await page.getByRole('alert').getByRole('button', {name: '关闭'}).click();
      await expect(page.getByRole('alert')).toHaveCount(0);
      if (viewport.name === 'narrow') {
        hub.reached.clear();
        release = hub.hold('graph.evaluate');
        await graphPane(page).getByRole('button', {name: '计算图谱'}).click();
        await expect.poll(() => hub.reached.has('graph.evaluate')).toBe(true);
        await historyToggle(page).click();
        await expect(historyToggle(page)).toHaveAttribute('aria-expanded', 'true');
        release();
        await expect(graphPane(page).locator('.graph-controls button.primary')).toHaveText('计算图谱');
        await expect(page.getByRole('alert')).toHaveCount(0);
        await page.keyboard.press('Escape');
        await expect(historyToggle(page)).toHaveAttribute('aria-expanded', 'false');
        await expect(page.getByRole('alert')).toContainText('节点拒绝：图谱数据不可读');
      }
      expect(hub.evaluations).toHaveLength(viewport.name === 'narrow' ? 3 : 2);
      expect(errors.filter(e => !/502/.test(e))).toEqual([]);
    });

    test('a task ID listed in two projects is two scopes: the other one shows nothing of the first', async ({page}) => {
      // A synthetic snapshot: the Runtime keys tasks by ID per node, so this only checks the scope identity.
      const hub = new Hub();
      hub.presets = [PRESET];
      hub.device = {...twoProjects, snapshot: {...twoProjects.snapshot, tasks: [row, {...row, workspace_id: ws2, name: '复用编号任务'}]}};
      const errors = await start(page, hub);
      await go(page, '任务');
      await page.getByLabel('执行节点').selectOption(node);
      await taskRow(page, '解析场验证').click();
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      await showGraph(page);
      await expect(binding(page)).toHaveValue(task);
      await computeGraph(page, hub);
      const release = hub.hold('graph.evaluate');
      await graphPane(page).getByRole('button', {name: '计算图谱'}).click();
      await expect.poll(() => hub.reached.has('graph.evaluate')).toBe(true);
      await modeTab(page, '结果文件').click();
      await go(page, '任务');
      await taskRow(page, '复用编号任务').click();
      await expect(page.locator('aside.tasks .task-scope')).toHaveText('所选任务 · 节点甲 · 项目二');
      release();
      await page.waitForTimeout(500);
      await go(page, '结果');
      await expect(source(page)).toHaveText('节点甲 · 项目二 · 复用编号任务，尚未加载结果文件');
      await modeTab(page, '图谱').click();
      await graphEmpty(page);
      await expect(binding(page)).toHaveValue(task);
      expect(hub.evaluations).toHaveLength(2);
      expect(errors).toEqual([]);
    });

    test('out of 结果, 图谱 reads no progress and drops a scrub not yet sent; both resume on return', async ({page}) => {
      const hub = new Hub();
      hub.presets = [PRESET];
      hub.device = {...device, snapshot: {...device.snapshot, tasks: [{...row, state: 'running'}]}};
      const sent = traffic(page);
      const errors = await setup(page, hub, {scene: false});
      const polls = () => sent.seen.filter(s => s === 'POST nodes/{node}/read task.events').length;
      await showGraph(page);
      await expect.poll(polls).toBe(1);
      await computeGraph(page, hub);
      await pause(page);
      await page.clock.runFor(60000);
      await page.waitForTimeout(500);
      const away = async (leave: () => Promise<void>, back: () => Promise<void>) => {
        const before = polls();
        expect(before).toBeGreaterThan(1);
        await leave();
        await page.clock.runFor(120000);
        await page.waitForTimeout(500);
        expect(polls()).toBe(before);
        await back();
        await expectMode(page, '图谱');
        await expect.poll(polls).toBe(before + 1);
        await page.clock.runFor(60000);
        await page.waitForTimeout(500);
      };
      // Leaving for 任务 or 工作台 stops the reads; 结果 reads at once and goes on.
      await away(() => go(page, '任务'), () => go(page, '结果'));
      await away(() => go(page, '工作台'), () => go(page, '结果'));
      if (isNarrow(page)) await away(async () => { await historyToggle(page).click(); await expect(historyPanel(page)).toBeVisible(); },
        async () => { await page.keyboard.press('Escape'); await expect(historyPanel(page)).toBeHidden(); });
      // A scrub not yet sent is dropped by leaving 结果 (and by the compact history); its step goes back.
      const leaves: [string, () => Promise<void>, () => Promise<void>][] = [
        ['任务', () => go(page, '任务'), () => go(page, '结果')], ['工作台', () => go(page, '工作台'), () => go(page, '结果')]];
      if (isNarrow(page)) leaves.push(['历史', () => historyToggle(page).click(), () => page.keyboard.press('Escape')]);
      for (const [, leave, back] of leaves) {
        await graphPane(page).getByRole('button', {name: '上一步'}).click();
        await expect(step(page)).toHaveText('500');
        await leave();
        await page.clock.runFor(1000);
        await back();
        await expect(step(page)).toHaveText('1000');
        await page.clock.runFor(1000);
        await page.waitForTimeout(300);
        expect(hub.evaluations).toHaveLength(1);
      }
      // A scrub left in view is sent once.
      await graphPane(page).getByRole('button', {name: '上一步'}).click();
      await page.clock.runFor(400);
      await expect.poll(() => hub.evaluations.length).toBe(2);
      expect(hub.evaluations[1].parameters).toEqual({step: 500});
      writeFileSync(test.info().outputPath('away-requests.json'), JSON.stringify(sent.seen, null, 2));
      sent.stop();
      expect(errors).toEqual([]);
    });

    test('a 计算图谱 sent before leaving 结果 completes there and is shown on return, framed as if computed in view', async ({page}) => {
      const hub = new Hub();
      hub.presets = [PRESET];
      hub.device = {...device, snapshot: {...device.snapshot, tasks: [row, row2]}};
      const errors = await setup(page, hub, {scene: false});
      await showGraph(page);
      await computeGraph(page, hub);
      await expect(footer(page)).toContainText('就绪');
      await page.waitForTimeout(300);
      const inView = await paneShot(page, graphPane(page), `${viewport.name}-computed-in-view`);
      // Another task and back gives a fresh panel; then a held 计算图谱 completes while 任务 is shown.
      await go(page, '任务');
      await taskRow(page, '对照任务').click();
      await taskRow(page, '解析场验证').click();
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      await go(page, '结果');
      await graphEmpty(page);
      const release = hub.hold('graph.evaluate');
      await graphPane(page).getByRole('button', {name: '计算图谱'}).click();
      await expect.poll(() => hub.reached.has('graph.evaluate')).toBe(true);
      await go(page, '任务');
      release();
      await expect(vtkCanvas(graphPane(page))).toHaveCount(1);
      await expect(graphPane(page).locator('.status-line')).toHaveCount(0);
      await expectActive(page, '任务');
      await page.waitForTimeout(300);
      await go(page, '结果');
      await expectMode(page, '图谱');
      await expect(step(page)).toHaveText('1000');
      await page.waitForTimeout(300);
      const hidden = await paneShot(page, graphPane(page), `${viewport.name}-computed-hidden`);
      // Control: the same evaluation computed in view again, in a fresh panel.
      await go(page, '任务');
      await taskRow(page, '对照任务').click();
      await taskRow(page, '解析场验证').click();
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      await go(page, '结果');
      await graphEmpty(page);
      await computeGraph(page, hub);
      await expect(footer(page)).toContainText('就绪');
      await page.waitForTimeout(300);
      const again = await paneShot(page, graphPane(page), `${viewport.name}-computed-in-view-again`);
      const diffs = {hiddenVsInView: await pixelDiff(page, inView, hidden), inViewVsInViewAgain: await pixelDiff(page, inView, again)};
      writeFileSync(test.info().outputPath('pixel-diffs.json'), JSON.stringify(diffs, null, 2));
      expect(diffs.hiddenVsInView.pixels).toBeGreaterThanOrEqual(0);
      expect(diffs.hiddenVsInView.max).toBeLessThanOrEqual(24);
      expect(diffs.inViewVsInViewAgain.max).toBeLessThanOrEqual(24);
      expect(hub.evaluations).toHaveLength(3);
      expect(errors).toEqual([]);
    });

    test('a node chosen while 结果 is hidden reads no presets until 图谱 is shown in 结果 again', async ({page}) => {
      const hub = new Hub();
      hub.presets = [PRESET];
      hub.others = [{...device, id: node2, name: '节点乙', snapshot: {...device.snapshot, tasks: [], workspaces: []}}];
      const sent = traffic(page);
      const errors = await setup(page, hub, {scene: false});
      await showGraph(page);
      expect(presetReads(sent.seen)).toBe(1);
      // 图谱 stays the chosen mode; the node changes in 任务, twice, and the first task is chosen again.
      await go(page, '任务');
      await page.getByLabel('执行节点').selectOption(node2);
      await expect(graphPane(page)).toHaveCount(0);
      await page.waitForTimeout(500);
      await page.getByLabel('执行节点').selectOption(node);
      await project(page).selectOption(ws);
      await taskRow(page, '解析场验证').click();
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      await page.waitForTimeout(500);
      expect(presetReads(sent.seen)).toBe(1);
      await expect(graphPane(page)).toHaveCount(0);
      await go(page, '工作台');
      await page.waitForTimeout(300);
      expect(presetReads(sent.seen)).toBe(1);
      // Shown in 结果 again (one click, the mode is still 图谱): mounted fresh and its presets read once.
      await go(page, '结果');
      await expectMode(page, '图谱');
      await expect(graphPane(page).getByLabel('图谱预设')).toHaveValue('field-view');
      await page.waitForTimeout(300);
      expect(presetReads(sent.seen)).toBe(2);
      expect(hub.evaluations).toHaveLength(0);
      sent.stop();
      expect(errors).toEqual([]);
    });

    for (const leave of ['结果文件', '任务'] as const) {
      test(`a 图谱 module arriving after ${leave} was chosen reads its presets only once 图谱 is shown`, async ({page}) => {
        const hub = new Hub();
        hub.presets = [PRESET];
        let release!: () => void;
        hub.graphChunk = new Promise<void>(resolve => { release = resolve; });
        const sent = traffic(page);
        const errors = await setup(page, hub, {scene: false});
        await go(page, '结果');
        await modeTab(page, '图谱').click();
        await expect(graphPane(page)).toContainText('正在加载图谱模块…');
        if (leave === '结果文件') await modeTab(page, '结果文件').click(); else await go(page, '任务');
        release();
        // The retained Suspense mounts the panel hidden; it reads nothing.
        await expect(graphPane(page).locator('.graph-panel')).toHaveCount(1);
        await page.waitForTimeout(500);
        expect(presetReads(sent.seen)).toBe(0);
        await expect(graphPane(page).getByLabel('图谱预设', {exact: true})).toHaveValue('');
        if (leave === '结果文件') await modeTab(page, '图谱').click(); else await go(page, '结果');
        await expectMode(page, '图谱');
        await expect(graphPane(page).getByLabel('图谱预设')).toHaveValue('field-view');
        await page.waitForTimeout(300);
        expect(presetReads(sent.seen)).toBe(1);
        sent.stop();
        expect(errors).toEqual([]);
      });
    }
  });
}
