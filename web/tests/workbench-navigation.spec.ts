// Browser regression for the Hub Web section navigation (工作台 / 任务 / 结果): the explicit 在查看器中打开 / 读取日志
// shortcuts in Tasks open 结果 in one click with their target in view, and a late result never moves the user.
// It drives the built app (`npm run build` first, or STK_WEB_DIST=<dir>) in Chromium; page.route serves the
// files and a mocked hub, so no server, model or network is used. Without a build these tests are skipped.
import {expect, test, type Locator, type Page, type Request, type Route} from '@playwright/test';
import {createHash} from 'node:crypto';
import {existsSync, readFileSync, writeFileSync} from 'node:fs';
import {extname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {scalarNpy} from './mupro-npy-fixture';

const DIST = process.env.STK_WEB_DIST || fileURLToPath(new URL('../dist/', import.meta.url));
test.skip(!existsSync(join(DIST, 'index.html')), `no built app in ${DIST}: run npm run build or set STK_WEB_DIST`);
test.use({serviceWorkers: 'block', launchOptions: {args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader']}});

const ORIGIN = 'http://localhost:47883'; // secure context for crypto.randomUUID; page.route answers before any socket
const node = 'a'.repeat(32), ws = 'b'.repeat(32), task = 'c'.repeat(32);
const createdId = (n: number) => '7'.repeat(30) + n.toString(16).padStart(2, '0'); // synthetic created workspaces
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
const HDF5_ARTIFACT = {path: 'case/run.h5', size: 8192, sha256: 'd'.repeat(64)};
const digestOf = (path: string) => createHash('sha256').update(path).digest('hex');
const HDF5_FIELDS = [
  {selector: '/t00000002/Polar', step: 2, name: 'Polar', shape: [4, 3, 2, 3], dtype: 'float32'},
  {selector: '/t00000002/Scalar', step: 2, name: 'Scalar', shape: [4, 3, 2, 1], dtype: 'float32'},
  {selector: '/t00000004/Polar', step: 4, name: 'Polar', shape: [4, 3, 2, 3], dtype: 'float32'},
];
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
  readonly conversationTasks = new Map<string, unknown[]>();
  readonly conversationFiles = new Map<string, unknown>();
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
  // When set, task.artifacts lists exactly these paths instead of scalar-0.vti (and scalar-1.vti once `later`). Each is
  // published as the Runtime describes it, with a size and a lowercase SHA-256 (here of its path, a synthetic stand-in).
  // `artifactRows` answers exactly these entries instead, for malformed or digest-less lists.
  artifactPaths?: string[];
  artifactRows?: unknown[];
  // `queueArtifacts`: each task.artifacts read then waits, in arrival order, in `artifactQueue` until the test calls
  // its release. `artifactReadError` refuses the read-only node read with that status. `reviewKinds`: an action of
  // these kinds goes to execution review, which GET actions then lists, instead of running.
  queueArtifacts = false;
  readonly artifactQueue: (() => void)[] = [];
  artifactReadError?: number;
  readonly reviewKinds = new Set<string>();
  readonly artifactPathsByTask = new Map<string, string[]>();
  readKinds = ['task.get', 'task.artifacts', 'task.events'];
  readonly taskReadResults = new Map<string, unknown>();
  taskReadError?: number;
  readonly hdf5Artifacts = new Map<string, typeof HDF5_ARTIFACT>();
  hdf5Fault?: 'wrong-digest' | 'invalid_data' | 'wrong-step';
  hdf5Fields = HDF5_FIELDS;
  voxelFault?: 'source' | 'digest' | 'size';
  private readonly voxelBlobs = new Map<string, Buffer>();
  field = 'phi';
  valueRange = scene.manifest.value_range;
  // 任务: `device` is the node the hub lists; `down` makes every hub call fail as an unreachable control service;
  // `review` sends a task.submit to execution review, which GET actions then lists until it is approved or refused.
  device: typeof device = device;
  // Further nodes the hub lists (no node reads are answered for them).
  others: Record<string, any>[] = [];
  down = false;
  review = false;
  // workspace.create answers with a new synthetic workspace (createdId(n) for the n-th create), which the target
  // node's snapshot then lists, as its next heartbeat would. 'review' sends it to execution review instead, and
  // The malformed replies omit or corrupt the workspace ID. `creates` records each create payload and target node.
  // `listLater` keeps a created workspace out of the snapshot until listCreated(), as a node whose next heartbeat
  // has not arrived yet.
  createReply: 'normal' | 'review' | 'no-id' | 'invalid-id' = 'normal';
  listLater = false;
  readonly creates: {node: string; name: string}[] = [];
  private unlisted: (() => void)[] = [];
  listCreated() { for (const list of this.unlisted.splice(0)) list(); }
  readonly actionRows: Record<string, any>[] = [];
  // task.logs: fails for every stream or one; `logTexts` keys `${task_id} ${stream}` (a string, or a Buffer for raw
  // bytes); `logPayloads` records each payload. As suan/runtime/service.py answers it, a reply is at most `logChunk`
  // bytes from the asked offset, with offset, next_offset and terminal (the task row's state when the read starts).
  // `logReply`: 'legacy' answers only {data}, as older nodes did; the faults corrupt one reply each, then reset.
  logsFail: boolean | 'stdout' | 'stderr' = false;
  readonly logTexts = new Map<string, string | Buffer>();
  readonly logPayloads: Record<string, any>[] = [];
  logChunk = 1024 * 1024;
  logReply: 'normal' | 'legacy' = 'normal';
  logFault: null | 'offset' | 'next_offset' | 'base64' | 'no-offsets' = null;
  readonly viewErrors = new Map<string, string>();
  reportedViewSource?: {task_id: string; path: string} | 'omit';
  reportedViewDigest?: string;
  reportedViewIndex?: number;
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
  graphReply: 'normal' | 'bad-payload' | 'outputs-only' = 'normal';
  graphPayloadStep?: number | null;
  graphVolume: 'normal' | 'omit' | 'fail' = 'normal';
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
  private async publishedArtifacts(taskId: string) {
    const later = this.later;
    if (this.queueArtifacts) await new Promise<void>(resolve => this.artifactQueue.push(resolve));
    await this.gate(`task.artifacts ${taskId}`);
    await this.gate('task.artifacts');
    const hdf5 = this.hdf5Artifacts.get(taskId);
    if (hdf5) return [hdf5, {path: 'case/Polar.00000002.dat', size: 1024}];
    if (this.artifactRows) return this.artifactRows;
    const paths = this.artifactPathsByTask.get(taskId) ?? this.artifactPaths ??
      ['scalar-0.vti', ...(later ? ['scalar-1.vti'] : [])];
    return paths.map(path => ({path, size: 10, sha256: digestOf(path)}));
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
      if (/^\/assets\/volume-[^/]+\.js$/.test(url.pathname)) {
        await this.gate('volume chunk');
        if (this.graphVolume === 'fail') return route.fulfill({status: 200, contentType: 'text/javascript',
          body: "throw new Error('Synthetic volume actor failure');"});
      }
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
    if (path === 'policy') return json({read_kinds: this.readKinds});
    if (path === 'graphs/presets') return json(this.presets);
    const stored = /^blobs\/([0-9a-f]{64})$/.exec(path);
    if (stored) {
      const voxel = this.voxelBlobs.get(stored[1]);
      if (voxel) return route.fulfill({status: 200, contentType: 'application/octet-stream', body: voxel});
      const file = join(EXAMPLE, `${stored[1]}.bin`);
      return existsSync(file) ? route.fulfill({status: 200, contentType: 'application/octet-stream', body: readFileSync(file)}) : json({detail: 'no blob'}, 404);
    }
    const files = /^sessions\/([^/]+)\/tasks\/([^/]+)\/files$/.exec(path);
    if (files && request.method() === 'GET') {
      const [, session, action] = files;
      const key = `${session} ${action}`;
      this.calls.push(`files ${key}`);
      await this.gateOnce(`files ${key}`);
      return json(this.conversationFiles.get(key) ?? {detail: 'Conversation task not found'},
        this.conversationFiles.has(key) ? 200 : 404);
    }
    const conversation = /^sessions\/([^/]+)(\/history|\/messages|\/tasks)?$/.exec(path);
    if (conversation) {
      const [, id, tail] = conversation;
      if (!tail) { this.calls.push(`legacy ${id}`); return json({detail: 'legacy GET would create a session'}, 500); }
      if (tail === '/tasks' && request.method() === 'GET') {
        this.calls.push(`tasks ${id}`);
        const tasks = this.conversationTasks.get(id);
        await this.gateOnce(`tasks ${id}`);
        return tasks ? json({id, tasks, more: false}) : json({detail: 'Not Found'}, 404);
      }
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
        await this.gateOnce('task.get');
        if (this.taskReadError) return json({detail: 'task read unavailable'}, this.taskReadError);
        const result = this.taskReadResults.get(id) ?? this.device.snapshot.tasks.find(t => t.id === id) ?? row;
        return json({result});
      }
      // The running task's event log: no new events yet.
      if (kind === 'task.events') return json({result: {events: [], next_offset: 0, size: 0, terminal: false}});
      if (kind === 'task.artifacts') {
        if (this.artifactReadError) return json({detail: '无权读取任务产物'}, this.artifactReadError);
        return json({result: await this.publishedArtifacts(request.postDataJSON().payload?.task_id)});
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
      if (this.reviewKinds.has(body.kind)) {
        const item = {id: body.id, state: 'review', review_reason: '读取或构建需要执行复核', request: {kind: body.kind, payload: body.payload}};
        this.actionRows.unshift(item);
        return json(item);
      }
      if (body.kind === 'view.build') {
        const field = this.field;
        const source = this.reportedViewSource ?? {task_id: body.payload.task_id, path: body.payload.path};
        const dataset_id = this.reportedViewDigest ?? digestOf(body.payload.path);
        const {mode, axis} = body.payload.options;
        const dimensions = [32, 28, 24];
        const index = mode === 'slice' ? this.reportedViewIndex ?? body.payload.options.index ?? Math.floor(dimensions[axis] / 2) : null;
        return json({id: body.id, state: 'succeeded',
          result: {...scene, manifest: {...scene.manifest, field, dataset_id, mode, axis, dimensions, index, value_range: this.valueRange,
            ...(source === 'omit' ? {} : {source})}}});
      }
      if (body.kind === 'view.probe') {
        return json({id: body.id, state: 'succeeded', result: {position: body.payload.position, values: [0.5], units: 'V'}});
      }
      if (body.kind === 'task.artifacts') return json({id: body.id, state: 'succeeded',
        result: await this.publishedArtifacts(body.payload.task_id)});
      if (body.kind === 'workspace.create') {
        this.creates.push({node: body.node_id, name: body.payload.name});
        if (this.createReply === 'review') {
          const item = {id: body.id, state: 'review', review_reason: '新建项目需要执行复核', request: {kind: body.kind, payload: body.payload}};
          this.actionRows.unshift(item);
          return json(item);
        }
        const made = {id: createdId(this.creates.length), name: String(body.payload.name).trim()};
        const list = (target: Record<string, any>) => ({...target, snapshot: {...target.snapshot,
          workspaces: [...target.snapshot.workspaces, made]}});
        const listing = () => {
          if (this.device.id === body.node_id) this.device = list(this.device) as typeof device;
          else this.others = this.others.map(other => other.id === body.node_id ? list(other) : other);
        };
        if (this.listLater) this.unlisted.push(listing); else listing();
        const result = this.createReply === 'no-id' ? {name: made.name} :
          this.createReply === 'invalid-id' ? {...made, id: 'not-a-workspace'} : made;
        return json({id: body.id, state: 'succeeded', result});
      }
      if (body.kind === 'task.submit') {
        if (!this.review) return json({id: body.id, state: 'succeeded', result: {id: task}});
        const item = {id: body.id, state: 'review', review_reason: '新命令需要执行复核', request: {kind: body.kind, payload: body.payload}};
        this.actionRows.unshift(item);
        return json(item);
      }
      if (body.kind === 'graph.evaluate') {
        const hdf5 = body.payload.graph?.nodes?.[0], type = hdf5?.type;
        if (type === 'stk.source.mupro_hdf5_fields@1' || type === 'stk.source.mupro_hdf5@1') {
          const fields = type === 'stk.source.mupro_hdf5_fields@1';
          const artifact = this.hdf5Artifacts.get(body.payload.bindings?.run?.task_id);
          const fault = this.hdf5Fault;
          const voxel = body.payload.outputs?.includes('voxel');
          const voxelFault = this.voxelFault;
          await this.gateOnce(fields ? 'hdf5 fields' : voxel ? 'hdf5 voxel' : 'hdf5 open');
          if (!artifact || artifact.sha256 !== hdf5.params.expected_sha256 || fault === 'invalid_data') {
            return json({id: body.id, state: 'failed', error: 'invalid_data: expected SHA-256'});
          }
          if (voxel) {
            const field = this.hdf5Fields.find(item => item.selector === hdf5.params.selector)!;
            const point = [0, 2, 4].map(axis => hdf5.params.extent[axis]);
            const bits = Buffer.alloc(field.dtype === 'uint64' ? 8 : 4);
            if (field.dtype === 'uint64') bits.writeBigUInt64LE(9223372036854775931n);
            else bits.writeFloatLE(0.3125);
            const bytes = scalarNpy(field.dtype === 'uint64' ? '<u8' : '<f4', bits);
            const sha = createHash('sha256').update(bytes).digest('hex');
            const served = Buffer.from(bytes);
            if (voxelFault === 'digest') served[served.length - 1] ^= 1;
            this.voxelBlobs.set(sha, voxelFault === 'size' ? Buffer.concat([served, Buffer.from([0])]) : served);
            const descriptor = {schema: 'stk.dataset/1', id: field.name, kind: 'image',
              geometry: {length_unit: 'grid_index', origin: voxelFault === 'source' ? [99, 99, 99] : point,
                spacing: [1, 1, 1], dimensions: [1, 1, 1]},
              time: {step: field.step}, fields: [{name: field.name, dtype: field.dtype, association: 'point', components: field.shape[3]}],
              frames: [{step: field.step, sources: {[field.name]: {...artifact, reader: 'mupro.hdf5@1', selector: field.selector}}}]};
            const outputs = {source: {type: 'dataset', descriptor}, voxel: {type: 'file', name: 'voxel.npy',
              media_type: 'application/x-npy', size: bytes.length, blob: sha}};
            return json({id: body.id, state: 'succeeded', result: {schema: 'stk.graph-result/1', profile: 'web', outputs}});
          }
          const manifest = JSON.parse(readFileSync(join(EXAMPLE, 'manifest.json'), 'utf8'));
          manifest.length_unit = 'grid_index';
          manifest.source.time = {step: fault === 'wrong-step' ? 4 : Number(hdf5.params.selector?.slice(2, 10)), time: null};
          const outputs = fields ? {fields: {type: 'value', value: {...artifact,
            sha256: fault === 'wrong-digest' ? 'e'.repeat(64) : artifact.sha256, reader: 'mupro.hdf5@1', fields: this.hdf5Fields}}} :
            {view: {type: 'payload', manifest}};
          return json({id: body.id, state: 'succeeded', result: {schema: 'stk.graph-result/1', profile: 'web', outputs}});
        }
        const asked = body.payload.parameters?.step, step = typeof asked === 'number' ? asked : STEPS[STEPS.length - 1];
        const manifest = this.graphReply === 'bad-payload' ? {schema: 'stk.payload/2'} :
          JSON.parse(readFileSync(join(EXAMPLE, 'manifest.json'), 'utf8'));
        if (manifest.source?.time) manifest.source.time.step = this.graphPayloadStep === undefined ? step : this.graphPayloadStep;
        if (this.graphVolume === 'omit' && Array.isArray(manifest.layers)) {
          manifest.layers = manifest.layers.filter((layer: {type: string}) => layer.type !== 'volume');
        }
        const output = {info: {type: 'value', value: '可用的图谱输出'}};
        const result = {outputs: this.graphReply === 'outputs-only' ? output :
          {main: {manifest}, ...(this.graphReply === 'bad-payload' ? output : {})},
          parameters: {step: {value: step, choices: STEPS}}};
        if (this.queueGraph) { this.queuedResults.set(body.id, result); return json({id: body.id, state: 'queued'}); }
        return json({id: body.id, state: 'succeeded', result});
      }
      if (body.kind === 'task.logs') {
        // As the node reads it: the stream defaults to stdout; text is per task and stream (LOG for any stdout not set).
        this.logPayloads.push(body.payload);
        const stream = body.payload.stream ?? 'stdout', offset = body.payload.offset ?? 0;
        const state = this.device.snapshot.tasks.find(t => t.id === body.payload.task_id)?.state;
        const terminal = ['succeeded', 'failed', 'cancelled'].includes(state ?? '');
        const text = this.logTexts.get(`${body.payload.task_id} ${stream}`) ?? (stream === 'stdout' ? LOG : '');
        const bytes = Buffer.from(text).subarray(offset, offset + this.logChunk);
        const fault = this.logFault;
        this.logFault = null;
        const fail = this.logsFail === true || this.logsFail === stream;
        if (fail) return json({id: body.id, state: 'failed', error: '日志暂不可读'});
        const data = fault === 'base64' ? '%%' : bytes.toString('base64');
        const result = this.logReply === 'legacy' || fault === 'no-offsets' ? {data} : {data,
          offset: fault === 'offset' ? offset + 1 : offset,
          next_offset: offset + bytes.length + (fault === 'next_offset' ? 1 : 0), terminal};
        return json({id: body.id, state: 'succeeded', result});
      }
    }
    return json({detail: `unmocked ${path}`}, 500);
  }
}

const nav = (page: Page) => page.getByRole('navigation', {name: '工作区'});
const go = (page: Page, label: string) => nav(page).getByRole('button', {name: label, exact: true}).click();
const shortcut = (page: Page, label: '在查看器中打开' | '读取日志') => page.locator('aside.tasks .inline').getByRole('button', {name: label, exact: true});
const surfaces = {工作台: 'aside.chat', 任务: 'aside.tasks', 结果: 'section.analysis'} as const;
const footer = (page: Page) => page.locator('footer');
// 任务 keeps the run environment and the new task form in disclosures under the queue.
const project = (page: Page) => page.locator('aside.tasks label', {hasText: /^项目/}).locator('select');
const disclosure = (page: Page, name: '运行环境' | '新建任务') => page.locator('aside.tasks details.setting > summary', {hasText: name});
async function selectEnvironment(page: Page, control: Locator, value: string) {
  if (!await control.isVisible()) await disclosure(page, '运行环境').click();
  await control.selectOption(value);
}

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
async function setup(page: Page, hub: Hub, {scene: withScene = true, verifiedTask = true} = {}) {
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.clock.install();
  await hub.install(page);
  await page.goto(ORIGIN + '/');
  await expectActive(page, '工作台');
  await page.getByLabel('对话内容').fill('未发送的草稿：分析 phi 场');
  await go(page, '任务');
  await selectEnvironment(page, page.getByLabel('执行节点'), node);
  await selectEnvironment(page, project(page), ws);
  await page.getByRole('button', {name: /解析场验证/}).click();
  await expectActive(page, '任务');
  if (verifiedTask) await expect(page.getByRole('region', {name: '所选任务状态'})).toContainText('已读取 Runtime 状态');
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
  await page.clock.pauseAt(await page.evaluate(() => Date.now()) + 500);
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

    test('Tasks 在查看器中打开 opens 结果 in one click and shows the files it reads', async ({page}) => {
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
      await shortcut(page, '在查看器中打开').click();
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
      hub.artifactRows = [{path: 'scalar-0.vti', size: 10}];
      const errors = await setup(page, hub, {scene: false});
      const fileList = page.getByLabel('结果文件'), log = page.locator('section.analysis details.logs pre');
      await go(page, '结果');
      await expect(fileList.locator('option', {hasText: 'scalar-0.vti'})).toHaveCount(1);
      hub.artifactRows = undefined;
      for (const [label, kind, away] of [['在查看器中打开', 'task.artifacts', '任务'], ['读取日志', 'task.logs', '工作台']] as const) {
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

    test('Tasks 在查看器中打开 keeps the chosen 图谱 mode and its panel', async ({page}) => {
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
      await shortcut(page, '在查看器中打开').click();
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
      await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
      await expect(disclosure(page, '运行环境')).toHaveText('运行环境 · 节点甲 · 项目一');
      await expect(disclosure(page, '新建任务')).toHaveText('新建任务 · 项目一');
      const row = queue(page).getByRole('button', {name: /解析场验证/});
      await expect(row).toBeInViewport({ratio: 1});
      await r.click(row, '任务行');
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      await expect(page.locator('aside.tasks .task-scope')).toHaveText('所选任务 · 节点甲 · 项目一');
      await expect(shortcut(page, '在查看器中打开')).toBeInViewport({ratio: 1});
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-connected-selected.png`)});
      // Initial setup has already folded. The next action opens its own disclosure.
      const at = [await top(queue(page)), await top(status(page))];
      await expect(page.getByLabel('执行节点')).toBeHidden();
      await r.click(disclosure(page, '新建任务'), '展开新建任务');
      await expect(page.getByRole('button', {name: '运行解析场示例'})).toBeEnabled();
      await expect(page.getByLabel('TaskSpec')).toBeVisible();
      expect([await top(queue(page)), await top(status(page))]).toEqual(at);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-connected-folded.png`)});
      await r.click(disclosure(page, '运行环境'), '展开运行环境');
      await expect(page.getByLabel('执行节点')).toHaveValue(node);
      await expect(project(page)).toHaveValue(ws);
      await expect(page.locator('aside.tasks .task.selected')).toHaveText(/解析场验证/);
      sent.stop();
      expect(writes(sent.seen)).toEqual([]);
      expect([...new Set(sent.seen)].sort()).toEqual(['/api/v1/nodes/{node}/read task.artifacts', '/api/v1/nodes/{node}/read task.get']);
      expect(hub.calls).toEqual([]);
      expect(r.record).toMatchObject({clicks: 4, selects: 2});
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
      expect(before).toMatchObject({node, workspace: ws, selected: '解析场验证成功', spec: '{"argv":["python3","draft.py"],"outputs":[]}'});
      const sent = posts(page);
      const r = route(page, `${viewport.name}-established`);
      // Zero clicks: the queue row, the selected task's status and its shortcuts are in view above both disclosures.
      await expect(queue(page).getByRole('button', {name: /解析场验证/})).toBeInViewport({ratio: 1});
      await expect(status(page)).toBeInViewport({ratio: 1});
      await expect(shortcut(page, '读取日志')).toBeInViewport({ratio: 1});
      expect(await top(status(page))).toBeLessThan(await top(disclosure(page, '运行环境')));
      await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
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
      expect(r.record).toMatchObject({clicks: 6, selects: 0});
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
      await selectEnvironment(page, page.getByLabel('执行节点'), node);
      await expect(queue(page).locator('.queue-head')).toHaveText('任务队列节点甲 · 离线 · 全部项目');
      // The whole node is listed while no project is chosen; the selected task shows its own project.
      await queue(page).getByRole('button', {name: /解析场验证/}).click();
      await expect(page.locator('aside.tasks .task-scope')).toHaveText('所选任务 · 节点甲 · 项目一');
      await expect(status(page)).toContainText('暂时无法读取 Runtime 状态');
      await expect(status(page)).toContainText('最近节点快照 · 成功');
      await expect(status(page).locator('.state')).toHaveClass('state succeeded');
      await selectEnvironment(page, project(page), other);
      await expect(queue(page)).toContainText('项目二 中暂无任务，可在下方「新建任务」中提交。');
      await expect(page.locator('aside.tasks .task')).toHaveCount(0);
      await expect(disclosure(page, '运行环境')).toHaveText('运行环境 · 节点甲 · 项目二');
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-offline-empty-project.png`)});
      expect(errors).toEqual([]);
    });

    test('task states match desktop labels while preserving the Runtime observation and result binding', async ({page}) => {
      const hub = new Hub();
      const known = [
        ['preparing', '准备中'], ['queued', '排队中'], ['submitting', '提交中'], ['running', '运行中'],
        ['succeeded', '成功'], ['failed', '失败'], ['cancelled', '已取消'], ['unknown', '待核实'],
        ['verifying', 'verifying'], ['running', '正在取消'],
      ] as const;
      const rows = known.map(([state, label], index) => ({
        ...row, id: state === 'queued' ? task : (index + 1).toString(16).padStart(32, '0'),
        name: state === 'queued' ? row.name : `任务 ${index + 1}`, state,
        cancel_requested: label === '正在取消' || state === 'cancelled',
      }));
      hub.device = {...device, snapshot: {...device.snapshot, tasks: rows}};
      hub.presets = [PRESET];
      const exact = {...row, state: 'running', cancel_requested: true, reason: '运行节点已收到请求',
        updated_at: '2026-11-10T12:01:00.000000Z'};
      hub.taskReadResults.set(task, exact);
      const errors = await start(page, hub);
      await go(page, '任务');
      await selectEnvironment(page, page.getByLabel('执行节点'), node);
      await selectEnvironment(page, project(page), ws);
      const states = queue(page).locator('.task .state');
      await expect(states).toHaveText(known.map(([, label]) => label));
      expect(await states.evaluateAll(items => items.map(item => item.className))).toEqual(known.map(([state]) => `state ${state}`));
      const target = queue(page).getByRole('button', {name: /解析场验证.*排队中/});
      await expect(target).toBeInViewport({ratio: 1});
      const initialScroll = await page.locator('aside.tasks').evaluate(el => el.scrollTop);
      const release = hub.holdNext('task.get');
      const sent = posts(page), measured = route(page, `${viewport.name}-task-state-selection`);
      await measured.click(target, '任务行');
      await expect(status(page)).toContainText('最近节点快照 · 排队中');
      await expect(status(page)).toContainText('正在读取 Runtime 状态');
      release();
      await expect(status(page)).toContainText('最近 Runtime 状态 · 正在取消');
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      await expect(status(page)).toContainText('Runtime 已记录取消请求');
      await expect(status(page)).toContainText('运行节点已收到请求');
      await expect(status(page).locator('.state')).toHaveClass('state running');
      await expect(target).toHaveClass('task selected');
      await expect.poll(() => sent.seen.toSorted()).toEqual([
        '/api/v1/nodes/{node}/read task.artifacts', '/api/v1/nodes/{node}/read task.get',
      ]);
      expect(await page.locator('aside.tasks').evaluate(el => el.scrollTop)).toBe(initialScroll);
      sent.stop();
      expect(measured.record).toMatchObject({clicks: 1, selects: 0});
      measured.save();
      await page.screenshot({path: test.info().outputPath('task-states.png')});

      const refresh = page.locator('aside.tasks .section-title').getByRole('button', {name: '刷新'});
      hub.taskReadResults.set(task, {...exact, state: 'verifying'});
      await refresh.click();
      await expect(status(page)).toContainText('Runtime 状态未确认');
      await expect(status(page)).toContainText('最近 Runtime 状态 · 正在取消');
      hub.taskReadError = 503;
      await refresh.click();
      await expect(status(page)).toContainText('暂时无法读取 Runtime 状态');
      await expect(status(page)).toContainText('最近 Runtime 状态 · 正在取消');
      await expect(target).toHaveClass('task selected');

      await showGraph(page);
      const options = binding(page).locator('option');
      await expect(options).toHaveText(['选择任务', ...rows.map((item, index) =>
        `${item.name} · ${item.id === task ? '正在取消' : known[index][1]}`)]);
      await expect(binding(page)).toHaveValue(task);
      expect(hub.evaluations).toEqual([]);
      expect(unexpected(errors, 503)).toEqual([]);
    });

    test('a long queue keeps the selected task and run environment within reach', async ({page}) => {
      const hub = new Hub();
      const more = Array.from({length: 199}, (_, index) => ({
        ...row, id: (index + 1).toString(16).padStart(32, '0'), name: `额外任务 ${index + 1}`,
      }));
      hub.device = {...device, snapshot: {...device.snapshot, tasks: [row, ...more]}};
      const errors = await start(page, hub);
      await go(page, '任务');
      await selectEnvironment(page, page.getByLabel('执行节点'), node);
      await selectEnvironment(page, project(page), ws);
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
      await disclosure(page, '新建任务').click();
      await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
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
// The chosen file while the build 在查看器中打开 sent for it is still pending.
const loading = (file: string) => `已选 ${file}，正在加载视图…`;
const fileViewMode = (page: Page) => page.getByRole('combobox', {name: '视图', exact: true});
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

    test('an accepted iso build preserves the chosen level for another explicit load', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub, {scene: false});
      await go(page, '结果');
      await page.getByLabel('结果文件').selectOption('scalar-0.vti');
      await fileViewMode(page).selectOption('iso');
      const level = page.getByRole('spinbutton', {name: '等值'}), load = page.getByRole('button', {name: '加载视图'});
      await expect(level).toHaveValue('0');  // Before any view has supplied a midpoint.
      await level.fill('0.25');
      const sent = posts(page);
      await load.click();
      await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
      await expect(footer(page)).toContainText('就绪');
      await expect(level).toHaveValue('0.25');
      await load.click();
      await expect(footer(page)).toContainText('就绪');
      expect(hub.builds.map(build => [build.task_id, build.path, build.options.mode, build.options.level]))
        .toEqual(Array(2).fill([task, 'scalar-0.vti', 'iso', 0.25]));
      expect(writes(sent.seen)).toEqual(Array(2).fill('/api/v1/actions view.build'));
      sent.stop();
      expect(errors).toEqual([]);
    });

    test('a held iso build renders its requested view and keeps the level edited meanwhile', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub);
      await go(page, '结果');
      await fileViewMode(page).selectOption('iso');
      const level = page.getByRole('spinbutton', {name: '等值'}), load = page.getByRole('button', {name: '加载视图'});
      await expect(level).toHaveValue('0.5');  // Seeded by the accepted slice.
      hub.field = 'held-iso';
      const release = hub.hold('view.build');
      try {
        await load.click();
        await expect.poll(() => hub.reached.has('view.build')).toBe(true);
        await expect(title(page)).toHaveText('phi');
        await level.fill('0.75');
      } finally {
        release();
      }
      await expect(title(page)).toHaveText('held-iso');
      await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
      await expect(footer(page)).toContainText('就绪');
      await expect(level).toHaveValue('0.75');
      await load.click();
      await expect(footer(page)).toContainText('就绪');
      expect(hub.builds.slice(1).map(build => [build.task_id, build.path, build.options.level]))
        .toEqual([[task, 'scalar-0.vti', 0.5], [task, 'scalar-0.vti', 0.75]]);
      expect(errors).toEqual([]);
    });

    test('non-iso results seed only an untouched level for the chosen file', async ({page}) => {
      const hub = new Hub();
      hub.later = true;
      const errors = await setup(page, hub);
      await go(page, '结果');
      const mode = fileViewMode(page), level = page.getByRole('spinbutton', {name: '等值'});
      const load = page.getByRole('button', {name: '加载视图'});
      await mode.selectOption('iso');
      await expect(level).toHaveValue('0.5');
      hub.valueRange = [0, 2];
      await load.click();
      await expect(footer(page)).toContainText('就绪');
      await expect(level).toHaveValue('0.5');
      expect(hub.builds[1].options.level).toBe(0.5);

      await mode.selectOption('vectors');
      await load.click();
      await expect(footer(page)).toContainText('就绪');
      await mode.selectOption('iso');
      await expect(level).toHaveValue('1');

      hub.valueRange = [0, 4];
      await mode.selectOption('slice');
      const release = hub.hold('view.build');
      try {
        await load.click();
        await expect.poll(() => hub.reached.has('view.build')).toBe(true);
        await mode.selectOption('iso');
        await level.fill('0.75');
      } finally {
        release();
      }
      await expect(footer(page)).toContainText('就绪');
      await expect(level).toHaveValue('0.75');
      await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));

      await page.getByLabel('结果文件').selectOption('scalar-1.vti');
      await mode.selectOption('slice');
      await load.click();
      await expect(source(page)).toHaveText(shown('显示 scalar-1.vti'));
      await expect(footer(page)).toContainText('就绪');
      await mode.selectOption('iso');
      await expect(level).toHaveValue('2');
      expect(hub.builds.map(build => build.options.mode)).toEqual(['slice', 'iso', 'vectors', 'slice', 'slice']);
      expect(errors).toEqual([]);
    });

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
      await r.click(shortcut(page, '在查看器中打开'), 'Tasks 在查看器中打开');
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
      // Until a graph has actually been shown, the selected task/file are not graph provenance.
      await page.getByRole('tab', {name: '图谱'}).click();
      await expect(source(page)).toHaveText('尚未显示图谱结果，选择数据源并计算图谱');
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
      await selectEnvironment(page, page.getByLabel('执行节点'), node);
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
      await selectEnvironment(page, project(page), ws);
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
      await selectEnvironment(page, page.getByLabel('执行节点'), node);
      await selectEnvironment(page, project(page), ws);
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
      await r.click(shortcut(page, '在查看器中打开'), 'Tasks 在查看器中打开');
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
        ['显示的文件', 'scalar-0.vti'], ['显示的切片', 'Z · 索引 0'], ['已选文件', 'scalar-1.vti尚未加载，点「加载视图」后显示']]);
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
      // Opening 图谱 without an evaluated result reveals no task or file provenance.
      await r.click(page.getByRole('tab', {name: '图谱'}), '图谱');
      await r.click(sourceToggle(page), '来源');
      await expect(sourcePanel(page)).toContainText('尚未显示图谱结果');
      expect(await detailValues(page)).toEqual([]);
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
      await selectEnvironment(page, page.getByLabel('执行节点'), node);
      await selectEnvironment(page, project(page), ws);
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

// Conversation history in the common navigation: below the navigation in the left rail, on demand from the top
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
// The Web and native workbenches use the same logical width for the compact navigation.
const isNarrow = (page: Page) => page.viewportSize()!.width <= 700;
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

    test('conversation column keeps its composer visible while the transcript scrolls', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const messages = Array.from({length: 36}, (_, i) =>
        say(`layout-${i}`, i % 2 ? 'assistant' : 'user', i === 3 ? 'grid_index_'.repeat(45) : `核对第 ${i + 1} 个网格结果`));
      hub.saved.set(A, messages);
      await hub.install(page);
      const sent = posts(page);
      await page.goto(ORIGIN + '/');
      await expectActive(page, '工作台');

      const chat = page.locator(surfaces.工作台);
      const log = chat.getByRole('log', {name: '对话记录'});
      const input = draft(page), send = sendButton(page), composer = chat.locator('.chat-composer');
      await expect.soft(chat.getByRole('heading')).toHaveText('新对话 · 未保存');
      await expect.soft(chat.locator('.chat-intro')).toHaveText('从一个科学问题开始');
      await expect(send).toBeDisabled();
      const bounds = async () => ({chat: (await chat.boundingBox())!, log: (await log.boundingBox())!,
        composer: (await composer.boundingBox())!, input: (await input.boundingBox())!, send: (await send.boundingBox())!});
      const empty = await bounds();
      const rail = isNarrow(page) ? 0 : 144;
      const width = Math.min(viewport.width - rail, 880);
      expect(empty.chat.width).toBe(width);
      expect(empty.chat.x).toBe((viewport.width - rail - width) / 2 + rail);
      expect(empty.log.x).toBe(empty.composer.x);
      expect(empty.log.width).toBe(empty.composer.width);
      expect.soft(empty.send.width).toBeLessThan(110);
      expect(empty.send.x + empty.send.width).toBe(empty.composer.x + empty.composer.width - 9);
      expect(empty.send.y + empty.send.height).toBeLessThan(empty.composer.y + empty.composer.height);
      expect(empty.chat.y + empty.chat.height - empty.composer.y - empty.composer.height).toBeGreaterThan(80);
      expect(empty.composer.y - empty.log.y - empty.log.height).toBeLessThan(32);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-conversation-empty.png`)});

      await choose(page, /相场参数讨论/);
      await shows(page, messages.map(message => message.content));
      await expect(label(page)).toHaveText('相场参数讨论');
      await expect(label(page)).toHaveAttribute('title', `相场参数讨论 · ${A.slice(0, 6)}`);
      const transcript = (await log.boundingBox())!;
      const user = (await log.locator('article.user').first().boundingBox())!;
      const assistant = (await log.locator('article.assistant').first().boundingBox())!;
      expect(user.x + user.width).toBeCloseTo(transcript.x + transcript.width, 0);
      expect(user.width).toBeLessThanOrEqual(transcript.width * 0.85 + 1);
      expect(assistant.x).toBe(transcript.x);
      expect(assistant.width).toBeGreaterThan(user.width);
      await input.fill('待核对的网格');
      await expect(composer).toHaveCSS('border-top-color', 'rgb(126, 156, 216)');
      await input.press('End');
      await input.press('Enter');
      await expect(input).toHaveValue('待核对的网格\n');
      expect(sent.seen).toEqual([]);
      const readingBounds = await bounds();
      await log.hover();
      await page.mouse.wheel(0, 520);
      const offset = () => log.evaluate(el => el.scrollTop);
      await expect.poll(offset).toBeGreaterThan(0);
      expect.soft(await log.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
      expect(await chat.evaluate(el => el.scrollTop)).toBe(0);
      expect(await page.evaluate(() => scrollY)).toBe(0);
      const reading = await offset();
      expect(readingBounds.chat.y + readingBounds.chat.height - readingBounds.composer.y - readingBounds.composer.height)
        .toBeLessThanOrEqual(24);
      expect((await bounds()).composer).toEqual(readingBounds.composer);
      expect((await bounds()).input).toEqual(readingBounds.input);
      expect((await bounds()).send).toEqual(readingBounds.send);
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-conversation-reading.png`)});

      await go(page, '任务');
      await go(page, '工作台');
      await expect(input).toHaveValue('待核对的网格\n');
      expect(await offset()).toBe(reading);
      expect((await bounds()).composer).toEqual(readingBounds.composer);
      expect((await bounds()).input).toEqual(readingBounds.input);
      expect((await bounds()).send).toEqual(readingBounds.send);
      expect(sent.seen).toEqual([]);
      await input.focus();
      await page.keyboard.press('Tab');
      await expect(send).toBeFocused();
      await page.keyboard.press('Enter');
      await expect.poll(() => hub.messages.map(message => [message.session, message.content])).toEqual([[A, '待核对的网格\n']]);
      expect(sent.seen).toHaveLength(1);
      sent.stop();
      writeFileSync(test.info().outputPath('conversation-layout.json'), JSON.stringify({
        viewport: page.viewportSize(), initial: '工作台 · 新对话 · 未保存', empty, reading,
        historyClicks: isNarrow(page) ? 2 : 1, navigationClicks: 2, sendKey: 'Enter on focused 发送',
        postCountBeforeSend: 0, postCountAfterSend: sent.seen.length,
      }, null, 2));
    });

    test('associated tasks read only the current conversation and return focus to its entry', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const taskId = '1'.repeat(32), actionId = '2'.repeat(32);
      hub.conversationTasks.set(A, [{
        message_id: '3'.repeat(32), action_id: actionId, node_id: '4'.repeat(32),
        workspace_id: '5'.repeat(32), state: 'succeeded', task_id: taskId,
      },{
        message_id: '3'.repeat(32), action_id: '6'.repeat(32), node_id: '4'.repeat(32),
        workspace_id: '5'.repeat(32), state: 'rejected', task_id: null,
      }]);
      await setup(page, hub);
      const sent = posts(page);
      await go(page, '工作台');
      const launcher = page.getByRole('button', {name: '关联任务'});
      await expect(launcher).toHaveCount(0);
      await choose(page, /相场参数讨论/);
      await draft(page).fill('保留未发送草稿');
      const before = await state(page);
      await expect(launcher).toBeVisible();
      expect(hub.calls).toEqual([`history ${A}`]);
      const bytes = Buffer.alloc(327, 42);
      const sha256 = createHash('sha256').update(bytes).digest('hex');
      const log = Buffer.from('First line\n<img src=x onerror="window.untrustedPreview=true">\n');
      const logDigest = createHash('sha256').update(log).digest('hex');
      hub.conversationFiles.set(`${A} ${actionId}`, {id: A, action_id: actionId, task_id: taskId, more: false,
        files: [{path: 'case/result.h5', size: 327, sha256},
          {path: 'case/run.log', size: log.length, sha256: logDigest}]});
      let wrongBytes = true;
      const downloadQueries: string[] = [];
      await page.route(`**/api/v1/sessions/${A}/tasks/${actionId}/file?*`, route => {
        const url = new URL(route.request().url());
        downloadQueries.push(url.search);
        return route.fulfill({status: 200, contentType: 'application/octet-stream',
          body: url.searchParams.get('path') === 'case/run.log' ? log : wrongBytes ? Buffer.alloc(327, 41) : bytes});
      });
      await launcher.click();
      const panel = page.getByRole('dialog', {name: '关联任务'});
      await expect(panel).toContainText(taskId);
      await expect(panel).toContainText('复核未通过');
      await expect(panel.getByRole('button', {name: '关闭'})).toBeFocused();
      expect(hub.calls).toEqual([`history ${A}`, `tasks ${A}`]);
      const filesLauncher = panel.getByRole('button', {name: '查看文件'});
      await filesLauncher.click();
      const files = page.getByRole('dialog', {name: '发布文件'});
      await expect(files).toContainText('case/result.h5');
      await expect(files).toContainText('327 字节');
      const back = files.getByRole('button', {name: '返回关联任务'});
      await expect(back).toBeFocused();
      const download = files.getByRole('button', {name: '下载 case/result.h5'});
      await download.click();
      await expect(files.getByRole('alert')).toContainText('文件摘要与发布记录不符');
      wrongBytes = false;
      const downloaded = page.waitForEvent('download');
      await download.click();
      const saved = await downloaded;
      expect(saved.suggestedFilename()).toBe('result.h5');
      expect(readFileSync((await saved.path())!)).toEqual(bytes);
      expect(downloadQueries).toEqual(Array(2).fill('?' + new URLSearchParams({path: 'case/result.h5', sha256})));
      await expect(files.getByRole('button', {name: '预览 case/result.h5'})).toHaveCount(0);
      const preview = files.getByRole('button', {name: '预览 case/run.log'});
      await preview.click();
      const previewPanel = page.getByRole('dialog', {name: '文件预览'});
      await expect(previewPanel.getByRole('heading', {name: 'case/run.log'})).toBeFocused();
      expect(await previewPanel.getByLabel('文件内容').textContent()).toBe(log.toString());
      await expect(previewPanel.locator('img')).toHaveCount(0);
      await expect(previewPanel.getByRole('button', {name: '返回关联任务'})).toHaveCount(0);
      await expect(previewPanel.getByRole('button', {name: '关闭'})).toBeVisible();
      await previewPanel.screenshot({path: test.info().outputPath('conversation-file-preview.png')});
      await previewPanel.getByRole('button', {name: '返回发布文件'}).click();
      await expect(preview).toBeFocused();
      expect(downloadQueries[2]).toBe('?' + new URLSearchParams({path: 'case/run.log', sha256: logDigest}));
      await files.screenshot({path: test.info().outputPath('conversation-files.png')});
      await back.click();
      await expect(filesLauncher).toBeFocused();
      const releaseFiles = hub.holdNext(`files ${A} ${actionId}`);
      await filesLauncher.click();
      await expect(files.getByRole('status')).toContainText('正在读取文件');
      await expect.poll(() => hub.reached.has(`files ${A} ${actionId}`)).toBe(true);
      await back.click();
      releaseFiles();
      await expect(filesLauncher).toBeFocused();
      await expect(panel).not.toContainText('case/result.h5');
      await page.keyboard.press('Escape');
      await expect(panel).toHaveCount(0);
      await expect(launcher).toBeFocused();
      await expect(draft(page)).toHaveValue('保留未发送草稿');
      expect(await state(page)).toEqual(before);
      await choose(page, /铁电回线分析/);
      await launcher.click();
      await expect(panel.getByRole('alert')).toContainText('未提供此对话的任务列表');
      await expect(panel).not.toContainText(taskId);
      await panel.getByRole('button', {name: '关闭'}).click();
      await expect(launcher).toBeFocused();
      expect(hub.calls).toEqual([`history ${A}`, `tasks ${A}`, `files ${A} ${actionId}`, `files ${A} ${actionId}`,
        `history ${B}`, `tasks ${B}`]);
      const release = hub.holdNext(`tasks ${B}`);
      await launcher.click();
      await expect(panel.getByRole('status')).toContainText('正在读取');
      await expect.poll(() => hub.reached.has(`tasks ${B}`)).toBe(true);
      await page.keyboard.press('Escape');
      release();
      await expect(launcher).toBeFocused();
      await choose(page, /相场参数讨论/);
      await expect(panel).toHaveCount(0);
      await expect(draft(page)).toHaveValue('保留未发送草稿');
      expect(sent.seen).toEqual([]);
      sent.stop();
      writeFileSync(test.info().outputPath('conversation-files.json'), JSON.stringify({
        viewport: page.viewportSize(), openTasksClicks: 1, openFilesClicks: 1, openPreviewClicks: 1,
        returnToFilesClicks: 1, returnToTasksClicks: 1,
        closeTasksKey: 'Escape', requests: hub.calls, posts: sent.seen,
      }, null, 2));
    });

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
          // Navigation and history share a rail to the left of the active section.
          await expect(page.getByRole('region', {name: '对话历史'})).toBeVisible();
          expect(await historyPanel(page).evaluate(el => (el as HTMLElement).inert)).toBe(false);
          await expect(historyToggle(page)).toHaveCount(0);
          const rail = (await nav(page).boundingBox())!, column = (await historyPanel(page).boundingBox())!;
          expect([rail.x, rail.width, column.x, column.width]).toEqual([0, 144, 0, 144]);
          expect(column.y).toBe(rail.y + rail.height);
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
      await expect(page.locator('aside.chat .conversation-name')).toHaveText('相场参数讨论');
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
      await expect(page.locator('aside.chat .conversation-name')).toHaveText('铁电回线分析');
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
          await expect(page.locator('aside.chat .conversation-name')).toHaveText('铁电回线分析');
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
      await expect(page.locator('aside.chat .conversation-name')).toHaveText('新会话');
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

    test('history restores each conversation reading position', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      hub.rows.push({id: X, name: '晶格变化记录', created: ++clock});
      const longThread = (prefix: string) => Array.from({length: 60}, (_, i) =>
        say(`${prefix}-${i}`, i % 2 === 0 ? 'user' : 'assistant', `${prefix} 段落 ${i}`));
      const first = longThread('A'), third = longThread('C');
      hub.saved.set(A, first);
      hub.saved.set(X, third);
      await hub.install(page);
      const sent = posts(page);
      await page.goto(ORIGIN + '/');
      await expectActive(page, '工作台');

      const log = page.getByRole('log', {name: '对话记录'});
      const position = () => log.evaluate(el => el.scrollTop);
      const scroll = (top: number) => log.evaluate((el, value) => {el.scrollTop = value;}, top);
      await choose(page, /相场参数讨论/);
      await shows(page, first.map(m => m.content));
      expect(await position()).toBe(0);
      await draft(page).fill('A 的草稿');
      await scroll(560);
      expect(await position()).toBe(560);
      await choose(page, /相场参数讨论/);
      expect(await position()).toBe(560);
      await go(page, '任务');
      await go(page, '结果');
      await go(page, '工作台');
      expect(await position()).toBe(560);

      await choose(page, /铁电回线分析/);
      await shows(page, ['B 的问题']);
      expect(await position()).toBe(0);
      await choose(page, /相场参数讨论/);
      await shows(page, first.map(m => m.content));
      await expect(draft(page)).toHaveValue('A 的草稿');
      expect(await position()).toBe(560);
      if (isNarrow(page)) await expect(log).toBeFocused();

      await go(page, '任务');
      await choose(page, /晶格变化记录/);
      await shows(page, third.map(m => m.content));
      expect(await position()).toBe(0);
      await scroll(880);
      expect(await position()).toBe(880);
      // The cached A transcript gets its position immediately. Leaving aborts its read and restores C instead.
      const release = hub.holdNext(`history ${A}`);
      await choose(page, /相场参数讨论/);
      await expect.poll(() => hub.reached.has(`history ${A}`)).toBe(true);
      expect(await position()).toBe(560);
      const cancelled = page.waitForEvent('requestfailed', request => new URL(request.url()).pathname === `/api/v1/sessions/${A}/history`);
      await choose(page, /晶格变化记录/);
      release();
      await cancelled;
      await shows(page, third.map(m => m.content));
      expect(await position()).toBe(880);

      if (isNarrow(page)) await historyToggle(page).click();
      await historyPanel(page).getByRole('button', {name: '新对话', exact: true}).click();
      expect(await position()).toBe(0);
      await expect(draft(page)).toBeFocused();
      await expect(draft(page)).toHaveValue('');

      await page.getByRole('button', {name: '断开', exact: true}).click();
      await page.getByText('使用已有设备凭据', {exact: true}).click();
      await page.getByLabel('设备凭据', {exact: true}).fill('abcdefghijklmnopqrstu');
      await page.getByRole('button', {name: '连接', exact: true}).click();
      await expectActive(page, '工作台');
      await choose(page, /相场参数讨论/);
      await shows(page, first.map(m => m.content));
      expect(await position()).toBe(0);
      await expect(draft(page)).toHaveValue('');
      expect(hub.calls).toEqual([A, A, B, A, X, A, X, A].map(id => `history ${id}`));
      expect(sent.seen).toEqual([]);
      sent.stop();
    });

    test('the composer can return keyboard focus to the saved transcript', async ({page}) => {
      const hub = new Hub();
      conversations(hub);
      const messages = Array.from({length: 60}, (_, index) =>
        say(`read-${index}`, index % 2 ? 'assistant' : 'user', `已保存段落 ${index}`));
      hub.saved.set(A, messages);
      await hub.install(page);
      const sent = posts(page);
      await page.goto(ORIGIN + '/');
      await choose(page, /相场参数讨论/);
      await shows(page, messages.map(message => message.content));

      const log = page.getByRole('log', {name: '对话记录'});
      const position = () => log.evaluate(element => element.scrollTop);
      await draft(page).fill('保留的草稿');
      await page.keyboard.press('Shift+Tab');
      await expect(log).toBeFocused();
      await page.keyboard.press('PageDown');
      await expect.poll(position).toBeGreaterThan(100);
      await page.keyboard.press('End');
      await expect.poll(() => log.evaluate(element =>
        Math.abs(element.scrollHeight - element.clientHeight - element.scrollTop))).toBeLessThanOrEqual(1);
      await page.keyboard.press('Tab');
      await expect(draft(page)).toBeFocused();
      await expect(draft(page)).toHaveValue('保留的草稿');
      const readingPosition = await position();
      await go(page, '任务');
      await go(page, '工作台');
      expect(await position()).toBe(readingPosition);
      expect(hub.calls).toEqual([`history ${A}`]);
      expect(sent.seen).toEqual([]);
      sent.stop();
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
      await shortcut(page, '在查看器中打开').click();
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
      await expect(label(page)).toHaveText('新会话');
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
      await expect(label(page)).toHaveText('铁电回线分析');
      await expect(sendButton(page)).toBeEnabled();
      await expect(draft(page)).toHaveValue('B 的草稿');
      // A proxy's 404 page for a listed conversation: a read failure with 重新读取, and A is not sendable yet.
      hub.historyFault = 'proxy';
      await choose(page, /相场参数讨论/);
      await expect(failed).toContainText('请求失败 (404)');
      await expect(label(page)).toHaveText('相场参数讨论');
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
      await expect(label(page)).toHaveText('旧列表中的对话');
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
      await expect(label(page)).toHaveText('新会话');
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
      await expect(label(page)).toHaveText('新会话');
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
      await expect(label(page)).toHaveText('新会话');
      late();
      await expect(footer(page)).toContainText('就绪');
      await page.waitForTimeout(300);
      expect(await transcript(page)).toEqual(['第二个对话', '回复：第二个对话']);
      await expect(label(page)).toHaveText('新会话');
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

test('at the native rail breakpoint, history moves from the left rail to the top navigation', async ({page}) => {
  await page.setViewportSize({width: 701, height: 844});
  const hub = new Hub();
  conversations(hub);
  const errors = await setup(page, hub, {scene: false});
  await expect(historyToggle(page)).toHaveCount(0);
  const rail = (await nav(page).boundingBox())!;
  const history = (await historyPanel(page).boundingBox())!;
  const tasks = await box(page, 'aside.tasks');
  expect([rail.x, rail.width, history.x, history.width, history.y]).toEqual([0, 144, 0, 144, rail.y + rail.height]);
  expect(tasks.x).toBeGreaterThanOrEqual(144);
  await item(page, /相场参数讨论/).click();
  await shows(page, ['A 的问题', 'A 的回答']);
  await go(page, '任务');
  await page.setViewportSize({width: 700, height: 844});
  const strip = (await nav(page).boundingBox())!;
  expect([strip.x, strip.width]).toEqual([0, 700]);
  expect((await box(page, 'aside.tasks')).y).toBe(strip.y + strip.height);
  await expect(historyPanel(page)).toBeHidden();
  await historyToggle(page).click();
  await expect(item(page, /相场参数讨论/)).toBeInViewport({ratio: 1});
  await page.keyboard.press('Escape');
  await expect(historyToggle(page)).toBeFocused();
  await choose(page, /新对话.*有草稿/);
  await expectActive(page, '工作台');
  await expect(draft(page)).toHaveValue('未发送的草稿：分析 phi 场');
  expect(hub.calls).toEqual([`history ${A}`]);
  expect(hub.messages).toEqual([]);
  expect(hub.actionRows).toEqual([]);
  expect(errors).toEqual([]);
});

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
  const controls = (await historyPanel(page).locator('.history-controls').boundingBox())!;
  expect(controls.y).toBeGreaterThanOrEqual(panel.y);
  expect(row.y).toBeGreaterThanOrEqual(controls.y + controls.height);
  expect(row.y + row.height).toBeLessThanOrEqual(panel.y + panel.height);
  expect(await historyPanel(page).evaluate(el => el.scrollTop)).toBeGreaterThan(0);
  await historyPanel(page).getByRole('button', {name: '新对话', exact: true}).click();
  await expect(draft(page)).toBeFocused();
  expect(hub.messages).toHaveLength(0);
  expect(errors).toEqual([]);
});

for (const viewport of [{width: 1440, height: 900}, {width: 390, height: 844}]) {
  test(`history search opens an older conversation from its title at ${viewport.width}px`, async ({page}) => {
    await page.setViewportSize(viewport);
    const hub = new Hub();
    conversations(hub);
    for (let i = 0; i < 30; i++) {
      hub.rows.push({id: (0x100 + i).toString(16).padStart(32, '0'), name: `近期记录 ${i}`, created: 1794830600 + i});
    }
    await setup(page, hub);
    await choose(page, /铁电回线分析/);
    await shows(page, ['B 的问题']);
    await draft(page).fill('当前未发送草稿');
    const before = await work(page);
    const sent = posts(page);
    await go(page, '任务');
    if (isNarrow(page)) await historyToggle(page).click();
    const initialCount = await entries(page).count();
    expect(initialCount).toBe(33); // 32 saved conversations and the initial local draft.
    const search = historyPanel(page).getByRole('searchbox', {name: '搜索对话'});
    await search.click();
    await search.fill('没有匹配的标题');
    await expect(historyPanel(page).getByRole('status')).toContainText('没有匹配的对话');
    await search.press('Enter');
    await search.fill('近期');
    await expect(entries(page)).toHaveCount(30);
    await search.press('Enter');
    await expectActive(page, '任务', {covered: isNarrow(page)});
    expect(hub.calls).toEqual([`history ${B}`]);
    await search.fill('相场 讨论');
    await expect(entries(page)).toHaveCount(1);
    await page.screenshot({path: test.info().outputPath('history-search.png')});
    await search.press('Enter');
    await expectActive(page, '工作台');
    await expect(page.getByRole('log', {name: '对话记录'})).toBeFocused();
    await expect(label(page)).toContainText('相场参数讨论');
    expect(hub.calls).toEqual([`history ${B}`, `history ${A}`]);
    expect(await work(page)).toEqual(before);
    if (isNarrow(page)) await historyToggle(page).click();
    await expect(search).toHaveValue('相场 讨论');
    await search.fill('');
    await expect(entries(page)).toHaveCount(initialCount);
    await item(page, /铁电回线分析/).click();
    await expect(draft(page)).toHaveValue('当前未发送草稿');
    expect(sent.seen).toEqual([]);
    sent.stop();
    writeFileSync(test.info().outputPath('history-search.json'), JSON.stringify({
      viewport, initial: '任务页 · 已打开 B · B 有未发送草稿 · 历史含 32 条',
      openHistoryClicks: isNarrow(page) ? 1 : 0, searchClicks: 1, selectKeys: ['Enter'],
      historyReads: hub.calls, posts: sent.seen,
    }, null, 2));
  });
}

for (const viewport of [{width: 1440, height: 900}, {width: 390, height: 844}]) {
  test(`explicit send follows new messages until the reader scrolls away at ${viewport.width}px`, async ({page}) => {
    await page.setViewportSize(viewport);
    const hub = new Hub();
    conversations(hub);
    const long = (prefix: string) => Array.from({length: 60}, (_, index) =>
      say(`${prefix}-${index}`, index % 2 ? 'assistant' : 'user', `${prefix} 已保存段落 ${index}`));
    hub.saved.set(A, long('A'));
    hub.saved.set(B, long('B'));
    await setup(page, hub, {scene: false});
    await choose(page, /相场参数讨论/);
    const log = page.getByRole('log', {name: '对话记录'});
    const follow = page.getByRole('button', {name: '跟随最新', exact: true});
    const top = () => log.evaluate(el => el.scrollTop);
    const remaining = () => log.evaluate(el => el.scrollHeight - el.clientHeight - el.scrollTop);
    const input = draft(page);
    await expect(log.locator('article')).toHaveCount(60);
    expect(await top()).toBe(0);
    await expect(follow).toBeVisible();
    await input.fill('检查本次网格');
    const initial = await input.boundingBox();
    const release = hub.holdNext(`send ${A}`);
    await input.press('Control+Enter');
    await expect.poll(remaining).toBeLessThanOrEqual(1);
    await expect(log.getByText('检查本次网格')).toBeInViewport();
    expect(await input.boundingBox()).toEqual(initial);
    await log.evaluate(el => { el.scrollTop = 520; });
    await expect(follow).toBeVisible();
    const reading = await top();
    expect(reading).toBe(520);
    release();
    await expect.poll(() => hub.messages.length).toBe(1);
    await expect(log.locator('article')).toHaveCount(62);
    expect(await top()).toBe(reading);
    await follow.click();
    await expect.poll(remaining).toBeLessThanOrEqual(1);
    await expect(log).toBeFocused();
    await expect(follow).toHaveCount(0);

    await input.fill('等待中的下一条');
    const releaseLater = hub.holdNext(`send ${A}`);
    await sendButton(page).click();
    await expect(log.getByText('等待中的下一条')).toBeInViewport();
    const beforeSwitch = await top();
    await choose(page, /铁电回线分析/);
    await expect(log.locator('article')).toHaveCount(60);
    await log.evaluate(el => { el.scrollTop = 430; });
    releaseLater();
    await expect.poll(() => hub.messages.length).toBe(2);
    expect(await top()).toBe(430);
    await expect(follow).toBeVisible();
    await choose(page, /相场参数讨论/);
    await expect(log.locator('article')).toHaveCount(64);
    expect(await top()).toBe(beforeSwitch);
  });

  test(`a saved conversation can jump to its latest message before any send at ${viewport.width}px`, async ({page}) => {
    await page.setViewportSize(viewport);
    const hub = new Hub();
    conversations(hub);
    const messages = Array.from({length: 60}, (_, index) =>
      say(`jump-${index}`, index % 2 ? 'assistant' : 'user', `已保存段落 ${index}`));
    hub.saved.set(A, messages);
    await setup(page, hub, {scene: false});
    const sent = posts(page);
    const log = page.getByRole('log', {name: '对话记录'});
    const follow = page.getByRole('button', {name: '跟随最新', exact: true});
    const last = log.getByText('已保存段落 59', {exact: true});

    await choose(page, /相场参数讨论/);
    await expect(log.locator('article')).toHaveCount(messages.length);
    await expect(last).not.toBeInViewport();
    await draft(page).fill('未发送草稿');
    await follow.click();
    await expect(last).toBeInViewport();
    await expect(follow).toHaveCount(0);
    await expect(log).toBeFocused();
    await expect(draft(page)).toHaveValue('未发送草稿');

    await log.press('PageUp');
    await expect(last).not.toBeInViewport();
    await expect(follow).toBeVisible();
    await log.press('Shift+Tab');
    await expect(follow).toBeFocused();
    await follow.press('Enter');
    await expect(last).toBeInViewport();
    await expect(log).toBeFocused();
    await log.press('PageUp');
    await expect(last).not.toBeInViewport();
    await choose(page, /铁电回线分析/);
    await expect(log.getByText('B 的问题')).toBeVisible();
    await expect(follow).toHaveCount(0);
    await choose(page, /相场参数讨论/);
    await expect(follow).toBeVisible();
    await expect(last).not.toBeInViewport();
    await expect(draft(page)).toHaveValue('未发送草稿');
    expect(hub.calls).toEqual([`history ${A}`, `history ${B}`, `history ${A}`]);
    expect(sent.seen).toEqual([]);
    sent.stop();
  });

  test(`conversation shortcut sends once and retains composer focus at ${viewport.width}px`, async ({page}) => {
    await page.setViewportSize(viewport);
    const hub = new Hub();
    conversations(hub);
    await setup(page, hub, {scene: false});
    await choose(page, /相场参数讨论/);
    const input = draft(page);
    const sent = posts(page);
    await input.fill('检查网格');
    await input.press('Enter');
    await expect(input).toHaveValue('检查网格\n');
    await input.dispatchEvent('keydown', {key: 'Enter', ctrlKey: true, isComposing: true});
    await input.dispatchEvent('keydown', {key: 'Enter', ctrlKey: true, repeat: true});
    expect(sent.seen).toEqual([]);
    const release = hub.holdNext(`send ${A}`);
    await input.press('Control+Enter');
    await expect(input).toBeFocused();
    await expect(input).toHaveValue('');
    await expect.poll(() => hub.reached.has(`send ${A}`)).toBe(true);
    await input.fill('留在这里的第二份草稿');
    await input.press('Control+Enter');
    expect(sent.seen).toHaveLength(1);
    release();
    await expect.poll(() => hub.messages.map(message => message.content)).toEqual(['检查网格\n']);
    await expect(input).toHaveValue('留在这里的第二份草稿');
    await expect(input).toBeFocused();
    sent.stop();
  });
}

test('wide history keyboard activation enters the transcript without tabbing through other conversations', async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  const hub = new Hub();
  conversations(hub);
  for (let i = 0; i < 30; i++) {
    hub.rows.push({id: (0x100 + i).toString(16).padStart(32, '0'), name: `较早的对话 ${i}`, created: 1794830300 - i});
  }
  const messages = Array.from({length: 60}, (_, i) =>
    say(`read-${i}`, i % 2 ? 'assistant' : 'user', `已保存段落 ${i}`));
  hub.saved.set(A, messages);
  await hub.install(page);
  const sent = posts(page);
  await page.goto(ORIGIN + '/');

  const first = item(page, /相场参数讨论/), second = item(page, /铁电回线分析/);
  const log = page.getByRole('log', {name: '对话记录'});
  const position = () => log.evaluate(el => el.scrollTop);
  const railPosition = () => historyPanel(page).evaluate(el => el.scrollTop);
  await first.click();
  await shows(page, messages.map(message => message.content));
  await expect(first).toBeFocused(); // Pointer selection still lets the user browse the rail.
  await draft(page).fill('保留的草稿');
  await log.evaluate(el => { el.scrollTop = 560; });
  await second.click();
  await shows(page, ['B 的问题']);
  await expect(entries(page)).toHaveCount(32);
  await historyPanel(page).evaluate(el => { el.scrollTop = el.scrollHeight; });
  const header = (await historyPanel(page).locator('.history-controls').boundingBox())!;
  const rail = (await historyPanel(page).boundingBox())!;
  expect(header.y).toBeGreaterThanOrEqual(rail.y);
  expect(header.y + header.height).toBeLessThan(rail.y + rail.height);
  await historyPanel(page).getByRole('button', {name: '新对话', exact: true}).click({trial: true});
  await historyPanel(page).evaluate(el => { el.scrollTop = 0; });
  await go(page, '任务');

  await first.focus();
  const railTop = await railPosition();
  await page.keyboard.press('Enter');
  await expectActive(page, '工作台');
  await expect(log).toBeFocused();
  await expect(draft(page)).toHaveValue('保留的草稿');
  expect(await position()).toBe(560);
  await page.keyboard.press('PageDown');
  await expect.poll(position).toBeGreaterThan(560);
  expect(await railPosition()).toBe(railTop);

  await go(page, '任务');
  await second.evaluate(element => (element as HTMLButtonElement).click()); // Activation without pointer detail.
  await shows(page, ['B 的问题']);
  await expect(log).toBeFocused();
  expect(hub.calls).toEqual([A, B, A, B].map(id => `history ${id}`));
  expect(sent.seen).toEqual([]);
  sent.stop();
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
      expect(graphSource[0]).toBe('显示的三维结果，场视图 · 解析场验证 · 第 1000 步');
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
      const fileRows = [['节点', `节点甲${node}`], ['项目', `项目一${ws}`], ['任务', `解析场验证${task}`], ['显示的文件', 'scalar-0.vti'], ['显示的切片', 'Z · 索引 0']];
      const graphRows = [
        ['显示内容', '显示的三维结果'], ['图谱预设', '场视图field-view'], ['输出', 'main'], ['节点', '节点甲' + node],
        ['计算绑定 field', '解析场验证' + task], ['运行工作区 field', '项目一' + ws], ['已显示时间步', '1000'],
      ];
      expect(await rows()).toEqual(fileRows);
      await modeTab(page, '图谱').click();
      await computeGraph(page, hub);
      await expect(source(page)).toHaveText(graphSourceA);
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
      await selectEnvironment(page, page.getByLabel('执行节点'), node2);
      await expect(graphPane(page)).toHaveCount(0);
      release();
      await page.waitForTimeout(500);
      await selectEnvironment(page, page.getByLabel('执行节点'), node);
      await selectEnvironment(page, project(page), ws);
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
      await selectEnvironment(page, project(page), '');
      await selectEnvironment(page, project(page), ws);
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
      await selectEnvironment(page, page.getByLabel('执行节点'), node2);
      await expect(graphPane(page)).toHaveCount(0);
      await selectEnvironment(page, page.getByLabel('执行节点'), node);
      await selectEnvironment(page, project(page), ws);
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
  await selectEnvironment(page, project(page), id);
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
      await selectEnvironment(page, page.getByLabel('执行节点'), node);
      await selectEnvironment(page, project(page), ws);
      // In 项目一, no task selected: a task bound by hand in 图谱 and computed; the node queues it.
      await showGraph(page);
      await expect(source(page)).toHaveText('尚未显示图谱结果，选择数据源并计算图谱');
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
      await selectEnvironment(page, page.getByLabel('执行节点'), node);
      await selectEnvironment(page, project(page), ws2);
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
      await selectEnvironment(page, page.getByLabel('执行节点'), node);
      await selectEnvironment(page, project(page), ws);
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
      await selectEnvironment(page, page.getByLabel('执行节点'), node);
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
      await selectEnvironment(page, page.getByLabel('执行节点'), node2);
      await expect(graphPane(page)).toHaveCount(0);
      await page.waitForTimeout(500);
      await selectEnvironment(page, page.getByLabel('执行节点'), node);
      await selectEnvironment(page, project(page), ws);
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

// 任务 → 结果 → 任务 through a Tasks shortcut, as in the native focused workbench: the rail's 任务 straight from 结果
// gives the keyboard focus back to the shortcut that opened it while the same task scope is selected and the shortcut
// is there, enabled and wholly in view. 任务 keeps both scroll offsets, the queue and the draft; 结果 keeps its mode
// and Viewer. Every other way back (plain rail trips, 工作台 or history, another scope, a removed, busy or clipped
// shortcut) leaves the focus on the rail, and a late read never moves it.
const longQueue = {...device, snapshot: {...device.snapshot, tasks: [row, ...Array.from({length: 199}, (_, index) => ({
  ...row, id: (index + 1).toString(16).padStart(32, '0'), name: `额外任务 ${index + 1}`,
}))]}};
const railButton = (page: Page, name: keyof typeof surfaces) => nav(page).getByRole('button', {name, exact: true});
const offsets = (page: Page) => page.locator('aside.tasks').evaluate(el =>
  ({tasks: el.scrollTop, queue: el.querySelector('.task-list')!.scrollTop}));
const focused = (page: Page) => page.evaluate(() => {
  const element = document.activeElement as HTMLElement | null;
  return element ? `${element.closest('nav,aside,section')?.className.split(' ')[0] ?? ''} ${element.tagName} ${element.textContent}` : '';
});
// The queue scrolled inside its own list and 任务 scrolled to centre the shortcuts (a nonzero offset where 任务 overflows).
async function place(page: Page) {
  await queue(page).locator('.task-list').evaluate(el => { el.scrollTop = 160; });
  await page.locator('aside.tasks').evaluate(el => {
    const at = [...el.querySelectorAll('.inline > button')].find(b => b.textContent === '在查看器中打开')!.getBoundingClientRect();
    const area = el.getBoundingClientRect();
    el.scrollTop += at.top + at.height / 2 - (area.top + area.height / 2);
  });
  const at = await offsets(page);
  expect(at.queue).toBe(160);
  for (const name of ['在查看器中打开', '读取日志'] as const) await expect(shortcut(page, name)).toBeInViewport({ratio: 1});
  return at;
}
// Pixels of the scrolled queue and of the unsubmitted TaskSpec (apart from the shortcut, whose focus ring may differ).
async function tasksPixels(page: Page, name: string) {
  return [await queue(page).locator('.task-list').screenshot({path: test.info().outputPath(`queue-${name}.png`)}),
    await page.getByLabel('TaskSpec').screenshot({path: test.info().outputPath(`taskspec-${name}.png`)})];
}
type How = 'pointer' | 'Enter' | 'Space';
// Measured activations of one route, apart from its setup: real pointer clicks at the target's centre, or keys on it.
function measured(page: Page, name: string) {
  const record = {route: name, clicks: 0, keys: 0, steps: [] as string[]};
  return {
    record,
    activate: async (target: Locator, how: How, step: string) => {
      record.steps.push(`${how} ${step}`);
      if (how === 'pointer') {
        record.clicks++;
        const at = (await target.boundingBox())!;
        await page.mouse.click(at.x + at.width / 2, at.y + at.height / 2);
        return;
      }
      record.keys++;
      await target.evaluate(el => (el as HTMLElement).focus({preventScroll: true}));
      if (how === 'Enter') { await page.keyboard.down('Enter'); await page.keyboard.down('Enter'); await page.keyboard.up('Enter'); }
      else await page.keyboard.press('Space');
    },
    save: () => writeFileSync(test.info().outputPath(`route-${name}.json`), JSON.stringify(record, null, 2)),
  };
}
// The selected task's shortcut row in 任务 over a 200-task queue, a moved Viewer in 结果 and drafts in both pages.
async function prepare(page: Page, hub: Hub, {graph = false} = {}) {
  hub.device = longQueue;
  const errors = await setup(page, hub);
  await go(page, '结果');
  // 图谱 is mounted before the clock is frozen (a paused clock holds its lazy module), then shown again after the shot.
  if (graph) {
    await modeTab(page, '图谱').click();
    await expect(graphPane(page).locator('.graph-panel')).toHaveCount(1);
    await graphPane(page).locator('.graph-panel').evaluate(el => { (el as any).__marker = 'same-graph'; });
    await modeTab(page, '结果文件').click();
  }
  await pause(page);
  const viewer = await paneShot(page, filePane(page), 'viewer-before');
  if (graph) await modeTab(page, '图谱').click();
  await go(page, '任务');
  await place(page);
  const pixels = await tasksPixels(page, 'before');
  return {errors, viewer, pixels, at: await place(page), before: await state(page)};
}
async function expectKept(page: Page, ready: Awaited<ReturnType<typeof prepare>>, name: string) {
  expect(await offsets(page)).toEqual(ready.at);
  expect(await state(page)).toEqual(ready.before);
  const pixels = await tasksPixels(page, name);
  expect(pixels.map((shot, i) => shot.equals(ready.pixels[i]))).toEqual([true, true]);
}

// Task log streams: 读取日志 opens the selected task's standard output in 结果 and the open pane switches explicitly
// to 标准错误 and back with the same task.logs action. Synthetic failed task: empty stdout, diagnosis on stderr only.
const STDERR = 'Traceback (most recent call last):\n  File "analysis.py", line 7, in <module>\nValueError: 网格尺寸必须为正\n';
const failedTasks = {...device, snapshot: {...device.snapshot, tasks: [{...row, state: 'failed'}, row2]}};
const logPane = (page: Page) => page.locator('section.analysis details.logs');
const logStreams = (page: Page) => logPane(page).getByRole('group', {name: '日志流'});
const logStream = (page: Page, name: '标准输出' | '标准错误') => logStreams(page).getByRole('button', {name, exact: true});
async function expectStream(page: Page, name: '标准输出' | '标准错误', text: string) {
  await expect(logPane(page).locator('pre')).toHaveText(text);
  await expect(logStream(page, name)).toHaveAttribute('aria-pressed', 'true');
  await expect(logStream(page, name === '标准输出' ? '标准错误' : '标准输出')).toHaveAttribute('aria-pressed', 'false');
}
const NO_LOG = '选择任务读取日志，或在三维视图中选取一个位置。';

for (const viewport of viewports) {
  test.describe(`${viewport.name} task log streams`, () => {
    test.use({viewport: {width: viewport.width, height: viewport.height}});

    test('a failed task\'s 标准错误 is one click from 读取日志 and keeps the Viewer, drafts and return focus', async ({page}) => {
      const hub = new Hub();
      hub.device = failedTasks;
      hub.logTexts.set(`${task} stdout`, '');
      hub.logTexts.set(`${task} stderr`, STDERR);
      const errors = await setup(page, hub);
      // Fixed start: 任务 with the failed task selected; 结果 has a moved Viewer and no stream switch yet.
      await go(page, '结果');
      await expect(logStreams(page)).toHaveCount(0);
      await pause(page);
      const viewer = await paneShot(page, filePane(page), 'viewer-before');
      await go(page, '任务');
      await expect(shortcut(page, '读取日志')).toBeInViewport({ratio: 1});
      const before = await state(page);
      const sent = posts(page);
      const r = measured(page, `${viewport.name}-stderr`);
      await r.activate(shortcut(page, '读取日志'), 'pointer', '读取日志');
      await expectActive(page, '结果');
      await expect(logPane(page).locator('summary')).toBeFocused();
      await expect(footer(page)).toContainText('就绪');
      // The empty stdout is named as such, not shown as the no-log hint.
      await expectStream(page, '标准输出', '标准输出暂无内容。');
      await expect(logStream(page, '标准错误')).toBeInViewport({ratio: 1});
      await r.activate(logStream(page, '标准错误'), 'pointer', '标准错误');
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准错误', STDERR);
      expect(hub.logPayloads).toEqual([{task_id: task}, {task_id: task, stream: 'stderr'}]);
      expect(r.record).toMatchObject({clicks: 2, keys: 0});
      r.save();
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-stderr.png`)});
      // 任务 straight from 结果 gives the focus back to 读取日志; nothing else in 任务 or 结果 changed.
      await railButton(page, '任务').click();
      await expect(shortcut(page, '读取日志')).toBeFocused();
      expect(await state(page)).toEqual(before);
      // Section switches and choosing the selected task again read no log, and the accepted stderr stays.
      for (const section of ['结果', '工作台', '任务', '结果', '任务']) await go(page, section);
      await taskRow(page, '解析场验证').click();
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      await go(page, '结果');
      await expectStream(page, '标准错误', STDERR);
      await page.waitForTimeout(300);
      expect(hub.logPayloads).toHaveLength(2);
      // The shortcut re-reads the stream accepted for this task; 标准输出 goes back with the original payload.
      await go(page, '任务');
      await shortcut(page, '读取日志').click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准错误', STDERR);
      await logStream(page, '标准输出').click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', '标准输出暂无内容。');
      expect(hub.logPayloads.slice(2)).toEqual([{task_id: task, stream: 'stderr'}, {task_id: task}]);
      // A probe result covering the log marks no stream as shown.
      await page.getByRole('button', {name: '查询原始值'}).click();
      await expect(logPane(page).locator('pre')).toContainText('"values"');
      for (const name of ['标准输出', '标准错误'] as const) await expect(logStream(page, name)).toHaveAttribute('aria-pressed', 'false');
      await expect(footer(page)).toContainText('就绪');
      sent.stop();
      expect(writes(sent.seen)).toEqual([...Array(4).fill('/api/v1/actions task.logs'), '/api/v1/actions view.probe']);
      expect([hub.evaluations, hub.builds.length, hub.calls, hub.replies]).toEqual([[], 1, [], 0]);
      expect(await state(page)).toEqual(before);
      expect((await paneShot(page, filePane(page), 'viewer-after')).equals(viewer)).toBe(true);
      expect(errors).toEqual([]);
    });

    test('a failed or expired stream read keeps the accepted log; another task starts again at 标准输出', async ({page}) => {
      const hub = new Hub();
      hub.device = failedTasks;
      hub.logTexts.set(`${task} stderr`, STDERR);
      hub.logTexts.set(`${task2} stdout`, '对照任务输出\n');
      hub.logTexts.set(`${task2} stderr`, '对照任务错误\n');
      const errors = await setup(page, hub, {scene: false});
      const alert = page.getByRole('alert');
      await shortcut(page, '读取日志').click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', LOG);
      // The 40-line log scrolls inside the pane under its stream switch, which stays in view.
      await logPane(page).evaluate(el => { el.scrollTop = el.scrollHeight; });
      const [pane, switcher] = [(await logPane(page).boundingBox())!, (await logStreams(page).boundingBox())!];
      expect(switcher.y).toBeGreaterThanOrEqual(pane.y);
      await expect(logStream(page, '标准错误')).toBeInViewport({ratio: 1});
      // A failed 标准错误 read reports its error and keeps the confirmed stdout with its label; the shortcut re-reads stdout.
      hub.logsFail = 'stderr';
      await logStream(page, '标准错误').click();
      await expect(alert).toContainText('日志暂不可读');
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', LOG);
      await alert.getByRole('button', {name: '关闭'}).click();
      hub.logsFail = false;
      await go(page, '任务');
      await shortcut(page, '读取日志').click();
      await expect(footer(page)).toContainText('就绪');
      await logStream(page, '标准错误').click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准错误', STDERR);
      expect(hub.logPayloads).toEqual([{task_id: task}, {task_id: task, stream: 'stderr'}, {task_id: task}, {task_id: task, stream: 'stderr'}]);
      // Held 标准错误 re-reads, then 对照任务 chosen before they answer: neither the late text nor a late error is
      // adopted, and 任务 stays.
      for (const late of ['text', 'error'] as const) {
        const release = hub.hold('task.logs');
        hub.reached.clear();
        await go(page, '结果');
        await logStream(page, '标准错误').click();
        await expect.poll(() => hub.reached.has('task.logs')).toBe(true);
        await go(page, '任务');
        await taskRow(page, '对照任务').click();
        await expect(status(page)).toContainText('已读取 Runtime 状态');
        hub.logsFail = late === 'error' ? 'stderr' : false;
        release();
        await expect(footer(page)).toContainText('就绪');
        await page.waitForTimeout(300);
        await expect(alert).toHaveCount(0);
        await expectActive(page, '任务');
        if (late === 'text') {
          // Back to the first task to hold the second read there.
          await taskRow(page, '解析场验证').click();
          await expect(status(page)).toContainText('已读取 Runtime 状态');
          await shortcut(page, '读取日志').click();
          await expect(footer(page)).toContainText('就绪');
          await expectStream(page, '标准输出', LOG);
          await go(page, '任务');
        }
      }
      hub.logsFail = false;
      await go(page, '结果');
      await expect(logPane(page).locator('pre')).toHaveText(NO_LOG);
      await expect(logStreams(page)).toHaveCount(0);
      await expect(alert).toHaveCount(0);
      // 对照任务's own shortcut reads its standard output with the original payload, not the first task's stream.
      await go(page, '任务');
      await shortcut(page, '读取日志').click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', '对照任务输出\n');
      // Back to the first task (a new selection): no log and no stream switch until 读取日志, which starts at stdout.
      await go(page, '任务');
      await taskRow(page, '解析场验证').click();
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      await go(page, '结果');
      await expect(logPane(page).locator('pre')).toHaveText(NO_LOG);
      await expect(logStreams(page)).toHaveCount(0);
      await go(page, '任务');
      await shortcut(page, '读取日志').click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', LOG);
      expect(hub.logPayloads.slice(4)).toEqual([{task_id: task, stream: 'stderr'}, {task_id: task}, {task_id: task, stream: 'stderr'},
        {task_id: task2}, {task_id: task}]);
      expect(errors).toEqual([]);
    });

    test('a held 标准错误 read keeps the keyboard on its stream button', async ({page}) => {
      const hub = new Hub();
      hub.device = failedTasks;
      hub.logTexts.set(`${task} stderr`, STDERR);
      await setup(page, hub, {scene: false});
      await shortcut(page, '读取日志').click();
      await expectStream(page, '标准输出', LOG);
      const release = hub.hold('task.logs');
      hub.reached.clear();
      const requests = posts(page);
      const stderr = logStream(page, '标准错误');
      await stderr.focus();
      try {
        await page.keyboard.press('Enter');
        await expect.poll(() => hub.reached.has('task.logs')).toBe(true);
        await expect(stderr).toBeDisabled();
        await expect(stderr).toBeFocused();
        await page.keyboard.press('Enter');
      } finally {
        release();
      }
      await expectStream(page, '标准错误', STDERR);
      await expect(stderr).toBeFocused();
      requests.stop();
      expect(requests.seen.filter(call => call.endsWith('task.logs'))).toEqual(['/api/v1/actions task.logs']);
      expect(hub.logPayloads).toEqual([{task_id: task}, {task_id: task, stream: 'stderr'}]);
    });
  });
}

