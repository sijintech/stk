// 图谱 (graph) mode: evaluate a preset graph next to the data (action graph.evaluate), draw the returned
// stk.payload/2, scrub steps with the camera kept, show plots/images/tables, and a task.events progress line.
import React, {useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState} from 'react';
import {action, api, blob, readNode, type Json} from './api';
import {cachedBlob, loadPayload, loadStkp, type LoadedPayload} from './payload';
import {bindingNames, blobSha, coerceParameters, DISPLAYABLE, duration, editorKind, emptyProgress, EVENTS_POLL_MS, EVENTS_TAIL_BYTES, foldEvents,
  frameDataset, framesFromArtifacts, initialValues, nextEventsDelay, outputImages, payloadOutputs, presetParameters, progressText, resolveProbeArtifact, resolveProbeTarget,
  selectOutputs, stepChoices, stepParameter, tableData, waitForAction, type Artifact, type GraphParameter, type GraphResult, type Preset,
  type ProbeContext, type ProgressState, type TableData} from './graph';
import ErrorBoundary from './ErrorBoundary';
import type {PickInfo} from './PayloadViewer';
import {muProArtifact, muProFrames, muProManifest, muProRequest, type MuProArtifact, type MuProFrame, type MuProSource} from './muproHdf5';

const Viewer = React.lazy(() => import('./Viewer'));
const fetchBlob = (sha: string, signal?: AbortSignal) => blob(sha, signal);
const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
const message = (e: unknown) => (e instanceof Error ? e.message : String(e));
const UNIT_NAMES: Record<string, string> = {unspecified: '单位未指定', '1': '无量纲', normalized: '归一化', grid_index: '网格索引'};
const unitLabel = (unit?: unknown) => (typeof unit === 'string' && unit ? ` [${Object.prototype.hasOwnProperty.call(UNIT_NAMES, unit) ? UNIT_NAMES[unit] : unit}]` : '');
const REVIEW_TEXT = '图谱计算超过自动执行额度，正在等待复核；批准后结果会自动显示。';
/** Files a field source can read (stk.source.file@1: DAT, NPY, VTI, legacy VTK, VTKHDF). */
const FIELD_FILE = /\.(dat|npy|vti|vtk|vtkhdf|hdf|h5)$/i;
/** A warning or error of a graph result: `{code, message, node?}` or plain text. */
const issueText = (w: unknown) => (typeof w === 'string' ? w : w && typeof w === 'object' && typeof (w as any).message === 'string'
  ? `${(w as any).node ? `${(w as any).node}：` : ''}${(w as any).message}` : JSON.stringify(w));

type EvaluationSource = {
  kind: 'evaluation', scope: string, node: string, display: 'scene' | 'outputs',
  output?: string, step: number | null,
  bindings: {name: string, task: string, taskName?: string, workspace?: string}[],
} & ({presetId: string, presetName?: string, hdf5?: never} | {hdf5: MuProSource, presetId?: never, presetName?: never});
export type GraphSource = EvaluationSource | {kind: 'local', scope: string, node: string, file: string};
type GraphView = {payload: LoadedPayload, source: GraphSource, key: string, probe?: ProbeContext, signal?: AbortSignal};
type CompletedTask = {name: string, workspace: string};

async function evaluateGraph(node: string, request: Json, isCurrent: () => boolean,
                             onStatus: (text: string) => void, signal?: AbortSignal): Promise<GraphResult | null> {
  const started = Date.now();
  const first = await action(node, 'graph.evaluate', request, () => { if (isCurrent()) onStatus(REVIEW_TEXT); },
    {timeoutMs: signal ? 0 : 20000, remember: !signal, keepQueued: true, active: isCurrent});
  const item = await waitForAction(first, {poll: () => api(`actions/${first.id}`, 'GET', undefined, signal), isCurrent, sleep,
    onPending: pending => onStatus(pending.state === 'review' ? REVIEW_TEXT
      : `图谱计算排队中（已等待 ${duration((Date.now() - started) / 1000)}），完成后自动显示；无需重复提交。`)});
  if (!item || !isCurrent()) return null;
  if (item.state === 'failed') throw new Error(item.error || '图谱计算失败');
  if (item.state === 'rejected') throw new Error('图谱计算未获批准');
  if (item.state !== 'succeeded' || !item.result || typeof item.result !== 'object') throw new Error('图谱计算没有返回结果，可在操作列表中查看');
  return item.result as GraphResult;
}

