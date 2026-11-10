// Browser regression for the Hub Web section navigation (工作台 / 任务 / 结果): the explicit 结果 / 读取日志
// shortcuts in Tasks open 结果 in one click with their target in view, and a late result never moves the user.
// It drives the built app (`npm run build` first, or STK_WEB_DIST=<dir>) in Chromium; page.route serves the
// files and a mocked hub, so no server, model or network is used. Without a build these tests are skipped.
import {expect, test, type Page, type Request, type Route} from '@playwright/test';
import {existsSync, readFileSync} from 'node:fs';
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
  field = 'phi';
  logsFail = false;
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
      const file = join(DIST, url.pathname === '/' ? 'index.html' : url.pathname);
      if (!existsSync(file)) return route.fulfill({status: 404, body: ''});
      return route.fulfill({status: 200, contentType: types[extname(file)] || 'application/octet-stream', body: readFileSync(file)});
    }
    const path = url.pathname.slice('/api/v1/'.length);
    const json = (body: unknown, status = 200) => route.fulfill({status, contentType: 'application/json', body: JSON.stringify(body)});
    if (path === 'events') { this.streams.push(route); return; } // open and silent until the hub publishes
    if (path === 'devices') return json([device]);
    if (path === 'actions' && request.method() === 'GET') return json([]);
    if (path === 'sessions') return json(this.rows);
    if (path === 'policy') return json({read_kinds: ['task.get', 'task.artifacts', 'task.events']});
    if (path === 'graphs/presets') return json([]);
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
      if (kind === 'task.get') return json({result: row});
      if (kind === 'task.artifacts') {
        const later = this.later;
        await this.gate(kind);
        return json({result: [{path: 'scalar-0.vti', size: 10}, ...(later ? [{path: 'scalar-1.vti', size: 10}] : [])]});
      }
    }
    if (path === 'actions' && request.method() === 'POST') {
      const body = request.postDataJSON();
      await this.gate(body.kind);
      if (body.kind === 'view.build') return json({id: body.id, state: 'succeeded', result: {...scene, manifest: {...scene.manifest, field: this.field}}});
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
  await page.locator('aside.tasks select').nth(1).selectOption(ws);
  await page.getByRole('button', {name: /解析场验证/}).click();
  await expectActive(page, '任务');
  await expect(page.getByRole('region', {name: '所选任务状态'})).toContainText('已读取 Runtime 状态');
  await page.locator('aside.tasks summary', {hasText: '自定义任务'}).click();
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
    workspace: await page.locator('aside.tasks select').nth(1).inputValue(),
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