// 继续读取: from the first block of the selected task's log, one click reads the next block of the shown stream with the
// same task.logs action from the accepted next_offset (source bytes) and appends it. Synthetic CJK text, so byte and
// character offsets differ; the 30-byte blocks split a line and a character of the running task's stdout.
const runningTasks = {...device, snapshot: {...device.snapshot, tasks: [{...row, state: 'running'}, row2]}};
const finishedTasks = {...device, snapshot: {...device.snapshot, tasks: [row, row2]}};
const RUN_LOG = '第1步 网格已生成\n第2步 求解收敛\n', RUN_FIRST = '第1步 网格已生成\n第2', RUN_MORE = '第3步 写出结果\n';
const RUN_CUT = 30, RUN_BYTES = Buffer.byteLength(RUN_LOG);
const logMore = (page: Page) => logPane(page).locator('.log-streams').getByRole('button', {name: /^(继续读取|已读完)$/});
const logNote = (page: Page) => logPane(page).getByRole('status');
async function expectMore(page: Page, label: '继续读取' | '已读完', note: string) {
  await expect(logMore(page)).toHaveText(label);
  await expect(logMore(page)).toHaveAttribute('aria-disabled', label === '已读完' ? 'true' : 'false');
  await expect(logNote(page)).toHaveText(note);
}

