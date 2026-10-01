"""Build a geometry cache from a (large) ASCII FBX exported by Navisworks.

    python nwdcache.py model.fbx            -> model.cache/   (read once)
    python nwdcache.py model.fbx --stats    -> also print what the small objects are

The FBX is streamed line by line, so memory use does not grow with the file.
Cache layout (all coordinates in mm, relative to meta['origin']):
    verts.f32   (N,3) float32  welded vertices of every object
    tris.i32    (M,3) int32    triangles, indices local to their object
    cpts.f32    (K,3) float32  curve points
    objects.npz  per object: vert_off, vert_cnt, tri_off, tri_cnt, bbox(6),
                 layer (index into meta['layers']), flags, name (index)
    curves.npz   per curve:  pt_off, pt_cnt, bbox(6), layer, flags, name
    meta.json    origin, layers, names, counts
flags: 1 = bolt (by name), 2 = maintenance space (MSPA), 4 = centre line (CL)
"""
import os, re, sys, json, time, argparse, collections
import numpy as np
from fbxascii import local_matrix, geometric_matrix

BOLT = 1
SPACE = 2
CENTRE = 4

# Japanese characters in names were destroyed by the export; the ASCII
# parts survive: "(1?_3?)_M10_P" bolt sets, "U???JIS?(15A)" U-bolts.
BOLT_RE = re.compile(r'(_M\d+_[PT](_\d+)?$)|(^U.*JIS.*\(\d+A\)$)|\bBOLT|\bNUT\b|WASHER', re.I)
FILE_RE = re.compile(r'\.(nwc|nwd|nwf|dwg|dgn|rvt|ifc|dxf)$', re.I)
XFORM = {b'Lcl Translation', b'Lcl Rotation', b'Lcl Scaling', b'PreRotation', b'PostRotation',
         b'RotationOffset', b'RotationPivot', b'ScalingOffset', b'ScalingPivot', b'RotationOrder',
         b'GeometricTranslation', b'GeometricRotation', b'GeometricScaling'}
ITEMTYPE = '項目 - 類型'.encode('utf-8')


def parse_p(line):
    """'P: "Name", "type", "label", "flags",v1,v2,v3' -> (name, [floats])."""
    s = line.strip()[3:]
    q = s.split(b'"')
    name = q[1]
    tail = q[-1].lstrip(b',')
    vals = [float(x) for x in tail.split(b',') if x.strip()] if tail else []
    return name, vals


