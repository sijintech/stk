from copy import deepcopy
from uuid import UUID

import pytest

from suan.federation.coordinator import FederationCoordinator, CoordinatorError
from suan.federation.protocol import RESULT_FORMAT
from test_federation_protocol import manifest, spec
from test_federation_training import model


class Client:
    def __init__(self,run):
        self.run_manifest=run; self.active=True; self.submissions=[]; self.records={}; self.uploads=[]; self.lost=False
    def run(self,run_id): return {"manifest":deepcopy(self.run_manifest),"active":self.active}
    def upload_model(self,run_id,number,raw): self.uploads.append(raw)
    def submit(self,node_id,message,action_id):
        self.submissions.append((node_id,deepcopy(message),action_id))
        result={"format":RESULT_FORMAT,**{k:message[k] for k in ("run_id","round","participant_id","grant_id")},
                "state":"running","task_id":"c"*32,"update_id":None,"update":None}
        self.records[action_id]={"state":"succeeded","result":result}
        if self.lost: raise OSError("reply lost after Hub commit")
        return {"state":"queued"}
    def action(self,action_id,**kwargs): return deepcopy(self.records[action_id])


def coordinator(tmp_path):
    run=manifest(); client=Client(run)
    value=FederationCoordinator(tmp_path / "private",client,None)
    value.create(run,spec(),model(spec()))
    value.prepare_round(run["run_id"])
    return value,client,run["run_id"]


def test_prepare_open_get_and_recover_never_start_training(tmp_path):
    value,client,run_id=coordinator(tmp_path)
    assert not client.submissions and not client.uploads
    reopened=FederationCoordinator(value.root,client,None)
    assert reopened.get(run_id,1)["state"]=="prepared"
    reopened.recover(run_id,1)
    assert not client.submissions and not client.uploads


def test_lost_submission_is_resolved_by_original_action_without_replay(tmp_path):
    value,client,run_id=coordinator(tmp_path); client.lost=True
    original=value.train(run_id,1)
    assert len(client.submissions)==3 and len(client.uploads)==1
    assert {x["phase"] for x in original["actions"]}=={"uncertain"}
    reopened=FederationCoordinator(value.root,client,None)
    restored=reopened.recover(run_id,1)
    assert {x["phase"] for x in restored["actions"]}=={"done"}
    reopened.train(run_id,1)
    assert len(client.submissions)==3 and len(client.uploads)==1
    assert [x["action_id"] for x in original["actions"]]==[x["action_id"] for x in restored["actions"]]


def test_status_uses_fresh_originals_after_completed_observations(tmp_path):
    value,client,run_id=coordinator(tmp_path)
    value.train(run_id,1); value.recover(run_id,1)
    value.observe(run_id,1); value.recover(run_id,1)
    value.observe(run_id,1)
    status=[x for x in client.submissions if x[1]["operation"]=="status"]
    assert len(status)==6 and len({x[2] for x in status})==6
    assert len([x for x in client.submissions if x[1]["operation"]=="train"])==3


def test_revoke_mapping_conflict_and_quorum_fail_before_side_effect(tmp_path):
    value,client,run_id=coordinator(tmp_path)
    client.active=False
    with pytest.raises(CoordinatorError): value.train(run_id,1)
    assert not client.uploads and not client.submissions
    client.active=True; client.run_manifest["coordinator_id"]="e"*64
    with pytest.raises(CoordinatorError): value.train(run_id,1)
    client.run_manifest["coordinator_id"]="a"*64
    with pytest.raises(ValueError): value.aggregate(run_id,1)
    assert value.get(run_id,1)["state"]=="prepared"


def test_existing_run_identity_never_adopts_changed_model(tmp_path):
    value,client,run_id=coordinator(tmp_path)
    changed=spec(); changed["learning_rate"]=.2
    run=manifest()
    from suan.federation.protocol import training_spec_sha256
    run["spec_sha256"]=training_spec_sha256(changed)
    with pytest.raises(CoordinatorError): value.create(run,changed,model(changed))
    assert value.get(run_id,1)["state"]=="prepared"


def test_initial_and_round_model_substitution_is_rejected_before_publication(tmp_path):
    run=manifest(); client=Client(run)
    value=FederationCoordinator(tmp_path / "private",client,None)
    value.create(run,spec(),model(spec()))
    from suan.federation import inputs
    path=value.root / run["run_id"]
    inputs.write_bytes(path / "initial.bin",model(spec(),weights=4),replace=True)
    with pytest.raises(CoordinatorError,match="retained model identity"):
        value.prepare_round(run["run_id"])
    inputs.write_bytes(path / "initial.bin",model(spec()),replace=True)
    value.prepare_round(run["run_id"])
    inputs.write_bytes(path / "1" / "model.bin",model(spec(),weights=4),replace=True)
    with pytest.raises(CoordinatorError,match="frozen identity"):
        value.train(run["run_id"],1)
    assert not client.uploads and not client.submissions


def test_explicit_collect_after_definitive_action_failure_can_recheck_node(tmp_path):
    value,client,run_id=coordinator(tmp_path)
    value.train(run_id,1); value.recover(run_id,1)
    current=value.collect(run_id,1)
    for item in current["actions"]:
        if item["message"]["operation"]=="collect":
            client.records[item["action_id"]]={"state":"failed","result":None}
    value.recover(run_id,1)
    value.collect(run_id,1)
    assert len([x for x in client.submissions if x[1]["operation"]=="collect"])==6


def test_interrupted_aggregation_is_not_replayed_after_reopen(tmp_path):
    import hashlib
    import struct
    from suan.federation.updates import encode_arrays
    value,client,run_id=coordinator(tmp_path)
    value.train(run_id,1); value.recover(run_id,1)
    current=value.collect(run_id,1)
    delta=encode_arrays([{"name":"weights","dtype":"f64","shape":[1,1],"data":struct.pack("<d",.1)},
                         {"name":"bias","dtype":"f64","shape":[1],"data":struct.pack("<d",.2)}],kind="delta")
    for i,item in enumerate(current["actions"]):
        if item["message"]["operation"]!="collect": continue
        request=item["message"]; result=client.records[item["action_id"]]["result"]
        result.update(state="delivered",update_id=str(UUID(int=100+i)),update={
            "format":"stk.federation-update/1", **{k:request[k] for k in ("run_id","round","participant_id","spec_sha256","dataset_sha256","grant_id")},
            "model_sha256":request["model"]["sha256"],"update_sha256":hashlib.sha256(delta).hexdigest(),
            "update_bytes":len(delta),"num_examples":3,"metrics":{"loss":.1},"masked":False})
    client.fetch_update=lambda *_:delta
    value.recover(run_id,1)
    class Aggregate:
        calls=0
        def aggregate(self,*args,**kwargs):
            self.calls+=1
            raise RuntimeError("private algorithm path must not escape")
    algorithm=Aggregate(); value.aggregator=algorithm
    with pytest.raises(CoordinatorError) as failure: value.aggregate(run_id,1)
    assert "private algorithm path" not in str(failure.value)
    assert value.get(run_id,1)["state"]=="aggregate_uncertain"
    reopened=FederationCoordinator(value.root,client,algorithm)
    with pytest.raises(CoordinatorError): reopened.aggregate(run_id,1)
    assert algorithm.calls==1