for (const viewport of viewports) {
  test.describe(`${viewport.name} task log continuation`, () => {
    test.use({viewport: {width: viewport.width, height: viewport.height}});

    test('继续读取 appends the next block at the accepted byte offset and keeps the Viewer, stream and focus', async ({page}) => {
      const hub = new Hub();
      hub.device = runningTasks;
      hub.logChunk = RUN_CUT;
      hub.logTexts.set(`${task} stdout`, RUN_LOG);
      const errors = await setup(page, hub);
      await go(page, '结果');
      await pause(page);
      const viewer = await paneShot(page, filePane(page), 'viewer-before');
      await go(page, '任务');
      // Fixed start: 结果 after 读取日志 shows the first 30 bytes of stdout, ending inside 步 and inside the second line.
      await shortcut(page, '读取日志').click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', RUN_FIRST);
      await expectMore(page, '继续读取', '');
      expect(hub.logPayloads).toEqual([{task_id: task}]);
      await expect(logMore(page)).toBeInViewport({ratio: 1});
      const before = await state(page), layout = await logLayout(page);
      const sent = posts(page);
      const r = measured(page, `${viewport.name}-continue`);
      await r.activate(logMore(page), 'pointer', '继续读取');
      await expect(footer(page)).toContainText('就绪');
      // The half line and the split character are completed in place; the request asked byte 30, not a text length.
      await expectStream(page, '标准输出', RUN_LOG);
      expect(RUN_FIRST.length).not.toBe(RUN_CUT);
      expect(hub.logPayloads.slice(1)).toEqual([{task_id: task, offset: RUN_CUT}]);
      await expectActive(page, '结果');
      await expect(logMore(page)).toBeFocused();
      await expectMore(page, '继续读取', '');
      expect(r.record).toMatchObject({clicks: 1, keys: 0});
      r.save();
      await page.screenshot({path: test.info().outputPath(`${viewport.name}-continue.png`)});
      expect(await logLayout(page)).toEqual(layout);
      sent.stop();
      expect(writes(sent.seen)).toEqual(['/api/v1/actions task.logs']);
      expect(await state(page)).toEqual(before);
      expect((await paneShot(page, filePane(page), 'viewer-after')).equals(viewer)).toBe(true);
      // Nothing new yet while the task runs: the text stays and the user may read again later.
      await logMore(page).click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', RUN_LOG);
      await expectMore(page, '继续读取', '暂无新内容，可稍后继续读取。');
      // Section switches, 刷新, choosing the task again and the periodic refresh send no continuation.
      for (const section of ['任务', '工作台', '结果', '任务']) await go(page, section);
      await page.locator('aside.tasks .section-title').getByRole('button', {name: '刷新'}).click();
      await taskRow(page, '解析场验证').click();
      await page.clock.runFor(11000);
      await go(page, '结果');
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', RUN_LOG);
      expect(hub.logPayloads).toHaveLength(3);
      // The task writes more, then ends: each click reads once from the accepted offset; an empty block at the end stops.
      hub.logTexts.set(`${task} stdout`, RUN_LOG + RUN_MORE);
      await logMore(page).click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', RUN_LOG + RUN_MORE);
      await expectMore(page, '继续读取', '');
      hub.device = finishedTasks;
      await logMore(page).click();
      await expect(footer(page)).toContainText('就绪');
      await expectMore(page, '已读完', '标准输出已读完，任务已结束。');
      await expect(logMore(page)).toBeFocused();
      await logMore(page).click({force: true});
      await page.keyboard.press('Enter');
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', RUN_LOG + RUN_MORE);
      const end = RUN_BYTES + Buffer.byteLength(RUN_MORE);
      expect(hub.logPayloads.slice(1)).toEqual([RUN_CUT, RUN_BYTES, RUN_BYTES, end].map(offset => ({task_id: task, offset})));
      // A raw-value probe after the log covers it and hides 继续读取; the stream switch shows the log again.
      await page.getByRole('button', {name: '查询原始值'}).click();
      await expect(logPane(page).locator('pre')).toContainText('"values"');
      await expect(logMore(page)).toHaveCount(0);
      await expect(footer(page)).toContainText('就绪');
      await logStream(page, '标准输出').click();
      await expect(footer(page)).toContainText('就绪');
      // An explicit stream read starts again at the first block, which a finished task can still continue.
      await expectStream(page, '标准输出', RUN_FIRST);
      await expectMore(page, '继续读取', '');
      expect(hub.logPayloads.at(-1)).toEqual({task_id: task});
      expect(errors).toEqual([]);
    });

    test('a held 标准错误 continuation keeps the keyboard, sends one request and completes a split character', async ({page}) => {
      const hub = new Hub();
      hub.device = failedTasks;
      hub.logChunk = 20;
      const stderr = 'ValueError: 网格🔥尺寸\n'; // 🔥 takes bytes 18–21, so the first block ends inside it
      hub.logTexts.set(`${task} stdout`, '');
      hub.logTexts.set(`${task} stderr`, stderr);
      const errors = await setup(page, hub, {scene: false});
      await shortcut(page, '读取日志').click();
      await expect(footer(page)).toContainText('就绪');
      // The failed task's empty stdout has ended at once; its stderr is one click away.
      await expectStream(page, '标准输出', '标准输出暂无内容。');
      await expectMore(page, '已读完', '标准输出已读完，任务已结束。');
      await logStream(page, '标准错误').focus();
      await page.keyboard.press('Enter');
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准错误', 'ValueError: 网格');
      await expectMore(page, '继续读取', '');
      await expect(logStream(page, '标准错误')).toBeFocused();
      await page.keyboard.press('Tab');
      await expect(logMore(page)).toBeFocused();
      const release = hub.hold('task.logs');
      hub.reached.clear();
      const requests = posts(page);
      try {
        await page.keyboard.press('Enter');
        await expect.poll(() => hub.reached.has('task.logs')).toBe(true);
        await expect(logMore(page)).toHaveAttribute('aria-disabled', 'true');
        await expect(logMore(page)).toBeFocused();
        await page.keyboard.press('Enter');
        await page.keyboard.press('Space');
        await logMore(page).click({force: true});
      } finally {
        release();
      }
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准错误', stderr);
      await expect(logMore(page)).toBeFocused();
      requests.stop();
      expect(requests.seen.filter(call => call.endsWith('task.logs'))).toEqual(['/api/v1/actions task.logs']);
      await page.keyboard.press('Enter');
      await expect(footer(page)).toContainText('就绪');
      await expectMore(page, '已读完', '标准错误已读完，任务已结束。');
      await expect(logMore(page)).toBeFocused();
      await expectStream(page, '标准错误', stderr);
      expect(hub.logPayloads).toEqual([{task_id: task}, {task_id: task, stream: 'stderr'},
        {task_id: task, stream: 'stderr', offset: 20}, {task_id: task, stream: 'stderr', offset: Buffer.byteLength(stderr)}]);
      expect(errors).toEqual([]);
    });

    test('a failed, malformed or expired continuation keeps the confirmed log; a retry asks the same offset', async ({page}) => {
      const hub = new Hub();
      hub.device = runningTasks;
      hub.logChunk = RUN_CUT;
      hub.logTexts.set(`${task} stdout`, RUN_LOG);
      hub.logTexts.set(`${task2} stdout`, '对照任务输出\n');
      const errors = await setup(page, hub, {scene: false});
      const alert = page.getByRole('alert');
      await shortcut(page, '读取日志').click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', RUN_FIRST);
      // A failed read and each malformed reply report an error and keep the first block and 继续读取.
      for (const [fault, message] of [['fail', '日志暂不可读'], ['offset', '日志回执格式无效'], ['next_offset', '日志回执格式无效'],
        ['base64', '日志回执格式无效'], ['no-offsets', '日志回执格式无效']] as const) {
        if (fault === 'fail') hub.logsFail = 'stdout'; else hub.logFault = fault;
        await logMore(page).click();
        await expect(alert).toContainText(message);
        await expect(footer(page)).toContainText('就绪');
        await expectStream(page, '标准输出', RUN_FIRST);
        await expectMore(page, '继续读取', '');
        await alert.getByRole('button', {name: '关闭'}).click();
        hub.logsFail = false;
      }
      await logMore(page).click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', RUN_LOG);
      expect(hub.logPayloads.slice(1)).toEqual(Array(6).fill({task_id: task, offset: RUN_CUT}));
      // Held continuations, then 对照任务 chosen before they answer: neither the late text nor a late error is adopted.
      hub.logTexts.set(`${task} stdout`, RUN_LOG + RUN_MORE);
      for (const late of ['text', 'error'] as const) {
        const release = hub.hold('task.logs');
        hub.reached.clear();
        await logMore(page).click();
        await expect.poll(() => hub.reached.has('task.logs')).toBe(true);
        await go(page, '任务');
        await taskRow(page, '对照任务').click();
        await expect(status(page)).toContainText('已读取 Runtime 状态');
        hub.logsFail = late === 'error' ? 'stdout' : false;
        release();
        await expect(footer(page)).toContainText('就绪');
        await page.waitForTimeout(300);
        await expect(alert).toHaveCount(0);
        await expectActive(page, '任务');
        await go(page, '结果');
        await expect(logPane(page).locator('pre')).toHaveText(NO_LOG);
        await expect(logStreams(page)).toHaveCount(0);
        hub.logsFail = false;
        // Back to the first task, a new scope: 读取日志 starts again at the first block, without an offset.
        await go(page, '任务');
        await taskRow(page, '解析场验证').click();
        await expect(status(page)).toContainText('已读取 Runtime 状态');
        await shortcut(page, '读取日志').click();
        await expect(footer(page)).toContainText('就绪');
        await expectStream(page, '标准输出', RUN_FIRST);
      }
      // The first held read continued the whole stdout (from byte 45), the second the new first block (from byte 30).
      expect(hub.logPayloads.slice(7)).toEqual([{task_id: task, offset: RUN_BYTES}, {task_id: task},
        {task_id: task, offset: RUN_CUT}, {task_id: task}]);
      expect(errors).toEqual([]);
    });

    test('an offset-zero continuation without offsets keeps the accepted empty log and can retry', async ({page}) => {
      const hub = new Hub();
      hub.device = {...runningTasks, snapshot: {...runningTasks.snapshot, tasks: [{...row, state: 'queued'}, row2]}};
      const stream = `${task} stdout`;
      hub.logTexts.set(stream, '');
      const errors = await setup(page, hub, {scene: false});
      await shortcut(page, '读取日志').click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', '标准输出暂无内容。');

      hub.logTexts.set(stream, '新输出\n');
      hub.logFault = 'no-offsets';
      await logMore(page).click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', '标准输出暂无内容。');
      await expect(page.getByRole('alert')).toContainText('日志回执格式无效');
      await expectMore(page, '继续读取', '暂无新内容，可稍后继续读取。');
      await expect(logMore(page)).toBeFocused();

      await page.keyboard.press('Enter');
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', '新输出');
      await expect(logMore(page)).toBeFocused();
      expect(hub.logPayloads).toEqual([{task_id: task}, {task_id: task, offset: 0}, {task_id: task, offset: 0}]);
      expect(errors).toEqual([]);
    });

    test('a split UTF-8 BOM is removed only at source byte zero', async ({page}) => {
      const hub = new Hub();
      hub.device = runningTasks;
      hub.logChunk = 2;
      hub.logTexts.set(`${task} stdout`, Buffer.from([0xef, 0xbb, 0xbf, 0x41, 0xef, 0xbb, 0xbf, 0x42]));
      const errors = await setup(page, hub, {scene: false});
      const text = logPane(page).locator('pre');
      await shortcut(page, '读取日志').click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', '标准输出暂无内容。');

      await logMore(page).click();
      await expect(footer(page)).toContainText('就绪');
      // The raw rendered string also determines copied text. Normalized locator text can hide the leading mark.
      expect(await text.textContent()).toBe('A');
      await logMore(page).click();
      await expect(footer(page)).toContainText('就绪');
      expect(await text.textContent()).toBe('A');
      await logMore(page).click();
      await expect(footer(page)).toContainText('就绪');
      expect(await text.textContent()).toBe('A\uFEFFB');
      expect(hub.logPayloads).toEqual([{task_id: task}, ...[2, 4, 6].map(offset => ({task_id: task, offset}))]);
      expect(errors).toEqual([]);
    });

    test('a reply without offsets shows its text and offers no continuation', async ({page}) => {
      const hub = new Hub();
      hub.device = runningTasks;
      hub.logReply = 'legacy';
      hub.logTexts.set(`${task} stdout`, RUN_LOG);
      hub.logTexts.set(`${task} stderr`, STDERR);
      const errors = await setup(page, hub, {scene: false});
      await shortcut(page, '读取日志').click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', RUN_LOG);
      await expect(logMore(page)).toHaveCount(0);
      await expect(logNote(page)).toHaveText('此日志回执不含读取位置，不能继续读取。');
      await logStream(page, '标准错误').click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准错误', STDERR);
      await expect(logMore(page)).toHaveCount(0);
      await expect(logStream(page, '标准错误')).toBeFocused();
      await page.waitForTimeout(300);
      expect(hub.logPayloads).toEqual([{task_id: task}, {task_id: task, stream: 'stderr'}]);
      expect(errors).toEqual([]);
    });

    test('继续读取 below a scrolled first block keeps the pane and 结果 where the user left them', async ({page}) => {
      const hub = new Hub();
      hub.device = runningTasks;
      hub.logChunk = 400; // the first block of the 40-line log is taller than the pane
      const errors = await setup(page, hub, {scene: false});
      await shortcut(page, '读取日志').click();
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', LOG.slice(0, 400));
      await logPane(page).evaluate(el => { el.scrollTop = 90; });
      const before = await logPane(page).evaluate(el => ({pane: el.scrollTop, room: el.scrollHeight > el.clientHeight}));
      expect(before).toEqual({pane: 90, room: true});
      const layout = await logLayout(page);
      await expect(logMore(page)).toBeInViewport({ratio: 1});
      const r = measured(page, `${viewport.name}-continue-scrolled`);
      await r.activate(logMore(page), 'pointer', '继续读取');
      await expect(footer(page)).toContainText('就绪');
      await expectStream(page, '标准输出', LOG);
      expect(await logPane(page).evaluate(el => el.scrollTop)).toBe(90);
      expect(await logLayout(page)).toEqual(layout);
      await expect(logMore(page)).toBeFocused();
      expect(r.record).toMatchObject({clicks: 1, keys: 0});
      expect(hub.logPayloads).toEqual([{task_id: task}, {task_id: task, offset: 400}]);
      expect(errors).toEqual([]);
    });
  });
}