def stream(path, tmpdir):
    """Pass 1: models, geometry arrays (spilled to disk), connections."""
    models = {}          # id -> [name, kind, {prop: vals}, itemtype]
    geoms = {}           # id -> (kind, v_off, v_cnt, i_off, i_cnt)
    conns = []           # (child, parent)
    fv = open(os.path.join(tmpdir, 'raw_v.f64'), 'wb')
    fi = open(os.path.join(tmpdir, 'raw_i.i32'), 'wb')
    v_tot = i_tot = 0
    section = None
    cur = None           # ('M', id) / ('G', id)
    pending = None       # array name whose 'a:' line comes next
    gv = gi = None
    gkind = None
    n = 0
    bad = 0
    expect = 0
    t0 = time.time()
    with open(path, 'rb') as f:
        head = f.read(18)
        if head == b'Kaydara FBX Binary':
            sys.exit('%s is a binary FBX; export it from Navisworks as ASCII FBX' % path)
        f.seek(0)
        for line in f:
            n += 1
            if n % 1000000 == 0:
                print('  %dM lines, %.0fs' % (n // 1000000, time.time() - t0), flush=True)
            if not line.startswith(b'\t'):
                if line.endswith(b'{\n') or line.endswith(b'{\r\n'):
                    section = line.split(b':')[0]
                continue
            if section == b'Objects':
                if line.startswith(b'\tModel: '):
                    q = line.split(b'"')
                    mid = int(line[8:line.index(b',')])
                    models[mid] = [q[1].split(b'::', 1)[-1].decode('utf-8', 'replace'),
                                   q[3].decode(), {}, '']
                    cur = ('M', mid)
                elif line.startswith(b'\tGeometry: '):
                    q = line.split(b'"')
                    gid = int(line[11:line.index(b',')])
                    gkind = q[3].decode()
                    cur = ('G', gid)
                    gv = gi = None
                elif line.startswith(b'\t}'):
                    if cur and cur[0] == 'G':
                        if gv is not None:
                            gv.tofile(fv)
                            if gi is not None:
                                gi.tofile(fi)
                            geoms[cur[1]] = (gkind, v_tot, len(gv) // 3, i_tot,
                                             0 if gi is None else len(gi))
                            v_tot += len(gv) // 3
                            i_tot += 0 if gi is None else len(gi)
                    cur = None
                elif line.startswith(b'\t\t'):
                    if cur is None:
                        continue
                    s = line.lstrip()
                    if cur[0] == 'M':
                        if s.startswith(b'P: "'):
                            name = s[4:s.index(b'"', 4)]
                            if name in XFORM:
                                _, vals = parse_p(line)
                                models[cur[1]][2][name.decode()] = vals
                            elif name == ITEMTYPE:
                                models[cur[1]][3] = s.split(b'"')[-2].decode('utf-8', 'replace')
                    else:
                        if pending and s.startswith(b'a:'):
                            # long arrays wrap: a line ending in ',' continues on the next
                            buf = s[2:].rstrip()
                            if buf.endswith(b','):
                                parts = [buf]
                                while parts[-1].endswith(b','):
                                    parts.append(next(f).strip())
                                    n += 1
                                buf = b''.join(parts)
                            got = buf.count(b',') + 1
                            if got != expect:
                                bad += 1
                                if bad <= 5:
                                    print('  WARNING line %d: %s has %d values, header says %d'
                                          % (n, pending.decode(), got, expect))
                            if pending == b'Vertices':
                                gv = np.fromstring(buf, dtype=np.float64, sep=',')
                            elif pending == b'Points':
                                gv = np.fromstring(buf, dtype=np.float64, sep=',').reshape(-1, 4)[:, :3].ravel()
                            elif pending == b'PolygonVertexIndex':
                                gi = np.fromstring(buf, dtype=np.int64, sep=',').astype(np.int32)
                            pending = None
                        elif s.startswith((b'Vertices: *', b'PolygonVertexIndex: *', b'Points: *')):
                            pending = s.split(b':')[0]
                            expect = int(s.split(b'*')[1].split()[0])
            elif section == b'Connections':
                if line.startswith(b'\tC: "OO"'):
                    p = line.split(b',')
                    conns.append((int(p[1]), int(p[2])))
    fv.close()
    fi.close()
    print('read %d lines in %.0fs: %d models, %d geometries, %d connections, %d bad arrays'
          % (n, time.time() - t0, len(models), len(geoms), len(conns), bad))
    return models, geoms, conns, v_tot, i_tot


def triangulate(idx):
    """FBX PolygonVertexIndex (last index of each polygon is ~i) -> (T,3) fan."""
    ends = np.nonzero(idx < 0)[0]
    real = np.where(idx < 0, ~idx, idx)
    starts = np.concatenate(([0], ends[:-1] + 1))
    cnt = ends - starts + 1
    ntri = np.maximum(cnt - 2, 0)
    if ntri.sum() == 0:
        return np.zeros((0, 3), np.int64)
    first = np.repeat(starts, ntri)
    k = np.arange(ntri.sum()) - np.repeat(np.cumsum(ntri) - ntri, ntri) + 1
    return np.stack([real[first], real[first + k], real[first + k + 1]], axis=1)


def build(path, outdir, stats):
    os.makedirs(outdir, exist_ok=True)
    models, geoms, conns, v_tot, i_tot = stream(path, outdir)
    parent = {}
    users = collections.defaultdict(list)     # geometry -> models using it
    for c, p in conns:
        if c in models:
            parent[c] = p
        elif c in geoms and p in models:
            users[c].append(p)

    world = {}

    def wmat(mid):
        if mid in world:
            return world[mid]
        M = local_matrix(models[mid][2])
        p = parent.get(mid)
        if p in models:
            M = wmat(p) @ M
        world[mid] = M
        return M

    sys.setrecursionlimit(100000)
    chain = {}

    def names(mid):
        if mid in chain:
            return chain[mid]
        p = parent.get(mid)
        c = (names(p) if p in models else []) + [models[mid][0]]
        chain[mid] = c
        return c

    def classify(mid):
        ch = names(mid)
        flags = 0
        if any(BOLT_RE.search(x) for x in ch):
            flags |= BOLT
        if any('MSPA' in x for x in ch):
            flags |= SPACE
        fi = max((i for i, x in enumerate(ch) if FILE_RE.search(x)), default=-1)
        src = ch[fi] if fi >= 0 else (ch[0] if ch else '')
        sub = ch[fi + 1] if 0 <= fi < len(ch) - 2 else ''
        if sub == 'CL':
            flags |= CENTRE
        layer = re.sub(FILE_RE, '', src) + ('/' + sub if sub else '')
        return flags, layer, ' / '.join(ch[max(fi, 0):])

    raw_v = np.memmap(os.path.join(outdir, 'raw_v.f64'), np.float64, 'r', shape=(v_tot, 3)) if v_tot else None
    raw_i = np.memmap(os.path.join(outdir, 'raw_i.i32'), np.int32, 'r', shape=(i_tot,)) if i_tot else None

    origin = None
    layers, layer_ix = [], {}
    names_l, name_ix = [], {}
    obj = collections.defaultdict(list)
    crv = collections.defaultdict(list)
    fv = open(os.path.join(outdir, 'verts.f32'), 'wb')
    ft = open(os.path.join(outdir, 'tris.i32'), 'wb')
    fc = open(os.path.join(outdir, 'cpts.f32'), 'wb')
    nv = nt = nc = 0
    t0 = time.time()
    done = 0
    for gid, (kind, vo, vc, io, ic) in geoms.items():
        for mid in users.get(gid, []):
            done += 1
            if done % 5000 == 0:
                print('  %d objects, %.0fs' % (done, time.time() - t0), flush=True)
            M = wmat(mid) @ geometric_matrix(models[mid][2])
            v = np.array(raw_v[vo:vo + vc])      # a copy: no view keeps the file open
            w = v @ M[:3, :3].T + M[:3, 3]
            if origin is None:
                origin = np.round(w[0] / 1000.0) * 1000.0
            w = w - origin
            flags, layer, full = classify(mid)
            if layer not in layer_ix:
                layer_ix[layer] = len(layers)
                layers.append(layer)
            if full not in name_ix:
                name_ix[full] = len(names_l)
                names_l.append(full)
            lo, hi = w.min(0), w.max(0)
            if kind == 'Mesh' and ic:
                tri = triangulate(np.array(raw_i[io:io + ic], dtype=np.int64))
                if not len(tri):
                    continue
                key = np.round(w / 0.01).astype(np.int64)
                uk, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
                inv = inv.ravel()
                tri = inv[tri]
                tri = tri[(tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])]
                if not len(tri):
                    continue
                pv = w[first].astype(np.float32)
                pv.tofile(fv)
                tri.astype(np.int32).tofile(ft)
                o = obj
                o['vert_off'].append(nv); o['vert_cnt'].append(len(pv))
                o['tri_off'].append(nt); o['tri_cnt'].append(len(tri))
                nv += len(pv); nt += len(tri)
            elif kind == 'NurbsCurve' and vc >= 2:
                w.astype(np.float32).tofile(fc)
                o = crv
                o['pt_off'].append(nc); o['pt_cnt'].append(vc)
                nc += vc
            else:
                continue
            o['bbox'].append(np.r_[lo, hi])
            o['layer'].append(layer_ix[layer])
            o['flags'].append(flags | (CENTRE if kind == 'NurbsCurve' and flags & CENTRE else 0))
            o['name'].append(name_ix[full])
            o['itemtype'].append(models[mid][3])
    fv.close(); ft.close(); fc.close()
    for mm in (raw_v, raw_i):
        if mm is not None:
            mm._mmap.close()
    del raw_v, raw_i
    for f in ('raw_v.f64', 'raw_i.i32'):
        os.remove(os.path.join(outdir, f))

    def save(fn, d, ints):
        arrs = {}
        for k, v in d.items():
            if k == 'itemtype':
                continue
            arrs[k] = np.array(v, dtype=np.float64 if k == 'bbox' else np.int64)
        np.savez(os.path.join(outdir, fn), **arrs)

    save('objects.npz', obj, True)
    save('curves.npz', crv, True)
    itypes = sorted(set(obj['itemtype']) | set(crv['itemtype']))
    meta = dict(source=os.path.abspath(path), origin=origin.tolist(), layers=layers, names=names_l,
                n_objects=len(obj['tri_cnt']), n_curves=len(crv['pt_cnt']),
                n_verts=nv, n_tris=nt, n_cpts=nc)
    with open(os.path.join(outdir, 'meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False)
    print('cache %s: %d objects, %d triangles, %d curves, origin %s, %.0fs'
          % (outdir, meta['n_objects'], nt, meta['n_curves'], origin.tolist(), time.time() - t0))
    if stats:
        report(outdir)


def report(outdir, small=50.0):
    """What would a size filter remove, and what does the bolt rule catch."""
    meta = json.load(open(os.path.join(outdir, 'meta.json'), encoding='utf-8'))
    o = np.load(os.path.join(outdir, 'objects.npz'))
    bb = o['bbox']
    size = (bb[:, 3:] - bb[:, :3]).max(1)
    flags = o['flags']
    bolt = (flags & BOLT) != 0
    print('\nobjects %d, triangles %d' % (len(size), o['tri_cnt'].sum()))
    print('bolt rule: %d objects, %d triangles' % (bolt.sum(), o['tri_cnt'][bolt].sum()))
    sm = (size < small) & ~bolt
    print('not bolts but smaller than %gmm: %d objects, %d triangles' % (small, sm.sum(), o['tri_cnt'][sm].sum()))

    def group(mask, title):
        c = collections.Counter()
        t = collections.Counter()
        for i in np.nonzero(mask)[0]:
            parts = meta['names'][o['name'][i]].split(' / ')
            key = ' / '.join(parts[-3:-1]) if len(parts) > 2 else parts[-1]
            c[key] += 1
            t[key] += o['tri_cnt'][i]
        print('\n%s (top 40 by count; owner / group)' % title)
        for k, n in c.most_common(40):
            print('  %6d objects %8d tris  %s' % (n, t[k], k))
    group(bolt, 'caught by the bolt rule')
    group(sm, 'smaller than %gmm, not bolts' % small)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('fbx')
    ap.add_argument('--stats', action='store_true')
    ap.add_argument('--report-only', action='store_true', help='skip building, just report on the cache')
    a = ap.parse_args()
    out = a.fbx.rsplit('.', 1)[0] + '.cache'
    if a.report_only:
        report(out)
    else:
        build(a.fbx, out, a.stats)
