"""Reviewed offline embedding recipes and exact publisher-file identities.

Adding a recipe is code review, never an arbitrary model name, remote code or
implicit fallback. Legacy E5 recipe identity stays byte-for-byte unchanged.
Qwen uses the publisher's last-token/instruction method with our explicit 512
complete-window CPU budget, rather than claiming its full advertised context.
Assets are provisioned externally; this module neither downloads nor loads them.
"""
import hashlib
import json
from pathlib import Path

CORE = {"torch": "2.14.1+cpu", "transformers": "4.57.6", "tokenizers": "0.22.2",
        "safetensors": "0.7.0", "numpy": "2.5.4", "huggingface-hub": "0.36.2"}
E5_RECIPE = {"encoder": "intfloat/multilingual-e5-small", "revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
    "dimensions": 384, "tokens": 512, "query_prefix": "query: ", "passage_prefix": "passage: ",
    "pooling": "attention_mask_mean", "normalization": "l2", "device": "cpu", "dtype": "float32",
    "windows": "complete_contiguous_scalar_partition/1", "threads": 2}
QWEN_RECIPE = {"encoder": "Qwen/Qwen3-Embedding-0.6B", "revision": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
    "dimensions": 1024, "tokens": 512,
    "query_prefix": "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:",
    "passage_prefix": "", "pooling": "last_nonpadding_token", "normalization": "l2", "device": "cpu",
    "dtype": "float32", "windows": "complete_contiguous_scalar_partition/1", "threads": 2}

_E5_FILES = {'1_Pooling/config.json': {'bytes': 200,
                           'sha256': '987f7a67a38fa564c849bb5d277c52ab9088a84368fc0be31a354125aebb12a0'},
 'README.md': {'bytes': 497538, 'sha256': '0038de97aee16258cecbad7ffda4b4febd6953e747a00e0ddbc8e6ed241e9c1c'},
 'config.json': {'bytes': 655, 'sha256': '69137736cab8b8903a07fe8afaafdda25aac55415a12a55d1bffa9f581abf959'},
 'model.safetensors': {'bytes': 470641600,
                       'sha256': '1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477'},
 'modules.json': {'bytes': 387, 'sha256': 'c6e29747481e8b5dd2b58401966aeac910de39092f90cda9a704b1545f902b04'},
 'sentence_bert_config.json': {'bytes': 57,
                               'sha256': '948201d8329907aae938fa62f9ceeed53f5694dacc2b87b9f3b78b37ee986529'},
 'sentencepiece.bpe.model': {'bytes': 5069051,
                             'sha256': 'cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865'},
 'special_tokens_map.json': {'bytes': 167,
                             'sha256': 'd05497f1da52c5e09554c0cd874037a083e1dc1b9cfd48034d1c717f1afc07a7'},
 'tokenizer.json': {'bytes': 17082730,
                    'sha256': '0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39'},
 'tokenizer_config.json': {'bytes': 443,
                           'sha256': 'a1d6bc8734a6f635dc158508bef000f8e2e5a759c7d92f984b2c86e5ff53425b'}}
_QWEN_FILES = {'1_Pooling/config.json': {'bytes': 313,
                           'sha256': '37bf193fa101f19101bfad9c31d3eb0f786e247b7b1e5cb7f007d730eed1ddbd'},
 'README.md': {'bytes': 17237, 'sha256': 'c34d9b7e5a267ad3fdd13227a253686bc90844ff4744a2a6a86c7c905e3d06f3'},
 'config.json': {'bytes': 727, 'sha256': 'b5bf1f51fc45be473a54718cef92448d90a1be001bf9b9a44b8c7f10a19feaa9'},
 'config_sentence_transformers.json': {'bytes': 215,
                                       'sha256': '10667c72ddb772627bf1780cb7f86af8e2ae0032b8c243c731172064105c6961'},
 'generation_config.json': {'bytes': 117,
                            'sha256': '28396d421a2108acce96383f6a7de78008f7f1b17f807958f3c14c51dbfb65fb'},
 'merges.txt': {'bytes': 1671853,
                'sha256': '8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5'},
 'model.safetensors': {'bytes': 1191586416,
                       'sha256': '0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd'},
 'modules.json': {'bytes': 349, 'sha256': '84e40c8e006c9b1d6c122e02cba9b02458120b5fb0c87b746c41e0207cf642cf'},
 'tokenizer.json': {'bytes': 11423705,
                    'sha256': 'def76fb086971c7867b829c23a26261e38d9d74e02139253b38aeb9df8b4b50a'},
 'tokenizer_config.json': {'bytes': 9706,
                           'sha256': '253153d0738ceb4c668d2eff957714dd2bea0b56de772a9fdccd96cbf517e6a0'},
 'vocab.json': {'bytes': 2776833,
                'sha256': 'ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910'}}


def _copy(value):
    return json.loads(json.dumps(value,ensure_ascii=False,allow_nan=False))


def worker_identity_sha256():
    """Bind the inference entry point AND its reviewed profile implementation."""
    root=Path(__file__).parent
    sources={name:hashlib.sha256((root/name).read_bytes()).hexdigest()
             for name in ('dense_worker.py','encoder_profiles.py')}
    return hashlib.sha256(json.dumps(sources,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def profiles():
    """Detached metadata: inspection is passive and does not verify local assets."""
    return _copy([
        {"id":"e5-small-cpu-f32", "recipe":E5_RECIPE, "core":CORE,
         "asset_format":"stk.e5-assets/1", "license":"MIT", "files":_E5_FILES},
        {"id":"qwen3-0.6b-cpu-f32", "recipe":QWEN_RECIPE, "core":CORE,
         "asset_format":"stk.literature-encoder-assets/1", "license":"Apache-2.0", "files":_QWEN_FILES},
    ])


def profile_for_recipe(recipe):
    """Require exact JSON types as well as known fields and values."""
    if type(recipe) is not dict:
        raise ValueError("Unknown local embedding recipe")
    encoded=json.dumps(recipe,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(",",":"))
    for profile in profiles():
        if encoded==json.dumps(profile["recipe"],sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(",",":")):
            return profile
    raise ValueError("Unknown local embedding recipe")


def profile_for_manifest(manifest):
    required={"format","model","revision","declared_license","files"}
    if (type(manifest) is not dict or not required.issubset(manifest)
            or set(manifest)-required-{"license_evidence"}):
        raise ValueError("Invalid local embedding asset manifest")
    if "license_evidence" in manifest:
        evidence=manifest["license_evidence"]
        if type(evidence) is not str or not 0<len(evidence.encode('utf-8'))<=1024:
            raise ValueError("Invalid local license evidence note")
    for profile in profiles():
        recipe=profile["recipe"]
        if (manifest["format"]==profile["asset_format"] and manifest["model"]==recipe["encoder"]
                and manifest["revision"]==recipe["revision"] and manifest["declared_license"]==profile["license"]
                and type(manifest["files"]) is dict):
            expected=json.dumps(profile["files"],sort_keys=True,separators=(",",":"))
            actual=json.dumps(manifest["files"],sort_keys=True,allow_nan=False,separators=(",",":"))
            if actual==expected:return profile
    raise ValueError("Unreviewed local embedding assets")