for (const viewport of viewports) {
  test.describe(`${viewport.name} 任务 return focus`, () => {
    test.use({viewport: {width: viewport.width, height: viewport.height}});

    for (const [launcher, how, graph] of [['在查看器中打开', 'pointer', false], ['在查看器中打开', 'Enter', false], ['读取日志', 'pointer', false],
      ['读取日志', 'Space', false], ['在查看器中打开', 'pointer', true]] as const) {
      test(`${launcher} by ${how}${graph ? ' in 图谱' : ''} then 任务 returns the focus to ${launcher} and keeps 任务 and 结果`, async ({page}) => {
        const hub = new Hub();
        const ready = await prepare(page, hub, {graph});
        const sent = posts(page), seen = traffic(page);
        const r = measured(page, `${viewport.name}-${launcher}-${how}${graph ? '-graph' : ''}`);
        await r.activate(shortcut(page, launcher), how, launcher);
        await expectActive(page, '结果');
        // The destination takes the focus, as before.
        if (launcher === '读取日志') await expect(page.locator('section.analysis details.logs summary')).toBeFocused();
        else if (graph) await expect(modeTab(page, '图谱')).toBeFocused();
        else await expect(page.getByLabel('结果文件')).toBeFocused();
        await expect(footer(page)).toContainText('就绪');
        await r.activate(railButton(page, '任务'), how, '任务');
        await expectActive(page, '任务');
        await expect(shortcut(page, launcher)).toBeFocused();
        expect(await focused(page)).toBe(`tasks BUTTON ${launcher}`);
        await page.waitForTimeout(300);
        await expect(shortcut(page, launcher)).toBeFocused();
        // As returned, before the element shots below scroll 任务 to take them.
        await page.screenshot({path: test.info().outputPath(`${viewport.name}-returned.png`)});
        await expectKept(page, ready, 'after');
        sent.stop(); seen.stop();
        const read = launcher === '在查看器中打开' ? '/api/v1/nodes/{node}/read task.artifacts' : '/api/v1/actions task.logs';
        expect(sent.seen).toEqual([read]);
        expect(seen.seen).toEqual([launcher === '在查看器中打开' ? 'POST nodes/{node}/read task.artifacts' : 'POST actions task.logs']);
        expect([hub.evaluations, hub.calls, hub.replies, hub.messages]).toEqual([[], [], 0, []]);
        expect(r.record).toMatchObject(how === 'pointer' ? {clicks: 2, keys: 0} : {clicks: 0, keys: 2});
        r.save();
        await go(page, '结果');
        await expectMode(page, graph ? '图谱' : '结果文件');
        if (graph) {
          expect(await graphPane(page).locator('.graph-panel').evaluate(el => (el as any).__marker ?? null)).toBe('same-graph');
          await modeTab(page, '结果文件').click();
        }
        expect((await paneShot(page, filePane(page), 'viewer-after')).equals(ready.viewer)).toBe(true);
        expect(ready.errors).toEqual([]);
      });
    }

    for (const how of ['pointer', 'Enter'] as const) {
      test(`rail 结果 by ${how} then 任务 leaves the focus on the rail`, async ({page}) => {
        const hub = new Hub();
        const ready = await prepare(page, hub);
        const sent = posts(page);
        const r = measured(page, `${viewport.name}-rail-${how}`);
        // A shortcut trip earlier is used up by its own return and by a later plain one.
        await r.activate(shortcut(page, '在查看器中打开'), how, '在查看器中打开');
        await expect(footer(page)).toContainText('就绪');
        await r.activate(railButton(page, '任务'), how, '任务');
        await expect(shortcut(page, '在查看器中打开')).toBeFocused();
        for (const step of ['结果', '任务'] as const) await r.activate(railButton(page, step), how, step);
        await expectActive(page, '任务');
        await expect(railButton(page, '任务')).toBeFocused();
        // The shortcut trip, then 结果 twice from the rail: 结果 again in place is passive as well.
        await r.activate(shortcut(page, '在查看器中打开'), how, '在查看器中打开');
        await expect(footer(page)).toContainText('就绪');
        for (const step of ['结果', '任务'] as const) await r.activate(railButton(page, step), how, step);
        await expect(railButton(page, '任务')).toBeFocused();
        await page.waitForTimeout(300);
        await expect(railButton(page, '任务')).toBeFocused();
        await expectKept(page, ready, 'after');
        sent.stop();
        expect(writes(sent.seen)).toEqual([]);
        r.save();
        expect(ready.errors).toEqual([]);
      });
    }

    test('a 工作台 or history trip from 结果 leaves the focus on the rail', async ({page}) => {
      const hub = new Hub();
      const ready = await prepare(page, hub);
      const sent = posts(page);
      const trips = [['工作台', async () => { await railButton(page, '工作台').click(); await expectActive(page, '工作台'); }]] as [string, () => Promise<void>][];
      if (viewport.name === 'narrow') {
        trips.push(['历史 Esc', async () => {
          await historyToggle(page).click();
          await expect(historyPanel(page)).toBeVisible();
          await page.keyboard.press('Escape');
          await expect(historyToggle(page)).toBeFocused();
        }]);
      } else {
        trips.push(['新对话', async () => {
          await historyPanel(page).getByRole('button', {name: '新对话', exact: true}).click();
          await expectActive(page, '工作台');
        }]);
      }
      for (const [name, trip] of trips) {
        await shortcut(page, '在查看器中打开').click();
        await expectActive(page, '结果');
        await expect(footer(page)).toContainText('就绪');
        await trip();
        await railButton(page, '任务').click();
        await expectActive(page, '任务');
        await expect(railButton(page, '任务'), name).toBeFocused();
        expect(await offsets(page)).toEqual(ready.at);
      }
      const {draft: _, ...kept} = ready.before;
      expect(await state(page)).toMatchObject(kept);
      sent.stop();
      expect(writes(sent.seen)).toEqual([]);
      expect([hub.calls, hub.replies]).toEqual([[], 0]);
      expect(ready.errors).toEqual([]);
    });

    test('a held read leaves the busy shortcut unfocused on return, and its late reply moves nothing', async ({page}) => {
      const hub = new Hub();
      const ready = await prepare(page, hub);
      for (const [launcher, kind] of [['在查看器中打开', 'task.artifacts'], ['读取日志', 'task.logs']] as const) {
        const release = hub.hold(kind);
        hub.reached.clear();
        await shortcut(page, launcher).click();
        await expectActive(page, '结果');
        await expect.poll(() => hub.reached.has(kind)).toBe(true);
        await railButton(page, '任务').click();
        await expectActive(page, '任务');
        await expect(shortcut(page, launcher)).toBeDisabled();
        await expect(railButton(page, '任务')).toBeFocused();
        release();
        await expect(footer(page)).toContainText('就绪');
        await expect(shortcut(page, launcher)).toBeEnabled();
        await page.waitForTimeout(300);
        await expect(railButton(page, '任务')).toBeFocused();
        expect(await offsets(page)).toEqual(ready.at);
      }
      expect(ready.errors).toEqual([]);
    });

    for (const clip of ['partly', 'wholly'] as const) {
      test(`a shortcut ${clip} out of view on return keeps the focus on the rail and the offsets`, async ({page}) => {
        const hub = new Hub();
        const ready = await prepare(page, hub);
        await shortcut(page, '在查看器中打开').click();
        await expectActive(page, '结果');
        await expect(footer(page)).toContainText('就绪');
        // A shorter window in 结果 (the same side of the compact width) puts the shortcut under the bottom of 任务;
        // the queue's height follows the window, so it is shortened 4 px at a time until the shortcut is clipped.
        const clipped = () => page.locator('aside.tasks').evaluate((el, clip) => {
          const at = [...el.querySelectorAll('.inline > button')].find(b => b.textContent === '在查看器中打开')!.getBoundingClientRect();
          const bottom = el.getBoundingClientRect().bottom;
          return clip === 'partly' ? at.top < bottom - 4 && at.bottom > bottom : at.top >= bottom;
        }, clip);
        for (let height = viewport.height; !await clipped(); height -= 4) {
          expect(height).toBeGreaterThan(300);
          await page.setViewportSize({width: viewport.width, height});
        }
        const at = await offsets(page);
        expect(at.queue).toBeGreaterThan(0);
        await railButton(page, '任务').click();
        await expectActive(page, '任务');
        const visible = await shortcut(page, '在查看器中打开').evaluate(el => {
          const at = el.getBoundingClientRect(), area = el.closest('aside')!.getBoundingClientRect();
          return [at.top < area.bottom, at.bottom <= area.bottom];
        });
        expect(visible).toEqual(clip === 'partly' ? [true, false] : [false, false]);
        await expect(railButton(page, '任务')).toBeFocused();
        expect(await offsets(page)).toEqual(at);
        expect(ready.errors).toEqual([]);
      });
    }

    test('another selection of the same task, or a node gone while in 结果, takes no focus back', async ({page}) => {
      const hub = new Hub();
      const ready = await prepare(page, hub);
      // Leaving the task and selecting the same ID again, then a plain rail trip.
      await shortcut(page, '在查看器中打开').click();
      await expect(footer(page)).toContainText('就绪');
      await railButton(page, '任务').click();
      await expect(shortcut(page, '在查看器中打开')).toBeFocused();
      await queue(page).locator('.task').filter({has: page.locator('span', {hasText: /^额外任务 5$/})}).click();
      await expect(page.locator('aside.tasks .task.selected')).toHaveText(/额外任务 5/);
      await queue(page).getByRole('button', {name: /解析场验证/}).click();
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      await expect(footer(page)).toContainText('就绪');
      for (const name of ['结果', '任务'] as const) await railButton(page, name).click();
      await expect(railButton(page, '任务')).toBeFocused();
      // The node is revoked while 结果 shows the shortcut's result: the scope and its shortcut are gone on return,
      // and stay gone when the node is listed again.
      await place(page);
      await shortcut(page, '在查看器中打开').click();
      await expect(footer(page)).toContainText('就绪');
      hub.device = {...longQueue, revoked: true};
      hub.publish();
      await expect(page.getByLabel('执行节点')).toHaveValue('');
      hub.device = longQueue;
      await page.clock.runFor(5000); // the next periodic refresh (the event stream reconnects on the frozen clock)
      await expect(page.getByLabel('执行节点').locator('option')).toHaveCount(2);
      await railButton(page, '任务').click();
      await expectActive(page, '任务');
      await expect(shortcut(page, '在查看器中打开')).toHaveCount(0);
      await expect(railButton(page, '任务')).toBeFocused();
      expect(ready.errors).toEqual([]);
    });
  });
}

test('History opened by narrowing clears the old Tasks shortcut return', async ({page}) => {
  const wide = {width: 1440, height: 900};
  await page.setViewportSize(wide);
  const hub = new Hub();
  const ready = await prepare(page, hub);
  await shortcut(page, '在查看器中打开').click();
  await expectActive(page, '结果');
  await expect(footer(page)).toContainText('就绪');
  await historyPanel(page).getByRole('button', {name: '新对话', exact: true}).focus();
  await page.setViewportSize({width: 390, height: 844});
  await expect(historyToggle(page)).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press('Escape');
  await expect(historyToggle(page)).toHaveAttribute('aria-expanded', 'false');
  await page.setViewportSize(wide);
  await expect(historyToggle(page)).toHaveCount(0);
  const at = await offsets(page);
  await railButton(page, '任务').click();
  await expectActive(page, '任务');
  await expect(shortcut(page, '在查看器中打开')).toBeInViewport({ratio: 1});
  await expect(railButton(page, '任务')).toBeFocused();
  expect(await offsets(page)).toEqual(at);
  expect(await state(page)).toEqual(ready.before);
  expect([hub.calls, hub.replies]).toEqual([[], 0]);
  expect(ready.errors).toEqual([]);
});

const graphTaskB = {...row, id: task2, workspace_id: ws2, name: '图谱来源乙'};
const graphTwoScopes = {...twoProjects, snapshot: {...twoProjects.snapshot, tasks: [row, graphTaskB]}};
const graphSourceA = '显示的三维结果，场视图 · 解析场验证 · 第 1000 步';
const graphSourceB = '显示的三维结果，场视图 · 图谱来源乙 · 第 1000 步';
const muproPanel = (page: Page) => graphPane(page).locator('details').filter({has: page.locator('summary', {hasText: /^MuPRO HDF5$/})});
const muproList = (page: Page) => muproPanel(page).getByRole('button', {name: '列出 HDF5 帧', exact: true});
const muproFrame = (page: Page) => muproPanel(page).getByRole('combobox', {name: 'HDF5 场与步号', exact: true});
const muproComponent = (page: Page) => muproPanel(page).getByRole('spinbutton', {name: 'HDF5 分量索引', exact: true});
const muproOpen = (page: Page) => muproPanel(page).getByRole('button', {name: '打开所选 HDF5 帧', exact: true});
const muproSource = '显示的三维结果，MuPRO HDF5 · 解析场验证 · 第 2 步';

for (const viewport of viewports) {
  test(`${viewport.name} MuPRO HDF5 route is reachable from Results scroll zero without scrolling`, async ({page}) => {
    await page.setViewportSize({width: viewport.width, height: viewport.height});
    const hub = new Hub();
    hub.presets = [PRESET];
    hub.hdf5Artifacts.set(task, HDF5_ARTIFACT);
    await setup(page, hub, {scene: false});
    await showGraph(page);
    const outer = page.locator('section.analysis');
    await outer.evaluate(el => {el.scrollTop = 0;});
    const offsets: {phase: string, outer: number, window: number}[] = [];
    const at = async (phase: string) => offsets.push({phase, outer: await outer.evaluate(el => el.scrollTop), window: await page.evaluate(() => scrollY)});
    const r = route(page, `${viewport.name}-hdf5-top`);
    const summary = muproPanel(page).locator('summary');
    await at('fixed-start');
    await expect(summary).toBeInViewport({ratio: 1});
    await r.click(summary, 'MuPRO HDF5');
    await at('expanded');
    await expect(muproList(page)).toBeInViewport({ratio: 1});
    await r.click(muproList(page), '列出 HDF5 帧');
    await expect(muproFrame(page)).toBeVisible();
    await at('listed');
    await expect(muproFrame(page)).toBeInViewport({ratio: 1});
    await r.select(muproFrame(page), '/t00000002/Polar', 'Polar · 第 2 步');
    await expect(muproComponent(page)).toBeInViewport({ratio: 1});
    await r.click(muproComponent(page), '分量索引');
    await muproComponent(page).fill('1');
    await at('component-selected');
    await expect(muproOpen(page)).toBeInViewport({ratio: 1});
    await r.click(muproOpen(page), '打开所选 HDF5 帧');
    await expect(source(page)).toHaveText(muproSource);
    await at('accepted');
    expect(offsets.every(row => row.outer === 0 && row.window === 0)).toBe(true);
    expect(r.record).toMatchObject({clicks: 4, selects: 1});
    expect(hub.evaluations).toHaveLength(2);
    r.save();
    writeFileSync(test.info().outputPath('hdf5-top-offsets.json'), JSON.stringify({viewport, offsets, numericInputs: 1, wheelEvents: 0}, null, 2));
    await page.screenshot({path: test.info().outputPath('hdf5-top-complete.png')});
  });

  test(`${viewport.name} MuPRO HDF5 lists pinned fields and opens only an explicit exact frame`, async ({page}) => {
    await page.setViewportSize({width: viewport.width, height: viewport.height});
    const hub = new Hub();
    hub.presets = [PRESET];
    hub.hdf5Artifacts.set(task, HDF5_ARTIFACT);
    const errors = await setup(page, hub, {scene: false});
    await showGraph(page);
    await computeGraph(page, hub);
    await expect(source(page)).toHaveText(graphSourceA);
    const canvas = vtkCanvas(graphPane(page));
    await canvas.evaluate(el => { (el as any).__hdf5SameCanvas = true; });
    const sent = posts(page);
    await muproPanel(page).locator('summary').click();
    expect(sent.seen).toEqual([]);

    hub.hdf5Fault = 'wrong-digest';
    await muproList(page).click();
    await expect(muproPanel(page).getByRole('alert')).toContainText('字段列表与发布文件不符');
    await expect(muproFrame(page)).toHaveCount(0);
    await expect(source(page)).toHaveText(graphSourceA);

    hub.hdf5Fault = undefined;
    await muproList(page).click();
    await expect(muproFrame(page)).toHaveValue('');
    await expect(muproFrame(page).locator('option')).toHaveText(['选择场与步号', 'Polar · 第 2 步', 'Scalar · 第 2 步', 'Polar · 第 4 步']);
    await expect(muproOpen(page)).toBeDisabled();
    await muproFrame(page).selectOption('/t00000002/Polar');
    await expect(muproPanel(page)).toContainText('float32 · 原生形状 4 × 3 × 2 × 3');
    await expect(muproComponent(page)).toHaveValue('');
    await expect(muproOpen(page)).toBeDisabled();
    await muproComponent(page).fill('3');
    await expect(muproOpen(page)).toBeDisabled();
    await muproComponent(page).fill('1');
    await expect(muproOpen(page)).toBeEnabled();
    expect(hub.evaluations).toHaveLength(3);
    expect(hub.evaluations[2]).toEqual({
      graph: {schema: 'stk.graph/1', catalog: {stk: 1}, nodes: [{id: 'fields', type: 'stk.source.mupro_hdf5_fields@1',
        params: {binding: 'run', path: HDF5_ARTIFACT.path, expected_sha256: HDF5_ARTIFACT.sha256}}], outputs: {fields: 'fields.out'}},
      bindings: {run: {task_id: task}}, profile: 'web', outputs: ['fields'], budget: {max_output_bytes: 256 * 1024},
    });

    for (const [fault, error] of [['invalid_data', 'expected SHA-256'], ['wrong-step', '步号或网格单位']] as const) {
      hub.hdf5Fault = fault;
      await muproOpen(page).click();
      await expect(muproPanel(page).getByRole('alert')).toContainText(error);
      await expect(source(page)).toHaveText(graphSourceA);
    }
    hub.hdf5Fault = undefined;
    await muproOpen(page).click();
    await expect(source(page)).toHaveText(muproSource);
    expect(hub.evaluations.at(-1)).toMatchObject({profile: 'web', bindings: {run: {task_id: task}}, outputs: ['view'], graph: {
      nodes: [
        {type: 'stk.source.mupro_hdf5@1', params: {binding: 'run', path: HDF5_ARTIFACT.path,
          expected_sha256: HDF5_ARTIFACT.sha256, selector: '/t00000002/Polar'}},
        {type: 'stk.render.volume@1', params: {field: {name: 'Polar', component: 1}, encoding: 'f32'}},
        {type: 'stk.view.scene@1'},
      ],
    }});
    await expect(graphPane(page).getByRole('button', {name: '查询原始值'})).toHaveCount(0);
    await expect(graphPane(page).getByRole('slider', {name: '时间步'})).toHaveCount(0);
    expect(await canvas.evaluate(el => (el as any).__hdf5SameCanvas)).toBe(true);
    await sourceToggle(page).click();
    expect(await detailRows(page)).toEqual([
      ['显示内容', '显示的三维结果'], ['原生读取器', 'mupro.hdf5@1'], ['发布文件', HDF5_ARTIFACT.path],
      ['发布 SHA-256', HDF5_ARTIFACT.sha256], ['场选择器', '/t00000002/Polar'], ['分量索引', '1'],
      ['输出', 'view'], ['节点', '节点甲' + node], ['计算绑定 run', '解析场验证' + task],
      ['运行工作区 run', '项目一' + ws], ['已显示时间步', '2'],
    ]);
    await sourcePanel(page).getByRole('button', {name: '收起'}).click();

    await muproFrame(page).selectOption('/t00000002/Scalar');
    await expect(muproComponent(page)).toHaveCount(0);
    await expect(muproOpen(page)).toBeEnabled();
    await muproOpen(page).click();
    await sourceToggle(page).click();
    await expect(sourcePanel(page)).toContainText('/t00000002/Scalar');
    expect(hub.evaluations.at(-1).graph.nodes[1].params.field).toEqual({name: 'Scalar', component: null});
    await sourcePanel(page).getByRole('button', {name: '收起'}).click();
    await computeGraph(page, hub);
    await expect(source(page)).toHaveText(graphSourceA);
    expect(hub.evaluations.at(-1).preset).toBe(PRESET.id);
    sent.stop();
    expect(sent.seen.filter(call => !call.endsWith('task.get')).every(call => call === '/api/v1/actions graph.evaluate')).toBe(true);
    expect(hub.messages).toEqual([]);
    expect(errors).toEqual([]);
  });
}

