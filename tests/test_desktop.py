from pathlib import Path
import time

import pytest

from suan.runtime.common import atomic_json

pytestmark = pytest.mark.desktop


@pytest.fixture
def qt(monkeypatch, tmp_path):
    pytest.importorskip('PySide6')
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    monkeypatch.setenv('STK_CONFIG_DIR', str(tmp_path / 'desktop'))
    monkeypatch.setenv('STK_PROFILES_FILE', str(tmp_path / 'connections.json'))
    monkeypatch.setenv('STK_STATE_DIR', str(tmp_path / 'local-runtime'))
    import suan.gui
    monkeypatch.syspath_prepend(str(Path(suan.gui.__file__).resolve().parent))
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    from PySide6.QtCore import QThreadPool
    assert QThreadPool.globalInstance().waitForDone(5000)
    app.processEvents()


def pump(app, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        assert time.monotonic() < deadline, 'Qt background operation timed out'
        time.sleep(.01)
    app.processEvents()


def test_main_window_from_unrelated_directory_without_ai(qt, monkeypatch, tmp_path):
    import main
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main.MainWindow, 'check_update', lambda self: None)
    main.ensure_config_directories()
    window = main.MainWindow(False)
    window.window_initialized = True
    window.resize(1200, 850)
    window.show()
    qt.processEvents()
    assert window.center_widget.runtimeTab is not None
    assert window.center_widget.vtkWidget is None  # Monitoring needs no GL context.
    assert window.center_widget.codeTab is not None
    assert window.compare_versions('0.1.0a1', '0.1.0') == -1
    assert window.compare_versions('0.1', '0.1.0') == 0
    assert main.Updater.UpdateWindow.compare_versions(None, '0.1.0a1', '0.1.0') == -1
    assert Path(main.get_resource_path('resources/styles.qss')).is_file()
    window.center_widget.runtimeTab.timer.stop()
    window.hide()
    window.deleteLater()
    qt.processEvents()


def test_desktop_remote_profile_upload_submit_logs_download(qt, runtime, monkeypatch, tmp_path):
    from Tab.runtime_tab import RuntimeTab
    client, supervisor, _, config = runtime
    workspace = client.create_workspace('remote desktop')['id']
    atomic_json(tmp_path / 'connections.json', {'test-server': {'url': client.url, 'token': config['token']}})
    tab = RuntimeTab()
    tab.timer.stop()
    tab.connections.setCurrentIndex(1)
    tab.connect_runtime()
    pump(qt, lambda: tab.client is not None and not tab.pending)
    assert tab.workspace.currentData() == workspace
    script = tmp_path / 'compute.py'
    script.write_text("from pathlib import Path\nprint('desktop complete')\nPath('answer.txt').write_text('42')\n")
    tab.upload_paths([(script, 'compute.py')])
    assert not tab.submit_button.isEnabled()
    pump(qt, lambda: not tab.pending)
    assert tab.submit_button.isEnabled()
    tab.arguments.setText('compute.py')
    tab.submit()
    pump(qt, lambda: not tab.pending)
    task = client.tasks()[0]
    from conftest import finish
    assert finish(client, supervisor, task['id'])['state'] == 'succeeded'
    tab.refresh()
    pump(qt, lambda: not tab.pending)
    tab.tasks.selectRow(0)
    tab.refresh()
    pump(qt, lambda: not tab.pending)
    assert 'desktop complete' in tab.log.toPlainText()
    assert tab.outputs.item(0).text() == 'answer.txt'
    downloaded = []
    monkeypatch.setattr(tab, 'open_result', downloaded.append)
    tab.download_selected(tab.outputs.item(0))
    pump(qt, lambda: not tab.pending)
    assert downloaded[0].read_text() == '42'
    assert downloaded[0] != supervisor.service.task_dir(task['id']) / 'work' / 'answer.txt'
    tab.deleteLater()
    qt.processEvents()
