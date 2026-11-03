# Explicit helper installation

The helper is a separate MIT program. The surrounding desktop remains GPL;
libdatachannel, its static dependencies and every bundled runtime library retain
their own licenses. The Python wheel contains the passive installation verifier,
not a helper binary, a dependency installer or third-party source archives.

Linux installation is opt-in (`STK_PEER_INSTALL=ON`). It installs only the helper
and its MIT text; an adversarial test peer is never installed. Configure a fresh
external build directory with explicit, pre-provisioned dependency locations:

```sh
cmake -S desktop/engine/lib/stk_peer -B /absolute/fresh-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DSTK_PEER_INSTALL=ON \
  -DCMAKE_PREFIX_PATH=/absolute/dependency-prefix
cmake --build /absolute/fresh-build --target stk-peer-transport --parallel 2
python3 desktop/engine/lib/stk_peer/package_helper.py \
  --build /absolute/fresh-build --prefix /absolute/absent-installation \
  --lock /absolute/reviewed-package-lock.json
```

Headers and libraries must belong to the same target platform/architecture. An
extracted distribution sysroot may require its explicit multiarch include path.
The Linux helper has `DT_RPATH=$ORIGIN/../lib` and no absolute install RUNPATH;
the packager removes dependency build RPATHs only from new copied libraries.
Existing build directories and dependency installations are not modified.

The reviewed lock is a build input, not a trusted runtime manifest. Its closed
release content must be produced from the builder's verified exact package
metadata. `package_helper.py` accepts the following fields:

| Field | Content |
|---|---|
| `format` | `stk.peer-helper-package-lock/1` |
| `platform`, `architecture` | `linux`, and `x86_64` or `aarch64` |
| `libraries` | Explicit absolute ordinary `path`, SHA-256, `soname`, component ID |
| `components` | ID, exact version, human-readable license scope, `notices`, `sources` |
| notice/source/build input | Explicit absolute `path`, SHA-256 and portable `name` |
| `build_files` | Build instructions, source provenance and dependency inventory |
| `host_requirements` | Explicit host runtime prerequisites and symbol-version floors |

Every component must include full notices and local corresponding-source
artifacts. An Ubuntu component includes its exact-version `.dsc`, all original
archives and packaging patches named in its SHA-256 section. Keep the official
metadata URLs, archive hashes and verification limits in bundled provenance.
Extract with `dpkg-source -x package_version.dsc`; its `debian/rules` and control
files retain build options and dependency information. Upstream-built components
include their exact source archive and build instructions, including static
usrsctp/header-only plog and nlohmann/json. Include referred common-license texts,
exceptions and any required component notices. Do not replace this with an
unverified source URL or assume a package-wide license label covers every file.

The ELF closure excludes only the explicitly listed host loader/glibc and C++
runtime prerequisites. All other observed ELF dependencies are bundled with
their own notices and sources. Dynamic providers, configuration and modules can
have additional requirements: the package's actual runtime acceptance must state
which paths were exercised. In particular, same-machine ICE tests do not prove
site proxy, NAT, TURN/TLS, Kerberos, PKCS#11 or arbitrary GIO plugin behavior.

The packager refuses an existing prefix, verifies all locked input hashes and
writes `helper-manifest.json` last. A failed partial prefix stays present without
a completed manifest. The manifest records exact ABI `stk.peer-helper-ipc/1`,
protocol `stk.peer/1`, OS, architecture, executable and every installed file's
size/hash/role/component, plus licenses/sources and host requirements. It contains
relative installed paths only. Keep completed installations immutable.

```python
from suan.peer.helper_installation import load_helper_installation
from suan.peer.transport import NativeTransport

installed = load_helper_installation(
    "/absolute/selected-installation", expected_manifest_sha256=trusted_digest)
# A separate explicit user action may then construct/start NativeTransport.
# Pass installed.executable as its helper argument.
```

The optional digest must come from a separately trusted release channel.
Self-consistent hashes do not authenticate a publisher, and validation is not a
sandbox against the installation owner replacing bytes after verification.
Rejected errors do not echo manifest contents or private paths. Missing,
incompatible, ambiguous, linked or modified files fail closed with no fallback.

The current builder and relocation proof cover Linux only. macOS/Windows package
assembly, signing, native dependency closure and clean-machine execution require
separate actual-platform delivery. Merely using an OS name in a manifest is not
such evidence.
