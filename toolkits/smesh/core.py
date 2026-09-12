"""Explicit-path adapters around the existing structure generators."""

from copy import deepcopy
from pathlib import Path
import toml


def generate_structure(config_path, output_dir):
    from structure_generator.scripts.generate_structure import generate_from_config
    from suan.runtime.common import inside
    config = deepcopy(toml.load(config_path))
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if config.get('target_program') == 'muBreakdown':
        name = config['output']['output_file']
        config['output']['output_file'] = str(inside(root, name))
        Path(config['output']['output_file']).parent.mkdir(parents=True, exist_ok=True)
    else:
        for group in ('eta_case_config', 'comp_case_config'):
            for case in config.get(group, []):
                path = inside(root, case['filename'])
                path.parent.mkdir(parents=True, exist_ok=True)
                case['filename'] = str(path)
    generate_from_config(config)
    return root
