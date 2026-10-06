"""The Token Plan key set in the app: precedence, private storage and never echoing the key.

Every key here is a made-up placeholder; no test sends a model request.
"""
import json
import os
import stat
import sys

import pytest

from suan.project import ProjectError, ProjectStore
from suan.project.aliyun import API_KEY_ENV, AliyunTokenPlanAdapter, TokenPlanCredentials, provider_info
from test_desktop_bridge import bridge_env, inproc  # noqa: F401

SESSION = "placeholder-session-key-0001"
SAVED = "placeholder-saved-key-0002"
ENVIRONMENT = "placeholder-environment-key-0003"


@pytest.fixture(autouse=True)
def no_environment_key(monkeypatch):
    monkeypatch.delenv(API_KEY_ENV, raising=False)


def test_session_saved_and_environment_keys_in_order(tmp_path, monkeypatch):
    credentials = TokenPlanCredentials(tmp_path / "state")
    assert credentials.info() == {"configured": False, "source": "", "can_remember": True}
    with pytest.raises(ProjectError, match="AI Assistant"):
        credentials.get()
    with pytest.raises(ProjectError) as invalid:
        credentials.set("short key!")
    assert "short" not in str(invalid.value)  # The rejected value is never echoed.
    assert credentials.set(SESSION) == {"configured": True, "source": "session", "can_remember": True}
    assert credentials.get() == SESSION and not (tmp_path / "state" / TokenPlanCredentials.FILE).exists()
    assert TokenPlanCredentials(tmp_path / "state").info()["configured"] is False  # Session keys are not kept.

    credentials.set(SAVED, remember=True)
    path = tmp_path / "state" / TokenPlanCredentials.FILE
    assert json.loads(path.read_text()) == {"format": 1, "key": SAVED}
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    reopened = TokenPlanCredentials(tmp_path / "state")
    assert reopened.info()["source"] == "saved" and reopened.get() == SAVED
    assert SAVED not in repr(reopened) and SAVED not in json.dumps(provider_info(reopened))

    monkeypatch.setenv(API_KEY_ENV, ENVIRONMENT)  # The environment always wins.
    assert reopened.info()["source"] == "environment" and reopened.get() == ENVIRONMENT
    monkeypatch.delenv(API_KEY_ENV)

    credentials.set(SESSION, remember=False)  # Choosing not to remember forgets the saved key.
    assert not path.exists() and credentials.info()["source"] == "session"
    assert credentials.clear() == {"configured": False, "source": "", "can_remember": True}
    assert not TokenPlanCredentials(None).info()["can_remember"]
    with pytest.raises(ProjectError, match="private state folder"):
        TokenPlanCredentials(None).set(SAVED, remember=True)


def test_adapter_binds_the_injected_credentials_only(tmp_path):
    credentials = TokenPlanCredentials(tmp_path)
    adapter, environment_only = AliyunTokenPlanAdapter(credentials), AliyunTokenPlanAdapter()
    credentials.set(SESSION)
    assert adapter._credentials.get() == SESSION
    with pytest.raises(ProjectError):
        environment_only._credentials.get()  # Another service's key never leaks into the default.


def test_bridge_sets_and_clears_the_key_without_returning_it(inproc, tmp_path):
    harness = inproc()
    store = ProjectStore.create(tmp_path / "p", "Keys")
    handle = harness.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    assert harness.call("project.requests.provider", {"handle": handle})["provider"]["configured"] is False
    error = harness.error("ai.credentials.set", {"key": "no good"})
    assert error["code"] == "invalid_params" and "no good" not in json.dumps(error)
    result = harness.call("ai.credentials.set", {"key": SAVED, "remember": True})
    assert result["provider"]["configured"] is True and result["provider"]["key_source"] == "saved"
    assert SAVED not in json.dumps(result)
    provider = harness.call("project.requests.provider", {"handle": handle})["provider"]
    assert provider["key_source"] == "saved" and SAVED not in json.dumps(provider)
    assert harness.call("ai.credentials.clear", {})["provider"]["configured"] is False
    assert not list((tmp_path / "bridge").glob("token-plan-key*"))
    assert not harness.violations
    harness.close()
