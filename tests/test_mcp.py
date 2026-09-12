import asyncio
import importlib.util

import pytest

from conftest import finish


@pytest.mark.skipif(importlib.util.find_spec('mcp') is None, reason='optional MCP extra')
def test_mcp_and_cli_observe_the_same_task(runtime, monkeypatch):
    from click.testing import CliRunner
    from suan.cli.main import cli
    from suan.mcp import server as adapter
    client, supervisor, _, config = runtime
    monkeypatch.setenv('STK_RUNTIME_URL', client.url)
    monkeypatch.setenv('STK_RUNTIME_TOKEN', config['token'])
    workspace = asyncio.run(adapter.create_workspace('MCP'))['id']
    spec = {'workspace_id': workspace, 'argv': ['{python}', '-c', "print('MCP task')"]}
    task = asyncio.run(adapter.submit_task(spec, 'mcp-key'))
    assert asyncio.run(adapter.submit_task(spec, 'mcp-key'))['id'] == task['id']
    assert finish(client, supervisor, task['id'])['state'] == 'succeeded'
    assert asyncio.run(adapter.get_task_logs(task['id']))['text'] == 'MCP task\n'
    result = CliRunner().invoke(cli, ['jobs', 'show', task['id']])
    assert result.exit_code == 0, result.output
    assert task['id'] in result.output and 'succeeded' in result.output
    registered = {tool.name for tool in asyncio.run(adapter.mcp.list_tools())}
    assert {'submit_task', 'cancel_task', 'get_task_logs', 'download_artifact'} <= registered
