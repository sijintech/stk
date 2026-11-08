"""Content-bound HDF5 datasets in a MuFerro result, separate from DAT stems."""
from ..api import ConnectorError
from ..builtin import field_stats, select_frame


def descriptors(observation):
    from suan.data.model import Field
    from . import field_descriptor
    from .hdf5 import _field_meta
    grouped = {}
    for item in observation["fields"]:
        grouped.setdefault(item["name"], []).append(item)
    result = []
    for name, items in sorted(grouped.items()):
        shape, dtype = items[0]["shape"], items[0]["dtype"]
        if any(item["shape"] != shape or item["dtype"] != dtype for item in items):
            raise ConnectorError("An HDF5 field changes shape or dtype between steps", "invalid_data")
        frames = [{"step": item["step"], "time": None, "sources": {name: {
            **{key: observation[key] for key in ("path", "sha256", "size", "reader")},
            "selector": item["selector"]}}} for item in items]
        descriptor = field_descriptor(name, shape[:3], frames, shape[3])
        # Stable qualification prevents DAT and HDF5 from silently replacing one another.
        descriptor["id"] = "hdf5:" + name
        descriptor["fields"] = [Field(name, dtype=dtype, components=shape[3],
                                      **_field_meta(name, shape[3])).to_json()]
        result.append(descriptor)
    return result


class HDF5Handle:
    """An immutable metadata observation; later reads must match its container SHA."""

    def __init__(self, run, descriptor):
        self.run, self.descriptor = run, descriptor

    @property
    def frames(self):
        return [{"step": frame["step"], **next(iter(frame["sources"].values()))}
                for frame in self.descriptor["frames"]]

    def frame(self, selector):
        return select_frame(self.frames, selector)

    def read(self, *, frame=None, fields=None, region=None, stride=None, check=None,
             max_bytes=256 * 1024 * 1024):
        from .source import read
        chosen = self.frame(frame)
        name = self.descriptor["fields"][0]["name"]
        if fields is not None and name not in fields:
            raise ConnectorError("The HDF5 dataset does not contain the requested field", "invalid_param")
        image = read(self.run, chosen["path"], chosen["selector"], expected_sha256=chosen["sha256"],
                     region=region, stride=stride, max_bytes=max_bytes, check=check)
        image.id = self.descriptor["id"]
        return image

    def stats(self, *, frame=None, field=None):
        name = self.descriptor["fields"][0]["name"]
        if field not in (None, name):
            raise ConnectorError("The HDF5 dataset does not contain the requested field", "invalid_param")
        return field_stats(self.read(frame=frame), name)