function MuProHdf5Control({node, task, artifact, onOpen}: {node: string, task: string, artifact: MuProArtifact,
  onOpen: (source: MuProSource, signal: AbortSignal, onStatus: (text: string) => void) => Promise<void>}) {
  const [frames, setFrames] = useState<MuProFrame[] | null>(null);
  const [selector, setSelector] = useState('');
  const [componentText, setComponent] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const request = useRef<AbortController | null>(null);
  const pending = useRef(false);
  useLayoutEffect(() => () => request.current?.abort(), []);
  const frame = frames?.find(item => item.selector === selector);
  const count = frame?.shape[3] ?? 0;
  const component = Number(componentText);
  const canOpen = !!frame && (count === 1 || (componentText !== '' && Number.isSafeInteger(component) && component >= 0 && component < count));

  async function run(open: boolean) {
    if (pending.current || (open && (!frame || !canOpen))) return;
    pending.current = true;
    request.current?.abort();
    const abort = new AbortController();
    request.current = abort;
    const isCurrent = () => !abort.signal.aborted;
    setError('');
    setStatus(open ? '正在打开 HDF5 帧…' : '正在读取 HDF5 字段…');
    try {
      if (open && frame) {
        await onOpen({artifact, frame, component: count === 1 ? null : component}, abort.signal, setStatus);
      } else {
        setFrames(null); setSelector(''); setComponent('');
        const result = await evaluateGraph(node, muProRequest(task, artifact), isCurrent, setStatus, abort.signal);
        if (result && isCurrent()) setFrames(muProFrames(result, artifact));
      }
    } catch (e) { if (isCurrent()) setError(message(e)); }
    finally { if (isCurrent()) { pending.current = false; setStatus(''); } }
  }

  return <details className="graph-extra"><summary>MuPRO HDF5</summary>
    <p className="muted">读取当前任务发布的 {artifact.path}。请明确选择场和步号。</p>
    <button type="button" disabled={!!status} onClick={() => void run(false)}>列出 HDF5 帧</button>
    {frames?.length === 0 && <p className="muted">该文件中没有可识别的 MuPRO HDF5 场。</p>}
    {!!frames?.length && <div className="view-controls graph-controls">
      <label>HDF5 场与步号<select value={selector} disabled={!!status} onChange={e => {setSelector(e.target.value); setComponent('');}}>
        <option value="">选择场与步号</option>{frames.map(item => <option key={item.selector} value={item.selector}>{item.name} · 第 {item.step} 步</option>)}
      </select></label>
      {count > 1 && <label>HDF5 分量索引<input aria-label="HDF5 分量索引" type="number" min={0} max={count - 1} step={1} value={componentText} disabled={!!status}
        onChange={e => setComponent(e.target.value)}/><small>从 0 到 {count - 1}</small></label>}
      <button type="button" className="primary" disabled={!!status || !canOpen} onClick={() => void run(true)}>打开所选 HDF5 帧</button>
    </div>}
    {frame && <p className="muted">{frame.dtype} · 原生形状 {frame.shape.join(' × ')}。空间单位为网格索引，物理时间与场单位未指定。</p>}
    {status && <p className="muted" role="status">{status}</p>}
    {error && <p className="muted" role="alert">{error}</p>}
  </details>;
}

function ParamEditor({param, value, onChange, options}: {param: GraphParameter, value: unknown, onChange: (value: unknown) => void, options?: string[]}) {
  const label = `${param.label || param.name}${unitLabel(param.unit)}`;
  const kind = editorKind(param);
  if (kind === 'boolean') return <label className="check" title={param.description}><input type="checkbox" checked={value === true || value === 'true'} onChange={e => onChange(e.target.checked)}/>{label}</label>;
  let field: React.ReactNode;
  if (kind === 'number' || kind === 'integer') field = <input type="number" step={kind === 'integer' ? 1 : 'any'} min={param.minimum} max={param.maximum} value={String(value ?? '')} onChange={e => onChange(e.target.value)}/>;
  else if (kind === 'enum') field = <select value={String(value ?? '')} onChange={e => onChange(e.target.value)}>{(param.choices ?? []).map(c => <option key={String(c)} value={String(c)}>{String(c)}</option>)}</select>;
  else if (kind === 'step') {
    const special = value === 'latest' || value === 'first';
    field = <span className="inline"><select aria-label={`${label} 方式`} value={special ? String(value) : 'number'} onChange={e => onChange(e.target.value === 'number' ? 0 : e.target.value)}>
      <option value="latest">最新</option><option value="first">最早</option><option value="number">指定</option></select>
      {!special && <input type="number" min={0} step={1} aria-label={label} value={String(value ?? 0)} onChange={e => onChange(e.target.value)}/>}</span>;
  } else if (options?.length) {
    // Suggest the bound task's result files; any relative path can still be typed.
    const list = `param-${param.name}-files`;
    field = <><input list={list} value={String(value ?? '')} onChange={e => onChange(e.target.value)}/><datalist id={list}>{options.map(o => <option key={o} value={o}/>)}</datalist></>;
  } else field = <input className={kind === 'json' ? 'mono' : undefined} value={String(value ?? '')} onChange={e => onChange(e.target.value)}/>;
  return <label title={param.description}>{label}{field}</label>;
}

