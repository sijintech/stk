"""Desktop task workspace; all HTTP/file transfers run outside the GUI thread."""

from pathlib import Path
import codecs
import json
import shlex
import uuid

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Qt
from PySide6.QtGui import QDesktopServices, QPixmap, QTextCursor
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QPushButton,
    QComboBox, QLineEdit, QLabel, QPlainTextEdit, QTableWidget, QTableWidgetItem,
    QFileDialog, QInputDialog, QMessageBox, QSpinBox, QListWidget, QSplitter, QDialog,
    QDialogButtonBox)

from suan.runtime.client import RuntimeClient
from suan.runtime.cli import default_state, get_client, profiles_path
from suan.runtime.common import atomic_json, init_config, read_json, inside
from suan.runtime.models import TaskSpec

STATES = {"preparing": "准备中", "submitting": "提交中", "queued": "排队中", "running": "运行中",
          "succeeded": "成功", "failed": "失败", "cancelled": "已取消", "unknown": "待核实"}


class Signals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class RequestWork(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = Signals()

    def run(self):
        try:
            self.signals.result.emit(self.fn())
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


class RuntimeTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.host = parent
        self.client = None
        self.pending = set()
        self.refreshing = False
        self.connection_epoch = 0
        self.log_task = None
        self.offsets = {"stdout": 0, "stderr": 0}
        self.decoders = {s: codecs.getincrementaldecoder('utf-8')('replace') for s in self.offsets}
        self.submission = None
        self.uploading = 0
        self.submitting = False
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.connections = QComboBox()
        self.connections.addItem('本机', None)
        for name in read_json(profiles_path(), {}):
            self.connections.addItem(name, name)
        row.addWidget(QLabel('运行位置'))
        row.addWidget(self.connections, 1)
        self.button(row, '连接', self.connect_runtime)
        self.button(row, '添加连接', self.add_connection)
        layout.addLayout(row)
        self.status = QLabel('连接后可提交任务；关闭桌面不会取消服务器任务。')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.workspace = QComboBox()
        self.workspace.currentIndexChanged.connect(self.workspace_changed)
        row.addWidget(QLabel('工作区'))
        row.addWidget(self.workspace, 1)
        self.button(row, '新建', self.create_workspace)
        self.button(row, '上传文件', self.upload_files)
        self.button(row, '上传文件夹', self.upload_folder)
        layout.addLayout(row)
        self.input_files = QListWidget()
        self.input_files.setMaximumHeight(90)
        layout.addWidget(self.input_files)
        self.input_files.itemDoubleClicked.connect(self.open_input)
        form = QFormLayout()
        self.name = QLineEdit()
        self.program = QLineEdit('{python}')
        self.arguments = QLineEdit()
        self.arguments.setPlaceholderText('例如 simulate.py --input input.json；含空格的参数请加引号')
        self.backend = QComboBox()
        self.backend.addItems(['local', 'pbs', 'slurm'])
        self.cpus = QSpinBox()
        self.cpus.setRange(1, 65536)
        self.nodes = QSpinBox()
        self.nodes.setRange(1, 65536)
        self.memory = QSpinBox()
        self.memory.setRange(0, 2147483647)
        self.memory.setSuffix(' MB（0 使用环境默认值）')
        self.walltime = QSpinBox()
        self.walltime.setRange(0, 2147483647)
        self.walltime.setSuffix(' 秒（0 使用环境默认值）')
        self.queue = QLineEdit()
        self.account = QLineEdit()
        for label, widget in [('任务名称', self.name), ('程序', self.program), ('参数', self.arguments),
                              ('执行方式', self.backend)]:
            form.addRow(label, widget)
        layout.addLayout(form)
        resource_button = QPushButton('资源配置')
        resource_button.setCheckable(True)
        layout.addWidget(resource_button)
        resource_widget = QWidget()
        resources_form = QFormLayout(resource_widget)
        for label, widget in [('每节点 CPU', self.cpus), ('节点数', self.nodes),
                              ('内存', self.memory), ('时间上限', self.walltime), ('集群队列', self.queue), ('集群账户', self.account)]:
            resources_form.addRow(label, widget)
        layout.addWidget(resource_widget)
        resource_widget.hide()
        resource_button.toggled.connect(resource_widget.setVisible)
        row = QHBoxLayout()
        self.submit_button = self.button(row, '提交任务', self.submit)
        self.retry_button = self.button(row, '重试上次提交', self.retry_submission)
        self.retry_button.setEnabled(False)
        self.button(row, '刷新', self.refresh)
        self.button(row, '取消选中任务', self.cancel_selected)
        layout.addLayout(row)
        self.tasks = QTableWidget(0, 4)
        self.tasks.setHorizontalHeaderLabels(['任务', '状态', '执行方式', '说明'])
        self.tasks.setSelectionBehavior(QTableWidget.SelectRows)
        self.tasks.setSelectionMode(QTableWidget.SingleSelection)
        self.tasks.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tasks.itemSelectionChanged.connect(self.select_task)
        self.tasks.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.tasks)
        split = QSplitter()
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(10000)
        self.outputs = QListWidget()
        self.log.setPlaceholderText('选中任务后显示 stdout / stderr 日志')
        self.outputs.setToolTip('双击结果文件下载、校验并打开')
        self.outputs.itemDoubleClicked.connect(self.download_selected)
        split.addWidget(self.log)
        split.addWidget(self.outputs)
        layout.addWidget(split)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMaximumHeight(260)
        layout.addWidget(self.preview)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)

    @staticmethod
    def button(row, text, callback):
        button = QPushButton(text)
        button.clicked.connect(callback)
        row.addWidget(button)
        return button

    def background(self, fn, callback=None, error=None, done=None):
        worker = RequestWork(fn)
        self.pending.add(worker)
        if callback:
            worker.signals.result.connect(callback)
        worker.signals.error.connect(error or self.show_error)
        worker.signals.finished.connect(lambda: self.pending.discard(worker))
        if done:
            worker.signals.finished.connect(done)
        QThreadPool.globalInstance().start(worker)

    def show_error(self, text):
        self.status.setText('操作未完成：' + text)

    def connect_runtime(self):
        profile = self.connections.currentData()
        self.connection_epoch += 1
        epoch = self.connection_epoch
        self.client = None
        self.workspace.clear()
        self.tasks.setRowCount(0)
        self.status.setText('正在连接…')

        def connect():
            if profile is None:
                from suan.runtime.daemon import start
                init_config(default_state())
                start(default_state())
            client = get_client(profile)
            health = client.health()
            if health['api_version'] != 1:
                raise ValueError('客户端与服务器 API 版本不兼容')
            return client, client.workspaces(), health

        def connected(result):
            if epoch != self.connection_epoch:
                return
            self.client = result[0]
            self.set_workspaces(result[1])
            self.status.setText('已连接' if result[2]['supervisor_running'] else '已连接，但任务调度服务未运行')
        self.background(connect, connected, lambda message: self.show_error(message) if epoch == self.connection_epoch else None)

    def add_connection(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('添加服务器连接')
        layout = QFormLayout(dialog)
        name, url, token = QLineEdit(), QLineEdit('http://127.0.0.1:9876'), QLineEdit()
        token.setEchoMode(QLineEdit.Password)
        layout.addRow(QLabel('先建立 SSH 隧道，再填写本机转发地址与服务器令牌。'))
        for title, field in [('连接名称', name), ('转发地址', url), ('服务器令牌', token)]:
            layout.addRow(title, field)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        values = (name.text().strip(), url.text().strip(), token.text().strip())
        def save():
            if not values[0]:
                raise ValueError('请输入连接名称')
            RuntimeClient(values[1], values[2]).health()
            profiles = read_json(profiles_path(), {})
            profiles[values[0]] = {'url': values[1], 'token': values[2]}
            atomic_json(profiles_path(), profiles)
        def saved(_):
            index = self.connections.findData(values[0])
            if index < 0:
                self.connections.addItem(values[0], values[0])
                index = self.connections.count() - 1
            self.connections.setCurrentIndex(index)
            self.connect_runtime()
        self.background(save, saved)

    def set_workspaces(self, workspaces, selected=None):
        selected = selected or self.workspace.currentData()
        self.workspace.blockSignals(True)
        self.workspace.clear()
        for workspace in workspaces:
            self.workspace.addItem(workspace['name'], workspace['id'])
        index = self.workspace.findData(selected)
        if index >= 0:
            self.workspace.setCurrentIndex(index)
        self.workspace.blockSignals(False)
        self.workspace_changed()

    def workspace_changed(self, *_):
        self.log_task = None
        self.log.clear()
        self.outputs.clear()
        self.input_files.clear()
        self.refresh()

    def create_workspace(self):
        if not self.client:
            return self.show_error('请先连接运行环境')
        name, ok = QInputDialog.getText(self, '新建工作区', '工作区名称')
        if ok and name.strip():
            client = self.client
            epoch = self.connection_epoch
            def create():
                workspace = client.create_workspace(name)
                return client.workspaces(), workspace['id']
            self.background(create, lambda result: self.set_workspaces(*result) if epoch == self.connection_epoch else None)

    def upload_paths(self, paths):
        client, workspace = self.client, self.workspace.currentData()
        if not client or not workspace:
            return self.show_error('请先选择工作区')
        self.uploading += 1
        self.submit_button.setEnabled(False)
        def upload():
            for local, remote in paths:
                client.upload(workspace, local, remote)
            return len(paths)
        def done():
            self.uploading -= 1
            self.submit_button.setEnabled(not self.uploading and not self.submitting)
        self.background(upload, lambda n: (self.status.setText(f'已上传并校验 {n} 个文件'), self.refresh()), done=done)

    def upload_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '上传输入文件')
        self.upload_paths([(Path(p), Path(p).name) for p in paths])

    def upload_folder(self):
        name = QFileDialog.getExistingDirectory(self, '上传输入文件夹')
        if name:
            root = Path(name)
            self.upload_paths([(p, p.relative_to(root).as_posix()) for p in root.rglob('*') if p.is_file()])

    def submit(self):
        if self.uploading:
            return self.show_error('请等待本批输入上传和校验完成')
        if not self.client or not self.workspace.currentData():
            return self.show_error('请先选择工作区')
        try:
            resources = {'cpus': self.cpus.value(), 'nodes': self.nodes.value()}
            for key, value in [('memory_mb', self.memory.value()), ('walltime_seconds', self.walltime.value()),
                               ('queue', self.queue.text().strip()), ('account', self.account.text().strip())]:
                if value:
                    resources[key] = value
            spec = TaskSpec(self.workspace.currentData(), [self.program.text().strip()] + shlex.split(self.arguments.text()),
                            backend=self.backend.currentText(), name=self.name.text(), resources=resources)
            self.submission = (self.client, spec, uuid.uuid4().hex)
            self.retry_submission()
        except ValueError as exc:
            self.show_error(str(exc))

    def retry_submission(self):
        if not self.submission:
            return
        client, spec, key = self.submission
        self.submitting = True
        self.submit_button.setEnabled(False)
        self.retry_button.setEnabled(False)
        def submitted(record):
            self.status.setText('任务已登记：' + record['id'])
            self.submission = None
            self.refresh()
        def failed(error):
            self.show_error(error + '；可重试上次提交，系统会识别重复请求。')
            self.retry_button.setEnabled(True)
        def done():
            self.submitting = False
            self.submit_button.setEnabled(not self.uploading)
        self.background(lambda: client.submit(spec, key), submitted, failed, done)

    def selected_id(self):
        row = self.tasks.currentRow()
        item = self.tasks.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item else None

    def select_task(self):
        task = self.selected_id()
        if task != self.log_task:
            self.log_task = task
            self.offsets = {'stdout': 0, 'stderr': 0}
            self.decoders = {s: codecs.getincrementaldecoder('utf-8')('replace') for s in self.offsets}
            self.log.clear()
            self.outputs.clear()
            self.preview.clear()

    def refresh(self):
        if not self.client or self.refreshing:
            return
        client, workspace = self.client, self.workspace.currentData()
        if not workspace:
            return
        epoch = self.connection_epoch
        selected = self.selected_id()
        offsets = self.offsets.copy()
        self.refreshing = True
        def fetch():
            logs = {s: client.logs(selected, s, n) for s, n in offsets.items()} if selected else {}
            return client.tasks(workspace), client.files(workspace), logs, client.artifacts(selected) if selected else []
        def display(data):
            if epoch != self.connection_epoch or workspace != self.workspace.currentData():
                return
            records, files, logs, artifacts = data
            current = self.selected_id()
            self.tasks.blockSignals(True)
            self.tasks.setRowCount(len(records))
            for row, record in enumerate(records):
                values = [record['spec']['name'] or record['id'][:12], STATES.get(record['state'], record['state']), record['spec']['backend'], record['reason']]
                if record['cancel_requested'] and record['state'] not in ('succeeded', 'failed', 'cancelled'):
                    values[1] = '正在取消'
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.UserRole, record['id'])
                    self.tasks.setItem(row, column, item)
                if record['id'] == current:
                    self.tasks.selectRow(row)
            self.tasks.blockSignals(False)
            self.input_files.clear()
            self.input_files.addItems([f['path'] for f in files])
            if selected and selected == self.selected_id() and selected == self.log_task:
                for stream, response in logs.items():
                    text = self.decoders[stream].decode(response['bytes'])
                    if text:
                        self.log.moveCursor(QTextCursor.End)
                        self.log.insertPlainText(text if stream == 'stdout' else '[stderr] ' + text)
                    self.offsets[stream] = response['next_offset']
                self.outputs.clear()
                self.outputs.addItems([a['path'] for a in artifacts])
        self.background(fetch, display,
                        error=lambda message: self.show_error(message) if epoch == self.connection_epoch else None,
                        done=lambda: setattr(self, 'refreshing', False))

    def cancel_selected(self):
        task, client = self.selected_id(), self.client
        if task and client:
            self.background(lambda: client.cancel(task), lambda _: self.refresh())

    def cache_path(self, task_id, filename):
        import hashlib
        server_key = hashlib.sha256(self.client.url.encode()).hexdigest()[:16]
        return inside(Path(default_state()).parent / 'cache' / server_key / task_id, filename)

    def open_input(self, item):
        client, workspace, name = self.client, self.workspace.currentData(), item.text()
        path, _ = QFileDialog.getSaveFileName(self, '下载工作区文件', Path(name).name)
        if path:
            self.background(lambda: client.download_input(workspace, name, path), self.open_result)

    def download_selected(self, item):
        task, client, name = self.selected_id(), self.client, item.text()
        if task and client:
            path = self.cache_path(task, name)
            self.background(lambda: client.download(task, name, path), self.open_result)

    def open_result(self, path):
        path = Path(path)
        self.status.setText('已下载并校验：' + str(path))
        if path.suffix.lower() in {'.png', '.jpg', '.jpeg'}:
            self.preview.setPixmap(QPixmap(str(path)).scaled(600, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        elif path.suffix.lower() == '.vtk' and hasattr(self.host, 'updateVTKVisualization'):
            import vtk
            reader = vtk.vtkDataSetReader()
            reader.SetFileName(str(path))
            reader.Update()
            mapper = vtk.vtkDataSetMapper()
            mapper.SetInputData(reader.GetOutput())
            mapper.SetScalarRange(reader.GetOutput().GetScalarRange())
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            renderer = vtk.vtkRenderer()
            renderer.AddActor(actor)
            renderer.ResetCamera()
            self.host.updateVTKVisualization(renderer, replace=True)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
