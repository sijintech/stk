"""Read selected table records and their scalar dependency closure in one transaction.

The caller owns the read transaction and revision. This does not persist rebuilt
evaluation caches or read unrelated tables' cell contents.
"""
import json

from .evaluation import dependencies, evaluate
from .field_types import read_options


READ_BATCH = 128  # Also fits SQLite builds with the historical 999-variable limit.


def batches(values):
    for start in range(0, len(values), READ_BATCH):
        yield values[start:start + READ_BATCH]


def placeholders(values):
    return ",".join("?" for _ in values)


class TableReader:
    def __init__(self, db, table_id, revision, version):
        self.db, self.table_id, self.revision, self.version = db, table_id, revision, version
        self.project_id = db.execute("SELECT id FROM project").fetchone()[0]
        self._fields = {}
        for row in db.execute("SELECT * FROM fields WHERE table_id=? ORDER BY rowid", (table_id,)):
            self._add_field(row)
        self.fields = [{key: value for key, value in field.items() if key not in {"table_id", "_project_id"}}
                       for field in self._fields.values()]

    def _add_field(self, row):
        field = dict(row)
        if self.version >= 14:
            field["options"] = read_options(self.db, field["id"], field["type"])
            field["_project_id"] = self.project_id
        self._fields[field["id"]] = field

    def records(self, identities, field_ids=None):
        """Keep full typed values for the requested fields; None means every field.

        Filters/sorts can project a few fields while a final page retains the
        complete record contract, including hidden columns and definitions.
        """
        output = {identity: {"id": identity, "values": {}} for identity in identities}
        if not output or field_ids == set():
            return list(output.values())
        literals, definitions, cached = {}, {}, {}
        record_map = {identity: {"id": identity, "table_id": self.table_id} for identity in identities}

        def definition(row):
            key = row["record_id"], row["field_id"]
            definitions[key] = json.loads(row["definition"])
            if row["result"] is not None:
                try:
                    cached[key] = json.loads(row["result"])
                except (ValueError, RecursionError):
                    pass  # Same rebuild-on-read behavior as ProjectStore.snapshot.

        for group in batches(identities):
            params = list(group)
            where = "record_id IN (" + placeholders(group) + ")"
            if field_ids is not None:
                ordered_fields = sorted(field_ids)
                where += " AND field_id IN (" + placeholders(ordered_fields) + ")"
                params.extend(ordered_fields)
            for row in self.db.execute("SELECT record_id,field_id,value FROM cells WHERE " + where, params):
                key = row["record_id"], row["field_id"]
                literals[key] = json.loads(row["value"])
                output[key[0]]["values"][key[1]] = literals[key]
            if self.version >= 2:
                for row in self.db.execute("SELECT record_id,field_id,definition,result FROM definitions "
                                           "LEFT JOIN evaluations USING(record_id,field_id) WHERE " + where, params):
                    definition(row)
        requested_definitions = list(definitions)

        # Even a cached target needs its dependency closure: a corrupt/missing
        # ancestor cache must invalidate downstream observations just as in a
        # whole-project snapshot. Exact cell joins avoid loading an entire source
        # record when only one of its fields is referenced.
        seen = set(literals) | definitions.keys()
        pending = set().union(*(dependencies(value) for value in definitions.values())) - seen
        while pending:
            next_pending = set()
            for group in batches(sorted(pending)):
                seen.update(group)
                missing_fields = sorted({key[1] for key in group} - self._fields.keys())
                for row in self.db.execute("SELECT * FROM fields WHERE id IN (" + placeholders(missing_fields) + ")", missing_fields):
                    self._add_field(row)
                missing_records = sorted({key[0] for key in group} - record_map.keys())
                for row in self.db.execute("SELECT * FROM records WHERE id IN (" + placeholders(missing_records) + ")", missing_records):
                    record_map[row["id"]] = dict(row)
                values = ",".join("(?,?)" for _ in group)
                sql = ("WITH wanted(record_id,field_id) AS (VALUES " + values + ") "
                       "SELECT wanted.record_id,wanted.field_id,c.value,d.definition,e.result FROM wanted "
                       "LEFT JOIN cells c USING(record_id,field_id) "
                       "LEFT JOIN definitions d USING(record_id,field_id) "
                       "LEFT JOIN evaluations e USING(record_id,field_id)")
                for row in self.db.execute(sql, [identity for key in group for identity in key]):
                    key = row["record_id"], row["field_id"]
                    if row["value"] is not None:
                        literals[key] = json.loads(row["value"])
                    if row["definition"] is not None:
                        definition(row)
                        next_pending.update(dependencies(definitions[key]))
            pending = next_pending - seen

        cache, _ = evaluate(self._fields, record_map, literals, definitions, cached, (), self.revision)
        for record_id, field_id in requested_definitions:
            record = output[record_id]
            record.setdefault("definitions", {})[field_id] = definitions[(record_id, field_id)]
            result = cache[(record_id, field_id)]
            record.setdefault("evaluations", {})[field_id] = result
            if result["state"] == "ok":
                record["values"][field_id] = result["value"]
        return list(output.values())