function BlobImage({sha, mediaType, alt}: {sha: string, mediaType: string, alt: string}) {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const current = useRef('');
  useEffect(() => {
    let alive = true;
    cachedBlob(sha, fetchBlob).then(data => {
      if (!alive) return;
      // Keep the previous image until the next one is ready (no flicker while scrubbing steps).
      const next = URL.createObjectURL(new Blob([data], {type: mediaType}));
      const previous = current.current;
      current.current = next;
      setUrl(next);
      setError('');
      if (previous) setTimeout(() => URL.revokeObjectURL(previous), 1000);
    }).catch(e => { if (alive) setError(message(e)); });
    return () => { alive = false; };
  }, [sha, mediaType]);
  useEffect(() => () => { if (current.current) URL.revokeObjectURL(current.current); }, []);
  if (error) return <p className="muted">{error}</p>;
  return url ? <img src={url} alt={alt}/> : <p className="muted">正在读取图片…</p>;
}

function BlobDownload({sha, name, mediaType, label}: {sha: string, name: string, mediaType?: string, label: string}) {
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      const data = await cachedBlob(sha, fetchBlob);
      const url = URL.createObjectURL(new Blob([data], {type: mediaType || 'application/octet-stream'}));
      const link = document.createElement('a');
      link.href = url; link.download = name;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } finally { setBusy(false); }
  }
  return <button className="quiet" disabled={busy} onClick={() => void save().catch(() => undefined)}>{label}</button>;
}

const HEX_COLOR = /^#[0-9a-f]{6}$/i;
const cell = (v: unknown) => typeof v === 'number' ? (Number.isInteger(v) ? String(v) : String(Number(v.toPrecision(6)))) : v === null || v === undefined ? '' : String(v);

function TableView({out}: {out: any}) {
  const [data, setData] = useState<TableData | null>(() => tableData(out));
  const [error, setError] = useState('');
  useEffect(() => {
    const inline = tableData(out);
    const sha = inline ? null : blobSha(out?.blob);
    setData(inline);
    if (!sha) return;
    let alive = true;
    cachedBlob(sha, fetchBlob).then(bytes => { if (alive) setData(tableData(JSON.parse(new TextDecoder().decode(bytes)), out?.column_names)); }).catch(e => { if (alive) setError(message(e)); });
    return () => { alive = false; };
  }, [out]);
  if (error) return <p className="muted">{error}</p>;
  if (!data) return <p className="muted">正在读取表格…</p>;
  const names = data.names;
  const rows = Math.max(...names.map(n => data.columns[n].length));
  const shown = Math.min(rows, 100);
  return <div className="data-table"><table><thead><tr>{names.map(n => <th key={n}>{n}{data.units[n] ? <small>{unitLabel(data.units[n])}</small> : null}</th>)}</tr></thead>
    <tbody>{Array.from({length: shown}, (_, r) => <tr key={r}>{names.map(n => { const v = data.columns[n][r];
      // Category colours (label_fractions 'color' column) get a swatch.
      return <td key={n}>{typeof v === 'string' && HEX_COLOR.test(v) ? <i className="swatch" style={{background: v}}/> : null}{cell(v)}</td>; })}</tr>)}</tbody></table>
    {rows > shown && <small className="muted">共 {rows} 行，显示前 {shown} 行</small>}</div>;
}

function OutputCard({name, out}: {name: string, out: any}) {
  const title = out?.spec?.figure?.title || name;
  if (out?.type === 'image' || out?.type === 'plot') {
    const images = outputImages(out);
    const shown = images.find(i => DISPLAYABLE.includes(i.mediaType));
    const data = blobSha(out.data_blob);
    return <figure className="output-card"><figcaption>{title}{data && <BlobDownload sha={data} name={`${name}.json`} mediaType="application/json" label="数据"/>}</figcaption>
      {shown ? <BlobImage sha={shown.sha} mediaType={shown.mediaType} alt={title}/> : <p className="muted">没有可显示的图片</p>}</figure>;
  }
  if (out?.type === 'table') return <figure className="output-card"><figcaption>{title}</figcaption><TableView out={out}/></figure>;
  if (out?.type === 'file') {
    const sha = blobSha(out);
    return <figure className="output-card"><figcaption>{title}</figcaption><p className="muted">{out.name} · {out.media_type}{out.size ? ` · ${(out.size / 1024).toFixed(0)} KiB` : ''}</p>
      {sha && <BlobDownload sha={sha} name={out.name || name} mediaType={out.media_type} label="下载"/>}</figure>;
  }
  const sha = out?.type === 'value' && !('value' in out) ? blobSha(out.blob) : null;
  return <figure className="output-card"><figcaption>{title}{sha && <BlobDownload sha={sha} name={`${name}.json`} mediaType="application/json" label="下载"/>}</figcaption>
    <JsonView out={out}/></figure>;
}

const JSON_PREVIEW = 4000;
function jsonText(value: unknown) {
  const text = JSON.stringify(value, null, 2) ?? String(value);
  return text.length > JSON_PREVIEW ? `${text.slice(0, JSON_PREVIEW)}\n…（共 ${text.length.toLocaleString()} 个字符，完整内容请下载）` : text;
}

