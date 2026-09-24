// Graph mode helpers (pure, no DOM): preset parameters, requested outputs, graph-result outputs, probe targets
// for view.probe, and folding monitoring events (task.events) into a progress line.
// Hub API: decisions "Hub API used by the web viewer"; result shape: docs/specs/stk-graph-v1.md §9.

export interface GraphParameter {name: string, type: string, default?: unknown, choices?: unknown[], minimum?: number, maximum?: number,
  unit?: string, label?: string, description?: string}
export interface GraphNode {id: string, type: string, params?: Record<string, any>, inputs?: Record<string, any>, label?: string}
export interface GraphDocument {schema?: string, name?: string, nodes?: GraphNode[], outputs?: Record<string, string>, parameters?: GraphParameter[]}
export interface Preset {id: string, name?: string, description?: string, graph?: GraphDocument, bindings?: {name: string, description?: string}[],
  parameters?: GraphParameter[]}
export interface GraphResult {schema?: string, graph_sha256?: string, graph_hash?: string, outputs?: Record<string, any>,
  parameters?: Record<string, {value?: unknown, choices?: unknown[]}>, timings?: Record<string, number>, cache?: {hits?: number, misses?: number},
  warnings?: unknown[], errors?: unknown[]}
export interface Artifact {path: string, size?: number, sha256?: string}

/** muFerro published frame names, as `suan/mupro/run.py` FRAME. */
export const FRAME = /(?:^|\/)([A-Za-z][A-Za-z0-9_]{0,7})\.(\d{8})\.dat$/;
const HEX64 = /^[0-9a-f]{64}$/;
const isObj = (v: unknown): v is Record<string, any> => typeof v === 'object' && v !== null && !Array.isArray(v);
const isParamRef = (v: unknown): v is {$param: string} => isObj(v) && Object.keys(v).length === 1 && typeof v.$param === 'string';
/** Own-property lookup (names come from graphs and results; "__proto__" must not reach Object.prototype). */
const own = (table: unknown, key: unknown): any => isObj(table) && typeof key === 'string' && Object.prototype.hasOwnProperty.call(table, key) ? table[key] : undefined;

export function presetParameters(preset: Preset | undefined): GraphParameter[] {
  const list = preset?.parameters ?? preset?.graph?.parameters ?? [];
  return Array.isArray(list) ? list.filter(p => isObj(p) && typeof p.name === 'string' && typeof p.type === 'string') : [];
}

export function bindingNames(preset: Preset | undefined): string[] {
  if (Array.isArray(preset?.bindings) && preset!.bindings.length) return preset!.bindings.map(b => b.name).filter(n => typeof n === 'string');
  const names = new Set<string>();
  for (const node of preset?.graph?.nodes ?? []) if (node.type?.startsWith('stk.source.') && typeof node.params?.binding === 'string') names.add(node.params.binding);
  return [...names];
}

export type EditorKind = 'number' | 'integer' | 'boolean' | 'enum' | 'string' | 'step' | 'json';
export function editorKind(p: GraphParameter): EditorKind {
  if (['number', 'integer', 'boolean', 'enum', 'string', 'step'].includes(p.type)) return p.type as EditorKind;
  return 'json';
}

export function initialValues(params: GraphParameter[]): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const p of params) {
    const declared = 'default' in p && (p.default !== null || editorKind(p) === 'json');
    const value = declared ? p.default : (p.type === 'step' ? 'latest' : p.type === 'boolean' ? false : p.type === 'enum' ? p.choices?.[0] : undefined);
    values[p.name] = editorKind(p) === 'json' && value !== undefined ? JSON.stringify(value) : value;
  }
  return values;
}

const isNumberOrNull = (v: unknown) => v === null || (typeof v === 'number' && Number.isFinite(v));
/** Graph parameter types edited as JSON (stk-graph-v1 parameter types) and their expected shapes. */
const JSON_SHAPES: Record<string, {test: (v: unknown) => boolean, text: string}> = {
  vector3: {test: v => Array.isArray(v) && v.length === 3 && v.every(x => typeof x === 'number' && Number.isFinite(x)), text: ' 3 个数的数组，例如 [0, 0, 1]'},
  int3: {test: v => Array.isArray(v) && v.length === 3 && v.every(x => Number.isInteger(x)), text: ' 3 个整数的数组'},
  range: {test: v => Array.isArray(v) && v.length === 2 && v.every(isNumberOrNull), text: ' [最小值, 最大值]（null 表示数据范围）'},
};

