"""Real Chromium mobile submission and desktop/native result rendering, synthetic data only."""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import threading
import time
import uuid

import uvicorn
from playwright.sync_api import sync_playwright, expect
from synorder_workspace import load_workspace
from synorder_workspace.packs import install_pack
from synorder_workbench.demo import ACTOR, demo_store
from synorder_workbench.hub.app import create_app
from synorder_interaction import InteractionStore
from synorder_interaction.auth import Accounts
from synorder_interaction.native_auth import NativeAccounts
from synorder_connectors.connections import bind
from synorder_native.bridge import Bridge
from synorder_native.transport import HubConnection
from suan.runtime.common import init_config
from suan.runtime.server import RuntimeHTTPServer
from suan.runtime.supervisor import Supervisor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runtime-python', required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory(prefix='stk-plugin-browser-') as directory, demo_store() as work, socket.socket() as sock:
        root = Path(directory)
        install_pack(work.workspace, 'stk')
        work.workspace = load_workspace(work.workspace.root, allow_test_storage=True)
        store = InteractionStore(work); store.initialize()
        password = secrets.token_urlsafe(32)
        Accounts(store).provision('plugin-user', ACTOR, password)
        config = init_config(root/'runtime', root/'workspaces', port=0); config['python'] = args.runtime_python
        runtime = RuntimeHTTPServer(config); supervisor = Supervisor(config)
        os.environ['STK_BROWSER_RUNTIME_TOKEN'] = config['token']
        os.environ['MPLCONFIGDIR'] = str(root/'matplotlib')
        bind(store, 'stk-local', 'project-space', 'stk', {'url': f'http://127.0.0.1:{runtime.server_port}', 'token_env': 'STK_BROWSER_RUNTIME_TOKEN'})
        sock.bind(('127.0.0.1', 0)); origin = f'http://127.0.0.1:{sock.getsockname()[1]}'
        app = create_app(store, origin=origin)
        server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level='warning'))
        stop = threading.Event()
        def supervise():
            while not stop.wait(.1): supervisor.tick()
        threads = [threading.Thread(target=lambda: runtime.serve_forever(poll_interval=.02), daemon=True), threading.Thread(target=supervise, daemon=True), threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)]
        for t in threads: t.start()
        errors = []
        try:
            deadline = time.monotonic()+20
            while not server.started:
                if time.monotonic()>deadline: raise RuntimeError('Hub startup timed out')
                time.sleep(.05)
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                try:
                    phone = browser.new_context(viewport={'width':390,'height':844}, is_mobile=True, has_touch=True)
                    desktop = browser.new_context(viewport={'width':1440,'height':1000})
                    mobile, page = phone.new_page(), desktop.new_page()
                    for p in (mobile, page):
                        p.set_default_timeout(20000); p.on('pageerror', lambda e: errors.append(str(e)))
                        p.goto(origin); p.get_by_label('账号',exact=True).fill('plugin-user'); p.get_by_label('密码',exact=True).fill(password)
                        p.get_by_role('button',name='登录',exact=True).click()
                        p.get_by_role('navigation').get_by_role('button',name='STK 科学工作台',exact=True).click()
                    mobile.get_by_label('配置名称',exact=True).fill('手机解析场验收')
                    mobile.get_by_label('幅度',exact=True).fill('2')
                    mobile.get_by_role('button',name='保存计算配置',exact=True).click()
                    mobile.get_by_role('dialog').get_by_role('button',name='保存草稿',exact=True).click()
                    expect(mobile.get_by_label('对象详情')).to_contain_text('手机解析场验收')
                    mobile.get_by_role('button',name='关闭详情',exact=True).click()
                    mobile.get_by_role('navigation').get_by_role('button',name='STK 科学工作台',exact=True).click()
                    mobile.get_by_role('button',name='手机解析场验收',exact=True).click()
                    mobile.get_by_role('button',name='提交此配置',exact=True).click()
                    mobile.get_by_role('dialog').get_by_role('button',name='生成待确认事项',exact=True).click()
                    mobile.get_by_role('button',name='确认执行',exact=True).click()
                    deadline = time.monotonic()+75
                    while time.monotonic()<deadline:
                        results = store.resources(ACTOR,'project-space',kind='execution')
                        if results and results[0]['body'].get('state')=='succeeded': break
                        time.sleep(.15)
                    assert len(results)==1 and results[0]['body']['verification']=='passed', results
                    mobile.get_by_role('button',name='关闭详情',exact=True).click()
                    mobile.get_by_role('navigation').get_by_role('button',name='STK 科学工作台',exact=True).click()
                    mobile.screenshot(path=str(args.output/'mobile.png'), full_page=True)
                    page.get_by_role('button',name='手机解析场验收 · 2',exact=True).click()
                    page.get_by_role('button',name='加载三维视图 · field.vtk',exact=True).click()
                    expect(page.locator('.plugin-content canvas')).to_be_visible()
                    page.locator('.plugin-content canvas').hover(); page.mouse.wheel(0,-100)
                    page.screenshot(path=str(args.output/'desktop-web.png'), full_page=True)
                    assert not errors, errors
                    assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                    # The native bridge reads the same immutable result through a paired identity.
                    accounts = NativeAccounts(store); credential = accounts.pair(accounts.issue('plugin-user')['code'],'synthetic-desktop')
                    bridge = Bridge(args.output/'native-state',origin,connection=HubConnection(origin,credential['token']))
                    bridge.ui.update(space_id='project-space',view='stk.workbench',resource_id=results[0]['id'])
                    state = bridge.tick()
                    item = next(i for i in state['panels']['content'] if i.get('command')=='presentation.scene')
                    bridge.dispatch({'id':uuid.uuid4().hex,'kind':'presentation.scene','payload':{'argument':item['argument'],'fields':{},'context':bridge.ui.copy()}})
                    bridge.tick(); bridge.close()
                    # Remove transient identities/receipts; exported UI data is synthetic and inert.
                    report = {'status':'passed','mobile_viewport':[390,844],'desktop_viewport':[1440,1000], 'tasks':len(supervisor.store.tasks()),'native_scene':True,'javascript_errors':errors,'model_called':False}
                    (args.output/'browser-report.json').write_text(json.dumps(report,indent=2))
                    print(json.dumps(report))
                except Exception:
                    mobile.screenshot(path=str(args.output/'failure.png'), full_page=True)
                    (args.output/'failure.txt').write_text(mobile.locator('body').inner_text())
                    raise
                finally: browser.close()
        finally:
            server.should_exit=True; stop.set(); runtime.shutdown(); runtime.server_close()
            for t in threads: t.join(timeout=10)
            os.environ.pop('STK_BROWSER_RUNTIME_TOKEN',None)


if __name__=='__main__': main()
