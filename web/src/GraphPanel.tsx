// 图谱 (graph) mode: evaluate a preset graph next to the data (action graph.evaluate), draw the returned
// stk.payload/2, scrub steps with the camera kept, show plots/images/tables, and a task.events progress line.
import React, {useEffect, useMemo, useRef, useState} from 'react';
import {action, api, blob, type Json} from './api';
import {cachedBlob, loadPayload, loadStkp, type LoadedPayload} from './payload';
import {bindingNames, blobSha, coerceParameters, DISPLAYABLE, editorKind, emptyProgress, foldEvents, frameDataset, framesFromArtifacts,
  initialValues, outputImages, payloadOutputs, presetParameters, progressText, resolveProbeTarget, selectOutputs, stepChoices, stepParameter,
  tableData, type Artifact, type GraphParameter, type GraphResult, type Preset, type ProgressState, type TableData} from './graph';
import type {PickInfo} from './PayloadViewer';

const Viewer = React.lazy(() => import('./Viewer'));
const fetchBlob = (sha: string, signal?: AbortSignal) => blob(sha, signal);
const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
const message = (e: unknown) => (e instanceof Error ? e.message : String(e));
const UNIT_NAMES: Record<string, string> = {unspecified: '单位未指定', '1': '无量纲', normalized: '归一化', grid_index: '网格索引'};
const unitLabel = (unit?: string) => (unit ? ` [${UNIT_NAMES[unit] ?? unit}]` : '');

function ParamEditor({param, value, onChange}: {param: GraphParameter, value: unknown, onChange: (value: unknown) => void}) {
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
    cachedBlob(sha, fetchBlob).then(bytes => { if (alive) setData(tableData(JSON.parse(new TextDecoder().decode(bytes)))); }).catch(e => { if (alive) setError(message(e)); });
    return () => { alive = false; };
  }, [out]);
  if (error) return <p className="muted">{error}</p>;
  if (!data) return <p className="muted">正在读取表格…</p>;
  const names = Object.keys(data.columns);
  const rows = Math.max(...names.map(n => data.columns[n].length));
  const shown = Math.min(rows, 100);
  return <div className="data-table"><table><thead><tr>{names.map(n => <th key={n}>{n}{data.units[n] ? <small>{unitLabel(data.units[n])}</small> : null}</th>)}</tr></thead>
    <tbody>{Array.from({length: shown}, (_, r) => <tr key={r}>{names.map(n => <td key={n}>{cell(data.columns[n][r])}</td>)}</tr>)}</tbody></table>
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
  const value = out?.type === 'value' ? out.value : out?.type === 'dataset' ? out.descriptor : out;
  return <figure className="output-card"><figcaption>{title}</figcaption><pre>{JSON.stringify(value, null, 2)?.slice(0, 4000)}</pre></figure>;
}

