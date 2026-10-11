"""Reading a LAMMPS input script the way STK needs to: its commands, the run parameters it takes, and the
commands STK does not run.

STK sets a case's parameters with ``-var`` (``lmp -var temperature 300``), which defines an *index* variable.
A script may declare a default with the same style (``variable temperature index 300``): LAMMPS then keeps
the command-line value. Declaring a parameter with another style is an error in LAMMPS, so it is refused here.

The checks cover the script, every file it includes (``include``/``jump``, to any depth) and the commands quoted
inside ``if ... then "..."`` and ``run ... every N "..."``. Refused: commands that run programs or load code
(``shell``, ``python``, ``plugin``, ``fix python/*``, ``pair_style python``, ``mdi``, ``kim``), environment and
Python variables (``getenv``, ``python``), a command word or variable style made from variables, moving the log
STK reads (``log``), and *literal* paths outside the case folder (absolute, ``~`` or ``..``). Paths assembled
from variables are not followed. These checks protect against accidents and against mistaking a script for a
pure input; they are not a sandbox (a Runtime client can run any command, docs/design/multiscale-engines.md).
"""
import math
import posixpath
import re

# Row fields of a LAMMPS case that a script can take as variables, with their kinds.
PARAMETERS = {"temperature": "number", "pressure": "number", "steps": "integer", "timestep": "number", "seed": "integer"}
PROPERTY_PARAMETERS = {"equilibration_steps": "integer", "sample_interval": "integer", "strain_rate": "number",
                       "solute_type": "integer"}
PARAMETERS.update(PROPERTY_PARAMETERS)
# Command words that run programs, load code or move the log STK reads.
FORBIDDEN_COMMANDS = {"shell", "python", "plugin", "log", "mdi", "kim", "kim_init", "kim_interactions", "kim_query",
                      "kim_param", "kim_property"}
FORBIDDEN_VARIABLE_STYLES = {"python", "getenv"}
OWN_FILES = {"log.lammps", "stk-lammps.json", "stk-lammps-input.json"}
MAX_SCRIPT_BYTES = 1024 * 1024
MAX_FILES = 100
MAX_NESTING = 8
MAX_SEED = 2 ** 31 - 1
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


class ScriptError(ValueError):
    pass


def _words(line):
    """Split one logical line into words as LAMMPS does: quotes group words, '#' outside quotes starts a comment."""
    words, current, quote, index, started = [], [], None, 0, False
    while index < len(line):
        if quote is None and line.startswith('"""', index):
            end = line.find('"""', index + 3)
            if end < 0:
                raise ScriptError("Unterminated triple quote")
            current.append(line[index + 3:end])
            started, index = True, end + 3
            continue
        char = line[index]
        if quote:
            if char == quote:
                quote = None
            else:
                current.append(char)
        elif char in "\"'":
            quote, started = char, True
        elif char == "#":
            break
        elif char.isspace():
            if started:
                words.append("".join(current))
                current, started = [], False
        else:
            current.append(char)
            started = True
        index += 1
    if quote:
        raise ScriptError("Unterminated quote")
    if started:
        words.append("".join(current))
    return words


def commands(text):
    """[(line number, words)] of a script; '&' at the end of a line continues it, and so does an open triple quote."""
    result, pending, first = [], "", None
    for number, raw in enumerate(text.splitlines(), 1):
        if first is None:
            first = number
        candidate = pending + raw
        if candidate.count('"""') % 2:
            pending = candidate + "\n"
            continue
        stripped = candidate.rstrip()
        if stripped.endswith("&"):
            pending = stripped[:-1] + " "
            continue
        words = _words(candidate)
        if words:
            result.append((first, words))
        pending, first = "", None
    if pending.strip():
        raise ScriptError("The script ends with a continued line or an open triple quote")
    return result


def _path_word(word):
    return word.startswith(("/", "~", "\\")) or bool(_DRIVE.match(word)) or ".." in re.split(r"[\\/]", word)


def _number(text, kind):
    try:
        value = int(text) if kind == "integer" else float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _nested(words):
    """The commands quoted inside ``if`` and ``run ... every``, which LAMMPS executes as input lines."""
    command = words[0]
    if command == "if":
        nested, index = [], 2
        while index < len(words):
            if words[index] in ("then", "else"):
                index += 1
            elif words[index] == "elif":
                index += 2
            else:
                nested.append(words[index])
                index += 1
        return nested
    if command == "run" and "every" in words:
        return [word for word in words[words.index("every") + 2:] if word != "NULL"]
    return []


