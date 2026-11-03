"""One fixed local literature job on private pipes; no reusable action queue."""
import base64
import ctypes
from contextlib import closing
import hashlib
import importlib.metadata as metadata
import json
import math
import os
from pathlib import Path
import struct
import sys
import zlib


def _png(width,height,rgba):
    def chunk(name,data):
        return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
    rows=b''.join(b'\0'+rgba[y*width*4:(y+1)*width*4] for y in range(height))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(rows,6))+chunk(b'IEND',b'')


def _render(library,citation,selected,long_edge):
    from suan.literature._io import opened, fail
    from suan.literature.pdf import checksum
    if metadata.version('pypdfium2')!='5.14.0':fail('parser_unavailable','Pinned local PDF renderer is unavailable')
    import pypdfium2 as pdf
    import pypdfium2.raw as raw
    distribution=metadata.distribution('pypdfium2')
    binaries=[p for p in distribution.files if str(p).endswith(('libpdfium.so','pdfium.dll','libpdfium.dylib'))]
    if len(binaries)!=1:fail()
    binary_sha=hashlib.sha256(distribution.locate_file(binaries[0]).read_bytes()).hexdigest()
    if binary_sha!=selected['parser']['binary_sha256']:fail('parser_changed','Selected rendering binary differs from citation parser')
    inner=citation['inner'];base=inner['base'] if inner['format']=='stk.literature-dense-citation/1' else inner
    with opened(library._object(base['source_sha256'])) as (stream,info):
        source=stream.read(32*1024**2+1)
    if len(source)!=info.st_size or hashlib.sha256(source).hexdigest()!=base['source_sha256']:fail('source_changed','Frozen PDF bytes changed')
    with pdf.PdfDocument(source) as document:
        with closing(document[base['page_index']]) as page:
            scale=(long_edge-1)/max(page.get_width(),page.get_height())
            bitmap=page.render(scale=scale,rotation=0,crop=(0,0,0,0),may_draw_forms=False,
                force_bitmap_format=raw.FPDFBitmap_BGRA,rev_byteorder=True,fill_color=(255,255,255,255))
            try:
                width,height,stride=bitmap.width,bitmap.height,bitmap.stride
                if (bitmap.n_channels!=4 or bitmap.mode!='RGBA' or not 1<=width<=long_edge
                        or not 1<=height<=long_edge or width*height>4*1024**2):fail()
                pixels=bytes(bitmap.buffer)
                rgba=b''.join(pixels[y*stride:y*stride+width*4] for y in range(height))
                encoded=_png(width,height,rgba)
                if len(encoded)>4*1024**2:fail('page_budget','Rendered page exceeds display budget')
                def point(x,y):
                    px,py=ctypes.c_double(),ctypes.c_double()
                    if not raw.FPDF_DeviceToPage(page,0,0,width,height,0,x,y,ctypes.byref(px),ctypes.byref(py)):fail()
                    return px.value,py.value
                a,b,c=point(0,0),point(width,0),point(0,height)
                ux,uy=(b[0]-a[0])/width,(b[1]-a[1])/width
                vx,vy=(c[0]-a[0])/height,(c[1]-a[1])/height
                determinant=ux*vy-uy*vx
                if not math.isfinite(determinant) or determinant==0:fail()
                matrix=[vy/determinant,-vx/determinant,(-vy*a[0]+vx*a[1])/determinant,
                        -uy/determinant,ux/determinant,(uy*a[0]-ux*a[1])/determinant]
                highlights=[]
                for char in selected['characters']:
                    if char['box'] is None:continue
                    left,bottom,right,top=char['box']
                    points=[]
                    for x,y in ((left,bottom),(right,bottom),(right,top),(left,top)):
                        points.append([matrix[0]*x+matrix[1]*y+matrix[2],matrix[3]*x+matrix[4]*y+matrix[5]])
                    highlights.append({k:char[k] for k in ('index','text_start','text_end')}|{'quad':points})
            finally:bitmap.close()
    library.resolve(base)  # Current approval and exact source after rasterization.
    return {'format':'stk.literature-page/1','citation':citation,'source_sha256':base['source_sha256'],
        'page':selected['page'],'text_status':selected['text_status'],'structure_status':selected['structure_status'],
        'renderer':{'adapter':'stk.pdfium-citation-page/1','pypdfium2':'5.14.0','binary_sha256':binary_sha,
                    'worker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        'image':{'mime':'image/png','bytes':len(encoded),'sha256':hashlib.sha256(encoded).hexdigest(),
                 'width':width,'height':height,'data_base64':base64.b64encode(encoded).decode()},
        'pdf_to_pixel':matrix,'highlights':highlights,'geometry_sha256':checksum(highlights)}


