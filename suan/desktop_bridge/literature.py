"""Desktop-only local literature admission, observation and owned workers.

No corpus, parser or encoder is opened by construction. Completed job metadata is
not authorization to reveal old source text: result reads recheck exact citations.
The service journal is separate from Library's original operation receipts.
"""
from concurrent.futures import ThreadPoolExecutor
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import stat
import struct
import sys
import threading
import time
import zlib
from uuid import UUID, uuid4

from suan.literature._io import LiteratureError
from suan.literature.pdf import canonical, checksum
from suan.literature.store import Library, _authorization, _text
from suan.materials.jobs import Lease, Locked
from .protocol import BridgeError, encode_message


def WorkerProcess(*args, **kwargs):
    # Shared pure DTO checks also run in the provisioned parser/E5 interpreters,
    # which intentionally do not acquire the parent bridge's psutil dependency.
    from .worker_process import WorkerProcess as Process
    return Process(*args, **kwargs)

METHODS = frozenset({'info', 'corpora.list', 'corpora.info', 'corpora.create', 'encoder.info', 'encoder.review',
    'encoder.select', 'import.review', 'import.commit', 'import.recover', 'versions.list',
    'versions.revoke', 'index.start', 'dense.build', 'search', 'citations.resolve', 'pages.render',
    'operations.get', 'operations.list', 'operations.result'})
READS = frozenset({'info', 'corpora.list', 'corpora.info', 'encoder.info', 'versions.list',
                  'operations.get', 'operations.list', 'operations.result'})
SYNC = frozenset({'versions.revoke'})
MODEL = frozenset({'dense.build', 'search'})
MAX_OPERATIONS, MAX_SERVICE_BYTES = 4096, 64 * 1024**2
MAX_METADATA, MAX_RESULT = 128 * 1024, 8 * 1024**2
MAX_DENSE_MANIFEST=128*1024**2
_CORPUS = re.compile(r'local_[0-9a-f]{32}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_STATE_KEYS = {'format', 'service_id', 'generation', 'encoder_generation', 'corpora', 'encoder'}
_RECORD_KEYS = {'format', 'operation_id', 'action', 'request', 'request_sha256', 'frozen', 'state', 'result_sha256', 'error'}
_JOB_ERRORS=frozenset({'unavailable','authorization_revoked','corpus_changed','encoder_changed','dense_stale','source_changed',
    'encoder_unavailable','parser_unavailable','invalid_data','invalid_path','invalid_file','citation_mismatch',
    'database_mismatch','operation_conflict','embedding_budget','page_budget'})


def _keys(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()): _bad('unavailable')


def _exact(left,right):
    return canonical(left)==canonical(right)


def _bounded(value, maximum=MAX_RESULT):
    """Bound containers before recursive JSON encoding, including local files."""
    pending=[(value,0)]; nodes=0
    while pending:
        item,depth=pending.pop(); nodes+=1
        if depth>32 or nodes>500000: _bad()
        if type(item) is dict:
            if len(item)>65536 or any(type(k) is not str for k in item): _bad()
            pending.extend((x,depth+1) for pair in item.items() for x in pair)
        elif type(item) is list:
            if len(item)>65536: _bad()
            pending.extend((x,depth+1) for x in item)
        elif type(item) is str:
            if len(item)>maximum: _bad()
            item.encode('utf-8')
        elif type(item) is float:
            if not math.isfinite(item): _bad()
        elif type(item) is int:
            if not -(2**63)<=item<2**63: _bad()
        elif item is not None and type(item) is not bool: _bad()
    if len(canonical(value))>maximum: _bad()


def _citation(value):
    from suan.literature.collection import _inner
    _keys(value,'format corpus_id database_id corpus_generation dense_generation inner evidence_sha256')
    if value['format']!='stk.literature-collection-citation/1' or not _CORPUS.fullmatch(value['corpus_id']): _bad()
    _uuid(value['database_id']);_integer(value['corpus_generation']);_sha(value['dense_generation']);_sha(value['evidence_sha256'])
    _inner(value['inner'])
    base=value['inner'].get('base',value['inner'])
    if not 0<=base['page_index']<256 or not base['start']<base['end']: _bad()
    if value['inner'].get('base') is not None and not value['inner']['start']<value['inner']['end']: _bad()
    if checksum({k:v for k,v in value.items() if k!='evidence_sha256'})!=value['evidence_sha256']: _bad()


def _encoder_review(value, *, authority=False):
    from suan.literature.encoder_profiles import E5_RECIPE, profile_for_recipe
    _keys(value,'format assets assets_sha256 python identity fingerprint')
    if value['format']!='stk.literature-encoder-review/1': _bad()
    _path(value['assets']);_path(value['python']);_sha(value['assets_sha256']);_sha(value['fingerprint'])
    identity=value['identity'];_keys(identity,'assets_sha256 recipe runtime')
    if identity['assets_sha256']!=value['assets_sha256'] or checksum(identity)!=value['fingerprint']: _bad()
    recipe=identity['recipe'];_keys(recipe,' '.join(E5_RECIPE))
    for key in ('dimensions','tokens','threads'):
        if not 1<=_integer(recipe[key],65536):_bad()
    for key in set(E5_RECIPE)-{'dimensions','tokens','threads'}:
        if key=='passage_prefix' and recipe[key]=='':continue
        _text(recipe[key],256)
    profile=profile_for_recipe(recipe) if authority else None
    runtime=identity['runtime'];_keys(runtime,'python platform machine packages worker_sha256')
    for key in ('python','platform','machine'): _text(runtime[key],1024)
    _sha(runtime['worker_sha256'])
    packages=runtime['packages']
    if type(packages) is not dict or not 1<=len(packages)<=512: _bad()
    for name,item in packages.items():
        _text(name,128);_keys(item,'version record_sha256');_text(item['version'],128)
        if item['record_sha256'] is not None:_sha(item['record_sha256'])
    if authority and any(packages.get(k,{}).get('version')!=v for k,v in profile['core'].items()): _bad()


def _import_review(value):
    _keys(value,'format corpus_id database_id corpus_generation source source_sha256 source_bytes document_id title authorization')
    if value['format']!='stk.literature-import-review/1' or not _CORPUS.fullmatch(value['corpus_id']): _bad()
    _uuid(value['database_id']);_integer(value['corpus_generation']);_path(value['source']);_sha(value['source_sha256'])
    if not 5<=_integer(value['source_bytes'],32*1024**2): _bad()
    _uuid(value['document_id']);_text(value['title'],256);_authorization(value['authorization'])


def _bad(code='invalid_params'):
    raise BridgeError(code, 'Local literature action is unavailable or its evidence changed', retryable=False)


def _uuid(value):
    try:
        if type(value) is not str or str(UUID(value)) != value: _bad()
    except (ValueError, AttributeError): _bad()
    return value


def _sha(value):
    if type(value) is not str or not _SHA.fullmatch(value): _bad()
    return value


def _integer(value, maximum=2**63-1):
    if type(value) is not int or not 0 <= value <= maximum: _bad()
    return value


def _path(value):
    if type(value) is not str or '\0' in value or len(value.encode('utf-8')) > 4096: _bad()
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts: _bad()
    return value


def _directory(path, create=False):
    for part in (*reversed(path.parents), path):
        try: info = part.lstat()
        except FileNotFoundError:
            if not create: raise
            part.mkdir(mode=0o700); info = part.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            _bad('unavailable')
    if os.name != 'nt' and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077): _bad('unavailable')