const voxelForm = (page: Page) => graphPane(page).getByRole('form', {name: 'HDF5 原始体素'});
const voxelRead = (page: Page) => voxelForm(page).getByRole('button', {name: '读取体素', exact: true});
const voxelCoordinate = (page: Page, axis: string) => voxelForm(page).getByRole('spinbutton', {name: `HDF5 网格 ${axis}`, exact: true});
const voxelValue = (page: Page) => voxelForm(page).getByLabel('HDF5 原始值', {exact: true});

async function openHdf5Field(page: Page, selector: string, component?: string) {
  await muproPanel(page).locator('summary').click();
  await muproList(page).click();
  await muproFrame(page).selectOption(selector);
  if (component !== undefined) await muproComponent(page).fill(component);
  await muproOpen(page).click();
  await expect(voxelForm(page)).toBeVisible();
}

for (const viewport of viewports) {
  test(`${viewport.name} HDF5 voxel reads only the accepted frame and exact component`, async ({page}) => {
    await page.setViewportSize({width: viewport.width, height: viewport.height});
    const hub = new Hub();
    hub.presets = [PRESET];
    hub.hdf5Artifacts.set(task, HDF5_ARTIFACT);
    hub.hdf5Fields = HDF5_FIELDS.map(item => item.name === 'Polar' ? {...item, dtype: 'uint64'} : item);
    const errors = await setup(page, hub, {scene: false});
    await showGraph(page);
    await expect(voxelForm(page)).toHaveCount(0);
    await openHdf5Field(page, '/t00000002/Polar', '1');
    await expect(source(page)).toHaveText(muproSource);
    const canvas = vtkCanvas(graphPane(page));
    await canvas.evaluate(el => { (el as any).__voxelCanvas = true; });
    await page.locator('section.analysis').evaluate(el => { el.scrollTop = 0; });
    const sent = posts(page);
    // Unopened selector/component edits do not become the source of the displayed frame.
    await muproFrame(page).selectOption('/t00000004/Polar');
    await muproComponent(page).fill('0');
    await expect(voxelForm(page)).toContainText('已显示 · Polar · 第 2 步 · 分量 1');
    await voxelCoordinate(page, 'X').fill('4');
    await expect(voxelRead(page)).toBeDisabled();
    await voxelCoordinate(page, 'X').fill('2');
    await voxelCoordinate(page, 'Y').fill('1');
    await expect(voxelCoordinate(page, 'Z')).toHaveValue('0');
    expect(sent.seen.filter(call => !call.endsWith('task.get'))).toEqual([]);
    await expect(voxelRead(page)).toBeInViewport({ratio: 1});
    const scroll = await page.locator('section.analysis').evaluate(el => el.scrollTop);
    const measured = route(page, `${viewport.name}-hdf5-voxel`);
    if (viewport.name === 'narrow') {
      await voxelRead(page).focus();
      await page.keyboard.press('Enter');
    } else {
      await measured.click(voxelRead(page), '读取体素');
    }
    await expect(voxelValue(page)).toHaveText('9223372036854775931 · uint64');
    await expect(voxelValue(page)).toBeInViewport({ratio: 1});
    expect(sent.seen.filter(call => !call.endsWith('task.get'))).toEqual(['/api/v1/actions graph.evaluate']);
    expect(hub.evaluations.at(-1)).toMatchObject({bindings: {run: {task_id: task}}, outputs: ['source', 'voxel'],
      graph: {nodes: [
        {params: {expected_sha256: HDF5_ARTIFACT.sha256, path: 'case/run.h5', selector: '/t00000002/Polar', extent: [2, 2, 1, 1, 0, 0]}},
        {params: {operation: 'component', component: 1}},
        {params: {format: 'npy'}},
      ]}});
    expect(await page.locator('section.analysis').evaluate(el => el.scrollTop)).toBe(scroll);
    expect(await canvas.evaluate(el => (el as any).__voxelCanvas)).toBe(true);
    await expect(source(page)).toHaveText(muproSource);
    expect(hub.probes).toEqual([]);
    expect(errors).toEqual([]);
    sent.stop();
    writeFileSync(test.info().outputPath('voxel-route.json'), JSON.stringify({viewport, scroll,
      pointerClicks: measured.record.clicks, enterKeys: viewport.name === 'narrow' ? 1 : 0, editedAxes: 2}, null, 2));
  });
}

test('HDF5 voxel ignores stale results after edits, hiding, frame replacement and task replacement', async ({page}) => {
  const hub = new Hub();
  hub.presets = [PRESET];
  hub.device = graphTwoScopes;
  hub.hdf5Artifacts.set(task, HDF5_ARTIFACT);
  await setup(page, hub, {scene: false});
  await showGraph(page);
  await openHdf5Field(page, '/t00000002/Scalar');

  async function holdRead() {
    hub.reached.delete('hdf5 voxel');
    const release = hub.holdNext('hdf5 voxel');
    const completed = page.waitForResponse(response => response.request().method() === 'POST' &&
      response.request().postDataJSON()?.payload?.outputs?.includes('voxel'));
    await voxelRead(page).click();
    await expect.poll(() => hub.reached.has('hdf5 voxel')).toBe(true);
    return async () => {release(); await completed;};
  }

  let finish = await holdRead();
  await voxelCoordinate(page, 'X').fill('2');
  await finish();
  await expect(voxelValue(page)).toHaveCount(0);
  await expect(voxelRead(page)).toBeEnabled();

  finish = await holdRead();
  await go(page, '任务');
  await finish();
  await go(page, '结果');
  await expect(voxelForm(page)).toBeVisible();
  await expect(voxelValue(page)).toHaveCount(0);
  await expect(voxelCoordinate(page, 'X')).toHaveValue('2');

  finish = await holdRead();
  await muproFrame(page).selectOption('/t00000004/Polar');
  await muproComponent(page).fill('2');
  await muproOpen(page).click();
  await expect(source(page)).toHaveText('显示的三维结果，MuPRO HDF5 · 解析场验证 · 第 4 步');
  await finish();
  await expect(voxelValue(page)).toHaveCount(0);
  await expect(voxelCoordinate(page, 'X')).toHaveValue('0');

  for (const [fault, error] of [['source', '坐标或类型'], ['digest', 'SHA-256'], ['size', '超过声明的大小']] as const) {
    hub.voxelFault = fault;
    await voxelRead(page).click();
    await expect(voxelForm(page).getByRole('alert')).toContainText(error);
    await expect(voxelValue(page)).toHaveCount(0);
    await expect(vtkCanvas(graphPane(page))).toHaveCount(1);
  }
  hub.voxelFault = undefined;
  await voxelRead(page).click();
  await expect(voxelValue(page)).toHaveText('0.3125 · float32');

  finish = await holdRead();
  await go(page, '任务');
  await chooseProject(page, ws2);
  await page.getByRole('button', {name: /图谱来源乙/}).click();
  await showGraph(page);
  await computeGraph(page, hub);
  await finish();
  await expect(source(page)).toHaveText(graphSourceB);
  await expect(voxelForm(page)).toHaveCount(0);
  expect(hub.probes).toEqual([]);
});

test('MuPRO HDF5 replies from a former task cannot populate or replace the current graph', async ({page}) => {
  const hub = new Hub();
  hub.presets = [PRESET];
  hub.device = graphTwoScopes;
  hub.hdf5Artifacts.set(task, HDF5_ARTIFACT);
  await setup(page, hub, {scene: false});
  await showGraph(page);
  await muproPanel(page).locator('summary').click();
  await muproList(page).click();
  await muproFrame(page).selectOption('/t00000002/Scalar');
  const release = hub.holdNext('hdf5 open');
  await muproOpen(page).click();
  await expect.poll(() => hub.reached.has('hdf5 open')).toBe(true);

  await go(page, '任务');
  await chooseProject(page, ws2);
  await page.getByRole('button', {name: /图谱来源乙/}).click();
  await showGraph(page);
  await expect(muproPanel(page)).toHaveCount(0);
  await computeGraph(page, hub);
  await expect(source(page)).toHaveText(graphSourceB);
  const finished = page.waitForResponse(r => r.request().postDataJSON()?.payload?.graph?.nodes?.[0]?.type === 'stk.source.mupro_hdf5@1');
  release();
  await finished;
  await expect(source(page)).toHaveText(graphSourceB);
  await expect(muproPanel(page)).toHaveCount(0);
  expect(hub.evaluations.map(request => request.bindings.run?.task_id ?? request.bindings.field?.task_id)).toEqual([task, task, task2]);
});

for (const viewport of viewports) {
  test(`${viewport.name} source opens the displayed graph binding, even when Tasks selects a different workspace`, async ({page}) => {
    await page.setViewportSize({width: viewport.width, height: viewport.height});
    const hub = new Hub();
    hub.device = graphTwoScopes;
    hub.presets = [PRESET];
    const errors = await setup(page, hub, {scene: false});
    await showGraph(page);
    await binding(page).selectOption(task2);
    await computeGraph(page, hub);
    await expect(source(page)).toHaveText(graphSourceB);
    expect(hub.evaluations[0].bindings).toEqual({field: {task_id: task2}});
    await sourceToggle(page).scrollIntoViewIfNeeded();
    await pause(page);
    const viewportArea = graphPane(page).locator('.viewport');
    const canvas = vtkCanvas(graphPane(page));
    await canvas.evaluate(el => { (el as any).__graphSource = 'same-canvas'; });
    const geometry = await viewportArea.boundingBox();
    const scroll = await page.locator('section.analysis').evaluate(el => el.scrollTop);
    await page.screenshot({path: test.info().outputPath('graph-source-fixed-start.png')});
    const sent = traffic(page), r = route(page, `${viewport.name}-graph-source`);
    await r.click(sourceToggle(page), '来源');
    await expect(sourcePanel(page)).toBeVisible();
    expect(await detailRows(page)).toEqual([
      ['显示内容', '显示的三维结果'], ['图谱预设', '场视图field-view'], ['输出', 'main'], ['节点', '节点甲' + node],
      ['计算绑定 field', '图谱来源乙' + task2], ['运行工作区 field', '项目二' + ws2], ['已显示时间步', '1000'],
    ]);
    expect(await viewportArea.boundingBox()).toEqual(geometry);
    await page.screenshot({path: test.info().outputPath('graph-source-open.png')});
    await r.click(sourcePanel(page).getByRole('button', {name: '收起'}), '收起');
    await expect(sourceToggle(page)).toBeFocused();
    expect(await canvas.evaluate(el => (el as any).__graphSource)).toBe('same-canvas');
    expect(await viewportArea.boundingBox()).toEqual(geometry);
    expect(await page.locator('section.analysis').evaluate(el => el.scrollTop)).toBe(scroll);
    sent.stop();
    expect(sent.seen).toEqual([]);
    expect(hub.evaluations).toHaveLength(1);
    expect([hub.calls, hub.messages, hub.replies, errors]).toEqual([[], [], 0, []]);
    expect(r.record).toMatchObject({clicks: 2, selects: 0});
    r.save();
    writeFileSync(test.info().outputPath('graph-source-requests.json'), JSON.stringify({
      setup: hub.evaluations, measured: sent.seen, source: graphSourceB, fixedViewport: viewport,
    }, null, 2));
  });
}

const rawGraphProbe = (page: Page) => graphPane(page).getByRole('button', {name: '查询原始值'});
async function pickGraphDomain(page: Page) {
  const canvas = vtkCanvas(graphPane(page));
  await canvas.scrollIntoViewIfNeeded();
  const box = (await canvas.boundingBox())!;
  const picked = graphPane(page).locator('.probe small');
  for (const [x, y] of [[.5, .52], [.45, .55], [.55, .55], [.42, .48], [.5, .63]]) {
    await page.mouse.click(box.x + box.width * x, box.y + box.height * y);
    if ((await picked.textContent())?.includes('Domains')) break;
  }
  await expect(picked).toContainText('Domains');
}

const datPreset = {...PRESET, graph: {nodes: [
  {id: 'run', type: 'stk.source.muferro_run@1', params: {binding: 'field'}},
  {id: 'src', type: 'stk.source.muferro_frame@1', inputs: {frames: {from: 'run.frames'}},
    params: {dataset: 'Polar', step: {$param: 'step'}}},
]}};
const datName = 'Polar.00001000.dat', datPath = `case/${datName}`;
for (const viewport of viewports) {
  test(`${viewport.name} task logs and graph probes keep the newer reading on screen`, async ({page}) => {
    await page.setViewportSize({width: viewport.width, height: viewport.height});
    const hub = new Hub();
    hub.device = graphTwoScopes;
    hub.presets = [datPreset];
    hub.artifactPathsByTask.set(task2, [datPath]);
    hub.logTexts.set(`${task} stderr`, STDERR);
    await setup(page, hub, {scene: false});
    await shortcut(page, '读取日志').click();
    await expectStream(page, '标准输出', LOG);
    await showGraph(page);
    await binding(page).selectOption(task2);
    await computeGraph(page, hub);
    await pickGraphDomain(page);

    const release = hub.hold('task.logs');
    hub.reached.clear();
    try {
      await logStream(page, '标准错误').click();
      await expect.poll(() => hub.reached.has('task.logs')).toBe(true);
      await rawGraphProbe(page).click();
      await expect(probeLog(page)).toContainText(datPath);
    } finally {
      release();
    }
    await expect(footer(page)).toContainText('就绪');
    await expect(probeLog(page)).toContainText(datPath);
    await modeTab(page, '结果文件').click();
    await expectStream(page, '标准错误', STDERR);
    await modeTab(page, '图谱').click();
    await expect(probeLog(page)).toContainText(datPath);

    // An older probe that arrives after the accepted log does not take over the panel either.
    const releaseProbe = hub.hold('view.probe');
    hub.reached.clear();
    try {
      await rawGraphProbe(page).click();
      await expect.poll(() => hub.reached.has('view.probe')).toBe(true);
      await logStream(page, '标准输出').click();
      await expectStream(page, '标准输出', LOG);
    } finally {
      releaseProbe();
    }
    await expect(rawGraphProbe(page)).toBeEnabled();
    expect(hub.probes).toHaveLength(2);
    await expectStream(page, '标准输出', LOG);
  });

  test(`${viewport.name} a graph probe clicked during 继续读取 stays on screen; 结果文件 shows the appended log`, async ({page}) => {
    await page.setViewportSize({width: viewport.width, height: viewport.height});
    const hub = new Hub();
    hub.device = graphTwoScopes;
    hub.presets = [datPreset];
    hub.artifactPathsByTask.set(task2, [datPath]);
    hub.logChunk = 200;
    await setup(page, hub, {scene: false});
    await shortcut(page, '读取日志').click();
    await expectStream(page, '标准输出', LOG.slice(0, 200));
    await showGraph(page);
    await binding(page).selectOption(task2);
    await computeGraph(page, hub);
    await pickGraphDomain(page);
    await expectStream(page, '标准输出', LOG.slice(0, 200));
    const release = hub.hold('task.logs');
    hub.reached.clear();
    try {
      await logMore(page).click();
      await expect.poll(() => hub.reached.has('task.logs')).toBe(true);
      await rawGraphProbe(page).click();
      await expect(probeLog(page)).toContainText(datPath);
    } finally {
      release();
    }
    await expect(footer(page)).toContainText('就绪');
    await expect(probeLog(page)).toContainText(datPath);
    await expect(logMore(page)).toHaveCount(0);
    await modeTab(page, '结果文件').click();
    await expectStream(page, '标准输出', LOG.slice(0, 400));
    await expectMore(page, '继续读取', '');
    expect(hub.logPayloads).toEqual([{task_id: task}, {task_id: task, offset: 200}]);
  });

  test(`${viewport.name} DAT probe resolves the shown binding's published frame only on explicit query`, async ({page}) => {
    await page.setViewportSize({width: viewport.width, height: viewport.height});
    const hub = new Hub();
    hub.device = graphTwoScopes;
    hub.presets = [datPreset];
    hub.artifactPathsByTask.set(task, [datName]);
    hub.artifactPathsByTask.set(task2, [datPath]);
    const legacy = viewport.name === 'narrow';
    if (legacy) hub.readKinds = ['task.get', 'task.events'];
    const errors = await setup(page, hub, {scene: false});
    await showGraph(page);
    const sent = posts(page);
    await binding(page).selectOption(task2);
    await computeGraph(page, hub);
    await expect(source(page)).toHaveText(graphSourceB);
    await pickGraphDomain(page);
    expect(sent.seen.filter(call => !call.endsWith('task.get'))).toEqual(['/api/v1/actions graph.evaluate']);

    const publication = page.waitForRequest(request => request.method() === 'POST' &&
      request.postDataJSON()?.kind === 'task.artifacts');
    await rawGraphProbe(page).click();
    expect((await publication).postDataJSON().payload).toEqual({task_id: task2});
    await expect(probeLog(page)).toContainText(datPath);
    expect(hub.probes).toMatchObject([{task_id: task2, path: datPath}]);
    expect(sent.seen.filter(call => !call.endsWith('task.get'))).toEqual([
      '/api/v1/actions graph.evaluate',
      legacy ? '/api/v1/actions task.artifacts' : '/api/v1/nodes/{node}/read task.artifacts',
      '/api/v1/actions view.probe',
    ]);

    hub.artifactPathsByTask.set(task2, [datName, datPath]);
    await rawGraphProbe(page).click();
    await expect(page.getByRole('alert')).toContainText('多个同名 MuFerro 帧');
    expect(hub.probes).toHaveLength(1);
    await expect(source(page)).toHaveText(graphSourceB);
    expect(errors).toEqual([]);
    sent.stop();
  });
}

test('DAT probe drops a held publication after the point changes and a held raw reply after the binding changes', async ({page}) => {
  const hub = new Hub();
  hub.device = graphTwoScopes;
  hub.presets = [datPreset];
  hub.artifactPathsByTask.set(task2, [datPath]);
  await setup(page, hub, {scene: false});
  await showGraph(page);
  await binding(page).selectOption(task2);
  await computeGraph(page, hub);
  await pickGraphDomain(page);

  const publicationKey = `task.artifacts ${task2}`;
  const releaseArtifacts = hub.hold(publicationKey);
  const oldRead = page.waitForRequest(request => request.method() === 'POST' && request.postDataJSON()?.kind === 'task.artifacts');
  await rawGraphProbe(page).click();
  await expect.poll(() => hub.reached.has(publicationKey)).toBe(true);
  const hubRequest = await oldRead;
  const cancelled = page.waitForEvent('requestfailed', {predicate: request => request === hubRequest});
  await graphPane(page).getByLabel('探针X').fill('1.5');
  await cancelled;
  releaseArtifacts();
  await expect(rawGraphProbe(page)).toBeEnabled();
  expect(hub.probes).toHaveLength(0);

  const releaseRaw = hub.hold('view.probe');
  await rawGraphProbe(page).click();
  await expect.poll(() => hub.reached.has('view.probe')).toBe(true);
  const response = page.waitForResponse(res => res.request().method() === 'POST' && res.request().postDataJSON()?.kind === 'view.probe');
  await binding(page).selectOption(task);
  releaseRaw();
  await response;
  await expect(source(page)).toHaveText(graphSourceB);
  await expect(probeLog(page)).not.toContainText(datPath);
  await expect(rawGraphProbe(page)).toBeEnabled();
  expect(hub.probes).toMatchObject([{task_id: task2, path: datPath, position: [1.5, expect.any(Number), expect.any(Number)]}]);
});

test('graph source keeps the displayed scene through a stale binding reply and a failed scene decode', async ({page}) => {
  const hub = new Hub();
  hub.device = graphTwoScopes;
  hub.presets = [{...PRESET, graph: {nodes: [
    {id: 'src', type: 'stk.source.file@1', params: {binding: 'field', path: 'field.dat'}},
  ]}}];
  const errors = await setup(page, hub, {scene: false});
  await showGraph(page);
  await binding(page).selectOption(task2);
  await computeGraph(page, hub);
  await expect(source(page)).toHaveText(graphSourceB);
  const canvas = vtkCanvas(graphPane(page));
  await canvas.evaluate(el => { (el as any).__graphSource = 'same-canvas'; });
  await pickGraphDomain(page);
  await graphPane(page).getByRole('button', {name: '查询原始值'}).click();
  await expect(probeLog(page)).toContainText('field.dat');
  expect(hub.probes).toMatchObject([{task_id: task2, path: 'field.dat'}]);
  await graphPane(page).getByLabel('探针X').fill('1.5');
  const release = hub.hold('graph.evaluate');
  await binding(page).selectOption(task);
  const response = page.waitForResponse(res => res.request().method() === 'POST' &&
    res.url().endsWith('/api/v1/actions') && res.request().postDataJSON()?.kind === 'graph.evaluate');
  await graphPane(page).getByRole('button', {name: '计算图谱'}).click();
  await expect.poll(() => hub.reached.has('graph.evaluate')).toBe(true);
  await expect(source(page)).toHaveText(graphSourceB);
  await binding(page).selectOption(task2);
  await expect(graphPane(page).getByRole('button', {name: '计算图谱'})).toBeEnabled();
  release();
  await response;
  await expect(source(page)).toHaveText(graphSourceB);
  await binding(page).selectOption(task);
  hub.graphReply = 'bad-payload';
  await graphPane(page).getByRole('button', {name: '计算图谱'}).click();
  await expect(page.getByRole('alert')).toContainText('三维结果无法显示');
  await expect(graphPane(page).locator('.graph-outputs')).toContainText('可用的图谱输出');
  await expect(source(page)).toHaveText(graphSourceB);
  await sourceToggle(page).click();
  expect(await detailValues(page)).toContain(task2);
  expect(await detailValues(page)).not.toContain(task);
  await page.keyboard.press('Escape');
  expect(await canvas.evaluate(el => (el as any).__graphSource)).toBe('same-canvas');
  await expect(graphPane(page).getByLabel('探针X')).toHaveValue('1.5');
  await expect(probeLog(page)).toContainText('field.dat');
  hub.graphReply = 'normal';
  hub.graphPayloadStep = 500;
  await graphPane(page).getByRole('button', {name: '计算图谱'}).click();
  await expect(source(page)).toHaveText('显示的三维结果，场视图 · 解析场验证 · 第 500 步');
  await expect(probeLog(page)).not.toContainText('field.dat');
  expect(hub.evaluations.map(request => request.bindings.field.task_id)).toEqual([task2, task, task, task]);
  expect(errors).toEqual([]);
});

test('graph provenance waits for the renderer and survives a delayed actor failure', async ({page}) => {
  const hub = new Hub();
  hub.device = graphTwoScopes;
  hub.presets = [PRESET];
  hub.graphPayloadStep = null;
  hub.graphVolume = 'omit';
  const errors = await setup(page, hub, {scene: false});
  await showGraph(page);
  await binding(page).selectOption(task2);
  await computeGraph(page, hub);
  await expect(source(page)).toHaveText(graphSourceB);
  const canvas = vtkCanvas(graphPane(page));
  await canvas.evaluate(el => { (el as any).__graphSource = 'previous-actor'; });
  hub.graphVolume = 'fail';
  const release = hub.hold('volume chunk');
  await binding(page).selectOption(task);
  await graphPane(page).getByRole('button', {name: '计算图谱'}).click();
  await expect.poll(() => hub.reached.has('volume chunk')).toBe(true);
  await expect(source(page)).toHaveText(graphSourceB);
  expect(await canvas.evaluate(el => (el as any).__graphSource)).toBe('previous-actor');
  release();
  await expect(graphPane(page).locator('.viewer-error')).toContainText('Synthetic volume actor failure');
  await expect(source(page)).toHaveText(graphSourceB);
  expect(await canvas.evaluate(el => (el as any).__graphSource)).toBe('previous-actor');
  expect(hub.evaluations.map(e => e.bindings.field.task_id)).toEqual([task2, task]);
  expect(errors).toEqual([]);
});

test('graph source distinguishes a local package and output cards without inventing a scene or task', async ({page}) => {
  const hub = new Hub();
  hub.device = graphTwoScopes;
  hub.presets = [PRESET];
  const errors = await setup(page, hub, {scene: false});
  await showGraph(page);
  await openPackage(page);
  await expect(source(page)).toHaveText('本地数据包，example.stkp');
  await sourceToggle(page).click();
  expect(await detailRows(page)).toEqual([['本地数据包', 'example.stkp']]);
  await page.keyboard.press('Escape');
  await chooseProject(page, ws2);
  await go(page, '结果');
  await graphEmpty(page);
  await expect(source(page)).toHaveText('尚未显示图谱结果，选择数据源并计算图谱');
  await binding(page).selectOption(task2);
  hub.graphReply = 'outputs-only';
  await graphPane(page).getByRole('button', {name: '计算图谱'}).click();
  await expect(graphPane(page).locator('.graph-outputs')).toContainText('可用的图谱输出');
  await expect(source(page)).toHaveText('显示的图谱输出，场视图 · 图谱来源乙 · 第 1000 步');
  await expect(vtkCanvas(graphPane(page))).toHaveCount(0);
  await sourceToggle(page).click();
  expect(await detailValues(page)).toContain(task2);
  expect(await detailValues(page)).not.toContain('main');
  expect(hub.evaluations).toHaveLength(1);
  expect(errors).toEqual([]);
});

for (const viewport of viewports) {
  for (const taskCount of [1, 200]) {
    test(`${viewport.name} first scope leaves 新建任务 reachable for a ${taskCount}-row queue`, async ({page}) => {
      await page.setViewportSize({width: viewport.width, height: viewport.height});
      const hub = new Hub();
      const extra = Array.from({length: taskCount - 1}, (_, i) => ({
        ...row, id: (i + 1).toString(16).padStart(32, '0'), name: `额外任务 ${i + 1}`,
      }));
      hub.device = {...device, snapshot: {...device.snapshot, tasks: [row, ...extra]}};
      const errors = await start(page, hub);
      await go(page, '任务');
      await expect(settings(page, '运行环境')).toHaveAttribute('open', '');
      await page.getByLabel('执行节点').selectOption(node);
      await project(page).selectOption(ws);
      await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
      await taskRow(page, '解析场验证').click();
      await expect(status(page)).toContainText('已读取 Runtime 状态');
      await expect(shortcut(page, '在查看器中打开')).toBeInViewport({ratio: 1});
      const surface = page.locator('aside.tasks');
      await surface.evaluate(el => { el.scrollTop = 0; });
      await pause(page);
      const summary = disclosure(page, '新建任务');
      const box = (await summary.boundingBox())!, pane = (await surface.boundingBox())!;
      await page.screenshot({path: test.info().outputPath('tasks-first-scope.png')});
      const sent = traffic(page), r = route(page, `new-task-${viewport.name}-${taskCount}`);
      const scrollRequired = Math.max(0, Math.ceil(box.y + box.height - pane.y - pane.height));
      const wheel = scrollRequired > 0 ? scrollRequired + 8 : 0;
      expect(wheel > 0).toBe(viewport.name === 'narrow' && taskCount === 200);
      if (wheel) {
        await page.mouse.move(pane.x + pane.width / 2, pane.y + pane.height - 10);
        await page.mouse.wheel(0, wheel);
        await expect.poll(() => surface.evaluate(el => el.scrollTop)).toBeGreaterThanOrEqual(scrollRequired);
      }
      await expect(summary).toBeInViewport({ratio: 1});
      await r.click(summary, '新建任务');
      await expect(page.getByLabel('TaskSpec')).toBeVisible();
      await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
      await expect(queue(page).locator('.task.selected')).toHaveText('解析场验证成功');
      sent.stop();
      expect(sent.seen).toEqual([]);
      expect(hub.evaluations).toHaveLength(0);
      expect([hub.calls, hub.messages, hub.replies, errors]).toEqual([[], [], 0, []]);
      expect(r.record).toMatchObject({clicks: 1, selects: 0});
      r.save();
      writeFileSync(test.info().outputPath('new-task-geometry.json'), JSON.stringify({
        viewport, taskCount, fixedStart: 'node and workspace chosen, one selected task, offset 0, first setup folded',
        summary: box, panel: pane, wheelDelta: wheel, measuredRequests: sent.seen, measuredClicks: r.record.clicks,
      }, null, 2));
    });
  }
}