def execute(message):
    from suan.desktop_bridge.literature import LiteratureService, _bounded, _keys, _exact
    _bounded(message,128*1024)
    _keys(message,'id action params frozen new_root')
    frozen=message['frozen']
    service=LiteratureService(Path(frozen['service_root']).parent,python=frozen['core_python'],
                              parser_python=frozen['parser_python'],encoder_python=frozen['encoder_python'])
    params=service._validate(message['action'],message['params'])
    if message['action'] in {'info','corpora.list','corpora.info','encoder.info','versions.list','operations.get','operations.list','operations.result','versions.revoke'}:raise ValueError
    service._validate_frozen(message['action'],params,frozen)
    if message['id']!=params['operation_id'] or hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=frozen['worker_sha256']:raise ValueError
    expected=str(service.root/'corpora'/frozen['new_corpus']) if message['action']=='corpora.create' else None
    if message['new_root']!=expected:raise ValueError
    from suan.literature._io import fail, inspect_pdf, opened
    from suan.literature.pdf import checksum
    from suan.literature.store import Library
    from suan.literature.collection import Collection
    from suan.literature.dense import DenseIndex, Encoder
    identity,action,params,frozen=message['id'],message['action'],message['params'],message['frozen']
    if action=='corpora.create':
        library=Library(Path(message['new_root']))
        # Explicit new-corpus action only; never called by construction or info.
        with library._db(write=True):pass
        return {'corpus_id':frozen['new_corpus'],'database_id':library.info()['database_id']}
    if action in {'encoder.review','encoder.select'}:
        from suan.literature.dense_worker import assets, runtime
        from suan.literature.encoder_profiles import profile_for_manifest
        chosen={**params,'python':frozen['encoder_python']} if action=='encoder.review' else frozen['review']
        path=Path(chosen['assets']);manifest=path/'manifest.json'
        with opened(manifest) as (stream,info):
            if info.st_size>16384:fail()
            contents=stream.read(16385)
            if len(contents)!=info.st_size:fail()
        manifest_sha=hashlib.sha256(contents).hexdigest()
        manifest=assets(path,manifest_sha)
        evidence={'assets_sha256':manifest_sha,'recipe':profile_for_manifest(manifest)['recipe'],'runtime':runtime()}
        result={'format':'stk.literature-encoder-review/1','assets':str(path),'assets_sha256':manifest_sha,
                'python':chosen['python'],'identity':evidence,'fingerprint':checksum(evidence)}
        if action=='encoder.select' and not _exact(result,frozen['review']):fail('encoder_changed','Reviewed local encoder changed')
        return result
    libraries={corpus:Library(Path(item['root'])) for corpus,item in frozen['corpora'].items()}
    for corpus,library in libraries.items():
        if library.info()['database_id']!=frozen['corpora'][corpus]['database_id']:fail('database_mismatch','Selected corpus database changed')
    corpus=params.get('corpus_id');library=libraries.get(corpus)
    if action=='import.review':
        before=library.info();source=inspect_pdf(Path(params['source']))
        if library.info()!=before:fail('corpus_changed','Selected corpus changed during review')
        return {'format':'stk.literature-import-review/1','corpus_id':corpus,'database_id':before['database_id'],
                'corpus_generation':before['generation'],'source':params['source'],'source_sha256':source['sha256'],
                'source_bytes':source['bytes'],'document_id':params['document_id'],'title':params['title'],
                'authorization':params['authorization']}
    if action=='import.commit':
        review=frozen['review'];library=libraries[review['corpus_id']]
        if library.info()['generation']!=review['corpus_generation']:fail('corpus_changed','Reviewed corpus changed')
        return library.import_pdf(identity,Path(review['source']),source_sha256=review['source_sha256'],
            source_bytes=review['source_bytes'],document_id=review['document_id'],title=review['title'],authorization=review['authorization'])
    if action=='import.recover':return library.recover_import(identity,params['original_operation_id'])
    if action=='index.start':return library.index_pdf(identity,params['version_id'],python=frozen['parser_python'],timeout=60)
    if action in {'dense.build','search'}:
        config=frozen['encoder'];encoder=Encoder(Path(config['assets']),assets_sha256=config['assets_sha256'],python=Path(config['python']))
        if action=='dense.build':
            if library.info()['generation']!=params['expected_generation']:fail('corpus_changed','Selected corpus changed')
            return DenseIndex(library).build(identity,encoder,timeout=params.get('timeout',600))
        found=Collection(libraries).search(params['query'],encoder,scopes=frozen['scopes'],limit=params.get('limit',10),timeout=120)
        if any(s['encoder_fingerprint']!=config['fingerprint'] for s in found['scopes']):fail('encoder_changed','Selected encoder proof changed')
        # Evaluation-only branch ledgers stay out of the product's result cache.
        return {k:v for k,v in found.items() if k!='branches'}
    collection=Collection(libraries)
    selected=collection.resolve(params['citation'],scopes=frozen['scopes'])
    if action=='citations.resolve':return selected
    if action=='pages.render':
        corpus=params['citation']['corpus_id'];return _render(libraries[corpus],params['citation'],selected,params.get('long_edge',1536))
    fail()


def main():
    protocol=os.fdopen(os.dup(sys.stdout.fileno()),'wb',buffering=0)
    # Native/third-party output cannot enter either protocol or bridge logs.
    sink=os.open(os.devnull,os.O_WRONLY)
    os.dup2(sink,1);os.dup2(sink,2);os.close(sink)
    sys.dont_write_bytecode=True
    os.environ['STK_TOKEN_PLAN_API_KEY']='';os.environ.pop('STK_TOKEN_PLAN_MODEL',None)
    def offline(event,_args):
        if event.startswith('socket.'):raise RuntimeError('Local literature worker has no network capability')
    sys.addaudithook(offline)
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    from suan.desktop_bridge.protocol import decode_line,encode_message
    identity=None
    try:
        line=sys.stdin.buffer.readline(128*1024+1)
        if len(line)>128*1024 or not line.endswith(b'\n'):raise ValueError
        message=decode_line(line);identity=message['id']
        result=execute(message)
        output=encode_message({'id':identity,'result':result})
        if len(output)>8*1024**2:raise ValueError
    except Exception as error:
        code=getattr(error,'code','unavailable')
        if code not in {'authorization_revoked','corpus_changed','encoder_changed','dense_stale','source_changed',
                'encoder_unavailable','parser_unavailable','invalid_data','invalid_path','invalid_file',
                'citation_mismatch','database_mismatch','operation_conflict','embedding_budget','page_budget'}:code='unavailable'
        output=encode_message({'id':identity,'error':{'code':code,'message':'Local literature job has no confirmed result'}})
    protocol.write(output);protocol.close()


if __name__=='__main__':main()
