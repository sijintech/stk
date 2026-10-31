"""Opt-in actual TCP/WSS Hub, three outbound agents and independent Linux Runtimes.

All datasets are synthetic and local. This verifies loopback STK transport, not
cross-site NAT/TURN, desktop consent UI or scientific/material validity.
"""
import asyncio
from contextlib import ExitStack, contextmanager
import os
from pathlib import Path
import socket
import struct
import sys
import threading
import time
from uuid import UUID

import pytest

from suan.federation.client import FederationClient
from suan.federation.coordinator import FederationCoordinator, CoordinatorError
from suan.federation.flower import FlowerAggregator
from suan.federation.node import NodeFederationService
from suan.federation.protocol import training_spec_sha256
from suan.federation.updates import decode_arrays
from test_federation_training import model, spec


def until(function, predicate, timeout=60):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=function()
        if predicate(value): return value
        time.sleep(.04)
    raise AssertionError("Federation operation did not reach its expected state before the test deadline")


@contextmanager
def runtime_node(root):
    from suan.runtime.common import init_config
    from suan.runtime.server import RuntimeHTTPServer
    from suan.runtime.client import RuntimeClient
    from suan.runtime.supervisor import Supervisor
    config=init_config(root / "runtime",root / "public-workspaces",port=0)
    config["scheduler_interval"]=0
    server=RuntimeHTTPServer(config)
    supervisor=Supervisor(config)
    stop=threading.Event()
    api=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.02},daemon=True)
    def tick():
        while not stop.is_set():
            supervisor.tick(); stop.wait(.03)
    scheduler=threading.Thread(target=tick,daemon=True)
    api.start(); scheduler.start()
    client=RuntimeClient(f"http://127.0.0.1:{server.server_port}",config["token"])
    try:
        yield client,config
    finally:
        for task in client.tasks():
            if task["state"] not in {"succeeded","failed","cancelled","unknown"}: client.cancel(task["id"])
        until(client.tasks,lambda rows:all(t["state"] in {"succeeded","failed","cancelled","unknown"} for t in rows),15)
        stop.set(); scheduler.join(5)
        server.shutdown(); server.server_close(); api.join(5)
        assert not api.is_alive() and not scheduler.is_alive()


@contextmanager
def hub_server(root):
    import uvicorn
    from suan.control.app import create_app
    listener=socket.socket()
    listener.bind(("127.0.0.1",0)); listener.listen()
    origin=f"http://127.0.0.1:{listener.getsockname()[1]}"
    app=create_app(root,"abcdefghijklmnopqrstuvwx")
    server=uvicorn.Server(uvicorn.Config(app,log_level="critical",access_log=False,lifespan="off"))
    thread=threading.Thread(target=server.run,kwargs={"sockets":[listener]},daemon=True)
    thread.start()
    until(lambda:server.started,bool,15)
    try: yield app,origin
    finally:
        server.should_exit=True; thread.join(15); listener.close()
        assert not thread.is_alive()


@contextmanager
def outbound(agent,origin,token):
    stop=threading.Event(); errors=[]
    async def main():
        runner=asyncio.create_task(agent.run(origin,token))
        try:
            while not stop.is_set(): await asyncio.sleep(.04)
        finally:
            runner.cancel(); await asyncio.gather(runner,return_exceptions=True)
    def run():
        try: asyncio.run(main())
        except Exception as exc: errors.append(type(exc).__name__)
    thread=threading.Thread(target=run,daemon=True); thread.start()
    try: yield
    finally:
        stop.set(); thread.join(15)
        assert not thread.is_alive() and not errors


