"""Compare paged queries with full-snapshot reads using disposable synthetic data.

Run from the repository root with an installed STK Python environment:
  python tools/benchmark_table_query.py --rows 10000
  python tools/benchmark_table_query.py --rows 10000 --mode opening
No user project, model endpoint, or external resource is opened.
"""
import argparse
from functools import cmp_to_key
import gc
import json
from pathlib import Path
import platform
from tempfile import TemporaryDirectory
from time import perf_counter
import tracemalloc
from uuid import UUID

from suan.project import ProjectStore
from suan.project.table_workbench import compare_records, matches, view_definition


def measure(operation):
    gc.collect()
    tracemalloc.start()
    started = perf_counter()
    try:
        result = operation()
        elapsed = perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, {'seconds': round(elapsed, 6), 'python_peak_bytes': peak}


def benchmark(rows, mode='query'):
    serial = 0

    def identity():
        nonlocal serial
        serial += 1
        return str(UUID(int=serial))

    with TemporaryDirectory(prefix='stk-query-benchmark-') as directory:
        store = ProjectStore.create(Path(directory) / 'project', 'Public synthetic benchmark')
        tables, field_sets = [], []
        # Seed literal storage directly so write-history/evaluation setup is not
        # included in read measurements. No existing database is modified.
        with store._connect(write=True) as db:
            for _ in range(2):
                table = identity()
                fields = [identity() for _ in range(8)]
                tables.append(table)
                field_sets.append(fields)
                db.execute('INSERT INTO tables VALUES (?,?)', (table, 'Synthetic'))
                db.executemany('INSERT INTO fields VALUES (?,?,?,?,?)', [
                    (field, table, str(index), 'integer' if index == 0 else 'text', None)
                    for index, field in enumerate(fields)])
                for index in range(rows):
                    record = identity()
                    db.execute('INSERT INTO records VALUES (?,?)', (record, table))
                    db.executemany('INSERT INTO cells VALUES (?,?,?,?)', [
                        (table, record, field, json.dumps(index if column == 0 else 'public synthetic text; ' * 12))
                        for column, field in enumerate(fields)])
        reports = []
        if mode in {'opening', 'all'}:
            before, baseline = measure(store.snapshot)

            def first_page():
                structure = store.catalog()
                records = store.read_table(tables[0], expected_revision=structure['project']['revision'], limit=200)
                return structure, records

            (structure, records), paged = measure(first_page)
            assert records['table']['records'] == before['tables'][0]['records'][:200]
            assert structure['project'] == before['project']
            for metadata, table in zip(structure['tables'], before['tables'], strict=True):
                assert metadata['fields'] == table['fields']
                assert metadata['record_count'] == len(table['records'])
            wire_bytes = lambda result: len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8'))
            baseline['response_json_bytes'] = wire_bytes(before)
            paged['response_json_bytes'] = wire_bytes(structure) + wire_bytes(records)
            reports.append({'mode': 'opening', 'full_snapshot_reference': baseline, 'catalog_and_record_page': paged,
                            'equal_records_and_metadata': True, 'returned_records': len(records['table']['records']),
                            'total_records': 2 * rows, 'paged_requests': 2})
            del before, structure, records
        for query_mode in (() if mode == 'opening' else ('page', 'filter', 'sort')):
            definition = {'version': 1, 'kind': 'grid'}
            if query_mode == 'filter':
                definition['filters'] = {'field_id': field_sets[0][0], 'op': 'gte', 'value': rows // 2}
            if query_mode == 'sort':
                definition['sorts'] = [{'field_id': field_sets[0][0], 'direction': 'desc'}]

            def reference():
                table = store.snapshot()['tables'][0]
                view, _ = view_definition(definition, table['fields'])
                records = [record for record in table['records'] if matches(record, view['filters'])]
                records.sort(key=cmp_to_key(lambda a, b: compare_records(a, b, view['sorts'])))
                return len(records), records[100:300]

            before, baseline = measure(reference)
            after, paged = measure(lambda: store.table.query(tables[0], expected_revision=0,
                                                             definition=definition, offset=100, limit=200))
            assert before == (after['total'], after['records'])
            reports.append({'mode': query_mode, 'full_snapshot_reference': baseline, 'paged_query': paged,
                            'equal_records': True, 'returned_records': len(after['records'])})
        return {'python': platform.python_version(), 'tables': 2, 'rows_per_table': rows,
                'fields_per_table': 8, 'offset': 0 if mode == 'opening' else 100, 'limit': 200,
                'measurement': 'backend elapsed time and traced Python allocations; excludes SQLite native memory and native UI',
                'results': reports}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows', type=int, default=10000)
    parser.add_argument('--mode', choices=('query', 'opening', 'all'), default='query')
    args = parser.parse_args()
    if not 1000 <= args.rows <= 100000:
        parser.error('--rows must be between 1000 and 100000')
    print(json.dumps(benchmark(args.rows, args.mode), indent=2))