export default function GraphPanel({node, task, tasks, artifacts, onError, onLog}: {node: string, task: string, tasks: Json[], artifacts: Json[],
  onError: (text: string) => void, onLog: (text: string) => void}) {
  const [presets, setPresets] = useState<Preset[] | null>(null);
  const [presetError, setPresetError] = useState('');
  const [presetId, setPresetId] = useState('');
  const [bindings, setBindings] = useState<Record<string, string>>({});
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [includeImages, setIncludeImages] = useState(false);
  const [result, setResult] = useState<GraphResult | null>(null);
  const [payload, setPayload] = useState<LoadedPayload | null>(null);
  const [localName, setLocalName] = useState('');
  const [status, setStatus] = useState('');
  const [running, setRunning] = useState(false);
  const [probe, setProbe] = useState<{position: number[], info?: PickInfo} | null>(null);
  const [progress, setProgress] = useState<ProgressState | null>(null);
  const generation = useRef(0);
  const debounce = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const preset = presets?.find(p => p.id === presetId);
  const params = useMemo(() => presetParameters(preset), [preset]);
  const names = useMemo(() => bindingNames(preset), [preset]);
  const stepName = useMemo(() => stepParameter(preset?.graph, params), [preset, params]);
  const fallbackSteps = useMemo(() => framesFromArtifacts(artifacts as Artifact[], frameDataset(preset?.graph)), [artifacts, preset]);
  const steps = stepChoices(result, stepName, fallbackSteps);
  const requested = stepName ? values[stepName] : undefined;
  const shownStep = typeof requested === 'number' || (typeof requested === 'string' && /^\d+$/.test(requested)) ? Number(requested) : steps.value;
  const stepIndex = shownStep === null ? -1 : steps.choices.indexOf(shownStep);
  const resetKey = `${presetId}|${JSON.stringify(bindings)}`;

  useEffect(() => {
    let alive = true;
    api('graphs/presets').then((list: unknown) => {
      if (!alive) return;
      const items = Array.isArray(list) ? (list as Preset[]).filter(p => p && typeof p.id === 'string') : [];
      setPresets(items);
      setPresetId(id => (items.some(p => p.id === id) ? id : items[0]?.id ?? ''));
    }).catch(e => { if (alive) { setPresets([]); setPresetError(message(e)); } });
    return () => { alive = false; clearTimeout(debounce.current); };
  }, []);

  // A new preset or data source starts from the preset defaults and a fresh camera.
  useEffect(() => {
    generation.current++;
    clearTimeout(debounce.current);
    setValues(initialValues(params));
    setBindings(Object.fromEntries(names.map(n => [n, task])));
    setResult(null); setPayload(null); setProbe(null); setStatus(''); setRunning(false); setLocalName('');
  }, [preset, params, names, task]);

  async function evaluate(overrides: Record<string, unknown> = {}) {
    if (!preset) return;
    const current = ++generation.current;
    const {parameters, errors} = coerceParameters(params, {...values, ...overrides});
    if (errors.length) { onError(errors.join('；')); return; }
    if (!node) { onError('请先选择执行节点'); return; }
    const missing = names.filter(n => !bindings[n]);
    if (missing.length) { onError(`请为数据源 ${missing.join('、')} 选择任务`); return; }
    const request: Json = {preset: preset.id, bindings: Object.fromEntries(names.map(n => [n, {task_id: bindings[n]}])), parameters, profile: 'web'};
    const outputs = selectOutputs(preset.graph, includeImages);
    if (outputs) request.outputs = outputs;
    setRunning(true);
    setStatus('正在数据所在节点计算图谱…');
    try {
      let item = await action(node, 'graph.evaluate', request, () => setStatus('图谱计算超过自动执行额度，正在等待复核；批准后结果会自动显示。'), {timeoutMs: 300000});
      const deadline = Date.now() + 30 * 60 * 1000;
      while ((item.state === 'review' || item.state === 'queued') && generation.current === current && Date.now() < deadline) {
        await sleep(2000);
        item = await api(`actions/${item.id}`);
      }
      if (generation.current !== current) return;
      if (item.state === 'failed') throw new Error(item.error || '图谱计算失败');
      if (item.state === 'rejected') throw new Error('图谱计算未获批准');
      if (item.state !== 'succeeded' || !item.result || typeof item.result !== 'object') throw new Error('图谱计算尚未返回结果，可在操作列表中查看');
      const graphResult = item.result as GraphResult;
      const views = payloadOutputs(graphResult);
      let loaded: LoadedPayload | null = null, payloadError = '';
      if (views.length) {
        setStatus('正在读取渲染数据…');
        // Plots and tables of the result are still shown when the 3D payload cannot be loaded.
        try { loaded = await loadPayload(views[0].manifest, {fetchBlob}); } catch (e) { payloadError = message(e); }
      }
      if (generation.current !== current) return;
      setResult(graphResult);
      setLocalName('');
      if (loaded) setPayload(loaded);
      setStatus('');
      if (payloadError) onError(`三维结果无法显示：${payloadError}`);
    } catch (e) {
      if (generation.current === current) { setStatus(''); onError(message(e)); }
    } finally {
      if (generation.current === current) setRunning(false);
    }
  }

  function scrub(index: number) {
    if (!stepName || index < 0 || index >= steps.choices.length) return;
    const step = steps.choices[index];
    setValues(v => ({...v, [stepName]: step}));
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => void evaluate({[stepName]: step}), 300);
  }
  function latest() {
    if (!stepName) return;
    clearTimeout(debounce.current);
    setValues(v => ({...v, [stepName]: 'latest'}));
    void evaluate({[stepName]: 'latest'});
  }

  // Minimal live progress for the bound running task (action task.events, see stk-events-v1.md §5).
  const progressTask = bindings[names[0]] || task;
  const taskState = tasks.find(t => t.id === progressTask)?.state;
  useEffect(() => {
    setProgress(null);
    if (!node || !progressTask || taskState !== 'running') return;
    let stop = false;
    (async () => {
      let offset = 0, failures = 0, state = emptyProgress();
      while (!stop) {
        let again = false;
        if (document.visibilityState === 'visible') {
          try {
            const item = await action(node, 'task.events', {task_id: progressTask, offset}, undefined, {remember: false, timeoutMs: 30000});
            if (stop) return;
            const r = item.result;
            failures = 0;
            if (r && Array.isArray(r.events)) {
              state = foldEvents(state, r.events);
              setProgress(state);
              const next = Number.isInteger(r.next_offset) ? r.next_offset : offset;
              again = next > offset && Number.isInteger(r.size) && next < r.size; // catch up on a long event log
              offset = next;
              if (r.terminal) return;
            }
          } catch (e) {
            if (stop) return;
            failures++;
            setProgress({...state, message: {level: 'warning', text: `监测事件暂不可用：${message(e)}`}});
            if (failures >= 3) return;
          }
        }
        if (!again) await sleep(10000);
      }
    })();
    return () => { stop = true; };
  }, [node, progressTask, taskState]);

  async function openLocal(file: File | undefined) {
    if (!file) return;
    const current = ++generation.current;
    try {
      const loaded = await loadStkp(await file.arrayBuffer());
      if (generation.current !== current) return;
      setPayload(loaded); setResult(null); setProbe(null); setLocalName(file.name); setRunning(false); setStatus('');
    } catch (e) { onError(message(e)); }
  }

  async function queryProbe() {
    if (!probe) return;
    const target = resolveProbeTarget(preset?.graph, probe.info?.probe, {bindings, values, result, artifacts: artifacts as Artifact[]});
    if ('error' in target) { onError(target.error); return; }
    const body: Json = {task_id: target.task_id, path: target.path, position: probe.position};
    if (target.metadata) body.metadata = target.metadata;
    setStatus('正在读取原始数据…');
    try {
      const item = await action(node, 'view.probe', body, () => setStatus('探针查询等待复核。'));
      if (item.result) onLog(JSON.stringify({layer: probe.info?.layerName, path: target.path, ...item.result}, null, 2));
      if (item.state !== 'review') setStatus('');
    } catch (e) { setStatus(''); onError(message(e)); }
  }

  const newerFrame = progress?.frame?.step !== undefined && steps.choices.length > 0 && progress.frame.step > steps.choices[steps.choices.length - 1];
  const outputs = Object.entries(result?.outputs ?? {}).filter(([, out]) => out?.manifest?.schema !== 'stk.payload/2');
  const timings = Object.values(result?.timings ?? {}).filter(Number.isFinite).reduce((a, b) => a + b, 0);
  const editable = params.filter(p => p.name !== stepName || !steps.choices.length);
  return <div className="graph-panel">
    <div className="view-controls graph-controls">
      <label>图谱预设<select aria-label="图谱预设" value={presetId} onChange={e => setPresetId(e.target.value)}>
        {!presets?.length && <option value="">{presets ? '暂无预设' : '正在读取预设…'}</option>}
        {presets?.map(p => <option key={p.id} value={p.id}>{p.name || p.id}</option>)}</select></label>
      {names.map(name => <label key={name}>数据源 {name}<select value={bindings[name] ?? ''} onChange={e => setBindings(b => ({...b, [name]: e.target.value}))}>
        <option value="">选择任务</option>{tasks.map(t => <option key={t.id} value={t.id}>{t.name || String(t.id).slice(0, 8)} · {t.state}</option>)}</select></label>)}
      <button className="primary" disabled={running || !preset || !node} onClick={() => void evaluate()}>{running ? '计算中…' : '计算图谱'}</button>
    </div>
    {presetError && <p className="muted">图谱预设不可用：{presetError}</p>}
    {preset?.description && <p className="muted preset-description">{preset.description}</p>}
    {editable.length > 0 && <div className="graph-params">{editable.map(p => <ParamEditor key={p.name} param={p} value={values[p.name]} onChange={v => setValues(vs => ({...vs, [p.name]: v}))}/>)}</div>}
    {stepName && steps.choices.length > 0 && !localName && <div className="scrubber">
      <span>时间步</span>
      <button className="quiet" aria-label="上一步" disabled={stepIndex <= 0} onClick={() => scrub(stepIndex - 1)}>‹</button>
      <input type="range" aria-label="时间步" min={0} max={steps.choices.length - 1} value={Math.max(0, stepIndex)} onChange={e => scrub(Number(e.target.value))}/>
      <button className="quiet" aria-label="下一步" disabled={stepIndex >= steps.choices.length - 1} onClick={() => scrub(stepIndex + 1)}>›</button>
      <strong>{shownStep ?? '—'}</strong><small className="muted">{stepIndex + 1} / {steps.choices.length}</small>
      <button className="quiet" disabled={running} onClick={latest}>最新</button>
    </div>}
    {progress && <p className="progress-line"><span className="running">● 运行中</span> {progressText(progress)}{newerFrame && <button className="quiet" onClick={latest}>查看最新帧</button>}</p>}
    {status && <p className="muted status-line">{status}</p>}
    {payload
      ? <React.Suspense fallback={<div className="viewport empty">正在加载三维模块…</div>}><Viewer scene={payload} resetKey={localName ? `local|${localName}` : resetKey} onPick={(position, info) => setProbe({position, info})}/></React.Suspense>
      : <div className="viewport"><div className="empty"><span className="orbit">◇</span><h2>用节点图描述要看的结果</h2><p>选择预设并绑定任务。计算在数据所在的节点完成，这里只接收渲染数据。</p></div></div>}
    {localName && <p className="muted">本地数据包 {localName} · 无法查询原始值</p>}
    {payload && !localName && <div className="probe"><strong>物理坐标探针</strong>
      {(probe?.position ?? [0, 0, 0]).map((v, i) => <input aria-label={`探针${'XYZ'[i]}`} key={i} type="number" value={Number(v.toPrecision(8))}
        onChange={e => setProbe(p => ({...(p ?? {}), position: (p?.position ?? [0, 0, 0]).map((n, j) => (i === j ? Number(e.target.value) : n))}))}/>)}
      <button disabled={!probe || running} onClick={() => void queryProbe()}>查询原始值</button>
      <small className="muted">{probe?.info ? `图层 ${probe.info.layerName}` : '点击表面或切片选取位置'}</small>
    </div>}
    {(outputs.length > 0 || result) && <div className="graph-outputs">{outputs.map(([name, out]) => <OutputCard key={name} name={name} out={out}/>)}</div>}
    {result && <p className="muted result-summary">{[result.cache ? `缓存命中 ${result.cache.hits ?? 0} · 重新计算 ${result.cache.misses ?? 0}` : '', timings ? `节点用时 ${timings.toFixed(2)} 秒` : '',
      (result.graph_sha256 || result.graph_hash) ? `图 ${String(result.graph_sha256 || result.graph_hash).replace('sha256:', '').slice(0, 12)}` : ''].filter(Boolean).join(' · ')}</p>}
    {Array.isArray(result?.warnings) && result!.warnings!.length > 0 && <details className="payload-warnings"><summary>{result!.warnings!.length} 条计算提示</summary>
      <ul>{result!.warnings!.map((w, i) => <li key={i}>{typeof w === 'string' ? w : JSON.stringify(w)}</li>)}</ul></details>}
    <details className="graph-extra"><summary>更多选项</summary>
      <label className="check"><input type="checkbox" checked={includeImages} onChange={e => setIncludeImages(e.target.checked)}/>同时生成离屏渲染 PNG（较慢）</label>
      <label>打开本地 .stkp 数据包<input type="file" accept=".stkp,application/octet-stream" onChange={e => void openLocal(e.target.files?.[0])}/></label>
    </details>
  </div>;
}
