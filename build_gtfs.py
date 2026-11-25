#!/usr/bin/env python3
"""Create a deterministic, checked public Arriva GTFS extract for DAxxv.

Source is the public Dutch OVapi OpenOV GTFS feed. Nothing here modifies ProRail data.
"""
import csv
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

SOURCE = 'https://gtfs.ovapi.nl/openov-nl/gtfs-openov-nl.zip'
LINES = {'RS11', 'RS12', 'RS15', 'RS18', 'RE18'}
OUTPUT = 'DAxxv_Rail_GTFS_Limburg.zip'


def rows(z, member):
    with z.open(member) as stream:
        return list(csv.DictReader(io.TextIOWrapper(stream, encoding='utf-8-sig', newline='')))


def selected_bytes(z, member, allowed, first_column, stop_ids=None):
    with z.open(member) as source:
        header = source.readline()
        columns = next(csv.reader([header.decode('utf-8-sig')]))
        if columns[0] != first_column:
            raise ValueError('Unexpected first field of ' + member)
        yield header
        for line in source:
            # OVapi identifiers occupy column one, and are not quoted or comma-containing.
            value = line.split(b',', 1)[0].decode('utf-8')
            if value in allowed:
                if stop_ids is not None:
                    fields = line.split(b',', 3)
                    if len(fields) < 3:
                        raise ValueError('Malformed stop_times row')
                    stop_ids.add(fields[2].decode('utf-8'))
                yield line


def store(zout, name, chunks):
    zi = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = 0o644 << 16
    with zout.open(zi, 'w') as dest:
        for chunk in chunks:
            dest.write(chunk)


def build(input_path):
    dist = Path('dist')
    dist.mkdir(exist_ok=True)
    with zipfile.ZipFile(input_path) as src:
        required = {'agency.txt', 'routes.txt', 'trips.txt', 'stop_times.txt',
                    'stops.txt', 'shapes.txt', 'calendar_dates.txt'}
        missing = required.difference(src.namelist())
        if missing:
            raise ValueError('Missing required GTFS files: ' + str(sorted(missing)))
        routes = rows(src, 'routes.txt')
        matches = [r for r in routes if r.get('agency_id') == 'IFF:ARRIVA'
                   and r.get('route_short_name') in LINES and r.get('route_type') == '2']
        found_lines = {r['route_short_name'] for r in matches}
        missing_lines = LINES - found_lines
        if missing_lines:
            agencies = {r.get('agency_id', ''): r.get('agency_name', '')
                        for r in rows(src, 'agency.txt')}
            print('OVapi source route diagnostics:', file=sys.stderr)
            for line in sorted(LINES):
                candidates = [r for r in routes
                              if r.get('route_short_name', '').strip().upper() == line]
                if not candidates:
                    print(f'  {line}: absent from routes.txt', file=sys.stderr)
                else:
                    for r in candidates[:8]:
                        agency_id = r.get('agency_id', '')
                        print(f"  {line}: agency_id={agency_id!r}, "
                              f"agency_name={agencies.get(agency_id, '')!r}, "
                              f"route_type={r.get('route_type', '')!r}, "
                              f"route_id={r.get('route_id', '')!r}", file=sys.stderr)
                    if len(candidates) > 8:
                        print(f'    ... and {len(candidates) - 8} more', file=sys.stderr)
            summary = ', '.join(sorted(missing_lines))
            print(f'::error title=OVapi Arriva GTFS missing rail lines::'
                  f'Missing: {summary}; keeping last verified publication', file=sys.stderr)
            raise ValueError(f'Missing required Arriva rail lines: {summary}')
        route_map = {r['route_id']: r['route_short_name'] for r in matches}
        trips = set()
        services = set()
        shapes = set()
        counts = {line: 0 for line in sorted(LINES)}
        with src.open('trips.txt') as stream:
            for row in csv.DictReader(io.TextIOWrapper(stream, encoding='utf-8-sig', newline='')):
                name = route_map.get(row.get('route_id'))
                if name:
                    trips.add(row['trip_id'])
                    services.add(row['service_id'])
                    if row.get('shape_id'):
                        shapes.add(row['shape_id'])
                    counts[name] += 1
        if not all(counts.values()):
            empty = [line for line, count in counts.items() if count == 0]
            raise ValueError('No trips present for required line(s): ' + ', '.join(empty))
        parents = {r['stop_id']: r.get('parent_station', '') for r in rows(src, 'stops.txt')}
        stop_ids = set()
        filename = dist / OUTPUT
        with zipfile.ZipFile(filename, 'w', allowZip64=True) as dst:
            store(dst, 'trips.txt', selected_bytes(src, 'trips.txt', route_map, 'route_id'))
            store(dst, 'stop_times.txt', selected_bytes(src, 'stop_times.txt', trips, 'trip_id', stop_ids))
            if not stop_ids:
                raise ValueError('No stop times selected')
            pending = list(stop_ids)
            while pending:
                parent = parents.get(pending.pop())
                if parent and parent not in stop_ids:
                    stop_ids.add(parent)
                    pending.append(parent)
            store(dst, 'stops.txt', selected_bytes(src, 'stops.txt', stop_ids, 'stop_id'))
            store(dst, 'shapes.txt', selected_bytes(src, 'shapes.txt', shapes, 'shape_id'))
            store(dst, 'calendar_dates.txt', selected_bytes(src, 'calendar_dates.txt', services, 'service_id'))
            if 'calendar.txt' in src.namelist():
                store(dst, 'calendar.txt', selected_bytes(src, 'calendar.txt', services, 'service_id'))
            store(dst, 'agency.txt', selected_bytes(src, 'agency.txt', {'IFF:ARRIVA'}, 'agency_id'))
            store(dst, 'routes.txt', selected_bytes(src, 'routes.txt', route_map, 'route_id'))
            for name in ('feed_info.txt', 'licenses.txt', 'ticketing_identifiers.txt', 'ticketing_deep_links.txt'):
                if name in src.namelist():
                    store(dst, name, [src.read(name)])
        with zipfile.ZipFile(filename) as output:
            if output.testzip():
                raise ValueError('Generated GTFS archive failed CRC check')
        feed = rows(src, 'feed_info.txt')[0] if 'feed_info.txt' in src.namelist() else {}
    manifest = {
        'schema_version': 1, 'type': 'arriva_gtfs_schedule',
        'source': SOURCE, 'filename': OUTPUT,
        'sha256': hashlib.sha256(filename.read_bytes()).hexdigest(),
        'size_bytes': filename.stat().st_size,
        'lines': sorted(LINES), 'trips_by_line': counts,
        'total_trips': sum(counts.values()),
        'feed_version': feed.get('feed_version', ''),
        'feed_start_date': feed.get('feed_start_date', ''),
        'feed_end_date': feed.get('feed_end_date', ''),
    }
    (dist / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('Usage: build_gtfs.py /path/to/gtfs-openov-nl.zip')
    build(sys.argv[1])
