// Development only (main.tsx imports it behind import.meta.env.DEV, so production bundles never contain it):
// `?example=1` renders docs/specs/examples/payload-v2/example.stkp without a hub; `?example=dir` loads the
// directory form (manifest.json + <sha256>.bin), exercising sha256 blob fetching and verification.
import {useEffect, useState} from 'react';
import Viewer, {type PickInfo} from './Viewer';
import {loadPayload, loadStkp, type LoadedPayload} from './payload';

// Asset URLs of the example files (outside the Vite root; import.meta.glob keeps them servable in dev).
const FILES = import.meta.glob(['../../docs/specs/examples/payload-v2/*.bin', '../../docs/specs/examples/payload-v2/manifest.json',
  '../../docs/specs/examples/payload-v2/example.stkp'], {query: '?url', import: 'default', eager: true}) as Record<string, string>;
const fileUrl = (name: string) => {
  const entry = Object.entries(FILES).find(([path]) => path.endsWith(`/${name}`));
  if (!entry) throw new Error(`示例文件 ${name} 不存在`);
  return entry[1];
};

async function loadExample(mode: string | null): Promise<LoadedPayload> {
  if (mode === 'dir') {
    const manifest = await (await fetch(fileUrl('manifest.json'))).json();
    return loadPayload(manifest, {fetchBlob: async sha => (await fetch(fileUrl(`${sha}.bin`))).arrayBuffer()});
  }
  return loadStkp(await (await fetch(fileUrl('example.stkp'))).arrayBuffer());
}

export default function ExampleView() {
  const mode = new URLSearchParams(location.search).get('example');
  const [payload, setPayload] = useState<LoadedPayload | null>(null);
  const [error, setError] = useState('');
  const [pick, setPick] = useState('点击立方体表面查看物理坐标与探针数据源');
  useEffect(() => { loadExample(mode).then(setPayload).catch(e => setError(e instanceof Error ? e.message : String(e))); }, [mode]);
  async function open(file: File | undefined) {
    if (!file) return;
    try { setPayload(await loadStkp(await file.arrayBuffer())); setError(''); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }
  const onPick = (position: number[], info?: PickInfo) =>
    setPick(`${info?.layerName ?? ''} · (${position.map(v => v.toFixed(3)).join(', ')}) · probe ${JSON.stringify(info?.probe ?? null)}`);
  return <main className="example-view">
    <header><div className="wordmark">STK <span>渲染数据包示例（开发模式）</span></div>
      <label className="file-pick">打开 .stkp<input type="file" accept=".stkp" onChange={e => void open(e.target.files?.[0])}/></label></header>
    <section className="analysis">
      {payload && <Viewer scene={payload} resetKey="example" onPick={onPick}/>}
      <p className="muted" data-testid="pick">{pick}</p>
      {error && <p role="alert">{error}</p>}
    </section>
  </main>;
}