/** A value output (inline, or offloaded to a JSON blob when large), a dataset descriptor or an unknown output. */
function JsonView({out}: {out: any}) {
  const sha = out?.type === 'value' && !('value' in out) ? blobSha(out.blob) : null;
  const inline = out?.type === 'value' ? out.value : out?.type === 'dataset' ? out.descriptor : out;
  const [text, setText] = useState<string | null>(() => (sha ? null : jsonText(inline)));
  const [error, setError] = useState('');
  useEffect(() => {
    setError('');
    if (!sha) { setText(jsonText(inline)); return; }
    setText(null);
    let alive = true;
    cachedBlob(sha, fetchBlob).then(bytes => { if (alive) setText(jsonText(JSON.parse(new TextDecoder().decode(bytes)))); })
      .catch(e => { if (alive) setError(message(e)); });
    return () => { alive = false; };
  }, [out]);
  if (error) return <p className="muted">{error}</p>;
  return text === null ? <p className="muted">正在读取数据…</p> : <pre>{text}</pre>;
}

// `active` is false while 图谱 is not in view (the file mode, another section or the compact history over 结果): the
// panel stays mounted with its result and camera. `scope` names the page's project and task scope; a new one starts the
// panel afresh, even at the same node with no task (local data packages and manually bound tasks included).
export default function GraphPanel({node, scope, task, tasks, artifacts, completedTask, canReadEvents, canReadArtifacts, active = true, onError, onLog, onSource}: {node: string, scope: string, task: string,
  tasks: Json[], artifacts: Json[], completedTask: CompletedTask | null, canReadEvents: boolean, canReadArtifacts: boolean, active?: boolean,
  onError: (text: string) => void, onLog: (text: string) => void, onSource: (source: GraphSource | null) => void}) {
  const [presets, setPresets] = useState<Preset[] | null>(null);
  const [presetError, setPresetError] = useState('');
  const [presetId, setPresetId] = useState('');
  const [bindings, setBindings] = useState<Record<string, string>>({});
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [includeImages, setIncludeImages] = useState(false);
  const [result, setResult] = useState<GraphResult | null>(null);
  const [view, setView] = useState<GraphView | null>(null);
  const [shownView, setShownView] = useState<GraphView | null>(null);
  const [outputsSource, setOutputsSource] = useState<EvaluationSource | null>(null);
  const [status, setStatus] = useState('');
  const [running, setRunning] = useState(false);
  const [probe, setProbe] = useState<{position: number[], info?: PickInfo} | null>(null);
  const [probeStatus, setProbeStatus] = useState('');
  const probeRequest = useRef<AbortController | null>(null);
  const cancelProbe = useCallback(() => {
    probeRequest.current?.abort();
    probeRequest.current = null;
    setProbeStatus('');
  }, []);
  const [progress, setProgress] = useState<ProgressState | null>(null);
  // Bumped whenever a pending evaluation is superseded (new request, preset/source change, local file, unmount).
  const generation = useRef(0);
  const offeredView = useRef<GraphView | null>(null);
  const displayedView = useRef<GraphView | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // The step value from before a scrub whose evaluation is still debounced (not yet sent).
  const scrubFrom = useRef<{value: unknown} | null>(null);

  const preset = presets?.find(p => p.id === presetId);
  const files = useMemo(() => [...new Set((artifacts as Artifact[]).map(a => a?.path).filter(path => typeof path === 'string' && FIELD_FILE.test(path)))].sort(), [artifacts]);
  const params = useMemo(() => presetParameters(preset), [preset]);
  const names = useMemo(() => bindingNames(preset), [preset]);
  const stepName = useMemo(() => stepParameter(preset?.graph, params), [preset, params]);
  const fallbackSteps = useMemo(() => framesFromArtifacts(artifacts as Artifact[], frameDataset(preset?.graph)), [artifacts, preset]);
  const steps = stepChoices(result, stepName, fallbackSteps);
  const requested = stepName ? values[stepName] : undefined;
  const shownStep = typeof requested === 'number' || (typeof requested === 'string' && /^\d+$/.test(requested)) ? Number(requested) : steps.value;
  const stepIndex = shownStep === null ? -1 : steps.choices.indexOf(shownStep);
  const localName = shownView?.source.kind === 'local' ? shownView.source.file : '';
  const hdf5 = completedTask && node && task ? muProArtifact(artifacts as Artifact[]) : null;
  const shownHdf5 = shownView?.source.kind === 'evaluation' && !!shownView.source.hdf5;
  // Output cards may arrive without a new scene. In that case the displayed canvas keeps its own source.
  const source = shownView?.source ?? outputsSource;
  useLayoutEffect(() => { onSource(source); }, [source, onSource]);

  function offerView(next: GraphView | null) {
    offeredView.current = next;
    setView(next);
  }

  function canShow(payload: LoadedPayload) {
    const offered = offeredView.current;
    return offered?.payload === payload && (offered === displayedView.current || !offered.signal?.aborted);
  }

  function sceneShown(payload: LoadedPayload) {
    const next = offeredView.current, previous = displayedView.current;
    if (!next || !canShow(payload) || next === previous) return;
    cancelProbe();
    displayedView.current = next;
    setShownView(next);
    if (previous?.key !== next.key) setProbe(null);
    if (next.source.kind === 'evaluation' && next.source.hdf5) {
      setResult(null); setOutputsSource(null);
    }
    onLog('');
  }

  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    // Unmounting abandons a pending evaluation: its polling stops at the next check.
    return () => { mounted.current = false; clearTimeout(debounce.current); generation.current++; };
  }, []);
  useLayoutEffect(() => {
    if (!active) cancelProbe();
    // A node change can unmount this panel. Stop discovery before a late list can dispatch a probe.
    return () => probeRequest.current?.abort();
  }, [active, cancelProbe]);
  // The presets are read once, when the panel is first in view: a panel mounted hidden (its module arriving after the
  // user left 图谱) reads nothing until it is shown.
  const presetsRead = useRef(false);
  useEffect(() => {
    if (!active || presetsRead.current) return;
    presetsRead.current = true;
    api('graphs/presets').then((list: unknown) => {
      if (!mounted.current) return;
      const items = Array.isArray(list) ? (list as Preset[]).filter(p => p && typeof p.id === 'string') : [];
      setPresets(items);
      setPresetId(id => (items.some(p => p.id === id) ? id : items[0]?.id ?? ''));
    }).catch(e => { if (mounted.current) { setPresets([]); setPresetError(message(e)); } });
  }, [active]);

  // A new preset or scope starts from the preset defaults and a fresh camera. This runs in the commit of
  // the change, so a reply of the old scope that arrives later (a queued evaluation, a probe, an error) is never shown.
  useLayoutEffect(() => {
    generation.current++;
    cancelProbe();
    clearTimeout(debounce.current); scrubFrom.current = null;
    setValues(initialValues(params));
    setBindings(Object.fromEntries(names.map(n => [n, task])));
    offerView(null); displayedView.current = null; setShownView(null); setOutputsSource(null);
    setResult(null); setProbe(null); setStatus(''); setRunning(false); onLog('');
  }, [preset, params, names, node, scope, task, onLog, cancelProbe]);

  function changeBinding(name: string, taskId: string) {
    if (bindings[name] === taskId) return;
    generation.current++;
    cancelProbe();
    clearTimeout(debounce.current); scrubFrom.current = null;
    offerView(displayedView.current);
    setBindings(current => ({...current, [name]: taskId}));
    setRunning(false); setStatus('');
  }

  async function evaluate(overrides: Record<string, unknown> = {}) {
    if (!preset) return;
    // Invalid input is reported without touching an evaluation already running: its result still arrives
    // and clears "计算中…" itself.
    const chosen = {...values, ...overrides};
    const {parameters, errors} = coerceParameters(params, chosen);
    if (errors.length) { onError(errors.join('；')); return; }
    if (!node) { onError('请先选择执行节点'); return; }
    const missing = names.filter(n => !bindings[n]);
    if (missing.length) { onError(`请为数据源 ${missing.join('、')} 选择任务`); return; }
    const current = ++generation.current;
    cancelProbe();
    const isCurrent = () => generation.current === current;
    offerView(displayedView.current);
    const bound = Object.fromEntries(names.map(n => [n, bindings[n]]));
    const boundSources = names.map(name => {
      const taskId = bound[name];
      const row = tasks.find(t => t.id === taskId);
      return {name, task: taskId, taskName: typeof row?.name === 'string' ? row.name : undefined,
        workspace: typeof row?.workspace_id === 'string' ? row.workspace_id : undefined};
    });
    const request: Json = {preset: preset.id, bindings: Object.fromEntries(names.map(n => [n, {task_id: bound[n]}])), parameters, profile: 'web'};
    const outputs = selectOutputs(preset.graph, includeImages);
    if (outputs) request.outputs = outputs;
    setRunning(true);
    setStatus('正在数据所在节点计算图谱…');
    try {
      // A graph.evaluate may queue behind other evaluations on the node or wait for review: keep polling
      // (with backoff) until it finishes or is superseded, instead of giving up after a fixed time.
      const graphResult = await evaluateGraph(node, request, isCurrent, setStatus);
      if (!graphResult || !isCurrent()) return;
      const views = payloadOutputs(graphResult);
      let loaded: LoadedPayload | null = null, payloadError = '';
      if (views.length) {
        setStatus('正在读取渲染数据…');
        // Plots and tables of the result are still shown when the 3D payload cannot be loaded.
        try { loaded = await loadPayload(views[0].manifest, {fetchBlob}); } catch (e) { payloadError = message(e); }
      }
      if (!isCurrent()) return;
      const resolved = stepChoices(graphResult, stepName, []).value;
      const graphSource: EvaluationSource = {
        kind: 'evaluation', scope, node, display: 'outputs', presetId: preset.id, presetName: preset.name,
        step: resolved !== null && resolved >= 0 ? resolved : null,
        bindings: boundSources,
      };
      setResult(graphResult);
      setOutputsSource(Object.values(graphResult.outputs ?? {}).some(out => out?.manifest?.schema !== 'stk.payload/2')
        ? graphSource : null);
      if (loaded) {
        const output = views[0].name, payloadStep: unknown = loaded.manifest.source?.time?.step;
        const step = typeof payloadStep === 'number' && Number.isSafeInteger(payloadStep) && payloadStep >= 0
          ? payloadStep : graphSource.step;
        const key = JSON.stringify([preset.id, bound, output]);
        offerView({payload: loaded, source: {...graphSource, display: 'scene', output, step}, key, probe: {
          bindings: bound, values: parameters, result: graphResult,
        }});
      }
      setStatus('');
      if (payloadError) onError(`三维结果无法显示：${payloadError}`);
    } catch (e) {
      if (isCurrent()) { setStatus(''); onError(message(e)); }
    } finally {
      if (isCurrent()) setRunning(false);
    }
  }

  async function openHdf5(hdf5Source: MuProSource, signal: AbortSignal, onStatus: (text: string) => void) {
    if (!completedTask || signal.aborted) return;
    const current = ++generation.current;
    cancelProbe();
    const isCurrent = () => generation.current === current && !signal.aborted;
    clearTimeout(debounce.current);
    const from = scrubFrom.current;
    if (from && stepName) setValues(v => ({...v, [stepName]: from.value}));
    scrubFrom.current = null;
    offerView(displayedView.current);
    setRunning(false); setStatus('');
    try {
      const graphResult = await evaluateGraph(node, muProRequest(task, hdf5Source.artifact, hdf5Source), isCurrent, onStatus, signal);
      if (!graphResult || !isCurrent()) return;
      onStatus('正在读取 HDF5 渲染数据…');
      const payload = await loadPayload(muProManifest(graphResult, hdf5Source.frame), {fetchBlob});
      if (!isCurrent()) return;
      if (!payload.layers.some(layer => layer.type === 'volume' && layer.visible !== false)) {
        throw new Error('HDF5 渲染数据没有可显示的体数据。');
      }
      offerView({payload, signal, key: JSON.stringify(['mupro.hdf5@1', task, hdf5Source.artifact.sha256, hdf5Source.frame.name, hdf5Source.component]),
        source: {kind: 'evaluation', scope, node, display: 'scene', output: 'view', step: hdf5Source.frame.step, hdf5: hdf5Source,
          bindings: [{name: 'run', task, taskName: completedTask.name, workspace: completedTask.workspace}]}});
    } catch (e) { if (isCurrent()) throw e; }
  }

  function scrub(index: number) {
    if (!stepName || index < 0 || index >= steps.choices.length) return;
    const step = steps.choices[index];
    if (!scrubFrom.current) scrubFrom.current = {value: values[stepName]};
    setValues(v => ({...v, [stepName]: step}));
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => { scrubFrom.current = null; void evaluate({[stepName]: step}); }, 300);
  }
  // Leaving 图谱 (for the file mode, another section or the compact history) sends nothing: a scrub not yet sent is
  // dropped and its step returns to the value before it. An evaluation already sent completes in place, in its own
  // scope, and is shown on return.
  useEffect(() => {
    const from = scrubFrom.current;
    if (active || !from || !stepName) return;
    clearTimeout(debounce.current); scrubFrom.current = null;
    setValues(v => ({...v, [stepName]: from.value}));
  }, [active, stepName]);
  function latest() {
    if (!stepName) return;
    clearTimeout(debounce.current); scrubFrom.current = null;
    setValues(v => ({...v, [stepName]: 'latest'}));
    void evaluate({[stepName]: 'latest'});
  }

  // Minimal live progress for the bound running task (task.events, see stk-events-v1.md §5).
  const progressTask = bindings[names[0]] ?? task;
  const taskState = tasks.find(t => t.id === progressTask)?.state;
  // Polls only while 图谱 is in view (canReadEvents), the page is visible and the task runs, every 10 s backing off
  // to 30 s while no new events arrive, and stops once the Runtime reports the task terminal.
  useEffect(() => {
    setProgress(null);
    if (!canReadEvents || !node || !progressTask || taskState !== 'running') return;
    const abort = new AbortController();
    let stop = false;
    let wake: (() => void) | null = null;
    // Resolves after `ms`, or at once on cleanup.
    const pause = (ms: number) => new Promise<void>(resolve => {
      const timer = setTimeout(() => { wake = null; resolve(); }, ms);
      wake = () => { clearTimeout(timer); wake = null; resolve(); };
    });
    // Resolves once the page is visible (no polls while hidden), or at once on cleanup.
    const visible = () => new Promise<void>(resolve => {
      if (stop || document.visibilityState === 'visible') { resolve(); return; }
      wake = () => { wake = null; resolve(); };
    });
    const onVisibility = () => { if (document.visibilityState === 'visible') wake?.(); };
    document.addEventListener('visibilitychange', onVisibility);
    (async () => {
      let offset = 0, failures = 0, delay = EVENTS_POLL_MS.min, state = emptyProgress();
      while (!stop) {
        await visible();
        if (stop) return;
        let again = false, received = false;
        try {
          const result = await readNode(node, 'task.events', {task_id: progressTask, offset}, abort.signal);
          if (stop) return;
          const r = result as Json | null;
          failures = 0;
          if (r && Array.isArray(r.events)) {
            received = r.events.length > 0;
            state = foldEvents(state, r.events);
            setProgress(state);
            const next = Number.isInteger(r.next_offset) && r.next_offset >= offset ? r.next_offset : offset;
            const size = Number.isInteger(r.size) ? r.size : next;
            // A long log is read from its tail (the progress line needs only the latest events).
            if (size - next > EVENTS_TAIL_BYTES) { offset = size - EVENTS_TAIL_BYTES; again = true; }
            else { again = next > offset && next < size; offset = next; }
            if (r.terminal && !again) return;
          }
        } catch (e) {
          if (stop) return;
          failures++;
          setProgress({...state, message: {level: 'warning', text: `监测事件暂不可用：${message(e)}`}});
          if (failures >= 3) return;
        }
        if (!again) { delay = nextEventsDelay(delay, received); await pause(delay); }
      }
    })();
    return () => { stop = true; abort.abort(); wake?.(); document.removeEventListener('visibilitychange', onVisibility); };
  }, [canReadEvents, node, scope, progressTask, taskState]);

  async function openLocal(file: File | undefined) {
    if (!file) return;
    // A local payload replaces the graph result, so a pending evaluation is abandoned.
    const current = ++generation.current;
    cancelProbe();
    clearTimeout(debounce.current); scrubFrom.current = null;
    offerView(displayedView.current);
    setRunning(false);
    setStatus('正在读取本地数据包…');
    try {
      const loaded = await loadStkp(await file.arrayBuffer());
      if (generation.current !== current) return;
      offerView({payload: loaded, source: {kind: 'local', scope, node, file: file.name}, key: `local|${file.name}`});
      setResult(null); setOutputsSource(null); setStatus('');
    } catch (e) { if (generation.current === current) { setStatus(''); onError(message(e)); } }
  }

  async function queryProbe() {
    const displayed = displayedView.current;
    if (!active || !probe || !displayed?.probe || probeRequest.current) return;
    const target = resolveProbeTarget(preset?.graph, probe.info?.probe, displayed.probe);
    if ('error' in target) { onError(target.error); return; }
    const abort = new AbortController();
    probeRequest.current = abort;
    const current = generation.current;
    const isCurrent = () => !abort.signal.aborted && generation.current === current && displayedView.current === displayed;
    onError('');
    setProbeStatus('正在读取原始数据…');
    let review = false;
    try {
      let path: string;
      if ('frame' in target) {
        // The current queue's list belongs to its selected task. A different graph binding needs its
        // own published list, fetched only when the user explicitly requests the raw value.
        const request = {task_id: target.task_id};
        const published = target.task_id === task && artifacts.length ? artifacts : canReadArtifacts
          ? await readNode(node, 'task.artifacts', request, abort.signal)
          : (await action(node, 'task.artifacts', request, undefined, {active: isCurrent, remember: false})).result;
        if (!isCurrent()) return;
        if (!Array.isArray(published)) throw new Error('无法读取所选计算的已发布文件');
        path = resolveProbeArtifact(target, published);
      } else {
        path = target.path;
      }
      const body: Json = {task_id: target.task_id, path, position: probe.position};
      if (target.metadata) body.metadata = target.metadata;
      const item = await action(node, 'view.probe', body, () => {
        if (isCurrent()) setProbeStatus('探针查询等待复核。');
      }, {active: isCurrent});
      if (!isCurrent()) return;
      review = item.state === 'review';
      if (item.result) onLog(JSON.stringify({layer: probe.info?.layerName, path, ...item.result}, null, 2));
    } catch (e) { if (isCurrent()) onError(message(e)); }
    finally {
      if (isCurrent()) {
        probeRequest.current = null;
        if (!review) setProbeStatus('');
      }
    }
  }

  const newerFrame = progress?.frame?.step !== undefined && steps.choices.length > 0 && progress.frame.step > steps.choices[steps.choices.length - 1];
  const outputs = Object.entries(result?.outputs ?? {}).filter(([, out]) => out?.manifest?.schema !== 'stk.payload/2');
  const issues = [...(Array.isArray(result?.errors) ? result!.errors : []), ...(Array.isArray(result?.warnings) ? result!.warnings : [])];
  const timings = Object.values(result?.timings ?? {}).filter(Number.isFinite).reduce((a, b) => a + b, 0);
  const editable = params.filter(p => p.name !== stepName || !steps.choices.length);
  return <div className="graph-panel">
    {hdf5 && presets !== null && <MuProHdf5Control key={JSON.stringify([scope, task, hdf5.sha256, hdf5.size])} node={node} task={task} artifact={hdf5} onOpen={openHdf5}/>}
    <div className="view-controls graph-controls">
      <label>图谱预设<select aria-label="图谱预设" value={presetId} onChange={e => setPresetId(e.target.value)}>
        {!presets?.length && <option value="">{presets ? '暂无预设' : '正在读取预设…'}</option>}
        {presets?.map(p => <option key={p.id} value={p.id}>{p.name || p.id}</option>)}</select></label>
      {names.map(name => <label key={name}>数据源 {name}<select value={bindings[name] ?? ''} onChange={e => changeBinding(name, e.target.value)}>
        <option value="">选择任务</option>{tasks.map(t => <option key={t.id} value={t.id}>{t.name || String(t.id).slice(0, 8)} · {t.state}</option>)}</select></label>)}
      <button className="primary" disabled={running || !preset || !node} onClick={() => void evaluate()}>{running ? '计算中…' : '计算图谱'}</button>
    </div>
    {presetError && <p className="muted">图谱预设不可用：{presetError}</p>}
    {preset?.description && <p className="muted preset-description">{preset.description}</p>}
    {editable.length > 0 && <div className="graph-params">{editable.map(p => <ParamEditor key={p.name} param={p} value={values[p.name]}
      options={p.type === 'string' && p.name === 'path' ? files : undefined} onChange={v => setValues(vs => ({...vs, [p.name]: v}))}/>)}</div>}
    {stepName && steps.choices.length > 0 && !localName && !shownHdf5 && <div className="scrubber">
      <span>时间步</span>
      <button className="quiet" aria-label="上一步" disabled={stepIndex <= 0} onClick={() => scrub(stepIndex - 1)}>‹</button>
      <input type="range" aria-label="时间步" min={0} max={steps.choices.length - 1} value={Math.max(0, stepIndex)} onChange={e => scrub(Number(e.target.value))}/>
      <button className="quiet" aria-label="下一步" disabled={stepIndex >= steps.choices.length - 1} onClick={() => scrub(stepIndex + 1)}>›</button>
      <strong>{shownStep ?? '—'}</strong><small className="muted">{stepIndex + 1} / {steps.choices.length}</small>
      <button className="quiet" disabled={running} onClick={latest}>最新</button>
    </div>}
    {progress && <p className="progress-line"><span className="running">● 运行中</span> {progressText(progress)}{newerFrame && !shownHdf5 && <button className="quiet" onClick={latest}>查看最新帧</button>}</p>}
    {(status || probeStatus) && <p className="muted status-line">{status || probeStatus}</p>}
    {view
      ? <ErrorBoundary resetKey={view.payload}><React.Suspense fallback={<div className="viewport empty">正在加载三维模块…</div>}>
        <Viewer scene={view.payload} resetKey={view.key} canShow={canShow}
          onShown={sceneShown} onPick={(position, info) => {cancelProbe(); setProbe({position, info});}}/></React.Suspense></ErrorBoundary>
      : <div className="viewport"><div className="empty"><span className="orbit">◇</span><h2>用节点图描述要看的结果</h2><p>选择预设并绑定任务。计算在数据所在的节点完成，这里只接收渲染数据。</p></div></div>}
    {localName && <p className="muted">本地数据包 {localName} · 无法查询原始值</p>}
    {shownView?.probe && <div className="probe"><strong>物理坐标探针</strong>
      {(probe?.position ?? [0, 0, 0]).map((v, i) => <input aria-label={`探针${'XYZ'[i]}`} key={i} type="number" value={Number(v.toPrecision(8))}
        onChange={e => {
          const value = Number(e.target.value);
          cancelProbe();
          setProbe(p => ({...(p ?? {}), position: (p?.position ?? [0, 0, 0]).map((n, j) => (i === j ? value : n))}));
        }}/>)}
      <button disabled={!probe || running || !!probeRequest.current} onClick={() => void queryProbe()}>查询原始值</button>
      <small className="muted">{probe?.info ? `图层 ${probe.info.layerName}` : '点击表面或切片选取位置'}</small>
    </div>}
    {(outputs.length > 0 || result) && <div className="graph-outputs">{outputs.map(([name, out]) => <OutputCard key={name} name={name} out={out}/>)}</div>}
    {result && <p className="muted result-summary">{[result.cache ? `缓存命中 ${result.cache.hits ?? 0} · 重新计算 ${result.cache.misses ?? 0}` : '', timings ? `节点用时 ${timings.toFixed(2)} 秒` : '',
      (result.graph_sha256 || result.graph_hash) ? `图 ${String(result.graph_sha256 || result.graph_hash).replace('sha256:', '').slice(0, 12)}` : ''].filter(Boolean).join(' · ')}</p>}
    {issues.length > 0 && <details className="payload-warnings" open={Array.isArray(result?.errors) && result!.errors!.length > 0}><summary>{issues.length} 条计算提示</summary>
      <ul>{issues.map((w, i) => <li key={i}>{issueText(w)}</li>)}</ul></details>}
    <details className="graph-extra"><summary>更多选项</summary>
      <label className="check"><input type="checkbox" checked={includeImages} onChange={e => setIncludeImages(e.target.checked)}/>同时生成离屏渲染 PNG（较慢）</label>
      <label>打开本地 .stkp 数据包<input key={scope} type="file" accept=".stkp,application/octet-stream" onChange={e => void openLocal(e.target.files?.[0])}/></label>
    </details>
  </div>;
}
