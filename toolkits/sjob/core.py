"""Path-explicit batch operations, retaining the legacy batch.json/list format."""

from pathlib import Path
import ast
import os
import re
import shlex
import shutil
import subprocess


def condition(expression):
    """Evaluate arithmetic/comparison expressions, rejecting calls and attributes."""
    expression = expression.replace('&&', ' and ').replace('||', ' or ')
    if len(expression) > 4096:
        raise ValueError('Batch condition is too long')
    tree = ast.parse(expression, mode='eval')
    allowed = (ast.Expression, ast.Constant, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp,
               ast.Not, ast.UAdd, ast.USub, ast.BinOp, ast.Add, ast.Sub, ast.Mult,
               ast.Div, ast.Mod, ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE,
               ast.Gt, ast.GtE)
    if any(not isinstance(node, allowed) for node in ast.walk(tree)):
        raise ValueError('Unsupported expression in batch condition')
    return bool(eval(compile(tree, '<batch-condition>', 'eval'), {'__builtins__': {}}, {}))


def schedule_batch(config_path, workdir):
    from .cli import getJsonVar, writeBatchList
    root = Path(workdir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    source = str(Path(config_path).resolve())
    target = root / 'batchList.txt'
    writeBatchList(getJsonVar(source, 'VarName'), getJsonVar(source, 'VarValue'),
                   getJsonVar(source, 'Condition') or '1>0', getJsonVar(source, 'Separator') or '+',
                   getJsonVar(source, 'Format') or '%s', str(target))
    return target


def batch_rows(batch_list, start=1, end=None):
    from .cli import getFolderName, replaceKeywordsStringIndex
    path = Path(batch_list).resolve()
    count = len(path.read_text().splitlines()) - 1
    end = count if end is None else end
    if count == 0 and start == 1 and end == 0:
        return []
    if start < 1 or end < start or end > count:
        raise ValueError('Batch start/end range is invalid')
    return [(i, getFolderName(i, str(path))) for i in range(start, end + 1)]


def replace_input(content, names, values, mode):
    for name, value in zip(names, values):
        fixed = name.startswith('@') or mode == '@'
        name = name.lstrip('&@').strip()
        if fixed:
            content = re.sub(r'\b' + re.escape(name) + r'\b', lambda _: value, content)
        else:
            # Replace an assignment's RHS, not the name inside its existing RHS.
            pattern = r'(?m)^(\s*' + re.escape(name) + r')\s*(?:=[^\n#!]*)?([#!][^\n]*)?$'
            content = re.sub(pattern, lambda m: m[1] + ' = ' + value + (' ' + m[2] if m[2] else ''), content)
    return content


def create_batch(file_list, workdir, batch_list=None, start=1, end=None):
    from .cli import getVariableOfIndex
    from suan.runtime.common import inside
    root = Path(workdir).resolve()
    batch = Path(batch_list).resolve() if batch_list else root / 'batchList.txt'
    names = [v.strip() for v in getVariableOfIndex(0, str(batch)).split('|')]
    files = shlex.split(file_list) if isinstance(file_list, str) else file_list
    result = []
    for index, folder in batch_rows(batch, start or 1, end):
        target = inside(root, folder)
        target.mkdir(parents=True, exist_ok=True)
        values = [v.strip() for v in getVariableOfIndex(index, str(batch)).split('|')]
        for entry in files:
            mode = entry[0] if entry.startswith(('&', '@')) else ''
            name = entry[1:] if mode else entry
            source = inside(root, name)
            output = inside(target, name)
            output.parent.mkdir(parents=True, exist_ok=True)
            if mode:
                output.write_text(replace_input(source.read_text(), names, values, mode))
            else:
                shutil.copy2(source, output)
        result.append(target)
    return result


def execute_batch(command, workdir, batch_list=None, start=1, end=None):
    from .cli import replaceKeywordsStringIndex
    from suan.runtime.common import inside
    root = Path(workdir).resolve()
    batch = Path(batch_list).resolve() if batch_list else root / 'batchList.txt'
    results = []
    for index, folder in batch_rows(batch, start, end):
        text = replaceKeywordsStringIndex(command, index, str(batch))
        argv = ['powershell', '-NoProfile', '-Command', text] if os.name == 'nt' else ['/bin/sh', '-c', text]
        # The legacy Command field is explicitly a shell program. Runtime's new
        # argv interface never constructs a shell string from API parameters.
        completed = subprocess.run(argv, cwd=inside(root, folder), check=True)
        results.append({'index': index, 'folder': folder, 'exit_code': completed.returncode})
    return results