@pytest.mark.parametrize("strategy",["fedavg","fedprox"])
def test_three_outbound_nodes_two_real_rounds_with_original_receipts(tmp_path,strategy):
    python=os.environ.get("STK_FEDERATION_TEST_PYTHON")
    if not python: pytest.skip("explicit installed Flower interpreter required")
    if sys.platform!="linux": pytest.skip("Linux Runtime acceptance")
    pytest.importorskip("uvicorn")
    import httpx
    from suan.control.agent import NodeAgent
    settings=spec("f64",strategy)
    run_id=str(UUID(int=100))
    owner={"Authorization":"Bearer abcdefghijklmnopqrstuvwx"}
    with ExitStack() as stack:
        app,origin=stack.enter_context(hub_server(tmp_path / "hub"))
        http=stack.enter_context(httpx.Client(base_url=origin,trust_env=False,follow_redirects=False,timeout=15))
        def pair(role):
            response=http.post("/api/v1/pairings",json={"role":role},headers=owner)
            assert response.status_code==200
            response=http.post("/api/v1/pairings/claim",json={"code":response.json()["code"],"name":"Synthetic test node"})
            assert response.status_code==200
            return response.json()
        coordinator=pair("client")
        participants=[]; services=[]; runtimes=[]; samples=[]
        for i in range(1,4):
            node=pair("node")
            runtime,config=stack.enter_context(runtime_node(tmp_path / ("node"+str(i))))
            service=NodeFederationService(runtime,tmp_path / ("private"+str(i)),python,
                                          workspace_root=config["workspace_root"])
            xs=[float(j)-1 for j in range(3+i)]; ys=[2*x-1 for x in xs]
            dataset=service.register_dataset(str(UUID(int=200+i)),[[x] for x in xs],[[y] for y in ys])
            grant=service.approve(settings,dataset["dataset_id"],run_id=run_id,coordinator_id="a"*64,
                                  participant_id=str(i)*64,max_rounds=2)
            participants.append({"node_id":node["device_id"],"participant_id":str(i)*64,
                                 "grant_id":grant.grant_id,"dataset_sha256":dataset["dataset_sha256"]})
            agent=NodeAgent(runtime,tmp_path / ("cache"+str(i)),federation=service)
            stack.enter_context(outbound(agent,origin,node["token"]))
            services.append(service); runtimes.append(runtime); samples.append((xs,ys))
        manifest={"format":"stk.federation-run/1","run_id":run_id,
                  "coordinator_device_id":coordinator["device_id"],"coordinator_id":"a"*64,
                  "spec_sha256":training_spec_sha256(settings),"participants":participants,"max_rounds":2}
        assert http.post("/api/v1/federation/runs",json=manifest,headers=owner).status_code==200
        client=FederationClient(origin,coordinator["token"])
        root=tmp_path / "coordinator"
        orchestration=FederationCoordinator(root,client,FlowerAggregator(python))
        orchestration.create(manifest,settings,model(settings))
        reference=(.25,-.2)
        for number in (1,2):
            assert orchestration.prepare_round(run_id)["round"]==number
            orchestration.train(run_id,number)
            until(lambda:orchestration.recover(run_id,number),lambda r:all(a["phase"]=="done" for a in r["actions"]))
            # A reopened coordinator and repeated explicit train reuse all original task identities.
            orchestration=FederationCoordinator(root,client,FlowerAggregator(python))
            orchestration.train(run_id,number)
            assert all(len(runtime.tasks())==number for runtime in runtimes)
            until(lambda:[runtime.tasks() for runtime in runtimes],
                  lambda groups:all(all(t["state"]=="succeeded" for t in group) for group in groups))
            orchestration.observe(run_id,number)
            until(lambda:orchestration.recover(run_id,number),lambda r:all(a["phase"]=="done" for a in r["actions"]))
            orchestration.collect(run_id,number)
            delivered=until(lambda:orchestration.recover(run_id,number),
                lambda r:all(a["phase"]=="done" for a in r["actions"]) and
                    sum(a["message"]["operation"]=="collect" and a["result"]["state"]=="delivered" for a in r["actions"])==3)
            action_count=len(delivered["actions"])
            assert len(orchestration.collect(run_id,number)["actions"])==action_count
            orchestration.aggregate(run_id,number)
            candidate=decode_arrays((root / run_id / str(number) / "candidate.bin").read_bytes())
            actual=tuple(struct.unpack("<d",a["data"])[0] for a in candidate["arrays"])
            fitted=[]
            for xs,ys in samples:
                w0,b0=reference; w,b=w0,b0
                for _ in range(settings["steps"]):
                    errors=[w*x+b-y for x,y in zip(xs,ys)]
                    dw=2*sum(e*x for e,x in zip(errors,xs))/len(xs)+settings["proximal_mu"]*(w-w0)
                    db=2*sum(errors)/len(xs)+settings["proximal_mu"]*(b-b0)
                    w,b=w-settings["learning_rate"]*dw,b-settings["learning_rate"]*db
                fitted.append((len(xs),w,b))
            reference=tuple(sum(row[0]*row[i] for row in fitted)/sum(row[0] for row in fitted) for i in (1,2))
            assert actual==pytest.approx(reference,rel=1e-13,abs=1e-13)
        for service,runtime in zip(services,runtimes):
            assert len(service.consent.list_updates()["updates"])==2
            assert all(x.state=="delivered" for x in service.consent.list_updates()["updates"])
            assert len(list((service.root / "jobs").glob("*/attempt.json")))==2
            snapshot=NodeAgent(runtime,tmp_path / "snapshot-cache",federation=service).snapshot()
            assert snapshot["tasks"]==[] and snapshot["workspaces"]==[]
        with pytest.raises(CoordinatorError): orchestration.prepare_round(run_id)