class _Reader:
    def __init__(self, files):
        self.files = {posixpath.normpath(name): name for name in files}
        self.units, self.defaults, self.includes, self.texts = None, {}, [], []

    def target(self, where, command, name):
        normal = posixpath.normpath(name) if name and "$" not in name else None
        if normal not in self.files:
            raise ScriptError(f"{where}: {command} must name a file of the case")
        return self.files[normal]

    def check(self, text, label, depth=0):
        if depth > MAX_NESTING:
            raise ScriptError(f"{label}: commands are nested more than {MAX_NESTING} deep")
        for line, words in commands(text):
            self.command(f"{label} line {line}", words, depth)

    def command(self, where, words, depth):
        command, lowered = words[0], [word.lower() for word in words]
        if "$" in command or command.startswith("v_"):
            raise ScriptError(f"{where}: a command word must be written out, not taken from a variable")
        if command.lower() in FORBIDDEN_COMMANDS:
            raise ScriptError(f"{where}: STK does not run the '{command}' command")
        if command == "variable" and len(words) > 2:
            if "$" in words[2]:
                raise ScriptError(f"{where}: a variable style must be written out, not taken from a variable")
            if lowered[2] in FORBIDDEN_VARIABLE_STYLES:
                raise ScriptError(f"{where}: STK does not run Python or read the environment from a script")
        if command == "fix" and len(words) > 3 and lowered[3].startswith("python"):
            raise ScriptError(f"{where}: STK does not run Python from a script (fix {words[3]})")
        if command == "pair_style" and any(word == "python" or word.startswith("python/") for word in lowered[1:]):
            raise ScriptError(f"{where}: STK does not run Python from a script (pair_style python)")
        for word in words[1:]:
            if _path_word(word):
                raise ScriptError(f"{where}: paths must stay inside the case folder ({word[:80]})")
        if command in ("include", "jump") and len(words) > 1 and words[1] != "SELF":
            self.includes.append(self.target(where, command, words[1]))
        if command == "units" and len(words) > 1:
            self.units = words[1]
        if command == "variable" and len(words) > 2 and words[1] in PARAMETERS:
            name, style = words[1], words[2]
            if style != "index":
                raise ScriptError(f"{where}: declare {name} as 'variable {name} index <default>' so STK can set it")
            value = _number(words[3], PARAMETERS[name]) if len(words) == 4 else None
            if value is None:
                raise ScriptError(f"{where}: the default of {name} must be a single {PARAMETERS[name]}")
            self.defaults.setdefault(name, value)
        for text in _nested(words):
            self.check(text, f"{where} (quoted command)", depth + 1)


def check_script(text, files=(), read=None):
    """Check a script and, when ``read(name)`` gives the text of a case file, every file it includes.

    Returns {units, parameters: {name: default or None}, used: [names], includes: [files]}. ``files`` are the
    case's file names (POSIX, relative): ``include`` and ``jump`` must name one of them."""
    reader, pending, seen = _Reader(files), [("script", text)], set()
    while pending:
        label, body = pending.pop()
        if len(body.encode("utf-8")) > MAX_SCRIPT_BYTES:
            raise ScriptError(f"{label} exceeds 1 MiB")
        reader.texts.append(body)
        start = len(reader.includes)
        reader.check(body, label)
        for name in reader.includes[start:]:
            if name not in seen and read is not None:
                seen.add(name)
                if len(seen) > MAX_FILES:
                    raise ScriptError("The script includes more than 100 files")
                pending.append((name, read(name)))
    joined = "\n".join(reader.texts)
    used = sorted(name for name in PARAMETERS
                  if name in reader.defaults or re.search(r"(\$\{%s\}|\bv_%s\b)" % (name, name), joined))
    return {"units": reader.units, "parameters": {name: reader.defaults.get(name) for name in used}, "used": used,
            "includes": sorted(set(reader.includes))}


def check_parameters(values, used):
    """Values for a run: each parameter the script uses is set and valid; the others are empty."""
    for name, kind in PARAMETERS.items():
        value = values.get(name)
        if name not in used:
            if value is not None:
                raise ScriptError(f"The script does not use {name}; clear it in the row")
            continue
        if value is None:
            raise ScriptError(f"The script uses {name}; set it in the row")
        if kind == "integer":
            if type(value) is not int or value < 1 or (name == "seed" and value > MAX_SEED):
                raise ScriptError(f"{name} must be a positive integer" + (" below 2^31" if name == "seed" else ""))
        elif type(value) not in (int, float) or not math.isfinite(value) or (name != "pressure" and value <= 0):
            raise ScriptError(f"{name} must be finite" + ("" if name == "pressure" else " and positive"))
    if "sample_interval" in used and "steps" in used and values["steps"] < 3 * values["sample_interval"]:
        raise ScriptError("steps must cover at least three sample intervals")
    return {name: values[name] for name in used}


def format_value(value):
    """A -var value: integers as written, other numbers with full precision."""
    return str(value) if type(value) is int else repr(float(value))