test('a keyboard workspace choice returns focus to the folded summary, and explicit reopening survives scope changes', async ({page}) => {
  const hub = new Hub();
  hub.device = twoProjects;
  hub.others = [{...device, id: node2, name: '节点乙', snapshot: {...device.snapshot,
    tasks: [], workspaces: [{id: ws2, name: '项目二'}]}}];
  const errors = await start(page, hub);
  await go(page, '任务');
  await page.getByLabel('执行节点').selectOption(node);
  const summary = disclosure(page, '运行环境'), area = page.locator('aside.tasks');
  await project(page).focus();
  const scroll = await area.evaluate(el => el.scrollTop);
  const sent = traffic(page);
  await page.keyboard.press('ArrowDown');
  await expect(project(page)).toHaveValue(ws);
  await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
  await expect(summary).toBeFocused();
  expect(await area.evaluate(el => el.scrollTop)).toBe(scroll);
  await page.keyboard.press('Enter');
  await expect(settings(page, '运行环境')).toHaveAttribute('open', '');
  await project(page).selectOption(ws2);
  await expect(settings(page, '运行环境')).toHaveAttribute('open', '');
  await page.getByLabel('执行节点').selectOption(node2);
  await expect(project(page)).toHaveValue('');
  await expect(settings(page, '运行环境')).toHaveAttribute('open', '');
  await project(page).selectOption(ws2);
  await expect(summary).toHaveText('运行环境 · 节点乙 · 项目二');
  await expect(settings(page, '运行环境')).toHaveAttribute('open', '');
  await summary.click();
  await go(page, '结果');
  await go(page, '任务');
  await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
  sent.stop();
  expect(sent.seen).toEqual([]);
  expect(errors).toEqual([]);
});

test('automatic folding leaves outside focus alone and reopens when the selected node is lost', async ({page}) => {
  const hub = new Hub();
  const errors = await start(page, hub);
  await go(page, '任务');
  await page.getByLabel('执行节点').selectOption(node);
  const refreshButton = page.locator('aside.tasks').getByRole('button', {name: '刷新', exact: true});
  await refreshButton.focus();
  await project(page).evaluate((el, id) => {
    (el as HTMLSelectElement).value = id;
    el.dispatchEvent(new Event('change', {bubbles: true}));
  }, ws);
  await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
  await expect(refreshButton).toBeFocused();
  hub.device = {...device, revoked: true};
  hub.publish();
  await expect(page.getByLabel('执行节点')).toHaveValue('');
  await expect(settings(page, '运行环境')).toHaveAttribute('open', '');
  await expect(refreshButton).toBeFocused();
  hub.device = device;
  hub.publish();
  await expect(page.getByLabel('执行节点').locator('option')).toHaveCount(2);
  await page.getByLabel('执行节点').selectOption(node);
  await project(page).selectOption(ws);
  await expect(settings(page, '运行环境')).toHaveAttribute('open', '');
  expect(errors).toEqual([]);
});

const preferredWorkspace = '5'.repeat(32);
function environmentHub() {
  const hub = new Hub();
  hub.device = {...device, snapshot: {...device.snapshot, workspaces: [{id: ws, name: '同名工作区'}]}};
  hub.others = [{...device, id: node2, name: '节点乙', snapshot: {...device.snapshot,
    tasks: [{...row, id: task2, name: '节点乙的任务', workspace_id: preferredWorkspace}],
    workspaces: [{id: preferredWorkspace, name: '同名工作区'}]}}];
  return hub;
}

async function chooseSecondEnvironment(page: Page) {
  await selectEnvironment(page, page.getByLabel('执行节点'), node2);
  await selectEnvironment(page, project(page), preferredWorkspace);
}

const savedEnvironment = (page: Page) => page.evaluate(() => sessionStorage.getItem('stk-run-environment'));

for (const viewport of viewports) {
  test(`${viewport.name} a paired tab reload restores its chosen environment on the first Tasks click`, async ({page}) => {
    await page.setViewportSize({width: viewport.width, height: viewport.height});
    const hub = environmentHub();
    const errors = await start(page, hub);
    await go(page, '任务');
    await chooseSecondEnvironment(page);
    await expect(taskRow(page, '节点乙的任务')).toBeVisible();

    const sent = traffic(page), requests = posts(page);
    await page.reload();
    await expectActive(page, '工作台');
    const r = route(page, `restore-environment-${viewport.name}`);
    await r.click(nav(page).getByRole('button', {name: '任务', exact: true}), '任务');
    await expectActive(page, '任务');
    await expect(disclosure(page, '运行环境')).toHaveText('运行环境 · 节点乙 · 同名工作区');
    await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
    await expect(page.getByLabel('执行节点')).toHaveValue(node2);
    await expect(project(page)).toHaveValue(preferredWorkspace);
    await expect(taskRow(page, '节点乙的任务')).toBeInViewport({ratio: 1});
    await expect(queue(page).locator('.task.selected')).toHaveCount(0);
    await expect(status(page)).toHaveCount(0);
    expect(await page.locator('aside.tasks').evaluate(el => el.scrollTop)).toBe(0);
    expect(r.record).toMatchObject({clicks: 1, selects: 0});
    expect([sent.seen, requests.seen, errors]).toEqual([[], [], []]);
    r.save();
    sent.stop();
    requests.stop();
  });
}

test('an unavailable first snapshot keeps the tab preference pending until an authenticated refresh', async ({page}) => {
  const hub = environmentHub();
  const errors = await start(page, hub);
  await go(page, '任务');
  await chooseSecondEnvironment(page);
  const saved = JSON.stringify({node: node2, workspace: preferredWorkspace});
  expect(await savedEnvironment(page)).toBe(saved);

  hub.down = true;
  const sent = posts(page);
  await page.reload();
  await expectActive(page, '工作台');
  await expect(page.locator('header .connection')).toContainText('连接中断');
  await go(page, '任务');
  await expect(settings(page, '运行环境')).toHaveAttribute('open', '');
  await expect(page.getByLabel('执行节点')).toHaveValue('');
  await expect(project(page)).toHaveValue('');
  expect(await savedEnvironment(page)).toBe(saved);
  await disclosure(page, '新建任务').click();
  const spec = page.getByLabel('TaskSpec');
  await spec.fill('{"argv":["python3","draft.py"],"outputs":[]}');

  hub.down = false;
  await page.locator('aside.tasks .section-title').getByRole('button', {name: '刷新'}).click();
  await expect(taskRow(page, '节点乙的任务')).toBeVisible();
  await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
  await expect(project(page)).toHaveValue(preferredWorkspace);
  await expect(spec).toHaveValue('{"argv":["python3","draft.py"],"outputs":[]}');
  expect(sent.seen).toEqual([]);
  sent.stop();
  expect(unexpected(errors, 503)).toEqual([]);
});

for (const invalid of ['revoked node', 'workspace absent from the chosen node'] as const) {
  test(`a fresh listing discards the previous environment with a ${invalid}`, async ({page}) => {
    const hub = environmentHub();
    const original = hub.others[0];
    const errors = await start(page, hub);
    await go(page, '任务');
    await chooseSecondEnvironment(page);
    hub.device = {...hub.device, snapshot: {...hub.device.snapshot,
      workspaces: [...hub.device.snapshot.workspaces, {id: preferredWorkspace, name: '同名工作区'}]}};
    hub.others = [invalid === 'revoked node' ? {...original, revoked: true} :
      {...original, snapshot: {...original.snapshot, workspaces: []}}];
    const sent = posts(page);
    await page.reload();
    await expectActive(page, '工作台');
    await go(page, '任务');
    await expect(page.getByLabel('执行节点').locator(`option[value="${node}"]`)).toHaveCount(1);
    await expect(settings(page, '运行环境')).toHaveAttribute('open', '');
    await expect(page.getByLabel('执行节点')).toHaveValue('');
    await expect(project(page)).toHaveValue('');
    expect(await savedEnvironment(page)).toBeNull();

    hub.others = [original];
    await page.locator('aside.tasks .section-title').getByRole('button', {name: '刷新'}).click();
    await expect(page.getByLabel('执行节点').locator(`option[value="${node2}"]`)).toHaveCount(1);
    await expect(page.getByLabel('执行节点')).toHaveValue('');
    expect([sent.seen, errors]).toEqual([[], []]);
    sent.stop();
  });
}

test('partial environment choices and an explicit disconnect forget the tab preference', async ({page}) => {
  const hub = environmentHub();
  const errors = await start(page, hub);
  await go(page, '任务');
  await chooseSecondEnvironment(page);
  await selectEnvironment(page, project(page), '');
  expect(await savedEnvironment(page)).toBeNull();
  await chooseSecondEnvironment(page);
  await selectEnvironment(page, page.getByLabel('执行节点'), node);
  await expect(project(page)).toHaveValue('');
  expect(await savedEnvironment(page)).toBeNull();
  await chooseSecondEnvironment(page);
  expect(await savedEnvironment(page)).not.toBeNull();
  await page.locator('header').getByRole('button', {name: '断开'}).click();
  await expect(page.getByLabel('一次性配对码')).toBeVisible();
  expect(await savedEnvironment(page)).toBeNull();
  await page.getByText('使用已有设备凭据').click();
  await page.getByLabel('设备凭据').fill('abcdefghijklmnopqrstu');
  await page.getByRole('button', {name: '连接', exact: true}).click();
  await expectActive(page, '工作台');
  await go(page, '任务');
  await expect(page.getByLabel('执行节点').locator(`option[value="${node2}"]`)).toHaveCount(1);
  await expect(page.getByLabel('执行节点')).toHaveValue('');
  await expect(project(page)).toHaveValue('');
  expect(errors).toEqual([]);
});

// 新建任务 after an explicit 新建 in 运行环境: when the create receipt names its workspace and that workspace is chosen
// for the same node and selection, the form is open by default. Its own buttons remain the only submission. An
// ordinary choice, a reply after the scope or connection changed, a review or a receipt without an ID leave it as it
// was, and so does an earlier manual opening or closing. A new workspace named like an existing one binds by its ID.
const createButton = (page: Page) => settings(page, '运行环境').getByRole('button', {name: '新建', exact: true});
const SPEC_DEFAULT = '{"argv":["python3","analysis.py"],"outputs":[]}';
async function createWorkspace(page: Page, name: string) {
  await page.getByLabel('项目名称').fill(name);
  await createButton(page).click();
}
// 任务 with a node chosen and 运行环境 still open from first setup.
async function nodeChosen(page: Page, hub: Hub) {
  const errors = await start(page, hub);
  await go(page, '任务');
  await page.getByLabel('执行节点').selectOption(node);
  await expect(settings(page, '运行环境')).toHaveAttribute('open', '');
  return errors;
}

test('a confirmed created environment can restore once the fresh listing contains its exact ID', async ({page}) => {
  const hub = new Hub();
  hub.listLater = true;
  const errors = await nodeChosen(page, hub);
  await createWorkspace(page, '项目一');
  const id = createdId(1);
  await expect(footer(page)).toContainText('就绪');
  await expect(disclosure(page, '新建任务')).toHaveText(`新建任务 · ${id.slice(0, 8)}`);
  await expect(project(page)).toHaveValue('');
  expect(await savedEnvironment(page)).toBe(JSON.stringify({node, workspace: id}));

  hub.listCreated();
  const sent = posts(page);
  await page.reload();
  await expectActive(page, '工作台');
  await go(page, '任务');
  await expect(project(page)).toHaveValue(id);
  await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
  await expect(settings(page, '新建任务')).not.toHaveAttribute('open', '');
  expect(hub.creates).toEqual([{node, name: '项目一'}]);
  expect([sent.seen, errors]).toEqual([[], []]);
  sent.stop();
});

for (const viewport of viewports) {
  test(`${viewport.name} a confirmed new workspace shows 新建任务 with no disclosure click and no submission`, async ({page}) => {
    await page.setViewportSize({width: viewport.width, height: viewport.height});
    const hub = new Hub();
    const errors = await nodeChosen(page, hub);
    await createWorkspace(page, '项目一');
    const made = createdId(1);
    await expect(project(page)).toHaveValue(made);
    await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
    await expect(disclosure(page, '运行环境')).toHaveText('运行环境 · 节点甲 · 项目一');
    await expect(footer(page)).toContainText('就绪');
    expect(hub.creates).toEqual([{node, name: '项目一'}]);
    const surface = page.locator('aside.tasks');
    await surface.evaluate(el => { el.scrollTop = 0; });
    await pause(page);
    // Fixed start: 任务 at offset 0, the new workspace just confirmed and chosen, 运行环境 folded by itself.
    const sent = traffic(page), r = route(page, `created-workspace-${viewport.name}`);
    await page.screenshot({path: test.info().outputPath(`${viewport.name}-created-workspace.png`)});
    await expectActive(page, '任务');
    await expect(queue(page)).toContainText('项目一 中暂无任务，可在下方「新建任务」中提交。');
    await expect(settings(page, '新建任务')).toHaveAttribute('open', '');
    await expect(disclosure(page, '新建任务')).toHaveText('新建任务 · 项目一');
    const spec = page.getByLabel('TaskSpec'), example = page.getByRole('button', {name: '运行解析场示例'});
    const review = page.getByRole('button', {name: '提交复核'});
    await expect(spec).toHaveValue(SPEC_DEFAULT);
    await expect(example).toBeEnabled();
    await expect(review).toBeEnabled();
    for (const target of [example, spec, review]) await expect(target).toBeInViewport({ratio: 1});
    const box = async (target: Locator) => (await target.boundingBox())!;
    const geometry = {viewport, panel: await box(surface), summary: await box(disclosure(page, '新建任务')),
      example: await box(example), spec: await box(spec), submit: await box(review),
      scrollTop: await surface.evaluate(el => el.scrollTop)};
    expect(geometry.scrollTop).toBe(0);
    sent.stop();
    expect(sent.seen).toEqual([]);
    expect(hub.creates).toHaveLength(1);
    expect([hub.calls, hub.messages, hub.replies, errors]).toEqual([[], [], 0, []]);
    expect(r.record).toMatchObject({clicks: 0, selects: 0});
    r.save();
    writeFileSync(test.info().outputPath('created-workspace-geometry.json'), JSON.stringify({
      fixedStart: '任务 at offset 0, new synthetic workspace confirmed and chosen, 运行环境 folded automatically',
      createdWorkspace: made, measuredClicks: r.record.clicks, measuredRequests: sent.seen, ...geometry,
    }, null, 2));
  });
}

test('the form opened for a new workspace submits only on its explicit button, for that workspace', async ({page}) => {
  const hub = new Hub();
  const errors = await nodeChosen(page, hub);
  const sent = posts(page);
  await createWorkspace(page, '项目一');
  const made = createdId(1);
  await expect(settings(page, '新建任务')).toHaveAttribute('open', '');
  await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
  await expect(footer(page)).toContainText('就绪');
  expect(writes(sent.seen)).toEqual(['/api/v1/actions workspace.create']);
  const submitted = page.waitForRequest(request => request.method() === 'POST' && request.url().endsWith('/api/v1/actions') &&
    request.postDataJSON()?.kind === 'task.submit');
  await page.getByRole('button', {name: '运行解析场示例'}).click();
  const body = (await submitted).postDataJSON();
  expect(body.node_id).toBe(node);
  expect(body.payload).toMatchObject({template: 'demo-field', spec: {workspace_id: made, name: '解析场验证'}});
  await expect(footer(page)).toContainText('就绪');
  sent.stop();
  expect(writes(sent.seen)).toEqual(['/api/v1/actions workspace.create', '/api/v1/actions task.submit']);
  await expectActive(page, '任务');
  await expect(project(page)).toHaveValue(made);
  await expect(settings(page, '新建任务')).toHaveAttribute('open', '');
  expect([hub.calls, hub.messages, hub.replies, errors]).toEqual([[], [], 0, []]);
});

test('ordinary choices, late replies, reviews and malformed receipts leave 新建任务 folded', async ({page}) => {
  const hub = new Hub();
  hub.device = twoProjects;
  hub.others = [{...device, id: node2, name: '节点乙', snapshot: {...device.snapshot, tasks: [], workspaces: [{id: ws2, name: '项目二'}]}}];
  const errors = await nodeChosen(page, hub);
  const sent = posts(page);
  const folded = async () => {
    await expect(footer(page)).toContainText('就绪');
    await expect(settings(page, '新建任务')).not.toHaveAttribute('open', '');
    await expect(page.getByLabel('TaskSpec')).toBeHidden();
  };
  // An ordinary choice of an existing workspace folds 运行环境 and leaves 新建任务 closed.
  await project(page).selectOption(ws);
  await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
  await folded();
  await disclosure(page, '运行环境').click();
  await project(page).selectOption(ws2);
  await folded();
  // A create answered after the node changed (and changed back) is not adopted.
  let release = hub.hold('workspace.create');
  await createWorkspace(page, '项目三');
  await expect.poll(() => hub.reached.has('workspace.create')).toBe(true);
  await page.getByLabel('执行节点').selectOption(node2);
  await page.getByLabel('执行节点').selectOption(node);
  release();
  await expect.poll(() => hub.creates.length).toBe(1);
  await expect(project(page).locator('option', {hasText: '项目三'})).toHaveCount(1);
  await expect(project(page)).toHaveValue('');
  await folded();
  // A create answered after another task selection in the same node is not adopted either.
  hub.reached.clear();
  await project(page).selectOption(ws);
  release = hub.hold('workspace.create');
  await createWorkspace(page, '项目四');
  await expect.poll(() => hub.reached.has('workspace.create')).toBe(true);
  await taskRow(page, '解析场验证').click();
  release();
  await expect.poll(() => hub.creates.length).toBe(2);
  await expect(project(page)).toHaveValue(ws);
  await folded();
  // Review and malformed create receipts leave the selected workspace in place.
  hub.createReply = 'review';
  await createWorkspace(page, '项目五');
  await expect(page.locator('aside.tasks article.review')).toContainText('新建项目需要执行复核');
  await expect(project(page)).toHaveValue(ws);
  await folded();
  for (const [reply, name] of [['no-id', '项目六'], ['invalid-id', '项目七']] as const) {
    hub.createReply = reply;
    await createWorkspace(page, name);
    await expect(project(page).locator('option', {hasText: name})).toHaveCount(1);
    await expect(project(page)).toHaveValue(ws);
    await folded();
  }
  await expect(disclosure(page, '新建任务')).toHaveText('新建任务 · 项目一');
  await expectActive(page, '任务');
  sent.stop();
  expect(writes(sent.seen).filter(s => !s.endsWith(' workspace.create'))).toEqual([]);
  expect(writes(sent.seen)).toHaveLength(5);
  expect(errors).toEqual([]);
});

test('a create answered after disconnecting and reconnecting is not adopted', async ({page}) => {
  const hub = new Hub();
  const errors = await nodeChosen(page, hub);
  const release = hub.hold('workspace.create');
  await createWorkspace(page, '项目三');
  await expect.poll(() => hub.reached.has('workspace.create')).toBe(true);
  await page.locator('header').getByRole('button', {name: '断开'}).click();
  await page.getByText('使用已有设备凭据').click();
  await page.getByLabel('设备凭据').fill('abcdefghijklmnopqrstu');
  await page.getByRole('button', {name: '连接', exact: true}).click();
  await expectActive(page, '工作台');
  const answered = page.waitForResponse(response => response.url().endsWith('/api/v1/actions') &&
    response.request().method() === 'POST' && response.request().postDataJSON()?.kind === 'workspace.create');
  release();
  expect((await (await answered).json()).result.id).toBe(createdId(1));
  await page.waitForTimeout(200); // the former page's continuation of that reply has run
  await go(page, '任务');
  await expect(settings(page, '运行环境')).toHaveAttribute('open', '');
  await expect(page.getByLabel('执行节点')).toHaveValue('');
  await expect(settings(page, '新建任务')).not.toHaveAttribute('open', '');
  await expect(footer(page)).toContainText('就绪');
  expect(errors).toEqual([]);
});

test('a 新建任务 closed by hand with a draft stays closed, with its draft, after a create', async ({page}) => {
  const hub = new Hub();
  hub.device = twoProjects;
  const errors = await nodeChosen(page, hub);
  const sent = posts(page);
  // Opened, edited and closed by hand before any create: a new workspace leaves it closed and the draft as typed.
  await disclosure(page, '新建任务').click();
  await page.getByLabel('TaskSpec').fill('{"argv":["python3","draft.py"],"outputs":[]}');
  await disclosure(page, '新建任务').click();
  await createWorkspace(page, '项目三');
  await expect(project(page)).toHaveValue(createdId(1));
  await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
  await expect(footer(page)).toContainText('就绪');
  await expect(settings(page, '新建任务')).not.toHaveAttribute('open', '');
  await disclosure(page, '新建任务').click();
  await expect(page.getByLabel('TaskSpec')).toHaveValue('{"argv":["python3","draft.py"],"outputs":[]}');
  sent.stop();
  expect(writes(sent.seen)).toEqual(['/api/v1/actions workspace.create']);
  expect(errors).toEqual([]);
});

test('after the automatic opening, ordinary choices keep 新建任务 open and a manual close holds for later creates', async ({page}) => {
  const hub = new Hub();
  hub.device = twoProjects;
  const errors = await nodeChosen(page, hub);
  const sent = posts(page);
  await createWorkspace(page, '项目三');
  await expect(project(page)).toHaveValue(createdId(1));
  await expect(settings(page, '新建任务')).toHaveAttribute('open', '');
  await page.getByLabel('TaskSpec').fill('{"argv":["python3","draft.py"],"outputs":[]}');
  await disclosure(page, '运行环境').click();
  await project(page).selectOption(ws2);
  await expect(settings(page, '新建任务')).toHaveAttribute('open', '');
  await disclosure(page, '新建任务').click();
  await createWorkspace(page, '项目四');
  await expect(project(page)).toHaveValue(createdId(2));
  await expect(footer(page)).toContainText('就绪');
  await expect(settings(page, '新建任务')).not.toHaveAttribute('open', '');
  await disclosure(page, '新建任务').click();
  await expect(page.getByLabel('TaskSpec')).toHaveValue('{"argv":["python3","draft.py"],"outputs":[]}');
  await expectActive(page, '任务');
  sent.stop();
  expect(writes(sent.seen)).toEqual(['/api/v1/actions workspace.create', '/api/v1/actions workspace.create']);
  expect(errors).toEqual([]);
});

test('the retained custom task draft cannot submit to a different workspace than the form shows', async ({page}) => {
  const hub = new Hub();
  hub.review = true;
  const errors = await nodeChosen(page, hub);
  const sent = posts(page);
  await createWorkspace(page, '原工作区');
  const original = createdId(1), current = createdId(2);
  await expect(project(page)).toHaveValue(original);
  const spec = page.getByLabel('TaskSpec');
  const draft = {workspace_id: original, argv: ['python3', 'draft.py'], outputs: []};
  await spec.fill(JSON.stringify(draft));
  await disclosure(page, '运行环境').click();
  await createWorkspace(page, '当前工作区');
  await expect(project(page)).toHaveValue(current);
  await expect(disclosure(page, '新建任务')).toHaveText('新建任务 · 当前工作区');
  await expect(spec).toHaveValue(JSON.stringify(draft));

  const submit = page.getByRole('button', {name: '提交复核'});
  const submittedWorkspaces: string[] = [];
  page.on('request', request => {
    if (request.method() !== 'POST' || !request.url().endsWith('/api/v1/actions')) return;
    const body = request.postDataJSON();
    if (body?.kind === 'task.submit') submittedWorkspaces.push(body.payload.spec.workspace_id);
  });
  await submit.click();
  await expect(footer(page)).toContainText('就绪');
  expect(submittedWorkspaces).toEqual([]);
  const creates = ['/api/v1/actions workspace.create', '/api/v1/actions workspace.create'];
  expect(writes(sent.seen)).toEqual(creates);
  await expect(page.getByRole('alert')).toContainText('工作区与当前项目不一致');
  await expect(spec).toHaveValue(JSON.stringify(draft));
  await expect(project(page)).toHaveValue(current);

  await spec.fill(JSON.stringify({...draft, workspace_id: current}));
  const request = page.waitForRequest(r => r.method() === 'POST' && r.url().endsWith('/api/v1/actions') &&
    r.postDataJSON()?.kind === 'task.submit');
  await submit.click();
  expect((await request).postDataJSON()).toMatchObject({node_id: node,
    payload: {spec: {...draft, workspace_id: current}}});
  await expect(footer(page)).toContainText('就绪');
  expect(submittedWorkspaces).toEqual([current]);
  sent.stop();
  expect(writes(sent.seen)).toEqual([...creates, '/api/v1/actions task.submit']);
  expect(errors).toEqual([]);
});

test('a new workspace the node lists only later opens 新建任务 at once, keeps it through the fold and submits to it', async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  const hub = new Hub();
  hub.listLater = true;
  const errors = await nodeChosen(page, hub);
  const sent = posts(page);
  await createWorkspace(page, '项目一');
  const made = createdId(1);
  await expect(footer(page)).toContainText('就绪');
  // The receipt is the evidence; the snapshot does not list the workspace yet, so 运行环境 stays open over it and
  // its 项目 list has no option for the chosen ID (the summaries name it by its ID).
  await expect(project(page)).toHaveValue('');
  await expect(settings(page, '新建任务')).toHaveAttribute('open', '');
  await expect(settings(page, '运行环境')).toHaveAttribute('open', '');
  await expect(disclosure(page, '新建任务')).toHaveText(`新建任务 · ${made.slice(0, 8)}`);
  const spec = page.getByLabel('TaskSpec'), review = page.getByRole('button', {name: '提交复核'});
  await spec.fill('{"argv":["python3","draft.py"],"outputs":[]}');
  const before = (await review.boundingBox())!;
  hub.listCreated();
  hub.publish();
  await expect(settings(page, '运行环境')).not.toHaveAttribute('open', '');
  await expect(disclosure(page, '新建任务')).toHaveText('新建任务 · 项目一');
  await expect(project(page)).toHaveValue(made);
  await expect(settings(page, '新建任务')).toHaveAttribute('open', '');
  await expect(spec).toHaveValue('{"argv":["python3","draft.py"],"outputs":[]}');
  const after = (await review.boundingBox())!;
  writeFileSync(test.info().outputPath('listed-later-geometry.json'), JSON.stringify({
    viewport: {width: 1440, height: 900}, createdWorkspace: made, submitBeforeListing: before, submitAfterFold: after,
    submitShiftY: after.y - before.y}, null, 2));
  expect(writes(sent.seen)).toEqual(['/api/v1/actions workspace.create']);
  const submitted = page.waitForRequest(request => request.method() === 'POST' && request.url().endsWith('/api/v1/actions') &&
    request.postDataJSON()?.kind === 'task.submit');
  await review.click();
  expect((await submitted).postDataJSON().payload).toEqual({spec: {workspace_id: made, argv: ['python3', 'draft.py'], outputs: []}});
  await expect(footer(page)).toContainText('就绪');
  sent.stop();
  expect(writes(sent.seen)).toEqual(['/api/v1/actions workspace.create', '/api/v1/actions task.submit']);
  await expectActive(page, '任务');
  expect(errors).toEqual([]);
});

// 结果 from a selected successful task's 在查看器中打开, as the desktop names it. When the list that click itself read
// and adopted publishes exactly one VTI, with a canonical path, a whole size and a lowercase SHA-256, beside only
// .log/.txt/.md notes, 结果文件 opens it in one step: that path is chosen and one view.build of the current slice
// options shows it, for that exact task and path. Any other list with exactly one file the 结果文件 list can show
// (no digest, NPY, DAT, VTK, a VTI beside another result, an ambiguous list) only preselects it, and 加载视图 stays
// the user's explicit click. More files, none, an existing or cleared choice, a shown Viewer, the 结果 nav button,
// 读取日志 and 图谱 keep the list as it is, as does a reply that arrives after the task or project changed, 结果
// was left, the mode switched, the history covered 结果 or the choice was edited; a 视图 edit while the list is read
// keeps the choice but leaves the build to 加载视图.
const fileList = (page: Page) => page.getByLabel('结果文件');
const loadButton = (page: Page) => page.getByRole('button', {name: '加载视图'});
const listed = async (page: Page) => (await fileList(page).locator('option').allTextContents()).slice(1);
const openInViewer = (page: Page) => shortcut(page, '在查看器中打开');
const built = (hub: Hub) => hub.builds.map(b => [b.task_id, b.path, b.options]);
const sliceOf = (path: string, axis = 2, index?: number) =>
  [task, path, {mode: 'slice', axis, ...(index === undefined ? {} : {index})}];
