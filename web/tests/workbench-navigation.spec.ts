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
const LOG = 'step 1 converged\nstep 2 converged\n';
const types: Record<string, string> = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.webmanifest': 'application/manifest+json'};

// Mocked hub. `later` switches task.artifacts to a longer list, so a click-time read is distinguishable from the
// read made on task selection; `hold(kind)` keeps that request pending until released.
class Hub {
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
    await page.route(`${ORIGIN}/**`, route => this.answer(route));
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
    if (path === 'events') return; // the event stream stays open and silent, as a live hub would
    if (path === 'devices') return json([device]);
    if (path === 'actions' && request.method() === 'GET') return json([]);
    if (path === 'sessions') return json([]);
    if (path === 'policy') return json({read_kinds: ['task.get', 'task.artifacts', 'task.events']});
    if (path === 'graphs/presets') return json([]);
    if (path.startsWith('sessions/')) return json({messages: []});
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

async function expectActive(page: Page, label: keyof typeof surfaces) {
  for (const [name, selector] of Object.entries(surfaces)) {
    const active = name === label;
    const button = nav(page).getByRole('button', {name, exact: true});
    if (active) await expect(button).toHaveAttribute('aria-current', 'page'); else await expect(button).not.toHaveAttribute('aria-current');
    if (active) await expect(page.locator(selector)).toBeVisible(); else await expect(page.locator(selector)).toBeHidden();
    expect(await page.locator(selector).evaluate(el => (el as HTMLElement).inert)).toBe(!active);
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
      const viewer = await page.locator('section.analysis .viewport').screenshot();
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
      expect((await page.locator('section.analysis .viewport').screenshot()).equals(viewer)).toBe(true);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-files-shortcut.png`)});
      expect(errors).toEqual([]);
    });

    test('Tasks 读取日志 opens 结果 with the log in view', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub);
      const pane = page.locator('section.analysis details.logs');
      await go(page, '结果');
      await freeze(page);
      const viewer = await page.locator('section.analysis .viewport').screenshot();
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
      await expect(pane).toBeInViewport();
      await expect(pane.locator('summary')).toBeFocused();
      await expect(footer(page)).toContainText('正在处理请求');
      await expect.poll(() => hub.reached.has('task.logs')).toBe(true);
      release();
      await expect(pane.locator('pre')).toHaveText(LOG);
      await expect(pane.locator('pre')).toBeInViewport();
      await expect(footer(page)).toContainText('就绪');
      await expectActive(page, '结果');
      await page.waitForTimeout(300);
      sent.stop();
      expect(sent.seen).toEqual(['/api/v1/actions task.logs']);
      expect(await state(page)).toEqual(before);
      expect((await page.locator('section.analysis .viewport').screenshot()).equals(viewer)).toBe(true);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-logs-shortcut.png`)});
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
