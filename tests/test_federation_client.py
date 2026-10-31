from copy import deepcopy
import json
from uuid import UUID

import pytest

from suan.federation.client import FederationClient, FederationTransportError
from test_federation_protocol import message, receipt
from test_federation_training import model, spec


@pytest.mark.parametrize("url",["http://remote.invalid","https://example.invalid/path","https://u:p@example.invalid",
                                "https://example.invalid?key=bad","https://example.invalid#bad"])
def test_client_rejects_unpaired_origin_forms(url):
    with pytest.raises(ValueError): FederationClient(url,"abcdefghijklmnopqrstu")


def test_download_checks_size_sha_and_bounded_response_before_use():
    raw=model(spec())
    from suan.federation.updates import decode_arrays
    msg=message(); msg["model"]={"sha256":decode_arrays(raw)["sha256"],"bytes":len(raw)}
    calls=[]
    def transport(method,path,body,headers,maximum):
        calls.append((method,path,maximum))
        return 200,raw
    client=FederationClient("http://127.0.0.1","abcdefghijklmnopqrstu",transport=transport)
    assert client.fetch_model(msg)==raw
    msg["model"]["sha256"]="f"*64
    with pytest.raises(FederationTransportError): client.fetch_model(msg)
    msg["model"]["bytes"]-=1
    with pytest.raises(FederationTransportError): client.fetch_model(msg)
    assert all(x[0]=="GET" for x in calls)


def test_upload_rejects_boolean_or_wrong_original_ack_and_never_retries():
    raw=model(spec()); calls=[]
    def transport(method,path,body,headers,maximum):
        from suan.federation.updates import decode_arrays
        calls.append(method)
        return 200,json.dumps({"run_id":str(UUID(int=1)),"round":True,"kind":"model","participant_id":"",
                               "update_id":"","sha256":decode_arrays(raw)["sha256"],"bytes":len(raw)}).encode()
    client=FederationClient("https://example.invalid","abcdefghijklmnopqrstu",transport=transport)
    with pytest.raises(FederationTransportError): client.upload_model(str(UUID(int=1)),1,raw)
    assert calls==["PUT"]


def test_transport_error_does_not_echo_headers_or_retry():
    calls=[]
    def transport(*args):
        calls.append(1)
        raise OSError("Bearer abcdefghijklmnopqrstu /private/file")
    client=FederationClient("https://example.invalid","abcdefghijklmnopqrstu",transport=transport)
    with pytest.raises(FederationTransportError) as caught: client.run(str(UUID(int=1)))
    assert "abcdefghijklmnopqrstu" not in str(caught.value) and "/private" not in str(caught.value)
    assert calls==[1]


def test_action_response_binds_original_and_closed_node_receipt():
    msg=message("status"); result=receipt(); action_id="c"*32; node_id="d"*32
    request={"id":action_id,"node_id":node_id,"kind":"fl.message","payload":msg}
    response={"id":action_id,"request":request,"state":"succeeded","result":result}
    client=FederationClient("http://localhost","abcdefghijklmnopqrstu",
                            transport=lambda *_:(200,json.dumps(response).encode()))
    assert client.action(action_id,node_id=node_id,message=msg)["result"]==result
    response["request"]=deepcopy(request); response["request"]["node_id"]="e"*32
    with pytest.raises(FederationTransportError): client.action(action_id,node_id=node_id,message=msg)


def test_private_runtime_guard_precedes_generic_cache_hits_and_graph_binding(tmp_path):
    from suan.control.agent import NodeAgent
    from suan.runtime.common import atomic_json
    class Service:
        def private_identities(self): return {"tasks":{"a"*32},"workspaces":{"b"*32}}
    agent=NodeAgent(None,tmp_path,federation=Service())
    action={"id":"c"*32,"kind":"task.logs","payload":{"task_id":"a"*32}}
    atomic_json(tmp_path/(action["id"]+".json"),{"request":action,"result":{"text":"old private result"}})
    with pytest.raises(ValueError,match="private federation"): agent.execute(action)
    with pytest.raises(ValueError,match="private federation"):
        agent._operation("d"*32,"graph.evaluate",{"bindings":{"run":{"task_id":"a"*32}}})
    with pytest.raises(ValueError,match="private federation"):
        agent.read("workspace.files",{"workspace_id":"b"*32})


def test_snapshot_filters_private_runtime_objects(tmp_path):
    from suan.control.agent import NodeAgent
    class Runtime:
        def tasks(self): return [{"id":i*32,"spec":{"name":"task","workspace_id":i*32}} for i in "ab"]
        def workspaces(self): return [{"id":i*32} for i in "ab"]
        def health(self): return {"ok":True}
    class Service:
        def private_identities(self): return {"tasks":{"a"*32},"workspaces":{"a"*32}}
    snapshot=NodeAgent(Runtime(),tmp_path,federation=Service()).snapshot()
    assert [x["id"] for x in snapshot["tasks"]]==["b"*32]
    assert snapshot["workspaces"]==[{"id":"b"*32}]


def test_large_history_snapshot_reads_each_private_reservation_once(tmp_path,monkeypatch):
    from suan.federation import inputs
    from suan.federation.node import NodeFederationService
    from suan.control.agent import NodeAgent
    from suan.materials.jobs import private_directory
    root=tmp_path / "private"
    for i in range(100):
        directory=private_directory(root / "jobs" / f"{i:064x}")
        inputs.write_json(directory / "state.json",{"task_id":None,"workspace_id":f"{i:032x}"})
    class Runtime:
        def tasks(self): return [{"id":f"{200+i:032x}","spec":{"name":"task","workspace_id":f"{300+i:032x}"}} for i in range(50)] + [
            {"id":"e"*32,"spec":{"name":"lost response","workspace_id":f"{1:032x}"}}]
        def workspaces(self): return [{"id":f"{300+i:032x}"} for i in range(50)]
        def health(self): return {"ok":True}
        def task(self,*_): pytest.fail("Snapshot should reuse Runtime list rows without per-task HTTP reads")
    runtime=Runtime(); service=NodeFederationService(runtime,root,None)
    original=inputs.read_json; calls=[]
    def counted(path): calls.append(path); return original(path)
    monkeypatch.setattr(inputs,"read_json",counted)
    snapshot=NodeAgent(runtime,tmp_path / "cache",federation=service).snapshot()
    assert len(calls)==100
    assert len(snapshot["tasks"])==50 and len(snapshot["workspaces"])==50
    assert "e"*32 not in [row["id"] for row in snapshot["tasks"]]


def test_unknown_task_reservation_created_during_runtime_lookup_is_denied(tmp_path):
    from suan.control.agent import NodeAgent
    class Service:
        tasks=set(); workspaces={"a"*32}
        def private_identities(self): return {"tasks":set(self.tasks),"workspaces":set(self.workspaces)}
    service=Service()
    class Runtime:
        lookups=0
        def task(self,task_id):
            self.lookups+=1
            service.tasks.add(task_id); service.workspaces.add("b"*32)
            return {"id":task_id,"spec":{"workspace_id":"b"*32}}
        def cancel(self,*_): pytest.fail("Ordinary cancel crossed a newly published private reservation")
    runtime=Runtime(); agent=NodeAgent(runtime,tmp_path,federation=service)
    with pytest.raises(ValueError,match="private federation"):
        agent.execute({"id":"c"*32,"kind":"task.cancel","payload":{"task_id":"d"*32}})
    assert runtime.lookups==1