// The index each view.build actually sent, or 中间层 where the payload had no index key at all.
const sentIndex = (hub: Hub) => hub.builds.map(b => Object.hasOwn(b.options, 'index') ? b.options.index : '中间层');
const indexBox = (page: Page) => page.getByRole('spinbutton', {name: '索引', exact: true});
const unfinished = (box: Locator) => box.evaluate(el => (el as HTMLInputElement).validity.badInput);
// The plane 来源 details name for the shown Viewer, read by opening and closing them.
async function slicePlace(page: Page) {
  await page.getByRole('button', {name: '来源', exact: true}).click();
  const row = page.getByRole('region', {name: '来源详情', exact: true}).locator('div').filter({has: page.locator('dt', {hasText: '显示的切片'})});
  const place = await row.count() ? await row.locator('dd').textContent() : null;
  await page.getByRole('button', {name: '收起', exact: true}).click();
  return place;
}
const LIST_READ = '/api/v1/nodes/{node}/read task.artifacts', LIST_ACTION = '/api/v1/actions task.artifacts';
const REVIEW_NOTE = '操作等待复核，请在任务面板查看完整参数。';
async function settled(page: Page) {
  await expect(footer(page)).toContainText('就绪');
  await page.waitForTimeout(300);
}
// Lists that keep the two-step route: the one file the list shows is chosen, and nothing is built.
const published = (path: string, extra: Record<string, unknown> = {}) => ({path, size: 10, sha256: digestOf(path), ...extra});
const TWO_STEP: [string, unknown[], string][] = [
  ['a VTI published without a digest', [{path: 'scalar-0.vti', size: 10}], 'scalar-0.vti'],
  ['a VTI with an uppercase digest', [published('scalar-0.vti', {sha256: digestOf('scalar-0.vti').toUpperCase()})], 'scalar-0.vti'],
  ['an empty VTI', [published('scalar-0.vti', {size: 0})], 'scalar-0.vti'],
  ['a sole NPY', [published('notes.txt'), published('field.npy')], 'field.npy'],
  ['a sole DAT', [published('case/Polar.00001000.dat')], 'case/Polar.00001000.dat'],
  ['a sole VTK', [published('mesh.vtk')], 'mesh.vtk'],
  ['a VTI beside a result JSON', [published('scalar-0.vti'), published('result.json')], 'scalar-0.vti'],
  ['a VTI beside an HDF5 file', [published('scalar-0.vti'), published('case/run.h5')], 'scalar-0.vti'],
  ['a result JSON listed before a VTI', [published('result.json'), published('scalar-0.vti')], 'scalar-0.vti'],
  ['a VTI with a non-canonical path', [published('./scalar-0.vti')], './scalar-0.vti'],
  ['a VTI that names the directory of a note', [published('out.vti'), published('out.vti/notes.txt')], 'out.vti'],
  ['a VTI beside notes repeated by case', [published('scalar-0.vti'), published('notes.txt'), published('NOTES.txt')], 'scalar-0.vti'],
  ['a VTI beside a note of negative size', [published('scalar-0.vti'), published('run.log', {size: -1})], 'scalar-0.vti'],
];
for (const viewport of viewports) {
  test.describe(`${viewport.name} single result file`, () => {
    test.use({viewport: {width: viewport.width, height: viewport.height}});

    for (const legacy of [false, true]) {
      test(`在查看器中打开 opens the sole published VTI in one click ${legacy ? 'through the legacy task.artifacts action' : 'through the read-only node read'}, and 任务 returns to it`, async ({page}) => {
        const hub = new Hub();
        // Notes beside it: logs and text are not results.
        hub.artifactPaths = ['notes.txt', 'run.log', 'README.md', 'scalar-0.vti'];
        if (legacy) hub.readKinds = ['task.get', 'task.events'];
        const release = hub.hold('task.artifacts');
        const errors = await setup(page, hub, {scene: false});
        await freeze(page);
        const sent = posts(page);
        const list = legacy ? LIST_ACTION : LIST_READ;
        const r = route(page, `${viewport.name}-${legacy ? 'legacy' : 'read'}-sole-vti`);
        await r.click(openInViewer(page), '在查看器中打开');
        await expectActive(page, '结果');
        await expect(fileList(page)).toBeFocused();
        await expect.poll(() => hub.reached.has('task.artifacts')).toBe(true);
        // While its list is read nothing is chosen or built, and 结果 names no file yet.
        await expect(fileList(page)).toHaveValue('');
        await expect(source(page)).toHaveText(shown('尚未加载结果文件'));
        expect(hub.builds).toEqual([]);
        expect(sent.seen).toEqual(legacy ? [list] : []);
        release();
        await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
        await expect(page.locator('section.analysis .legend')).toBeVisible();
        await expect(title(page)).toHaveText('phi');
        await expect(fileList(page)).toHaveValue('scalar-0.vti');
        expect(await listed(page)).toEqual(['scalar-0.vti']);
        await settled(page);
        await expect(fileList(page)).toBeFocused();
        expect(built(hub)).toEqual([sliceOf('scalar-0.vti')]);
        expect(sent.seen).toEqual([...(legacy ? [list] : []), '/api/v1/actions view.build']);
        // Fixed start: 任务 with the successful task selected, 结果文件 mode, no Viewer. Was 结果 + 加载视图.
        expect(r.record).toMatchObject({clicks: 1, selects: 0});
        await page.screenshot({path: test.info().outputPath(`${viewport.name}-${legacy ? 'legacy' : 'read'}-sole-vti.png`)});
        // One click back: 任务 returns the focus to the launcher. Opening the same task again lists it and keeps the scene.
        await page.locator('section.analysis .viewport canvas').evaluate(el => { (el as any).__marker = 'same-canvas'; });
        await r.click(nav(page).getByRole('button', {name: '任务', exact: true}), '任务');
        await expectActive(page, '任务');
        await expect(openInViewer(page)).toBeFocused();
        await page.screenshot({path: test.info().outputPath(`${viewport.name}-${legacy ? 'legacy' : 'read'}-sole-vti-returned.png`)});
        await r.click(openInViewer(page), '在查看器中打开');
        await expectActive(page, '结果');
        await settled(page);
        sent.stop();
        expect(await canvasMarker(page)).toBe('same-canvas');
        await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
        expect(built(hub)).toEqual([sliceOf('scalar-0.vti')]);
        expect(sent.seen).toEqual([...(legacy ? [list] : []), '/api/v1/actions view.build', list]);
        expect([hub.evaluations, hub.probes, hub.calls, hub.replies, hub.messages, hub.creates]).toEqual([[], [], [], 0, [], []]);
        expect(r.record).toMatchObject({clicks: 3, selects: 0});
        r.save();
        // Drafts and the task are kept.
        await expect(page.getByLabel('对话内容')).toHaveValue('未发送的草稿：分析 phi 场');
        await expect(page.getByLabel('TaskSpec')).toHaveValue('{"argv":["python3","draft.py"],"outputs":[]}');
        await expect(page.locator('aside.tasks .task.selected')).toContainText('解析场验证');
        expect(errors).toEqual([]);
      });
    }

    for (const [what, rows, file] of TWO_STEP) {
      test(`在查看器中打开 with ${what} only preselects it for 加载视图`, async ({page}) => {
        const hub = new Hub();
        hub.artifactRows = rows;
        const errors = await setup(page, hub, {scene: false});
        await openInViewer(page).click();
        await expect(fileList(page)).toHaveValue(file);
        await settled(page);
        await expect(fileList(page)).toBeFocused();
        await expect(source(page)).toHaveText(`${shown('尚未加载结果文件')}${pending(file)}`);
        await expect(page.locator('section.analysis .legend')).toHaveCount(0);
        expect(hub.builds).toEqual([]);
        await loadButton(page).click();
        await expect(source(page)).toHaveText(shown(`显示 ${file}`));
        expect(built(hub)).toEqual([sliceOf(file, 2, 0)]);
        expect(errors).toEqual([]);
      });
    }

    test('a failed legacy list read or a failed one-step build keeps its existing error and 加载视图', async ({page}) => {
      const hub = new Hub();
      hub.readKinds = ['task.get', 'task.events'];
      hub.viewErrors.set('task.artifacts', '无权读取任务产物');
      const errors = await setup(page, hub, {scene: false});
      await openInViewer(page).click();
      await expect(page.getByRole('alert')).toContainText('无权读取任务产物');
      await settled(page);
      await expect(fileList(page)).toHaveValue('');
      expect(await listed(page)).toEqual([]);
      expect(hub.builds).toEqual([]);
      await page.getByRole('alert').getByRole('button', {name: '关闭'}).click();
      hub.viewErrors.delete('task.artifacts');
      hub.viewErrors.set('view.build', '视图构建被拒绝');
      await go(page, '任务');
      await openInViewer(page).click();
      // The one build is reported as 加载视图 reports it; the choice stays for an explicit retry.
      await expect(page.getByRole('alert')).toContainText('视图构建被拒绝');
      await settled(page);
      await expect(fileList(page)).toHaveValue('scalar-0.vti');
      await expect(source(page)).toHaveText(`${shown('尚未加载结果文件')}${pending('scalar-0.vti')}`);
      expect(built(hub)).toEqual([sliceOf('scalar-0.vti')]);
      hub.viewErrors.delete('view.build');
      await loadButton(page).click();
      await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
      await expect(page.getByRole('alert')).toHaveCount(0);
      expect(built(hub)).toEqual([sliceOf('scalar-0.vti'), sliceOf('scalar-0.vti', 2, 0)]);
      expect(unexpected(errors, 502)).toEqual([]);
    });

    test('a refused current artifact read cannot fall back to a legacy action or build', async ({page}) => {
      const hub = new Hub();
      hub.readKinds = ['task.get', 'task.events'];
      const errors = await setup(page, hub, {scene: false});
      let release!: () => void;
      const held = new Promise<void>(resolve => { release = resolve; });
      let asked = false;
      await page.route('**/api/v1/nodes/*/read', async route => {
        const body = route.request().postDataJSON();
        if (body?.kind !== 'task.artifacts' || body?.payload?.task_id !== task) return route.fallback();
        asked = true;
        await held;
        await route.fulfill({status: 403, json: {detail: '无权读取任务产物'}});
      });
      const sent = posts(page);
      const launcher = openInViewer(page);
      try {
        // Advertise the node read and hold its exact-task response through the shortcut.
        hub.readKinds = ['task.get', 'task.events', 'task.artifacts'];
        hub.publish();
        await expect.poll(() => asked).toBe(true);
        await launcher.click();
        await expectActive(page, '结果');
        await expect(fileList(page)).toHaveValue('');
        expect(hub.builds).toEqual([]);
      } finally {
        release();
      }
      await expect(page.getByRole('button', {name: '连接工作台 →'})).toBeVisible();
      await page.waitForTimeout(300);
      sent.stop();
      expect(sent.seen).toContain('/api/v1/nodes/{node}/read task.artifacts');
      expect(writes(sent.seen)).toEqual([]);
      expect(hub.builds).toEqual([]);
      expect(unexpected(errors, 403)).toEqual([]);
    });

    test('a legacy artifact action in review cannot adopt its result envelope or build', async ({page}) => {
      const hub = new Hub();
      hub.readKinds = ['task.get', 'task.events'];
      const errors = await setup(page, hub, {scene: false});
      await page.route('**/api/v1/actions', async route => {
        const body = route.request().postDataJSON();
        if (route.request().method() !== 'POST' || body?.kind !== 'task.artifacts') return route.fallback();
        expect(body.payload).toEqual({task_id: task});
        const item = {id: body.id, state: 'review', review_reason: '读取结果文件需要执行复核',
          request: {kind: body.kind, payload: body.payload},
          result: [{path: 'scalar-0.vti', sha256: 'a'.repeat(64), size: 1024}]};
        hub.actionRows.unshift(item);
        await route.fulfill({json: item});
      });
      const sent = posts(page);
      await openInViewer(page).click();
      await expectActive(page, '结果');
      await expect(page.getByRole('alert')).toContainText('操作等待复核');
      await settled(page);
      await expect(fileList(page)).toHaveValue('');
      expect(await listed(page)).toEqual([]);
      await expect(page.locator('section.analysis .viewport canvas')).toHaveCount(0);
      sent.stop();
      expect(writes(sent.seen)).toEqual(['/api/v1/actions task.artifacts']);
      expect(hub.builds).toEqual([]);
      expect(errors).toEqual([]);
    });

    test('a build sent to execution review keeps its choice and opens nothing', async ({page}) => {
      const hub = new Hub();
      hub.reviewKinds.add('view.build');
      const errors = await setup(page, hub, {scene: false});
      await openInViewer(page).click();
      await expect(page.getByRole('alert')).toContainText(REVIEW_NOTE);
      await settled(page);
      await expect(fileList(page)).toHaveValue('scalar-0.vti');
      await expect(source(page)).toHaveText(`${shown('尚未加载结果文件')}${pending('scalar-0.vti')}`);
      await expect(page.locator('section.analysis .legend')).toHaveCount(0);
      expect(built(hub)).toEqual([sliceOf('scalar-0.vti')]);
      expect(hub.actionRows.map(a => [a.request.kind, a.state])).toEqual([['view.build', 'review']]);
      expect(errors).toEqual([]);
    });

    test('an already accepted terminal list opens the exact result without another read', async ({page}) => {
      const hub = new Hub();
      hub.artifactPaths = ['scalar-0.VTI'];
      const errors = await setup(page, hub, {scene: false});
      await go(page, '结果');
      await expect.poll(() => listed(page)).toEqual(['scalar-0.VTI']);
      await go(page, '任务');
      await freeze(page);
      const sent = posts(page);
      await openInViewer(page).click();
      await expect(source(page)).toHaveText(shown('显示 scalar-0.VTI'));
      await settled(page);
      sent.stop();
      expect(sent.seen).toEqual(['/api/v1/actions view.build']);
      expect(built(hub)).toEqual([sliceOf('scalar-0.VTI')]);
      expect(errors).toEqual([]);
    });

    for (const first of ['old', 'current'] as const) {
      test(`a click waiting on the heartbeat list adopts only the exact terminal list (${first} reply first)`, async ({page}) => {
        const hub = new Hub();
        hub.queueArtifacts = true;
        const releaseTask = hub.holdNext('task.get');
        const errors = await setup(page, hub, {scene: false, verifiedTask: false});
        await expect.poll(() => hub.artifactQueue.length).toBe(1);
        const [old] = hub.artifactQueue.splice(0);
        const sent = posts(page);
        await openInViewer(page).click();
        await expectActive(page, '结果');
        expect(sent.seen).toEqual([]);
        await expect(footer(page)).toContainText('列出结果文件…');
        releaseTask();
        await expect(page.locator('aside.tasks .task-observation')).toContainText('已读取 Runtime 状态');
        await expect.poll(() => hub.artifactQueue.length).toBe(1);
        const [current] = hub.artifactQueue.splice(0);
        if (first === 'old') {
          old();
          // The click still waits for the exact terminal list it needs.
          await expect(footer(page)).toContainText('列出结果文件…');
          await expect(fileList(page)).toHaveValue('');
          expect(built(hub)).toEqual([]);
        }
        current();
        await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
        if (first === 'current') old();
        await settled(page);
        sent.stop();
        expect(sent.seen).toEqual([LIST_READ, '/api/v1/actions view.build']);
        expect(built(hub)).toEqual([sliceOf('scalar-0.vti')]);
        expect(errors).toEqual([]);
      });
    }

    test('an automatic build requires the published digest before adopting its scene', async ({page}) => {
      const hub = new Hub();
      hub.reportedViewDigest = digestOf('another file');
      const errors = await setup(page, hub, {scene: false});
      await openInViewer(page).click();
      await expect(page.getByRole('alert')).toContainText('返回的数据摘要与发布文件不符');
      await expect(fileList(page)).toHaveValue('scalar-0.vti');
      await expect(page.locator('section.analysis .viewport canvas')).toHaveCount(0);
      expect(built(hub)).toEqual([sliceOf('scalar-0.vti')]);
      expect(errors).toEqual([]);
    });

    test('the default slice uses the selected axis midpoint and a later manual load keeps that index', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub, {scene: false});
      await go(page, '结果');
      await page.getByRole('combobox', {name: '方向', exact: true}).selectOption('0');
      await go(page, '任务');
      await openInViewer(page).click();
      await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
      await expect(page.getByRole('spinbutton', {name: '索引', exact: true})).toHaveValue('16');
      await page.getByRole('button', {name: '来源', exact: true}).click();
      await expect(page.getByRole('region', {name: '来源详情', exact: true})).toContainText('X · 索引 16');
      await page.getByRole('button', {name: '收起', exact: true}).click();
      await expect(loadButton(page)).toBeEnabled();
      await loadButton(page).click();
      await settled(page);
      expect(built(hub)).toEqual([sliceOf('scalar-0.vti', 0), sliceOf('scalar-0.vti', 0, 16)]);
      expect(errors).toEqual([]);
    });

    test('an explicit zero is used by the shortcut and a later edit stays in the form', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub, {scene: false});
      await go(page, '结果');
      const index = page.getByRole('spinbutton', {name: '索引', exact: true});
      await index.fill('3');
      await index.fill('0');
      await go(page, '任务');
      const release = hub.hold('view.build');
      try {
        await openInViewer(page).click();
        await expect.poll(() => hub.reached.has('view.build')).toBe(true);
        await index.fill('5');
      } finally {
        release();
      }
      await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
      await expect(index).toHaveValue('5');
      await page.getByRole('button', {name: '来源', exact: true}).click();
      await expect(page.getByRole('region', {name: '来源详情', exact: true})).toContainText('Z · 索引 0');
      expect(built(hub)).toEqual([sliceOf('scalar-0.vti', 2, 0)]);
      expect(errors).toEqual([]);
    });

    // 索引 has three states: untouched (a manual load sends the 0 it shows), a typed integer (0 included) sent as
    // typed, and cleared to 中间层, which sends no index so Runtime takes the selected axis's middle plane (the mock's
    // grid is 32 × 28 × 24: X 16, Y 14, Z 12). Editing it sends nothing, and an accepted receipt never refills it.
    test('a cleared 索引 asks Runtime for the middle plane of the selected axis, and a typed 0 asks for 0 again', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub);
      const index = indexBox(page);
      await go(page, '结果');
      // The untouched first manual load (in setup) sent the 0 the box showed.
      await expect(index).toHaveValue('0');
      expect(sentIndex(hub)).toEqual([0]);
      const controls = await page.locator('section.analysis .view-controls').boundingBox();
      const sent = posts(page);
      await index.fill('');
      await expect(index).toHaveValue('');
      await expect(index).toHaveAttribute('placeholder', '中间层');
      expect(await page.locator('section.analysis .view-controls').boundingBox()).toEqual(controls);
      await page.waitForTimeout(300);
      expect(sent.seen).toEqual([]);
      sent.stop();
      // The shown Viewer and its 来源 stay until a later build succeeds.
      await expect(slicePlace(page)).resolves.toBe('Z · 索引 0');
      await loadButton(page).click();
      await expect.poll(() => slicePlace(page)).toBe('Z · 索引 12');
      await expect(index).toHaveValue('');
      await page.getByRole('combobox', {name: '方向', exact: true}).selectOption('0');
      await expect(index).toHaveValue('');
      await loadButton(page).click();
      await expect.poll(() => slicePlace(page)).toBe('X · 索引 16');
      await expect(index).toHaveValue('');
      await index.fill('0');
      await loadButton(page).click();
      await expect.poll(() => slicePlace(page)).toBe('X · 索引 0');
      await expect(index).toHaveValue('0');
      await index.fill('');
      await loadButton(page).click();
      await expect.poll(() => slicePlace(page)).toBe('X · 索引 16');
      await settled(page);
      await expect(index).toHaveValue('');
      await expect(page.locator('section.analysis .viewport canvas')).toHaveCount(1);
      expect(sentIndex(hub)).toEqual([0, '中间层', '中间层', 0, '中间层']);
      expect(built(hub)).toEqual([sliceOf('scalar-0.vti', 2, 0), sliceOf('scalar-0.vti', 2), sliceOf('scalar-0.vti', 0),
        sliceOf('scalar-0.vti', 0, 0), sliceOf('scalar-0.vti', 0)]);
      expect(errors).toEqual([]);
    });

    test('a cleared 索引 opens the middle plane in one step and stays cleared through an in-flight edit and a failed build', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub, {scene: false});
      const index = indexBox(page);
      await go(page, '结果');
      await index.fill('3');
      await index.fill('');
      await go(page, '任务');
      await openInViewer(page).click();
      await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
      await settled(page);
      await expect.poll(() => slicePlace(page)).toBe('Z · 索引 12');
      await expect(index).toHaveValue('');
      await index.fill('5');
      const release = hub.hold('view.build');
      try {
        await loadButton(page).click();
        await expect.poll(() => hub.reached.has('view.build')).toBe(true);
        // Edits while the build is in flight belong to the next request; the Viewer keeps the current plane.
        await index.fill('');
        await page.getByRole('combobox', {name: '方向', exact: true}).selectOption('1');
        await expect(slicePlace(page)).resolves.toBe('Z · 索引 12');
      } finally {
        release();
      }
      await expect.poll(() => slicePlace(page)).toBe('Z · 索引 5');
      await settled(page);
      await expect(index).toHaveValue('');
      await expect(page.getByRole('combobox', {name: '方向', exact: true})).toHaveValue('1');
      hub.viewErrors.set('view.build', '切片构建失败');
      await loadButton(page).click();
      await expect(page.getByRole('alert')).toContainText('切片构建失败');
      await settled(page);
      await expect(slicePlace(page)).resolves.toBe('Z · 索引 5');
      await expect(page.locator('section.analysis .viewport canvas')).toHaveCount(1);
      await expect(index).toHaveValue('');
      hub.viewErrors.delete('view.build');
      await loadButton(page).click();
      await expect.poll(() => slicePlace(page)).toBe('Y · 索引 14');
      await settled(page);
      await expect(index).toHaveValue('');
      expect(sentIndex(hub)).toEqual(['中间层', 5, '中间层', '中间层']);
      expect(built(hub)).toEqual([sliceOf('scalar-0.vti', 2), sliceOf('scalar-0.vti', 2, 5), sliceOf('scalar-0.vti', 1),
        sliceOf('scalar-0.vti', 1)]);
      expect(errors.filter(e => !e.includes('502'))).toEqual([]);
    });

    // A half-typed number reads as '' in the box; typed into an emptied box it fires no change at all.
    test('an unfinished 索引 is neither an index nor 中间层: no build until it is finished or cleared', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub, {scene: false});
      const index = indexBox(page);
      await go(page, '结果');
      await index.fill('3');
      await index.fill('');
      await page.keyboard.type('-');
      expect(await unfinished(index)).toBe(true);
      await go(page, '任务');
      // The click reuses the list 结果 accepted, so it would build at once.
      await openInViewer(page).click();
      await expect(fileList(page)).toHaveValue('scalar-0.vti');
      expect(await unfinished(index)).toBe(true);
      await settled(page);
      expect(hub.builds).toEqual([]);
      await expect(page.locator('section.analysis .viewport canvas')).toHaveCount(0);
      const sent = posts(page);
      await loadButton(page).click();
      await expect(index).toBeFocused();
      await expect(page.getByRole('alert')).toHaveCount(0);
      await page.waitForTimeout(300);
      expect(sent.seen).toEqual([]);
      sent.stop();
      await page.keyboard.press('Backspace');
      expect(await unfinished(index)).toBe(false);
      await expect(index).toHaveValue('');
      await loadButton(page).click();
      await expect.poll(() => slicePlace(page)).toBe('Z · 索引 12');
      await settled(page);
      // From a typed index, the half-typed value is again refused and the shown plane is kept.
      await index.fill('4');
      await index.selectText();
      await page.keyboard.type('-');
      expect(await unfinished(index)).toBe(true);
      await loadButton(page).click();
      await page.waitForTimeout(300);
      await expect(slicePlace(page)).resolves.toBe('Z · 索引 12');
      expect(sentIndex(hub)).toEqual(['中间层']);
      expect(built(hub)).toEqual([sliceOf('scalar-0.vti', 2)]);
      expect(errors).toEqual([]);
    });

    test('a reply for the wrong default slice never replaces the Viewer', async ({page}) => {
      const hub = new Hub();
      hub.reportedViewIndex = 0;
      const errors = await setup(page, hub, {scene: false});
      await openInViewer(page).click();
      await expect(page.getByRole('alert')).toContainText('返回的切片位置与所选方向或索引不符');
      await expect(fileList(page)).toHaveValue('scalar-0.vti');
      await expect(page.locator('section.analysis .viewport canvas')).toHaveCount(0);
      expect(built(hub)).toEqual([sliceOf('scalar-0.vti')]);
      expect(errors).toEqual([]);
    });

    test('an in-flight automatic build cannot adopt its scene after the read capability is lost and restored', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub, {scene: false});
      const release = hub.hold('view.build');
      try {
        await openInViewer(page).click();
        await expect.poll(() => hub.reached.has('view.build')).toBe(true);
        hub.readKinds = ['task.get', 'task.events'];
        const denied = page.waitForResponse(res => res.url().endsWith('/api/v1/policy'));
        hub.publish();
        await denied;
        // The denied policy is a distinct render before the same read capability returns.
        await expect(footer(page)).toContainText('正在处理请求');
        hub.readKinds = ['task.get', 'task.artifacts', 'task.events'];
        const currentRead = page.waitForRequest(req => req.method() === 'POST' && req.postDataJSON()?.kind === 'task.artifacts');
        hub.publish();
        await currentRead;
      } finally {
        release();
      }
      await settled(page);
      await expect(page.locator('section.analysis .viewport canvas')).toHaveCount(0);
      expect(built(hub)).toEqual([sliceOf('scalar-0.vti')]);
      expect(errors).toEqual([]);
    });

    test('an artifact list containing a null entry opens nothing and leaves the workbench usable', async ({page}) => {
      const hub = new Hub();
      hub.artifactRows = [null, published('scalar-0.vti')];
      const errors = await setup(page, hub, {scene: false});
      await openInViewer(page).click();
      await expect(page.getByRole('alert')).toContainText('任务产物清单格式无效');
      await expect(fileList(page)).toHaveValue('');
      expect(built(hub)).toEqual([]);
      await go(page, '工作台');
      await expect(page.getByLabel('对话内容')).toHaveValue('未发送的草稿：分析 phi 场');
      expect(errors).toEqual([]);
    });

    test('a conflicting exact task fact keeps the successful heartbeat from authorizing a build', async ({page}) => {
      const hub = new Hub();
      hub.taskReadResults.set(task, {...row, state: 'failed'});
      const errors = await setup(page, hub, {scene: false, verifiedTask: false});
      await expect(page.getByRole('region', {name: '所选任务状态'})).toContainText('最近节点快照');
      await openInViewer(page).click();
      await expect(fileList(page)).toHaveValue('scalar-0.vti');
      await settled(page);
      expect(built(hub)).toEqual([]);
      await expect(page.locator('section.analysis .viewport canvas')).toHaveCount(0);
      expect(errors).toEqual([]);
    });

    test('leaving 结果 or changing the project while the list is read opens nothing', async ({page}) => {
      const hub = new Hub();
      hub.device = twoProjects;
      hub.artifactRows = [{path: 'scalar-0.vti', size: 10}];
      const errors = await setup(page, hub, {scene: false});
      for (const away of ['任务', '工作台'] as const) {
        const release = hub.hold('task.artifacts');
        hub.reached.clear();
        await go(page, '任务');
        await openInViewer(page).click();
        await expect.poll(() => hub.reached.has('task.artifacts')).toBe(true);
        await go(page, away);
        release();
        await settled(page);
        await expectActive(page, away);
        expect(hub.builds).toEqual([]);
      }
      await go(page, '结果');
      await expect(fileList(page)).toHaveValue('');
      await expect(source(page)).toHaveText(shown('尚未加载结果文件'));
      const release = hub.hold('task.artifacts');
      hub.reached.clear();
      await go(page, '任务');
      await openInViewer(page).click();
      await expect.poll(() => hub.reached.has('task.artifacts')).toBe(true);
      await go(page, '任务');
      await selectEnvironment(page, project(page), ws2);
      await go(page, '结果');
      release();
      await settled(page);
      await expectActive(page, '结果');
      await expect(source(page)).toHaveText('未选择任务，在「任务」中选择任务');
      expect(hub.builds).toEqual([]);
      expect(errors).toEqual([]);
    });

    test('a 视图 edit while the list is read, or another view at the click, leaves the build to 加载视图', async ({page}) => {
      const hub = new Hub();
      const release = hub.hold('task.artifacts');
      const errors = await setup(page, hub, {scene: false});
      await openInViewer(page).click();
      await expect.poll(() => hub.reached.has('task.artifacts')).toBe(true);
      await page.getByRole('combobox', {name: '方向', exact: true}).selectOption('0');
      release();
      await expect(fileList(page)).toHaveValue('scalar-0.vti');
      await settled(page);
      expect(hub.builds).toEqual([]);
      await loadButton(page).click();
      await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
      expect(built(hub)).toEqual([sliceOf('scalar-0.vti', 0, 0)]);
      // Another task in 等值面 view: the click preselects, and 加载视图 builds the view the user chose.
      hub.device = twoTasks;
      hub.artifactPathsByTask.set(task2, ['other.vti']);
      await go(page, '任务');
      await page.locator('aside.tasks .section-title').getByRole('button', {name: '刷新', exact: true}).click();
      await taskRow(page, '对照任务').click();
      await go(page, '结果');
      await fileViewMode(page).selectOption('iso');
      await go(page, '任务');
      await openInViewer(page).click();
      await expect(fileList(page)).toHaveValue('other.vti');
      await settled(page);
      expect(hub.builds).toHaveLength(1);
      await loadButton(page).click();
      await expect(source(page)).toHaveText(shown('显示 other.vti', '对照任务'));
      expect(hub.builds.map(b => [b.task_id, b.path, b.options.mode])).toEqual([[task, 'scalar-0.vti', 'slice'], [task2, 'other.vti', 'iso']]);
      expect(errors).toEqual([]);
    });

    // The one build of 在查看器中打开 is fenced like 加载视图: leaving 结果 keeps the page the user chose and lets the same
    // task's scene complete for the return; another file choice or task discards it, and 结果来源 never names it.
    const heldBuild: [string, (page: Page) => Promise<void>, '结果' | '任务', string][] = [
      ['leaving 结果', async page => { await go(page, '任务'); }, '任务', shown('显示 scalar-0.vti')],
      ['clearing the file choice', async page => { await fileList(page).selectOption(''); }, '结果', shown('尚未加载结果文件')],
      ['selecting another task', async page => { await go(page, '任务'); await taskRow(page, '对照任务').click(); }, '任务',
        shown('尚未加载结果文件', '对照任务')],
    ];
    for (const [what, act, stay, after] of heldBuild) {
      test(`a held one-step build after ${what} moves nothing and is shown only for its own choice`, async ({page}) => {
        const hub = new Hub();
        hub.device = twoTasks;
        hub.artifactPathsByTask.set(task2, ['other.vti']);
        const errors = await setup(page, hub, {scene: false});
        const release = hub.hold('view.build');
        hub.reached.clear();
        await openInViewer(page).click();
        await expect.poll(() => hub.reached.has('view.build')).toBe(true);
        // While it is built the file is chosen, not yet shown, named as loading, and the explicit retry waits for it.
        await expect(fileList(page)).toHaveValue('scalar-0.vti');
        await expect(source(page)).toHaveText(`${shown('尚未加载结果文件')}${loading('scalar-0.vti')}`);
        await expect(footer(page)).toContainText('正在加载视图…');
        await expect(loadButton(page)).toBeDisabled();
        await act(page);
        // The page the user is on then names no stage of the build.
        await expect(footer(page)).toContainText('正在处理请求…');
        release();
        await settled(page);
        await expectActive(page, stay);
        expect(built(hub)).toEqual([sliceOf('scalar-0.vti')]);
        if (stay === '任务') await go(page, '结果');
        await expect(source(page)).toHaveText(after);
        await expect(page.locator('section.analysis .legend')).toHaveCount(after === shown('显示 scalar-0.vti') ? 1 : 0);
        expect(built(hub)).toEqual([sliceOf('scalar-0.vti')]);
        expect(errors).toEqual([]);
      });
    }

    test('the 结果 nav button, 读取日志, several files, no viewable file and 图谱 choose no file', async ({page}) => {
      const hub = new Hub();
      hub.artifactRows = [{path: 'scalar-0.vti', size: 10}];
      const errors = await setup(page, hub, {scene: false});
      await go(page, '结果');
      await settled(page);
      expect(await listed(page)).toEqual(['scalar-0.vti']);
      await expect(fileList(page)).toHaveValue('');
      await go(page, '任务');
      await shortcut(page, '读取日志').click();
      await expect(probeLog(page)).toHaveText(LOG);
      await settled(page);
      await expect(fileList(page)).toHaveValue('');
      hub.artifactRows = undefined;
      for (const paths of [['scalar-0.vti', 'scalar-1.vti'], ['notes.txt', 'case/run.h5']]) {
        hub.artifactPaths = paths;
        await go(page, '任务');
        await shortcut(page, '在查看器中打开').click();
        await expect.poll(() => listed(page)).toEqual(paths.filter(p => p.endsWith('.vti')));
        await settled(page);
        await expect(fileList(page)).toHaveValue('');
      }
      // 图谱 mode: the shortcut keeps 图谱, and 结果文件 then shows the list it read with nothing chosen.
      hub.artifactPaths = ['scalar-0.vti'];
      await modeTab(page, '图谱').click();
      await go(page, '任务');
      await shortcut(page, '在查看器中打开').click();
      await expect(modeTab(page, '图谱')).toHaveAttribute('aria-selected', 'true');
      await settled(page);
      await modeTab(page, '结果文件').click();
      expect(await listed(page)).toEqual(['scalar-0.vti']);
      await expect(fileList(page)).toHaveValue('');
      expect(hub.builds).toEqual([]);
      expect(errors).toEqual([]);
    });

    test('a cleared choice under a shown Viewer stays cleared', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub);
      await go(page, '结果');
      await fileList(page).selectOption('');
      await go(page, '任务');
      await shortcut(page, '在查看器中打开').click();
      await settled(page);
      await expect(fileList(page)).toHaveValue('');
      await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
      expect(await canvasMarker(page)).toBe('same-canvas');
      expect(hub.builds.map(b => b.path)).toEqual(['scalar-0.vti']);
      expect(errors).toEqual([]);
    });

    test('a chosen file stays chosen and a cleared choice stays cleared with no Viewer shown', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub, {scene: false});
      await go(page, '结果');
      await fileList(page).selectOption('scalar-0.vti');
      await go(page, '任务');
      await shortcut(page, '在查看器中打开').click();
      await settled(page);
      await expect(fileList(page)).toHaveValue('scalar-0.vti');
      await fileList(page).selectOption('');
      await go(page, '任务');
      await shortcut(page, '在查看器中打开').click();
      await settled(page);
      await expect(fileList(page)).toHaveValue('');
      expect(await listed(page)).toEqual(['scalar-0.vti']);
      await expect(source(page)).toHaveText(shown('尚未加载结果文件'));
      expect(hub.builds).toEqual([]);
      expect(errors).toEqual([]);
    });

    const late: [string, (page: Page) => Promise<void>][] = [
      ['leaving 结果 and returning', async page => { await go(page, '任务'); await go(page, '结果'); }],
      ['switching to 图谱 and back', async page => { await modeTab(page, '图谱').click(); await modeTab(page, '结果文件').click(); }],
      ['editing the choice', async page => { await fileList(page).selectOption('scalar-0.vti'); await fileList(page).selectOption(''); }],
    ];
    if (viewport.name === 'narrow') late.push(['opening the history over 结果', async page => {
      await historyToggle(page).click(); await page.keyboard.press('Escape');
    }]);
    for (const [what, act] of late) {
      test(`a held shortcut list read chooses no file after ${what}`, async ({page}) => {
        const hub = new Hub();
        hub.artifactRows = [{path: 'scalar-0.vti', size: 10}];
        const errors = await setup(page, hub, {scene: false});
        await go(page, '结果');
        await expect.poll(() => listed(page)).toEqual(['scalar-0.vti']);
        await go(page, '任务');
        hub.artifactRows = undefined;
        hub.artifactPaths = ['scalar-1.vti'];
        const release = hub.hold('task.artifacts');
        hub.reached.clear();
        await shortcut(page, '在查看器中打开').click();
        await expect.poll(() => hub.reached.has('task.artifacts')).toBe(true);
        await act(page);
        await expectActive(page, '结果');
        release();
        // The late list is still adopted for the same task; it only chooses nothing.
        await expect.poll(() => listed(page)).toEqual(['scalar-1.vti']);
        await settled(page);
        await expect(fileList(page)).toHaveValue('');
        expect(hub.builds).toEqual([]);
        expect(errors).toEqual([]);
      });
    }

    test('a held shortcut list read of a task no longer selected chooses no file', async ({page}) => {
      const hub = new Hub();
      hub.device = twoTasks;
      hub.artifactPathsByTask.set(task2, ['other.vti']);
      const release = hub.hold(`task.artifacts ${task}`);
      const errors = await setup(page, hub, {scene: false});
      await shortcut(page, '在查看器中打开').click();
      await expect.poll(() => hub.reached.has(`task.artifacts ${task}`)).toBe(true);
      await go(page, '任务');
      await taskRow(page, '对照任务').click();
      await go(page, '结果');
      await expect.poll(() => listed(page)).toEqual(['other.vti']);
      release();
      await settled(page);
      await expect(fileList(page)).toHaveValue('');
      expect(await listed(page)).toEqual(['other.vti']);
      await expect(source(page)).toHaveText(shown('尚未加载结果文件', '对照任务'));
      expect(hub.builds).toEqual([]);
      expect(errors).toEqual([]);
    });
  });
}