def _ordinary(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, 'st_file_attributes', 0) & 0x400
            or os.name != 'nt' and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077)):
        _bad('unavailable')
    return info


def _decode(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result: _bad('unavailable')
            result[k] = v
        return result
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: _bad('unavailable'))


def _read(path, maximum):
    before = _ordinary(path)
    if before.st_size > maximum: _bad('unavailable')
    flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0)|getattr(os,'O_BINARY',0)
    with os.fdopen(os.open(path,flags),'rb') as stream:
        initial = os.fstat(stream.fileno()); data = stream.read(maximum+1); after = os.fstat(stream.fileno())
    named = _ordinary(path)
    cross = lambda s:(s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    if (len(data) > maximum or cross(before) != cross(initial) or cross(after) != cross(named)
            or cross(initial) != cross(after) or initial.st_ctime_ns != after.st_ctime_ns
            or before.st_ctime_ns != named.st_ctime_ns): _bad('unavailable')
    envelope = _decode(data)
    _bounded(envelope,maximum)
    if type(envelope) is not dict or set(envelope) != {'body', 'sha256'} or checksum(envelope['body']) != envelope['sha256']:
        _bad('unavailable')
    return envelope['body']


def _write(path, value, maximum, *, create=False):
    _bounded(value,maximum-128)
    data = canonical({'body': value, 'sha256': checksum(value)})
    if len(data) > maximum: _bad('unavailable')
    temporary = path.parent / ('.' + path.name + '.' + uuid4().hex + '.tmp')
    try:
        fd = os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        if create: os.link(temporary, path)
        else:
            _ordinary(path)
            os.replace(temporary, path)
    finally:
        try: temporary.unlink()
        except FileNotFoundError: pass


def child_environment():
    """Parent-selected allowlist: no ambient model, Hub or HF credentials."""
    result = {key: os.environ[key] for key in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG', 'LC_ALL', 'TZ'}
              if key in os.environ}
    result.update(STK_TOKEN_PLAN_API_KEY='', PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1',
                  TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1', TOKENIZERS_PARALLELISM='false')
    return result


def request_sha256(action, params):
    return hashlib.sha256(json.dumps({'action': action, 'params': params}, ensure_ascii=False,
        sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class LiteratureService:
    def __init__(self, state_dir, *, python=None, parser_python=None, encoder_python=None):
        self.parent = Path(state_dir).absolute()
        self.root = self.parent / 'literature'
        self.python = _path(str(python or sys.executable))
        self.parser_python = _path(str(parser_python or self.python))
        self.encoder_python = _path(str(encoder_python or self.python))
        self._lock = threading.RLock()
        self._closed, self._lease, self._pool, self._identity = False, None, None, None
        self._running, self._children = {}, {}

    def _state(self, *, create=False):
        if not self.root.exists() and not self.root.is_symlink():
            if self._identity is not None: _bad('unavailable')
            if not create: return None
            _directory(self.root, True)
            state = {'format': 'stk.desktop-literature-state/1', 'service_id': str(uuid4()),
                     'generation': 0, 'encoder_generation': 0, 'corpora': {}, 'encoder': None}
            _write(self.root/'state.json', state, MAX_METADATA, create=True)
        _directory(self.root)
        for child in self.root.iterdir():
            if child.name not in {'state.json','operations','results','corpora'}:_bad('unavailable')
        state = _read(self.root/'state.json', MAX_METADATA)
        if type(state) is not dict or set(state) != _STATE_KEYS or state['format'] != 'stk.desktop-literature-state/1': _bad('unavailable')
        _uuid(state['service_id']); _integer(state['generation']); _integer(state['encoder_generation'])
        if self._identity is not None and self._identity != state['service_id']: _bad('unavailable')
        self._identity = state['service_id']
        if type(state['corpora']) is not dict or len(state['corpora']) > 8: _bad('unavailable')
        for corpus, item in state['corpora'].items():
            if (not _CORPUS.fullmatch(corpus) or type(item) is not dict
                    or set(item) != {'name', 'database_id', 'create_operation'}): _bad('unavailable')
            _text(item['name'], 256); _uuid(item['create_operation'])
            _uuid(item['database_id'])
            if corpus!='local_'+UUID(item['create_operation']).hex: _bad('unavailable')
        if state['encoder'] is not None:
            item = state['encoder']
            if type(item) is not dict or set(item) != {'assets', 'assets_sha256', 'python', 'fingerprint', 'review_id'}: _bad('unavailable')
            _path(item['assets']); _path(item['python']); _sha(item['assets_sha256']); _sha(item['fingerprint']); _uuid(item['review_id'])
        return state

    def _own(self):
        if self._closed: _bad('shutting_down')
        if self._lease is None:
            _directory(self.parent, True)
            self._lease = Lease(self.parent/'literature-service.lock', timeout=0)
        return self._state(create=True)

    def _save_state(self, state):
        state['generation'] += 1
        _write(self.root/'state.json', state, MAX_METADATA)

    def _record_path(self, identity):
        return self.root/'operations'/(_uuid(identity)+'.json')

    def _record(self, identity):
        path = self._record_path(identity)
        if not path.exists() and not path.is_symlink(): return None
        _directory(path.parent)
        record = _read(path, MAX_METADATA)
        if (type(record) is not dict or set(record) != _RECORD_KEYS
                or record['format'] != 'stk.desktop-literature-operation/1'
                or record['operation_id'] != identity or record['action'] not in METHODS-READS
                or record['state'] not in {'running', 'completed', 'uncertain'}
                or record['request_sha256'] != request_sha256(record['action'], record['request'])): _bad('unavailable')
        if record['result_sha256'] is not None: _sha(record['result_sha256'])
        if not _exact(self._validate(record['action'],record['request'],authority=False),record['request']): _bad('unavailable')
        self._validate_frozen(record['action'],record['request'],record['frozen'])
        if record['state']=='completed':
            if record['result_sha256'] is None or record['error'] is not None:_bad('unavailable')
        elif record['result_sha256'] is not None: _bad('unavailable')
        if record['error'] is not None:
            _keys(record['error'],'code message');_text(record['error']['code'],64);_text(record['error']['message'],128)
            if record['error']['code'] not in _JOB_ERRORS:_bad('unavailable')
        if (record['state']=='uncertain')!=(record['error'] is not None):_bad('unavailable')
        return record

    def _public(self, record):
        if record is None: return None
        state = record['state']
        if state == 'running' and record['operation_id'] not in self._running: state = 'uncertain'
        return {key: record[key] for key in ('operation_id', 'action', 'request_sha256', 'result_sha256', 'error')} | {'state': state}

    def _library(self, state, corpus):
        if type(corpus) is not str or corpus not in state['corpora']: _bad('not_found')
        item = state['corpora'][corpus]
        if item['database_id'] is None: _bad('unavailable')
        library = Library(self.root/'corpora'/corpus)
        if library.info()['database_id'] != item['database_id']: _bad('unavailable')
        return library

    def _result(self, identity, *, internal=False):
        record = self._record(identity)
        if record is None: _bad('not_found')
        if record['state'] != 'completed' or record['result_sha256'] is None: _bad('unavailable')
        result = _read(self.root/'results'/(identity+'.json'), MAX_RESULT)
        if checksum(result) != record['result_sha256']: _bad('unavailable')
        self._check_result(record,result,publish=not internal)
        return result

    def _validate(self, action, params, *, authority=True):
        if action not in METHODS or type(params) is not dict: _bad()
        _bounded(params,32768)
        contracts = {
            'info': (set(),set()), 'corpora.list': (set(),set()), 'encoder.info': (set(),set()),
            'corpora.info': ({'corpus_id'},set()),
            'corpora.create': ({'operation_id','name'},set()),
            'encoder.review': ({'operation_id','assets'}, {'python'}),
            'encoder.select': ({'operation_id','review_id','review_sha256','expected_generation'},set()),
            'import.review': ({'operation_id','corpus_id','source','document_id','title','authorization'},set()),
            'import.commit': ({'operation_id','review_id','review_sha256'},set()),
            'import.recover': ({'operation_id','corpus_id','original_operation_id'},set()),
            'versions.list': ({'corpus_id'}, {'offset','limit'}),
            'versions.revoke': ({'operation_id','corpus_id','version_id'},set()),
            'index.start': ({'operation_id','corpus_id','version_id'},set()),
            'dense.build': ({'operation_id','corpus_id','expected_generation','encoder_generation'}, {'timeout'}),
            'search': ({'operation_id','scopes','query','encoder_generation'}, {'limit'}),
            'citations.resolve': ({'operation_id','scopes','citation'},set()),
            'pages.render': ({'operation_id','scopes','citation'}, {'long_edge'}),
            'operations.get': ({'operation_id'},set()),
            'operations.result': ({'operation_id','expected_request_sha256'},set()),
            'operations.list': (set(),{'offset','limit'}),
        }
        required, optional = contracts[action]
        if not required.issubset(params) or set(params)-required-optional: _bad()
        for key in ('operation_id','review_id','document_id','version_id','original_operation_id'):
            if key in params: _uuid(params[key])
        for key in ('review_sha256','expected_request_sha256'):
            if key in params: _sha(params[key])
        for key in ('expected_generation','encoder_generation','offset'):
            if key in params: _integer(params[key])
        if 'limit' in params and (type(params['limit']) is not int or not 1 <= params['limit'] <= (20 if action=='search' else 50)): _bad()
        if 'long_edge' in params and (type(params['long_edge']) is not int or not 256 <= params['long_edge'] <= 2048): _bad()
        if 'timeout' in params and (type(params['timeout']) is not int or not 1<=params['timeout']<=3600):_bad()
        if 'corpus_id' in params and (type(params['corpus_id']) is not str or not _CORPUS.fullmatch(params['corpus_id'])): _bad()
        for key in ('name','title','query'):
            if key in params: _text(params[key],256)
        for key in ('assets','python','source'):
            if key in params: _path(params[key])
        if authority and action=='encoder.review' and 'python' in params and params['python']!=self.encoder_python: _bad()
        if 'authorization' in params: _authorization(params['authorization'])
        if 'scopes' in params:
            scopes = params['scopes']
            if (type(scopes) is not list or not 1 <= len(scopes) <= 8 or any(type(c) is not str or not _CORPUS.fullmatch(c) for c in scopes)
                    or len(set(scopes)) != len(scopes)): _bad()
        if 'citation' in params:
            citation=params['citation']
            if type(citation) is not dict or len(canonical(citation)) > 4096: _bad()
            _citation(citation)
            if citation['corpus_id'] not in params['scopes']: _bad()
        return _decode(canonical(params))

    def call(self, action, params):
        try:
            # Historical admission belongs to the original request, even after
            # trusted interpreter configuration changes. It confers no new
            # dispatch authority; only a new identity checks current settings.
            params = self._validate(action, params, authority=False)
            with self._lock:
                if self._closed: _bad('shutting_down')
                if action in READS: return self._read_call(action,params)
                identity = params['operation_id']; previous = self._record(identity)
                if previous is not None:
                    if previous['action'] != action or previous['request_sha256'] != request_sha256(action,params): _bad('conflict')
                    return {'operation':self._public(previous)}
                params = self._validate(action, params)
                if action not in SYNC and (len(self._running) >= 2 or action in MODEL and any(r['action'] in MODEL for r in self._running.values())): _bad('busy')
                state = self._own()
                frozen = self._freeze(action,params,state)
                operations=self.root/'operations';results=self.root/'results'
                _directory(operations,True);_directory(results,True)
                self._capacity()
                record={'format':'stk.desktop-literature-operation/1','operation_id':identity,'action':action,
                    'request':params,'request_sha256':request_sha256(action,params),'frozen':frozen,
                    'state':'running','result_sha256':None,'error':None}
                _write(self._record_path(identity),record,MAX_METADATA,create=True)
                self._running[identity]=record
                if action in SYNC:
                    try:
                        library=self._library(state,params['corpus_id'])
                        result=library.revoke(identity,params['version_id'])
                        self._finish(record,result)
                    except Exception:
                        self._uncertain(record)
                    finally:self._running.pop(identity,None)
                    return {'operation':self._public(self._record(identity))}
                admission={'accepted':False}
                try:
                    if self._pool is None:self._pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='stk-literature')
                    self._pool.submit(self._drive,admission,record)
                except Exception:
                    self._uncertain(record);self._running.pop(identity,None)
                else:admission['accepted']=True
                return {'operation':self._public(self._record(identity))}
        except BridgeError:raise
        except Locked:_bad('busy')
        except LiteratureError as error:
            _bad('conflict' if error.code in {'operation_conflict','corpus_changed','dense_stale'} else 'invalid_params')
        except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError):_bad('unavailable')

    def _freeze(self,action,params,state):
        from suan.literature.encoder_profiles import worker_identity_sha256
        frozen={'service_id':state['service_id'],'encoder_generation':state['encoder_generation'],'scopes':[],
                'service_root':str(self.root),'core_python':self.python,'encoder_python':self.encoder_python,
                'encoder_worker_sha256':worker_identity_sha256(),
                'worker_sha256':hashlib.sha256(Path(__file__).with_name('literature_worker.py').read_bytes()).hexdigest()}
        if action=='corpora.create':
            if len(state['corpora'])+sum(r['action']=='corpora.create' for r in self._running.values()) >= 8:_bad('busy')
            corpus='local_'+UUID(params['operation_id']).hex
            if corpus in state['corpora']:_bad('conflict')
            frozen['new_corpus']=corpus
        elif action in {'encoder.select','import.commit'}:
            prior=self._record(params['review_id'])
            expected='encoder.review' if action=='encoder.select' else 'import.review'
            if prior is None or prior['action'] != expected:_bad('not_found')
            review=self._result(params['review_id'],internal=True)
            if checksum(review)!=params['review_sha256']:_bad('conflict')
            frozen['review']=review
            if action=='encoder.select' and params['expected_generation']!=state['encoder_generation']:_bad('conflict')
            if action=='encoder.select' and review['python']!=self.encoder_python:_bad('conflict')
            if action=='import.commit':frozen['scopes']=[review['corpus_id']]
        else:
            frozen['scopes']=sorted(params.get('scopes',[params['corpus_id']] if 'corpus_id' in params else []))
        frozen['corpora']={}
        for corpus in frozen['scopes']:
            library=self._library(state,corpus);info=library.info()
            frozen['corpora'][corpus]={'root':str(library.root),'database_id':info['database_id'],'generation':info['generation']}
        if action=='import.commit':
            review=frozen['review'];current=frozen['corpora'][review['corpus_id']]
            if current['database_id']!=review['database_id'] or current['generation']!=review['corpus_generation']:_bad('conflict')
        if action in MODEL:
            if state['encoder'] is None:_bad('unsupported')
            if params['encoder_generation']!=state['encoder_generation']:_bad('conflict')
            if state['encoder']['python']!=self.encoder_python:_bad('conflict')
            selected_review=self._result(state['encoder']['review_id'],internal=True)
            if (selected_review['identity']['runtime']['worker_sha256']!=frozen['encoder_worker_sha256']
                    or selected_review['fingerprint']!=state['encoder']['fingerprint']):_bad('conflict')
            frozen['encoder']=state['encoder']
        if action=='dense.build' and params['expected_generation']!=frozen['corpora'][params['corpus_id']]['generation']:_bad('conflict')
        frozen['parser_python']=self.parser_python
        self._validate_frozen(action,params,frozen)
        return frozen

    def _capacity(self):
        total=_ordinary(self.root/'state.json').st_size
        for name in ('operations','results'):
            paths=list((self.root/name).iterdir())
            if len(paths)>MAX_OPERATIONS or name=='operations' and len(paths)>=MAX_OPERATIONS:_bad('busy')
            for path in paths:
                if path.suffix!='.json':_bad('unavailable')
                _uuid(path.stem);total+=_ordinary(path).st_size
        # Reserve a complete result and journal replacement for every admitted
        # task, including the new task, before any corpus effect is accepted.
        if total+(len(self._running)+1)*(MAX_RESULT+MAX_METADATA)>MAX_SERVICE_BYTES:_bad('busy')

    def _validate_frozen(self,action,params,value):
        fields='service_id encoder_generation scopes corpora parser_python encoder_python core_python service_root worker_sha256 encoder_worker_sha256'
        if action=='corpora.create':fields+=' new_corpus'
        if action in {'encoder.select','import.commit'}:fields+=' review'
        if action in MODEL:fields+=' encoder'
        _keys(value,fields);_uuid(value['service_id']);_integer(value['encoder_generation']);_sha(value['worker_sha256']);_sha(value['encoder_worker_sha256'])
        for key in ('parser_python','encoder_python','core_python','service_root'):_path(value[key])
        if value['service_root']!=str(self.root):_bad('unavailable')
        scopes=value['scopes']
        if (type(scopes) is not list or len(scopes)>8 or any(type(c) is not str or not _CORPUS.fullmatch(c) for c in scopes)
                or scopes!=sorted(set(scopes)) or type(value['corpora']) is not dict or set(value['corpora'])!=set(scopes)):_bad()
        if action=='corpora.create':
            if value['new_corpus']!='local_'+UUID(params['operation_id']).hex:_bad()
        if action in {'encoder.select','import.commit'}:
            review=value['review'];(_encoder_review if action=='encoder.select' else _import_review)(review)
            if checksum(review)!=params['review_sha256']:_bad()
            if action=='encoder.select' and (review['python']!=value['encoder_python'] or params['expected_generation']!=value['encoder_generation']):_bad()
            if action=='encoder.select' and review['identity']['runtime']['worker_sha256']!=value['encoder_worker_sha256']:_bad()
        expected=sorted(params.get('scopes',[params['corpus_id']] if 'corpus_id' in params else []))
        if action=='import.commit':expected=[value['review']['corpus_id']]
        if scopes!=expected:_bad()
        for corpus,item in value['corpora'].items():
            _keys(item,'root database_id generation');_uuid(item['database_id']);_integer(item['generation'])
            if item['root']!=str(self.root/'corpora'/corpus):_bad()
        if action in MODEL:
            item=value['encoder'];_keys(item,'assets assets_sha256 python fingerprint review_id')
            _path(item['assets']);_sha(item['assets_sha256']);_sha(item['fingerprint']);_uuid(item['review_id'])
            if item['python']!=value['encoder_python'] or params['encoder_generation']!=value['encoder_generation']:_bad()

    def _bound_libraries(self,record):
        state=self._state();frozen=record['frozen']
        if state is None or state['service_id']!=frozen['service_id']:_bad('unavailable')
        libraries={}
        for corpus,item in frozen['corpora'].items():
            library=self._library(state,corpus)
            if library.info()['database_id']!=item['database_id']:_bad('unavailable')
            libraries[corpus]=library
        return libraries

    def _resolve_all(self,record,citations):
        """Batch exact source proof, then recheck all approvals together."""
        from suan.literature.dense import _resolve_citations, _window_evidence
        libraries=self._bound_libraries(record);resolved=[None]*len(citations)
        for corpus,library in libraries.items():
            selected=[(i,c) for i,c in enumerate(citations) if c['corpus_id']==corpus]
            manifests={}
            with library._db() as db:
                for _,citation in selected:
                    _citation(citation)
                    if citation['database_id']!=record['frozen']['corpora'][corpus]['database_id']:_bad('conflict')
                    generation=citation['dense_generation']
                    if generation not in manifests:
                        row=db.execute('SELECT CASE WHEN length(CAST(manifest AS BLOB))<=? THEN manifest ELSE NULL END FROM dense_generations WHERE id=?',(MAX_DENSE_MANIFEST,generation)).fetchone()
                        if row is None or row[0] is None:_bad('unavailable')
                        manifest=_decode(row[0]);_bounded(manifest,MAX_DENSE_MANIFEST)
                        if checksum(manifest)!=generation:_bad('unavailable')
                        manifests[generation]=manifest
                    manifest=manifests[generation];inner=citation['inner'];base=inner.get('base',inner)
                    if not _exact(manifest['corpus_generation'],citation['corpus_generation']) or not any(_exact(w['citation'],base) for w in manifest['windows']):_bad('unavailable')
                    if 'base' in inner:
                        item=next((w for w in manifest['windows'] if w['key']==inner['window_key']),None)
                        if (inner['generation']!=generation or item is None or not _exact(item['citation'],base)
                                or any(not _exact(item[k],inner[k]) for k in ('start','end','text_sha256'))):_bad('unavailable')
            bases=[c['inner'].get('base',c['inner']) for _,c in selected]
            values=_resolve_citations(library,bases)
            for (position,citation),value in zip(selected,values,strict=True):
                inner=citation['inner']
                if 'base' in inner:value=_window_evidence(inner,value)
                resolved[position]={**value,'citation':citation,'corpus_id':corpus,'database_id':citation['database_id']}
        if any(value is None for value in resolved):_bad('unavailable')
        self._approval_fence(record,citations,libraries=libraries)
        return resolved

    def _approval_fence(self,record,citations,*,libraries=None):
        # Library deliberately permits only one DB connection per process.
        # Sequential captures followed by a matching monotonic-generation pass
        # establish an overlapping publication snapshot without nesting leases.
        # Same-service revocation is also serialized by the service call lock.
        libraries=self._bound_libraries(record) if libraries is None else libraries
        captured={}
        for corpus,library in sorted(libraries.items()):
            with library._db() as db:
                if db.execute('SELECT identity FROM meta WHERE id=1').fetchone()[0]!=record['frozen']['corpora'][corpus]['database_id']:_bad('unavailable')
                for citation in citations:
                    if citation['corpus_id']==corpus:
                        inner=citation['inner'];library._version(db,inner.get('base',inner)['version_id'],active=True)
                captured[corpus]=library._generation(db)
        for corpus,library in sorted(libraries.items()):
            info=library.info()
            if info['database_id']!=record['frozen']['corpora'][corpus]['database_id'] or info['generation']!=captured[corpus]:_bad('unavailable')

    def _check_result(self,record,result,*,publish=True):
        _bounded(result);action=record['action'];params=record['request'];frozen=record['frozen']
        if action=='corpora.create':
            _keys(result,'corpus_id database_id');_uuid(result['database_id'])
            if result['corpus_id']!=frozen['new_corpus']:_bad()
        elif action=='encoder.review':
            _encoder_review(result)
            if result['assets']!=params['assets'] or result['python']!=frozen['encoder_python']:_bad()
            if result['identity']['runtime']['worker_sha256']!=frozen['encoder_worker_sha256']:_bad()
        elif action=='encoder.select':
            _keys(result,'encoder_generation fingerprint')
            if not _exact(result,{'encoder_generation':frozen['encoder_generation']+1,'fingerprint':frozen['review']['fingerprint']}):_bad()
        elif action=='import.review':
            _import_review(result)
            if any(not _exact(result[k],params[k]) for k in ('corpus_id','source','document_id','title','authorization')):_bad()
            expected=frozen['corpora'][params['corpus_id']]
            if result['database_id']!=expected['database_id'] or result['corpus_generation']!=expected['generation']:_bad()
        elif action in {'import.commit','import.recover','index.start','versions.revoke','dense.build'}:
            _keys(result,'operation_id kind request_sha256 state receipt');_sha(result['request_sha256'])
            corpus=frozen['review']['corpus_id'] if action=='import.commit' else params['corpus_id']
            actual=self._bound_libraries(record)[corpus].operation(record['operation_id'])
            kind={'import.commit':'import','import.recover':'recover_import','index.start':'index','versions.revoke':'revoke','dense.build':'dense_build'}[action]
            if not _exact(result,actual) or result['operation_id']!=record['operation_id'] or result['state']!='completed' or result['kind']!=kind:_bad('unavailable')
            receipt=result['receipt']
            fields={'import.commit':'version_id document_id source_sha256 source_bytes generation',
                    'import.recover':'original_operation_id import','index.start':'version_id source_sha256 extraction_id page_count character_count text_status structure_status generation',
                    'versions.revoke':'version_id active generation',
                    'dense.build':'generation corpus_generation encoder_fingerprint paragraphs windows'}[action]
            _keys(receipt,fields)
            if action=='dense.build':
                _sha(receipt['generation']);_integer(receipt['corpus_generation']);_integer(receipt['paragraphs'],10000);_integer(receipt['windows'],20000)
                if receipt['encoder_fingerprint']!=frozen['encoder']['fingerprint'] or receipt['corpus_generation']!=params['expected_generation']:_bad()
            elif action=='import.recover':
                if receipt['original_operation_id']!=params['original_operation_id']:_bad()
                _keys(receipt['import'],'version_id document_id source_sha256 source_bytes generation')
            else:
                _uuid(receipt['version_id']);_integer(receipt['generation'])
                if action in {'index.start','versions.revoke'} and receipt['version_id']!=params['version_id']:_bad()
                if action=='versions.revoke' and receipt['active'] is not False:_bad()
                if action=='import.commit':
                    review=frozen['review']
                    if any(receipt[k]!=review[k] for k in ('document_id','source_sha256','source_bytes')):_bad()
                if action=='index.start':
                    _sha(receipt['source_sha256']);_sha(receipt['extraction_id']);_integer(receipt['page_count'],256);_integer(receipt['character_count'],4_000_000)
                    if receipt['text_status'] not in {'mapped','incomplete'} or receipt['structure_status']!='unreviewed':_bad()
        elif action=='search':
            from suan.literature.collection import RECIPE
            from suan.literature.encoder_profiles import profile_for_recipe
            review=self._result(frozen['encoder']['review_id'],internal=True)
            profile=profile_for_recipe(review['identity']['recipe'])
            retriever='local_collection_fts5_e5_rrf' if profile['id']=='e5-small-cpu-f32' else 'local_collection_fts5_qwen3_rrf'
            _keys(result,'retriever recipe query_sha256 scopes hits')
            if (result['retriever']!=retriever or not _exact(result['recipe'],RECIPE)
                    or result['query_sha256']!=hashlib.sha256(params['query'].encode()).hexdigest()
                    or type(result['scopes']) is not list or type(result['hits']) is not list
                    or len(result['hits'])>params.get('limit',10)):_bad()
            states={}
            for item in result['scopes']:
                _keys(item,'corpus_id database_id corpus_generation dense_generation encoder_fingerprint')
                corpus=item['corpus_id']
                if corpus not in frozen['corpora'] or corpus in states:_bad()
                _sha(item['dense_generation']);_sha(item['encoder_fingerprint']);_uuid(item['database_id']);_integer(item['corpus_generation'])
                if (item['database_id']!=frozen['corpora'][corpus]['database_id'] or item['corpus_generation']!=frozen['corpora'][corpus]['generation']
                        or item['encoder_fingerprint']!=frozen['encoder']['fingerprint']):_bad()
                states[corpus]=item
            if list(states)!=frozen['scopes']:_bad()
            cites=[];identities=set();ranked={'dense_rank':set(),'lexical_rank':set()};ordering=[]
            for hit in result['hits']:
                _keys(hit,'corpus_id database_id corpus_generation dense_generation encoder_fingerprint score dense_score dense_rank lexical_rank text text_status structure_status citation dense_window')
                if hit['corpus_id'] not in states or any(not _exact(hit[k],v) for k,v in states[hit['corpus_id']].items()):_bad()
                if type(hit['score']) is not float or not 0<hit['score']<=2/61:_bad()
                if hit['dense_score'] is not None and (type(hit['dense_score']) is not float or not -1.0001<=hit['dense_score']<=1.0001):_bad()
                for key in ('dense_rank','lexical_rank'):
                    if hit[key] is not None:
                        if not 1<=_integer(hit[key],20) or hit[key] in ranked[key]:_bad()
                        ranked[key].add(hit[key])
                if hit['dense_rank'] is None and hit['lexical_rank'] is None:_bad()
                if not _exact(hit['score'],sum(1/(60+hit[k]) for k in ('dense_rank','lexical_rank') if hit[k] is not None)):_bad()
                _text(hit['text'],16384)
                if hit['text_status'] not in {'mapped','incomplete'} or hit['structure_status']!='unreviewed':_bad()
                _citation(hit['citation']);cites.append(hit['citation'])
                provenance=('corpus_id','database_id','corpus_generation','dense_generation')
                if any(not _exact(hit['citation'][k],hit[k]) for k in provenance) or hit['citation']['inner']['format']!='stk.literature-citation/1':_bad()
                identity=(hit['corpus_id'],hit['database_id'],checksum(hit['citation']['inner']))
                if identity in identities:_bad()
                identities.add(identity);ordering.append((-hit['score'],identity))
                if (hit['dense_rank'] is None)!=(hit['dense_window'] is None) or (hit['dense_rank'] is None)!=(hit['dense_score'] is None):_bad()
                if hit['dense_window'] is not None:
                    window=hit['dense_window'];_citation(window);cites.append(window)
                    if (any(not _exact(window[k],hit[k]) for k in provenance) or window['inner']['format']!='stk.literature-dense-citation/1'
                            or not _exact(window['inner']['base'],hit['citation']['inner'])):_bad()
            if ordering!=sorted(ordering):_bad()
            if publish:
                verified=self._resolve_all(record,cites);position=0
                for hit in result['hits']:
                    if hit['text']!=verified[position]['text'] or hit['text_status']!=verified[position]['text_status']:_bad('unavailable')
                    position+=1+(hit['dense_window'] is not None)
                self._approval_fence(record,cites)
        elif action in {'citations.resolve','pages.render'}:
            if publish:
                selected=self._resolve_all(record,[params['citation']])[0]
                if action=='citations.resolve':
                    if not _exact(result,selected):_bad('unavailable')
                else:self._check_page(record,result,selected)
                self._approval_fence(record,[params['citation']])
        else:_bad('unavailable')

    def _check_page(self,record,result,selected):
        _keys(result,'format citation source_sha256 page text_status structure_status renderer image pdf_to_pixel highlights geometry_sha256')
        inner=record['request']['citation']['inner'];base=inner.get('base',inner)
        if (result['format']!='stk.literature-page/1' or result['citation']!=record['request']['citation'] or result['source_sha256']!=base['source_sha256']
                or any(result[k]!=selected[k] for k in ('page','text_status','structure_status'))):_bad()
        renderer=result['renderer'];_keys(renderer,'adapter pypdfium2 binary_sha256 worker_sha256')
        if renderer!={'adapter':'stk.pdfium-citation-page/1','pypdfium2':'5.14.0','binary_sha256':selected['parser']['binary_sha256'],'worker_sha256':record['frozen']['worker_sha256']}:_bad()
        image=result['image'];_keys(image,'mime bytes sha256 width height data_base64')
        for key in ('width','height'):
            if not 1<=_integer(image[key],record['request'].get('long_edge',1536)):_bad()
        if image['width']*image['height']>4*1024**2 or image['mime']!='image/png':_bad()
        encoded=base64.b64decode(image['data_base64'],validate=True)
        if (not 1<=len(encoded)<=4*1024**2 or image['bytes']!=len(encoded) or image['sha256']!=hashlib.sha256(encoded).hexdigest()
                or encoded[:16]!=b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
                or struct.unpack('>II',encoded[16:24])!=(image['width'],image['height'])):_bad()
        position=8;chunks=[]
        while position<len(encoded):
            if position+12>len(encoded):_bad()
            size=struct.unpack('>I',encoded[position:position+4])[0];end=position+12+size
            if end>len(encoded):_bad()
            name=encoded[position+4:position+8];data=encoded[position+8:end-4]
            if zlib.crc32(name+data)&0xffffffff!=struct.unpack('>I',encoded[end-4:end])[0]:_bad()
            chunks.append((name,data));position=end
        if ([name for name,_ in chunks]!=[b'IHDR',b'IDAT',b'IEND'] or chunks[0][1][8:]!=b'\x08\x06\x00\x00\x00' or chunks[2][1]):_bad()
        decoder=zlib.decompressobj();size=(image['width']*4+1)*image['height']
        rows=decoder.decompress(chunks[1][1],size+1)
        if len(rows)!=size or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:_bad()
        if any(rows[y*(image['width']*4+1)]!=0 for y in range(image['height'])):_bad()
        matrix=result['pdf_to_pixel']
        if type(matrix) is not list or len(matrix)!=6 or any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>1e9 for x in matrix):_bad()
        left,bottom,right,top=selected['page']['page_box'];width,height=image['width'],image['height']
        sx,sy=width/(right-left),height/(top-bottom)
        orientation=selected['page']['rotation']
        expected_matrix={0:[sx,0,-left*sx,0,-sy,top*sy],
            90:[0,width/(top-bottom),-bottom*width/(top-bottom),height/(right-left),0,-left*height/(right-left)],
            180:[-sx,0,right*sx,0,sy,-bottom*sy],
            270:[0,-width/(top-bottom),top*width/(top-bottom),-height/(right-left),0,right*height/(right-left)]}.get(orientation)
        if expected_matrix is None:_bad()
        # PDFium's device/page conversion uses native float transforms. Compare
        # all four page corners in pixels, rather than an absolute coefficient
        # epsilon that incorrectly rejects large/cropped coordinate origins.
        for x,y in ((left,bottom),(right,bottom),(right,top),(left,top)):
            for offset in (0,3):
                actual=matrix[offset]*x+matrix[offset+1]*y+matrix[offset+2]
                expected=expected_matrix[offset]*x+expected_matrix[offset+1]*y+expected_matrix[offset+2]
                if abs(actual-expected)>.02:_bad()
        expected=[]
        for char in selected['characters']:
            if char['box'] is None:continue
            left,bottom,right,top=char['box']
            points=[[matrix[0]*x+matrix[1]*y+matrix[2],matrix[3]*x+matrix[4]*y+matrix[5]]
                    for x,y in ((left,bottom),(right,bottom),(right,top),(left,top))]
            expected.append({k:char[k] for k in ('index','text_start','text_end')}|{'quad':points})
        if result['highlights']!=expected or result['geometry_sha256']!=checksum(expected):_bad()

    def _read_call(self,action,params):
        state=self._state()
        if action=='corpora.info':
            from suan.literature.dense import DenseIndex
            corpus=params['corpus_id']
            if state is None or corpus not in state['corpora']:_bad('not_found')
            expected=state['corpora'][corpus]['database_id']
            library=Library(self.root/'corpora'/corpus)
            with library._db() as db:
                if db is None or db.execute('SELECT identity FROM meta WHERE id=1').fetchone()[0]!=expected:_bad('unavailable')
                generation=library._generation(db);_integer(generation)
                result={'corpus_id':corpus,'database_id':expected,'generation':generation,
                    'dense_generation':None,'dense_source_generation':None,'dense_encoder_fingerprint':None}
                if DenseIndex._exists(db):
                    row=db.execute('SELECT m.current_generation,CASE WHEN length(CAST(g.manifest AS BLOB))<=? THEN g.manifest ELSE NULL END FROM dense_meta m LEFT JOIN dense_generations g ON g.id=m.current_generation WHERE m.id=1',(MAX_DENSE_MANIFEST,)).fetchone()
                    if row is None or row[1] is None:_bad('unavailable')
                    _sha(row[0]);manifest=_decode(row[1]);_bounded(manifest,MAX_DENSE_MANIFEST)
                    _keys(manifest,'format corpus_generation encoder encoder_fingerprint windows')
                    if (manifest['format']!='stk.literature-dense-generation/1' or checksum(manifest)!=row[0]
                            or type(manifest['encoder']) is not dict or checksum(manifest['encoder'])!=manifest['encoder_fingerprint']
                            or type(manifest['windows']) is not list or len(manifest['windows'])>20000):_bad('unavailable')
                    _integer(manifest['corpus_generation']);_sha(manifest['encoder_fingerprint'])
                    if manifest['corpus_generation']>generation:_bad('unavailable')
                    result.update(dense_generation=row[0],dense_source_generation=manifest['corpus_generation'],
                                  dense_encoder_fingerprint=manifest['encoder_fingerprint'])
                return result
        if action in {'info','corpora.list'}:
            corpora=[] if state is None else [{'corpus_id':c,**item} for c,item in sorted(state['corpora'].items())]
            return {'corpora':corpora,'encoder_generation':0 if state is None else state['encoder_generation'],
                    'encoder_configured':state is not None and state['encoder'] is not None,'active_jobs':len(self._running)}
        if action=='encoder.info':
            selection=None if state is None else state['encoder']
            return {'generation':0 if state is None else state['encoder_generation'],
                    'selection':None if selection is None else {k:selection[k] for k in ('assets_sha256','fingerprint','review_id')}}
        if action=='versions.list':
            if state is None:_bad('not_found')
            return {'versions':self._library(state,params['corpus_id']).versions(offset=params.get('offset',0),limit=min(params.get('limit',20),20))}
        if action=='operations.get':return {'operation':self._public(self._record(params['operation_id']))}
        if action=='operations.result':
            record=self._record(params['operation_id'])
            if record is None:_bad('not_found')
            if record['request_sha256']!=params['expected_request_sha256']:_bad('conflict')
            return {'operation':self._public(record),'result':self._result(params['operation_id'])}
        directory=self.root/'operations'
        if not directory.exists():return {'operations':[]}
        _directory(directory)
        paths=sorted(directory.iterdir())
        if len(paths)>MAX_OPERATIONS:_bad('unavailable')
        identities=[]
        for path in paths:
            if path.suffix!='.json':_bad('unavailable')
            identities.append(_uuid(path.stem))
        offset=params.get('offset',0);limit=params.get('limit',50)
        return {'operations':[self._public(self._record(i)) for i in identities[offset:offset+limit]]}

    def _finish(self,record,result):
        _bounded(result)
        if record['action'] in {'encoder.review','encoder.select'}:_encoder_review(result,authority=True)
        state=self._state()
        if state is None or state['service_id']!=record['frozen']['service_id']:_bad('unavailable')
        if record['action'] in MODEL and state['encoder_generation']!=record['frozen']['encoder_generation']:_bad('conflict')
        for corpus,expected in record['frozen']['corpora'].items():
            library=self._library(state,corpus)
            if library.info()['database_id']!=expected['database_id']:_bad('unavailable')
        if record['action']=='corpora.create':
            corpus=record['frozen']['new_corpus'];_uuid(result['database_id'])
            if (set(result)!={'corpus_id','database_id'} or result['corpus_id']!=corpus
                    or Library(self.root/'corpora'/corpus).info()['database_id']!=result['database_id']
                    or corpus in state['corpora'] or len(state['corpora'])>=8):_bad('conflict')
            state['corpora'][corpus]={'name':record['request']['name'],'database_id':result['database_id'],
                                     'create_operation':record['operation_id']};self._save_state(state)
        if record['action']=='encoder.select':
            _encoder_review(result)
            if state['encoder_generation']!=record['request']['expected_generation']:_bad('conflict')
            selected=record['frozen']['review']
            if not _exact(result,selected):_bad('conflict')
            state['encoder']={k:selected[k] for k in ('assets','assets_sha256','python','fingerprint')}
            state['encoder']['review_id']=record['request']['review_id'];state['encoder_generation']+=1;self._save_state(state)
            result={'encoder_generation':state['encoder_generation'],'fingerprint':selected['fingerprint']}
        self._check_result(record,result)
        path=self.root/'results'/(record['operation_id']+'.json')
        if path.exists():
            if checksum(_read(path,MAX_RESULT))!=checksum(result):_bad('conflict')
        else:_write(path,result,MAX_RESULT,create=True)
        record.update(state='completed',result_sha256=checksum(result),error=None)
        _write(self._record_path(record['operation_id']),record,MAX_METADATA)

    def _uncertain(self,record,code='unavailable'):
        if code not in _JOB_ERRORS:code='unavailable'
        record.update(state='uncertain',result_sha256=None,error={'code':code,'message':'Local action has no confirmed completion'})
        try:_write(self._record_path(record['operation_id']),record,MAX_METADATA)
        except Exception:pass

    def _drive(self,admission,record):
        identity=record['operation_id'];child=None
        try:
            with self._lock:
                if not admission['accepted'] or self._closed:return
                action=record['action'];params=record['request'];frozen=record['frozen']
                python=(self.encoder_python if action in {'encoder.review','encoder.select'}
                        else frozen['parser_python'] if action=='pages.render' else self.python)
                if hashlib.sha256(Path(__file__).with_name('literature_worker.py').read_bytes()).hexdigest()!=frozen['worker_sha256']:raise ValueError
                command=[python,'-I',str(Path(__file__).with_name('literature_worker.py'))]
                child=WorkerProcess(command,max_line=MAX_RESULT,env=child_environment())
                self._children[identity]=child
                payload={'id':identity,'action':action,'params':params,'frozen':frozen,
                         'new_root':str(self.root/'corpora'/frozen['new_corpus']) if action=='corpora.create' else None}
                child.outgoing.put(encode_message(payload))
            deadline=time.monotonic()+ (params.get('timeout',600)+10 if action=='dense.build' else 130 if action=='search' else 75)
            while True:
                with self._lock:
                    if self._closed:raise RuntimeError
                if time.monotonic()>deadline:raise TimeoutError
                try:message=child.incoming.get(timeout=.1)
                except queue.Empty:continue
                if (type(message) is not dict or message.get('id')!=identity or set(message) not in ({'id','result'},{'id','error'})):raise ValueError
                break
            child.stop();child=None
            with self._lock:
                self._children.pop(identity,None)
                if self._closed:raise RuntimeError
                if 'error' in message:
                    _keys(message['error'],'code message');_text(message['error']['code'],64);_text(message['error']['message'],128)
                    self._uncertain(record,message['error']['code'])
                else:self._finish(record,message['result'])
                self._running.pop(identity,None)
        except Exception:
            with self._lock:self._uncertain(record)
        finally:
            if child is not None:
                try:child.stop()
                except Exception:pass
            with self._lock:
                self._children.pop(identity,None);self._running.pop(identity,None)

    def shutdown(self):
        with self._lock:
            self._closed=True;children=list(self._children.values());pool=self._pool
        for child in children:
            try:child.stop()
            except Exception:pass
        # No journal writer may outlive the service lease or race a passive
        # reopen. Only two admitted tasks can exist and owned trees are stopped.
        if pool is not None:pool.shutdown(wait=True,cancel_futures=True)
        with self._lock:
            for record in self._running.values():self._uncertain(record)
            self._running.clear();self._children.clear()
            if self._lease is not None:self._lease.close();self._lease=None