/** Typed parameter values for graph.evaluate; editors hold strings for numbers and JSON types. */
export function coerceParameters(params: GraphParameter[], values: Record<string, unknown>): {parameters: Record<string, unknown>, errors: string[]} {
  const parameters: Record<string, unknown> = {};
  const errors: string[] = [];
  for (const p of params) {
    const raw = values[p.name];
    const label = p.label || p.name;
    if (raw === undefined || raw === '') { if (p.default === undefined) errors.push(`请填写参数 ${label}`); continue; }
    switch (editorKind(p)) {
      case 'number': case 'integer': {
        const n = typeof raw === 'number' ? raw : Number(raw);
        if (!Number.isFinite(n) || (p.type === 'integer' && !Number.isInteger(n))) { errors.push(`参数 ${label} 必须是${p.type === 'integer' ? '整数' : '数字'}`); continue; }
        if (p.minimum !== undefined && n < p.minimum) { errors.push(`参数 ${label} 不能小于 ${p.minimum}`); continue; }
        if (p.maximum !== undefined && n > p.maximum) { errors.push(`参数 ${label} 不能大于 ${p.maximum}`); continue; }
        parameters[p.name] = n;
        break;
      }
      case 'boolean': parameters[p.name] = raw === true || raw === 'true'; break;
      case 'enum': {
        const match = (p.choices ?? []).find(c => c === raw || String(c) === String(raw));
        if (match === undefined) errors.push(`参数 ${label} 的取值无效`); else parameters[p.name] = match;
        break;
      }
      case 'step': {
        if (raw === 'latest' || raw === 'first') { parameters[p.name] = raw; break; }
        const n = typeof raw === 'number' ? raw : Number(raw);
        if (!Number.isInteger(n) || n < 0) errors.push(`时间步 ${label} 必须是非负整数、latest 或 first`); else parameters[p.name] = n;
        break;
      }
      case 'string': parameters[p.name] = String(raw); break;
      default: {
        let value: unknown;
        try { value = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch { errors.push(`参数 ${label} 不是有效的 JSON`); continue; }
        const shape = JSON_SHAPES[p.type];
        if (shape && !shape.test(value)) { errors.push(`参数 ${label} 必须是${shape.text}`); continue; }
        parameters[p.name] = value;
      }
    }
  }
  return {parameters, errors};
}

const linkedNode = (link: unknown): string | null => isObj(link) && typeof link.from === 'string' ? link.from.split('.')[0] : null;
const linkedNodes = (inputs: Record<string, any> | undefined): string[] =>
  Object.values(inputs ?? {}).flatMap(v => (Array.isArray(v) ? v : [v]).map(linkedNode).filter((n): n is string => !!n));

/**
 * Outputs to request for the web: all graph outputs except scene outputs already delivered as a payload
 * output and (unless asked) offscreen PNG renders of scenes, which the web draws itself.
 */
export function selectOutputs(graph: GraphDocument | undefined, includeSceneImages = false): string[] | undefined {
  if (!graph || !isObj(graph.outputs) || !Array.isArray(graph.nodes)) return undefined;
  const nodes = new Map(graph.nodes.map(n => [n.id, n]));
  const nodeOf = (ref: string) => nodes.get(String(ref).split('.')[0]);
  const coveredScenes = new Set<string>();
  for (const ref of Object.values(graph.outputs)) {
    const node = nodeOf(ref);
    if (node?.type?.startsWith('stk.output.payload@')) { const scene = linkedNode(node.inputs?.scene); if (scene) coveredScenes.add(scene); }
  }
  const selected = Object.entries(graph.outputs).filter(([, ref]) => {
    const node = nodeOf(ref);
    if (!node) return true;
    if (node.type.startsWith('stk.view.scene@') && coveredScenes.has(node.id)) return false;
    if (node.type.startsWith('stk.output.image@') && !includeSceneImages) {
      const source = nodes.get(linkedNode(node.inputs?.source) ?? '');
      if (source?.type.startsWith('stk.view.scene@')) return false;
    }
    return true;
  }).map(([name]) => name);
  return selected.length ? selected : undefined;
}

/** sha256 of a blob reference: "<hex>", "sha256:<hex>" or {sha256}. */
export function blobSha(ref: unknown): string | null {
  if (typeof ref === 'string') { const hex = ref.startsWith('sha256:') ? ref.slice(7) : ref; return HEX64.test(hex) ? hex : null; }
  if (isObj(ref)) return blobSha(ref.sha256 ?? ref.blob);
  return null;
}

export const DISPLAYABLE = ['image/svg+xml', 'image/png', 'image/jpeg', 'image/webp'];
export interface OutputImage {sha: string, mediaType: string}

/** Images of an image/plot output, displayable types first (SVG preferred for plots). */
export function outputImages(out: any): OutputImage[] {
  const list: OutputImage[] = [];
  if (Array.isArray(out?.images)) for (const image of out.images) {
    const sha = blobSha(image);
    if (sha) list.push({sha, mediaType: String(image.media_type ?? image.blob?.media_type ?? 'image/png')});
  }
  const sha = blobSha(out?.blob) ?? blobSha(out?.sha256);
  if (sha && !list.some(i => i.sha === sha)) list.push({sha, mediaType: String(out?.media_type ?? out?.blob?.media_type ?? 'image/png')});
  const rank = (m: string) => { const i = DISPLAYABLE.indexOf(m); return i < 0 ? 99 : i; };
  return list.sort((a, b) => rank(a.mediaType) - rank(b.mediaType));
}

export interface TableData {columns: Record<string, unknown[]>, units: Record<string, string>}
export function tableData(value: unknown): TableData | null {
  if (!isObj(value)) return null;
  const columns = isObj(value.columns) ? value.columns : value;
  if (!Object.values(columns).every(Array.isArray) || !Object.keys(columns).length) return null;
  return {columns: columns as Record<string, unknown[]>, units: isObj(value.units) ? value.units as Record<string, string> : {}};
}

export function payloadOutputs(result: GraphResult | null | undefined): {name: string, manifest: any}[] {
  return Object.entries(result?.outputs ?? {}).filter(([, out]) => out?.manifest?.schema === 'stk.payload/2').map(([name, out]) => ({name, manifest: out.manifest}));
}

/** The step parameter bound by `$param` in a muFerro frame source (graph spec §6), or null. */
export function stepParameter(graph: GraphDocument | undefined, params: GraphParameter[]): string | null {
  for (const node of graph?.nodes ?? []) if (isParamRef(node.params?.step)) return node.params!.step.$param;
  return params.find(p => p.type === 'step')?.name ?? null;
}

export function frameDataset(graph: GraphDocument | undefined): string | null {
  const node = graph?.nodes?.find(n => n.type?.startsWith('stk.source.muferro_frame@'));
  return node ? (typeof node.params?.dataset === 'string' ? node.params.dataset : 'Polar') : null;
}

/** Steps published in a task's artifacts (fallback when a result reports no choices). */
export function framesFromArtifacts(artifacts: Artifact[], dataset: string | null): number[] {
  const steps = new Set<number>();
  for (const a of artifacts) {
    const m = FRAME.exec(a.path);
    if (m && (!dataset || m[1] === dataset)) steps.add(Number(m[2]));
  }
  return [...steps].sort((a, b) => a - b);
}

export function stepChoices(result: GraphResult | null | undefined, name: string | null, fallback: number[]): {value: number | null, choices: number[]} {
  const info: {value?: unknown, choices?: unknown[]} | undefined = name ? own(result?.parameters, name) : undefined;
  const choices = Array.isArray(info?.choices) ? info!.choices.filter((c): c is number => Number.isInteger(c) && (c as number) >= 0).sort((a, b) => a - b) : [];
  const value = Number.isInteger(info?.value) ? info!.value as number : null;
  return {value, choices: choices.length ? choices : fallback};
}

export interface ProbeTarget {task_id: string, path: string, node: string, metadata?: Record<string, unknown>}
export interface ProbeContext {bindings: Record<string, string>, values: Record<string, unknown>, result?: GraphResult | null, artifacts?: Artifact[]}

/**
 * Where view.probe should read for a picked layer: walks upstream from `pick.probe.node` to the first
 * field source (`stk.source.file@1` path, or the muFerro frame file of the resolved step).
 */
export function resolveProbeTarget(graph: GraphDocument | undefined, probe: {node?: string, dataset?: string} | undefined, ctx: ProbeContext): ProbeTarget | {error: string} {
  if (!probe?.node) return {error: '该图层未声明探针数据源（pick.probe）'};
  if (!graph?.nodes) return {error: '预设未附带图定义，无法定位探针数据'};
  const nodes = new Map(graph.nodes.map(n => [n.id, n]));
  const parameterDefaults = new Map((graph.parameters ?? []).map(p => [p.name, p.default]));
  const param = (node: GraphNode, name: string) => {
    const v = node.params?.[name];
    return isParamRef(v) ? (own(ctx.values, v.$param) ?? parameterDefaults.get(v.$param)) : v;
  };
  const queue = [probe.node];
  const seen = new Set<string>();
  while (queue.length) {
    const id = queue.shift()!;
    if (seen.has(id)) continue;
    seen.add(id);
    const node = nodes.get(id);
    if (!node) continue;
    const metadata: Record<string, unknown> = {};
    for (const key of ['origin', 'spacing'] as const) { const v = param(node, key); if (Array.isArray(v) && v.length === 3) metadata[key] = v; }
    const extra = Object.keys(metadata).length ? {metadata} : {};
    if (node.type.startsWith('stk.source.file@')) {
      const binding = param(node, 'binding'), path = param(node, 'path');
      const task = own(ctx.bindings, binding);
      if (!task) return {error: `数据源 ${String(binding)} 尚未绑定任务`};
      if (typeof path !== 'string' || !path) return {error: `节点 ${id} 缺少文件路径`};
      return {task_id: task, path, node: id, ...extra};
    }
    if (node.type.startsWith('stk.source.muferro_frame@')) {
      const dataset = String(param(node, 'dataset') ?? probe.dataset ?? 'Polar');
      const ref = node.params?.step;
      const resolved = isParamRef(ref) ? own(ctx.result?.parameters, ref.$param)?.value ?? own(ctx.values, ref.$param) : Number.isInteger(ref) ? ref : own(ctx.result?.parameters, `${id}.step`)?.value;
      const step = typeof resolved === 'string' && /^\d+$/.test(resolved) ? Number(resolved) : resolved;
      if (!Number.isInteger(step) || (step as number) < 0) return {error: '请先完成一次图谱计算以确定探针所在的时间步'};
      const run = nodes.get(linkedNode(node.inputs?.frames) ?? '');
      const binding = run ? param(run, 'binding') : undefined;
      const task = own(ctx.bindings, binding);
      if (!task) return {error: `数据源 ${String(binding ?? '?')} 尚未绑定任务`};
      const caseDir = run ? String(param(run, 'case_dir') ?? '.') : '.';
      const name = `${dataset}.${String(step).padStart(8, '0')}.dat`;
      const published = ctx.artifacts?.find(a => { const m = FRAME.exec(a.path); return !!m && m[1] === dataset && Number(m[2]) === step; });
      const path = published?.path ?? (caseDir && caseDir !== '.' ? `${caseDir.replace(/\/+$/, '')}/${name}` : name);
      return {task_id: task, path, node: id, ...extra};
    }
    queue.push(...linkedNodes(node.inputs));
  }
  return {error: `从节点 ${probe.node} 向上未找到场数据源`};
}

// ---------------------------------------------------------------------------------------------
// Waiting for a graph.evaluate action (hub action lifecycle: review → queued → succeeded | failed | rejected).

export interface WaitOptions {
  /** Reads the action again (GET /api/v1/actions/{id}). */
  poll: () => Promise<any>,
  /** False once the request was superseded (a newer evaluation, another preset, the panel unmounted). */
  isCurrent: () => boolean,
  sleep: (ms: number) => Promise<unknown>,
  /** Called before each wait with the action still pending. */
  onPending?: (item: any) => void,
  initialDelayMs?: number, maxDelayMs?: number,
  /** Consecutive failed reads tolerated (network hiccups) before giving up. */
  maxFailures?: number,
}

/**
 * Polls an action while it awaits review or is queued, with backoff (2 s → 10 s) and no deadline: an evaluation
 * may wait behind others on a busy node and must still be shown when it completes. Resolves with the finished
 * action, or null when the request is no longer current (then nothing more is fetched).
 */
export async function waitForAction(item: any, options: WaitOptions): Promise<any | null> {
  const {poll, isCurrent, sleep, onPending, initialDelayMs = 2000, maxDelayMs = 10000, maxFailures = 5} = options;
  let delay = initialDelayMs, failures = 0;
  while (item?.state === 'review' || item?.state === 'queued') {
    if (!isCurrent()) return null;
    onPending?.(item);
    await sleep(delay);
    if (!isCurrent()) return null;
    try {
      item = await poll();
      failures = 0;
      delay = Math.min(maxDelayMs, delay * 1.5);
    } catch (error) {
      if (++failures >= maxFailures) throw error;
      delay = Math.min(maxDelayMs, delay * 2);
    }
  }
  return isCurrent() ? item : null;
}

/** task.events polling interval: 10 s while events arrive, backing off to 30 s while the log is quiet. */
export const EVENTS_POLL_MS = {min: 10000, max: 30000};
export function nextEventsDelay(current: number, received: boolean): number {
  return received ? EVENTS_POLL_MS.min : Math.min(EVENTS_POLL_MS.max, Math.round(current * 1.5));
}
/** A long event log is read from its last 256 KiB (the progress line needs only the latest events). */
export const EVENTS_TAIL_BYTES = 256 * 1024;

// ---------------------------------------------------------------------------------------------
// Monitoring events (docs/specs/stk-events-v1.md) → one progress line.

export interface ProgressState {
  progress?: Record<string, unknown>, frame?: {dataset?: string, step?: number}, phase?: string,
  message?: {level: string, text: string}, completed?: {status?: string, reason?: string}, lastTs?: number, count: number,
}
export const emptyProgress = (): ProgressState => ({count: 0});

export function foldEvents(state: ProgressState, events: unknown[]): ProgressState {
  const next: ProgressState = {...state};
  for (const e of events) {
    if (!isObj(e) || !isObj(e.data)) continue;
    next.count++;
    if (Number.isFinite(e.ts)) next.lastTs = Math.max(next.lastTs ?? 0, e.ts);
    const d = e.data;
    switch (e.type) {
      case 'progress': next.progress = d; break;
      case 'frame': next.frame = {dataset: typeof d.dataset === 'string' ? d.dataset : undefined, step: Number.isInteger(d.step) ? d.step : undefined}; break;
      case 'run.phase': next.phase = d.state === 'end' ? undefined : String(d.name ?? ''); break;
      case 'message': if (d.level === 'warning' || d.level === 'error') next.message = {level: d.level, text: String(d.text ?? '')}; break;
      case 'run.completed': next.completed = {status: d.status, reason: d.reason}; break;
    }
  }
  return next;
}

const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
export function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} 秒`;
  if (s < 3600) return `${Math.floor(s / 60)} 分 ${s % 60} 秒`;
  return `${Math.floor(s / 3600)} 小时 ${Math.floor((s % 3600) / 60)} 分`;
}

export function progressText(state: ProgressState): string {
  const parts: string[] = [];
  const statusNames: Record<string, string> = {succeeded: '成功', failed: '失败', cancelled: '已取消'};
  if (state.completed) parts.push(`程序报告结束：${statusNames[state.completed.status ?? ''] ?? state.completed.status ?? '未知'}${state.completed.reason ? `（${state.completed.reason}）` : ''}`);
  const p = state.progress ?? {};
  const fraction = num(p.fraction);
  const step = num(p.step) ?? num(p.completed_steps), total = num(p.total_steps);
  if (fraction !== null) parts.push(`${(fraction * 100).toFixed(fraction < 0.1 ? 1 : 0)}%`);
  if (step !== null) parts.push(total !== null ? `步 ${step} / ${total}` : `步 ${step}`);
  const eta = num(p.eta_s);
  if (eta !== null && !state.completed) parts.push(`预计剩余 ${duration(eta)}`);
  const phase = state.phase ?? (typeof p.phase === 'string' ? p.phase : undefined);
  if (phase) parts.push(`阶段 ${phase}`);
  if (state.frame?.step !== undefined) parts.push(`最新帧 ${state.frame.dataset ?? ''} ${state.frame.step}`.replace('  ', ' '));
  if (state.message) parts.push(`${state.message.level === 'error' ? '错误' : '警告'}：${state.message.text.slice(0, 120)}`);
  if (state.lastTs) parts.push(`更新于 ${new Date(state.lastTs * 1000).toLocaleTimeString()}`);
  return parts.length ? parts.join(' · ') : state.count ? '已接收事件，暂无进度' : '尚无监测事件（任务可能未接入 STK 监测）';
}