// The footer names the stage of one 在查看器中打开 click in its one status place: 列出结果文件… while the click waits
// for the list it needs, 正在加载视图… while the build it sent for the file it chose is pending, and 来源 names that
// file as loading. Only while 结果文件 is in view for the same connection, task and choice; every other request, and
// every page the user moved to, keeps 正在处理请求…. `footerTrail` records every footer status from its call on, so
// a stage shown for one frame cannot pass unnoticed.
const footerStatus = (page: Page) => footer(page).evaluate(el => el.firstChild?.textContent ?? '');
async function footerTrail(page: Page) {
  await page.evaluate(() => {
    const footer = document.querySelector('footer')!;
    const trail: string[] = [footer.firstChild?.textContent ?? ''];
    (window as any).__footerTrail = trail;
    new MutationObserver(() => {
      const text = footer.firstChild?.textContent ?? '';
      if (trail[trail.length - 1] !== text) trail.push(text);
    }).observe(footer, {subtree: true, childList: true, characterData: true});
  });
  return () => page.evaluate(() => [...(window as any).__footerTrail] as string[]);
}
const STAGES = ['列出结果文件…', '正在加载视图…'], STAGE_TEXT = /^(列出结果文件|正在加载视图)…$/;
const staged = (trail: string[]) => trail.filter(text => STAGES.includes(text));
const lastRow = async (page: Page) => (await detailRows(page)).at(-1);
// Nothing beyond the list read and the one build: no graph, probe, conversation, model, create or task write.
const quiet = (hub: Hub) => [hub.evaluations, hub.probes, hub.calls, hub.replies, hub.messages, hub.creates];
const QUIET = [[], [], [], 0, [], []];
function evidence(name: string, data: unknown) {
  writeFileSync(test.info().outputPath(`progress-${name}.json`), JSON.stringify(data, null, 2));
}
for (const viewport of viewports) {
  test.describe(`${viewport.name} result open progress`, () => {
    test.use({viewport: {width: viewport.width, height: viewport.height}});

    test('an accepted sole VTI list goes straight to 正在加载视图… in one click, with no list read', async ({page}) => {
      const hub = new Hub();
      hub.artifactPaths = ['notes.txt', 'scalar-0.vti'];
      const errors = await setup(page, hub, {scene: false});
      await go(page, '结果');
      await expect.poll(() => listed(page)).toEqual(['scalar-0.vti']);
      await go(page, '任务');
      await expect(footer(page)).toContainText('就绪');
      await freeze(page);
      const trail = await footerTrail(page);
      const release = hub.hold('view.build');
      hub.reached.clear();
      const sent = posts(page);
      const r = route(page, `${viewport.name}-progress-accepted`);
      try {
        await r.click(openInViewer(page), '在查看器中打开');
        await expectActive(page, '结果');
        await expect.poll(() => hub.reached.has('view.build')).toBe(true);
        await expect(footer(page)).toContainText('正在加载视图…');
        await expect(fileList(page)).toBeFocused();
        await expect(fileList(page)).toHaveValue('scalar-0.vti');
        await expect(source(page)).toHaveText(`${shown('尚未加载结果文件')}${loading('scalar-0.vti')}`);
        await expect(loadButton(page)).toBeDisabled();
        await expect(page.locator('section.analysis .viewport canvas')).toHaveCount(0);
        await page.screenshot({path: test.info().outputPath(`${viewport.name}-progress-accepted-loading.png`)});
        // 来源 details name the chosen file as loading, not as one to load.
        await sourceToggle(page).click();
        expect((await detailRows(page)).slice(-2)).toEqual([['显示的文件', '尚未加载结果文件'], ['已选文件', 'scalar-0.vti正在加载视图…']]);
        await page.keyboard.press('Escape');
        await expect(sourcePanel(page)).toHaveCount(0);
      } finally {
        release();
      }
      await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
      await settled(page);
      sent.stop();
      const seen = await trail();
      // The click's first status is the build's; no list wait and no generic busy text before it.
      expect(seen.slice(0, 2)).toEqual(['就绪', '正在加载视图…']);
      expect(staged(seen)).toEqual(['正在加载视图…']);
      expect(seen.at(-1)).toBe('就绪');
      expect(sent.seen).toEqual(['/api/v1/actions view.build']);
      expect(built(hub)).toEqual([sliceOf('scalar-0.vti')]);
      expect(quiet(hub)).toEqual(QUIET);
      expect(r.record).toMatchObject({clicks: 1, selects: 0});
      r.save();
      evidence(`${viewport.name}-accepted`, {route: r.record, requests: sent.seen, builds: hub.builds, footer: seen});
      expect(errors).toEqual([]);
    });

    for (const legacy of [false, true]) {
      test(`a held list ${legacy ? 'action' : 'read'} shows 列出结果文件… and then 正在加载视图… for the file it chose`, async ({page}) => {
        const hub = new Hub();
        if (legacy) hub.readKinds = ['task.get', 'task.events'];
        const releaseList = hub.hold('task.artifacts');
        const errors = await setup(page, hub, {scene: false});
        await freeze(page);
        const trail = await footerTrail(page);
        const sent = posts(page);
        const r = route(page, `${viewport.name}-progress-held-${legacy ? 'action' : 'read'}`);
        const releaseBuild = hub.hold('view.build');
        try {
          await r.click(openInViewer(page), '在查看器中打开');
          await expectActive(page, '结果');
          await expect.poll(() => hub.reached.has('task.artifacts')).toBe(true);
          await expect(footer(page)).toContainText('列出结果文件…');
          await expect(fileList(page)).toBeFocused();
          await expect(fileList(page)).toHaveValue('');
          await expect(source(page)).toHaveText(shown('尚未加载结果文件'));
          await expect(loadButton(page)).toBeDisabled();
          await page.screenshot({path: test.info().outputPath(`${viewport.name}-progress-held-listing.png`)});
          releaseList();
          await expect.poll(() => hub.reached.has('view.build')).toBe(true);
          await expect(footer(page)).toContainText('正在加载视图…');
          await expect(source(page)).toHaveText(`${shown('尚未加载结果文件')}${loading('scalar-0.vti')}`);
          await expect(fileList(page)).toBeFocused();
        } finally {
          releaseList();
          releaseBuild();
        }
        await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
        await settled(page);
        sent.stop();
        const seen = await trail();
        expect(seen.slice(0, 2)).toEqual(['就绪', '列出结果文件…']);
        expect(staged(seen)).toEqual(STAGES);
        // The read held before the click is the one it used: no other list request.
        expect(sent.seen).toEqual([...(legacy ? [LIST_ACTION] : []), '/api/v1/actions view.build']);
        expect(built(hub)).toEqual([sliceOf('scalar-0.vti')]);
        expect(quiet(hub)).toEqual(QUIET);
        expect(r.record).toMatchObject({clicks: 1, selects: 0});
        r.save();
        evidence(`${viewport.name}-held-${legacy ? 'action' : 'read'}`, {route: r.record, requests: sent.seen, builds: hub.builds, footer: seen});
        expect(errors).toEqual([]);
      });
    }

    // Each stage ends with the request: the existing failure or review notice and the manual 加载视图 remain. A case may
    // return a step that runs after setup (a page route then takes precedence over the Hub's).
    const ends: [string, (hub: Hub) => ((page: Page) => Promise<void>) | void, string, string, string | null, (number | string)[]][] = [
      ['a failed legacy list action', hub => {
        hub.readKinds = ['task.get', 'task.events'];
        hub.viewErrors.set('task.artifacts', '无权读取任务产物');
      }, '列出结果文件…', '', '无权读取任务产物', [502]],
      ['a legacy list action sent to review', hub => {
        hub.readKinds = ['task.get', 'task.events'];
        return page => page.route('**/api/v1/actions', async route => {
          const body = route.request().postDataJSON();
          if (route.request().method() !== 'POST' || body?.kind !== 'task.artifacts') return route.fallback();
          const item = {id: body.id, state: 'review', review_reason: '读取结果文件需要执行复核',
            request: {kind: body.kind, payload: body.payload}, result: [published('scalar-0.vti')]};
          hub.actionRows.unshift(item);
          await route.fulfill({json: item});
        });
      }, '列出结果文件…', '', '操作等待复核', []],
      ['a list with a null entry', hub => { hub.artifactRows = [null, published('scalar-0.vti')]; },
        '列出结果文件…', '', '任务产物清单格式无效', []],
      ['a VTI published without a digest', hub => { hub.artifactRows = [{path: 'scalar-0.vti', size: 10}]; },
        '列出结果文件…', 'scalar-0.vti', null, []],
      ['a failed build', hub => { hub.viewErrors.set('view.build', '视图构建被拒绝'); },
        '正在加载视图…', 'scalar-0.vti', '视图构建被拒绝', [502]],
      ['a build sent to review', hub => { hub.reviewKinds.add('view.build'); },
        '正在加载视图…', 'scalar-0.vti', REVIEW_NOTE, []],
      ['a build whose digest is not the published one', hub => { hub.reportedViewDigest = digestOf('another file'); },
        '正在加载视图…', 'scalar-0.vti', '返回的数据摘要与发布文件不符', []],
    ];
    // These two fail the click itself, which ends its busy period at once; the others end the stage with their notice
    // or choice, before the refresh that follows them.
    const thrown = new Set(['a failed legacy list action', 'a list with a null entry']);
    for (const [what, configure, stage, file, alert, statuses] of ends) {
      test(`${what} ends the dedicated stage and keeps the manual route`, async ({page}) => {
        const hub = new Hub();
        const after = configure(hub);
        const errors = await setup(page, hub, {scene: false});
        if (after) await after(page);
        if (stage === '正在加载视图…') {
          // The list is accepted before the click, so the click goes straight to its build.
          await go(page, '结果');
          await expect.poll(() => listed(page)).toEqual(['scalar-0.vti']);
          await go(page, '任务');
          await expect(footer(page)).toContainText('就绪');
        }
        const trail = await footerTrail(page);
        await openInViewer(page).click();
        if (alert) await expect(page.getByRole('alert')).toContainText(alert);
        await settled(page);
        const seen = await trail();
        expect(staged(seen)).toEqual([stage]);
        expect(seen.slice(-2)).toEqual([thrown.has(what) ? stage : '正在处理请求…', '就绪']);
        await expect(fileList(page)).toHaveValue(file);
        await expect(page.locator('section.analysis .viewport canvas')).toHaveCount(0);
        if (file) {
          await expect(source(page)).toHaveText(`${shown('尚未加载结果文件')}${pending(file)}`);
          await expect(loadButton(page)).toBeEnabled();
          await sourceToggle(page).click();
          expect(await lastRow(page)).toEqual(['已选文件', `${file}尚未加载，点「加载视图」后显示`]);
          await page.keyboard.press('Escape');
        } else {
          await expect(source(page)).toHaveText(shown('尚未加载结果文件'));
        }
        expect(built(hub)).toEqual(stage === '正在加载视图…' ? [sliceOf(file)] : []);
        expect(unexpected(errors, ...statuses)).toEqual([]);
      });
    }

    // Leaving while the click waits for its list: the click then opens nothing, and no page names its stage again.
    const awayFromList: [string, (page: Page, hub: Hub) => Promise<void>, '结果' | '任务' | '工作台'][] = [
      ['going to 任务', async page => { await go(page, '任务'); }, '任务'],
      ['going to 工作台', async page => { await go(page, '工作台'); }, '工作台'],
      // 结果 again, from 结果: the page stays as it is, but the click no longer opens anything.
      ['choosing 结果 again', async page => { await go(page, '结果'); }, '结果'],
      ['switching to 图谱 and back', async page => { await modeTab(page, '图谱').click(); await modeTab(page, '结果文件').click(); }, '结果'],
      ['choosing a file', async page => { await fileList(page).selectOption('scalar-0.vti'); }, '结果'],
      ['selecting another task', async page => { await go(page, '任务'); await taskRow(page, '对照任务').click(); }, '任务'],
      ['changing the project', async page => { await go(page, '任务'); await selectEnvironment(page, project(page), ws2); }, '任务'],
      ['losing the read capability', async (page, hub) => {
        hub.readKinds = ['task.get', 'task.events'];
        const denied = page.waitForResponse(res => res.url().endsWith('/api/v1/policy'));
        hub.publish();
        await denied;
        await expect.poll(() => footerStatus(page)).not.toMatch(STAGE_TEXT);
      }, '结果'],
    ];
    if (viewport.name === 'narrow') awayFromList.push(['opening the history over 结果 and closing it', async page => {
      await historyToggle(page).click(); await page.keyboard.press('Escape');
    }, '结果']);
    for (const [what, act, stay] of awayFromList) {
      test(`${what} while the list is read ends 列出结果文件… at once`, async ({page}) => {
        const hub = new Hub();
        hub.device = {...device, snapshot: {...device.snapshot, tasks: [row, row2],
          workspaces: [{id: ws, name: '项目一'}, {id: ws2, name: '项目二'}]}};
        hub.artifactPathsByTask.set(task2, ['other.vti']);
        // A listing with no digest is accepted first, so the click reads the list again, and that read is held.
        hub.artifactRows = [{path: 'scalar-0.vti', size: 10}];
        const errors = await setup(page, hub, {scene: false});
        await go(page, '结果');
        await expect.poll(() => listed(page)).toEqual(['scalar-0.vti']);
        await go(page, '任务');
        await expect(footer(page)).toContainText('就绪');
        hub.artifactRows = undefined;
        const release = hub.hold(`task.artifacts ${task}`);
        hub.reached.clear();
        let trail!: () => Promise<string[]>;
        try {
          await openInViewer(page).click();
          await expect.poll(() => hub.reached.has(`task.artifacts ${task}`)).toBe(true);
          await expect(footer(page)).toContainText('列出结果文件…');
          await act(page, hub);
          await expectActive(page, stay);
          expect(STAGES).not.toContain(await footerStatus(page));
          trail = await footerTrail(page);
          if (stay !== '结果') {
            await go(page, '结果');
            expect(STAGES).not.toContain(await footerStatus(page));
          }
        } finally {
          release();
        }
        await settled(page);
        expect(staged(await trail())).toEqual([]);
        expect(hub.builds).toEqual([]);
        await expect(source(page)).not.toContainText('正在加载视图');
        expect(unexpected(errors, 403)).toEqual([]);
      });
    }

    // Leaving while its build is pending: the page left to names no stage. Back in 结果 with the same connection, task
    // and choice, the pending build is named again (it can still be shown); any other change ends it for good.
    const awayFromBuild: [string, (page: Page, hub: Hub) => Promise<void>, boolean][] = [
      ['going to 任务 and back', async page => {
        await go(page, '任务'); expect(STAGES).not.toContain(await footerStatus(page)); await go(page, '结果');
      }, true],
      ['switching to 图谱 and back', async page => {
        await modeTab(page, '图谱').click(); expect(STAGES).not.toContain(await footerStatus(page));
        await modeTab(page, '结果文件').click();
      }, true],
      ['clearing the file choice', async page => { await fileList(page).selectOption(''); }, false],
      ['selecting another task and coming back to it', async page => {
        await go(page, '任务'); await taskRow(page, '对照任务').click(); await taskRow(page, '解析场验证').click(); await go(page, '结果');
      }, false],
      ['changing the project and back', async page => {
        await go(page, '任务'); await selectEnvironment(page, project(page), ws2); await selectEnvironment(page, project(page), ws);
        await go(page, '结果');
      }, false],
      ['losing and regaining the read capability', async (page, hub) => {
        hub.readKinds = ['task.get', 'task.events'];
        const denied = page.waitForResponse(res => res.url().endsWith('/api/v1/policy'));
        hub.publish();
        await denied;
        await expect.poll(() => footerStatus(page)).not.toMatch(STAGE_TEXT);
        hub.readKinds = ['task.get', 'task.artifacts', 'task.events'];
        const restored = page.waitForResponse(res => res.url().endsWith('/api/v1/policy'));
        hub.publish();
        await restored;
      }, false],
    ];
    if (viewport.name === 'narrow') awayFromBuild.push(['opening the history over 结果 and closing it', async page => {
      await historyToggle(page).click(); expect(STAGES).not.toContain(await footerStatus(page)); await page.keyboard.press('Escape');
    }, true]);
    for (const [what, act, kept] of awayFromBuild) {
      test(`${what} while the build is pending ${kept ? 'names the same build again' : 'ends 正在加载视图… for good'}`, async ({page}) => {
        const hub = new Hub();
        hub.device = {...device, snapshot: {...device.snapshot, tasks: [row, row2],
          workspaces: [{id: ws, name: '项目一'}, {id: ws2, name: '项目二'}]}};
        hub.artifactPathsByTask.set(task2, ['other.vti']);
        const errors = await setup(page, hub, {scene: false});
        const release = hub.hold('view.build');
        hub.reached.clear();
        let trail!: () => Promise<string[]>;
        try {
          await openInViewer(page).click();
          await expect.poll(() => hub.reached.has('view.build')).toBe(true);
          await expect(footer(page)).toContainText('正在加载视图…');
          await act(page, hub);
          await expectActive(page, '结果');
          if (kept) {
            await expect(footer(page)).toContainText('正在加载视图…');
            await expect(source(page)).toHaveText(`${shown('尚未加载结果文件')}${loading('scalar-0.vti')}`);
          } else {
            expect(STAGES).not.toContain(await footerStatus(page));
            await expect(source(page)).not.toContainText('正在加载视图');
          }
          trail = await footerTrail(page);
        } finally {
          release();
        }
        await settled(page);
        const seen = await trail();
        expect(staged(seen)).toEqual(kept ? ['正在加载视图…'] : []);
        expect(built(hub)).toEqual([sliceOf('scalar-0.vti')]);
        await expect(page.locator('section.analysis .legend')).toHaveCount(kept ? 1 : 0);
        if (kept) await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
        else await expect(source(page)).not.toContainText('显示 scalar-0.vti');
        expect(unexpected(errors, 403)).toEqual([]);
      });
    }

    test('加载视图, 读取日志, a revisit of a shown scene and a failed task keep the generic status', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub, {scene: false});
      const trail = await footerTrail(page);
      // The explicit 加载视图 keeps its own status and wording.
      await go(page, '结果');
      await fileList(page).selectOption('scalar-0.vti');
      let release = hub.hold('view.build');
      hub.reached.clear();
      await loadButton(page).click();
      await expect.poll(() => hub.reached.has('view.build')).toBe(true);
      await expect(footer(page)).toContainText('正在处理请求…');
      await expect(source(page)).toHaveText(`${shown('尚未加载结果文件')}${pending('scalar-0.vti')}`);
      release();
      await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
      await settled(page);
      await page.locator('section.analysis .viewport canvas').evaluate(el => { (el as any).__marker = 'same-canvas'; });
      // 读取日志.
      await go(page, '任务');
      release = hub.hold('task.logs');
      hub.reached.clear();
      await shortcut(page, '读取日志').click();
      await expect.poll(() => hub.reached.has('task.logs')).toBe(true);
      await expect(footer(page)).toContainText('正在处理请求…');
      release();
      await settled(page);
      // A revisit of the shown scene reads the list again but opens nothing: its source and canvas stay.
      await go(page, '任务');
      release = hub.hold(`task.artifacts ${task}`);
      hub.reached.clear();
      await openInViewer(page).click();
      await expect.poll(() => hub.reached.has(`task.artifacts ${task}`)).toBe(true);
      await expect(footer(page)).toContainText('正在处理请求…');
      await expect(source(page)).toHaveText(shown('显示 scalar-0.vti'));
      release();
      await settled(page);
      expect(await canvasMarker(page)).toBe('same-canvas');
      expect(staged(await trail())).toEqual([]);
      expect(built(hub)).toEqual([sliceOf('scalar-0.vti', 2, 0)]);
      expect(errors).toEqual([]);
    });

    test('a click in 等值面 view names its list wait, then only preselects', async ({page}) => {
      const hub = new Hub();
      const errors = await setup(page, hub, {scene: false});
      await go(page, '结果');
      await expect.poll(() => listed(page)).toEqual(['scalar-0.vti']);
      await fileViewMode(page).selectOption('iso');
      await go(page, '任务');
      await expect(footer(page)).toContainText('就绪');
      const trail = await footerTrail(page);
      const release = hub.hold(`task.artifacts ${task}`);
      hub.reached.clear();
      await openInViewer(page).click();
      await expect.poll(() => hub.reached.has(`task.artifacts ${task}`)).toBe(true);
      await expect(footer(page)).toContainText('列出结果文件…');
      release();
      await expect(fileList(page)).toHaveValue('scalar-0.vti');
      await settled(page);
      await expect(source(page)).toHaveText(`${shown('尚未加载结果文件')}${pending('scalar-0.vti')}`);
      expect(staged(await trail())).toEqual(['列出结果文件…']);
      expect(hub.builds).toEqual([]);
      expect(errors).toEqual([]);
    });

    test('a failed task reads its list with the generic status and chooses nothing', async ({page}) => {
      const hub = new Hub();
      hub.device = {...device, snapshot: {...device.snapshot, tasks: [{...row, state: 'failed'}]}};
      hub.artifactPaths = ['notes.txt', 'scalar-0.vti'];
      const errors = await setup(page, hub, {scene: false});
      await expect(page.getByRole('region', {name: '所选任务状态'})).toContainText('失败');
      await go(page, '结果');
      await expect.poll(() => listed(page)).toEqual(['scalar-0.vti']);
      await go(page, '任务');
      await expect(footer(page)).toContainText('就绪');
      const trail = await footerTrail(page);
      const release = hub.hold(`task.artifacts ${task}`);
      hub.reached.clear();
      await openInViewer(page).click();
      await expect.poll(() => hub.reached.has(`task.artifacts ${task}`)).toBe(true);
      await expect(footer(page)).toContainText('正在处理请求…');
      release();
      await settled(page);
      expect(staged(await trail())).toEqual([]);
      await expect(fileList(page)).toHaveValue('');
      expect(hub.builds).toEqual([]);
      expect(errors).toEqual([]);
    });
  });
}

test('a failed task keeps its published result available for explicit selection', async ({page}) => {
  const hub = new Hub();
  hub.device = {...device, snapshot: {...device.snapshot, tasks: [{...row, state: 'failed'}]}};
  hub.artifactPaths = ['notes.txt', 'scalar-0.vti'];
  const errors = await setup(page, hub, {scene: false});
  await expect(page.getByRole('region', {name: '所选任务状态'})).toContainText('失败');
  await shortcut(page, '在查看器中打开').click();
  await expect.poll(() => listed(page)).toEqual(['scalar-0.vti']);
  await expect(footer(page)).toContainText('就绪');
  await expect(fileList(page)).toHaveValue('');
  await expect(loadButton(page)).toBeDisabled();
  await fileList(page).selectOption('scalar-0.vti');
  await expect(loadButton(page)).toBeEnabled();
  expect(hub.builds).toEqual([]);
  expect(errors).toEqual([]);
});
