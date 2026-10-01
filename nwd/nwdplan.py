"""Plan drawings (DXF) of one area of a model cached by nwdcache.py.

    python nwdplan.py CACHE info
    python nwdplan.py CACHE probe X Y Z [--radius 200] [--align pairs.txt]
    python nwdplan.py CACHE align pairs.txt
    python nwdplan.py CACHE plan [--rect X1 Y1 X2 Y2] [--cut Z] [--bottom Z] [options]
        (no --rect and no --boxes: the whole model)
    python nwdplan.py CACHE plan --boxes boxes.txt [--align pairs.txt] [options]

Coordinates: without --align everything is in the model's own (Navisworks)
coordinates; with --align, rects, boxes, --cut/--bottom and the DXF are in
E3D coordinates (E/N/U, mm; W and S negative).

pairs.txt, one common point per line (2 or more lines for a rotation):
    nwdX nwdY nwdZ   e3dE e3dN e3dU   [label]
boxes.txt, one plan per line (rotated frames allowed):
    NAME  E N U  XLEN YLEN ZLEN  XDIR_E XDIR_N
    centre, full lengths, the box's X axis in plan; the plan is cut at the
    box top and drops what is below the box bottom.

Plan options:
    --cut Z / --bottom Z   override the elevation range
    --min-size 50          skip objects whose largest size is under this (mm);
                           never applied to layers named *PIP* (small-bore piping)
    --keep-bolts           keep objects the bolt rule caught
    --hidden               also write hidden lines (layer *_HIDDEN, off)
    --res 5                visibility grid, mm per pixel
    --out DIR              where the DXF/PNG go (default: next to the cache)
"""
import os, re, sys, json, math, time, argparse, zlib
import numpy as np
import ezdxf
import shapely
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union, polygonize

BOLT, SPACE, CENTRE = 1, 2, 4
TOL = 5.0            # mm, depth tolerance for visibility


# --------------------------------------------------------------- cache
class Cache:
    def __init__(self, d):
        self.dir = d
        self.meta = json.load(open(os.path.join(d, 'meta.json'), encoding='utf-8'))
        self.origin = np.array(self.meta['origin'])
        self.obj = dict(np.load(os.path.join(d, 'objects.npz')))
        self.crv = dict(np.load(os.path.join(d, 'curves.npz')))
        m = self.meta
        self.verts = np.memmap(os.path.join(d, 'verts.f32'), np.float32, 'r', shape=(m['n_verts'], 3)) \
            if m['n_verts'] else np.zeros((0, 3), np.float32)
        self.tris = np.memmap(os.path.join(d, 'tris.i32'), np.int32, 'r', shape=(m['n_tris'], 3)) \
            if m['n_tris'] else np.zeros((0, 3), np.int32)
        self.piping_layer = np.array([bool(re.search('pip', x, re.I)) for x in self.meta['layers']] + [False])
        self.cpts = np.memmap(os.path.join(d, 'cpts.f32'), np.float32, 'r', shape=(m['n_cpts'], 3)) \
            if m['n_cpts'] else np.zeros((0, 3), np.float32)


# ----------------------------------------------------------- transforms
class Align:
    """NWD world -> E3D world: rotation about Z, then translation."""

    def __init__(self, theta=0.0, t=(0.0, 0.0, 0.0)):
        self.c, self.s = math.cos(theta), math.sin(theta)
        self.theta = theta
        self.t = np.array(t, float)

    def apply(self, p):
        p = np.asarray(p, float)
        x = self.c * p[..., 0] - self.s * p[..., 1] + self.t[0]
        y = self.s * p[..., 0] + self.c * p[..., 1] + self.t[1]
        return np.stack([x, y, p[..., 2] + self.t[2]], -1)

    def invert(self, q):
        q = np.asarray(q, float)
        x, y = q[..., 0] - self.t[0], q[..., 1] - self.t[1]
        return np.stack([self.c * x + self.s * y, -self.s * x + self.c * y, q[..., 2] - self.t[2]], -1)


def read_pairs(path):
    P, Q, L = [], [], []
    for line in open(path, encoding='utf-8-sig'):
        line = line.split('#')[0].strip()
        if not line:
            continue
        f = re.split(r'[\s,]+', line)
        nums = [float(x) for x in f[:6]]
        P.append(nums[:3]); Q.append(nums[3:6]); L.append(' '.join(f[6:]))
    return np.array(P), np.array(Q), L


def fit_align(P, Q):
    if len(P) == 1:
        return Align(0.0, Q[0] - P[0])
    cp, cq = P[:, :2].mean(0), Q[:, :2].mean(0)
    a, b = P[:, :2] - cp, Q[:, :2] - cq
    th = math.atan2((a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]).sum(), (a * b).sum())
    c, s = math.cos(th), math.sin(th)
    t2 = cq - np.array([c * cp[0] - s * cp[1], s * cp[0] + c * cp[1]])
    return Align(th, (t2[0], t2[1], (Q[:, 2] - P[:, 2]).mean()))


def report_align(P, Q, L, al):
    print('rotation %.4f deg, translation E %.1f N %.1f U %.1f'
          % (math.degrees(al.theta), *al.t))
    if len(P) == 1:
        print('one point only: translation, no rotation assumed - give 2 or more points to check')
    R = al.apply(P) - Q
    for i in range(len(P)):
        print('  %-20s residual dE %7.1f dN %7.1f dU %7.1f  (%.1f mm)'
              % (L[i] or 'point %d' % (i + 1), *R[i], np.linalg.norm(R[i])))
    if len(P) >= 2:
        dp = np.linalg.norm(P[:, None, :2] - P[None, :, :2], axis=-1)
        dq = np.linalg.norm(Q[:, None, :2] - Q[None, :, :2], axis=-1)
        m = dp > 1
        if m.any():
            r = dq[m] / dp[m]
            print('distance ratio E3D/NWD %.5f .. %.5f (1.0 = same units)' % (r.min(), r.max()))


class Frame:
    """Plan frame: box centre (cx, cy), X axis angle; u, v local, z kept."""

    def __init__(self, cx, cy, ang):
        self.cx, self.cy = cx, cy
        self.c, self.s = math.cos(ang), math.sin(ang)

    def to_local(self, p):
        x, y = p[..., 0] - self.cx, p[..., 1] - self.cy
        return np.stack([self.c * x + self.s * y, -self.s * x + self.c * y, p[..., 2]], -1)

    def to_world2(self, u, v):
        return self.cx + self.c * u - self.s * v, self.cy + self.s * u + self.c * v


# ------------------------------------------------------------ geometry
def clip_tris(V, oid, z, keep_below, want_segs):
    """Clip triangles (T,3,3) to z. Returns kept triangles, their object ids
    and the cut segments ((S,2,3), object ids) when want_segs."""
    d = V[:, :, 2] - z
    inside = d <= 0 if keep_below else d >= 0
    k = inside.sum(1)
    keep = [V[k == 3]]
    koid = [oid[k == 3]]
    segs, soid = [], []

    def cut(A, B):
        # canonical order (lower z first) so both triangles sharing an edge
        # compute exactly the same point
        lo = np.where((A[:, 2] <= B[:, 2])[:, None], A, B)
        hi = np.where((A[:, 2] <= B[:, 2])[:, None], B, A)
        t = (z - lo[:, 2]) / (hi[:, 2] - lo[:, 2])
        P = lo + (hi - lo) * t[:, None]
        P[:, 2] = z
        return P

    for cnt in (1, 2):
        m = k == cnt
        if not m.any():
            continue
        W, ins, oo = V[m], inside[m], oid[m]
        # rotate so the odd vertex (the lone inside one, or the lone outside one) is first
        odd = ins if cnt == 1 else ~ins
        first = np.argmax(odd, 1)
        idx = (first[:, None] + np.arange(3)[None, :]) % 3
        W = np.take_along_axis(W, idx[:, :, None], 1)
        A, B, C = W[:, 0], W[:, 1], W[:, 2]
        P, Q = cut(A, B), cut(A, C)
        if cnt == 1:                      # A in: triangle A P Q
            keep.append(np.stack([A, P, Q], 1)); koid.append(oo)
        else:                             # A out: quad P B C Q
            keep.append(np.stack([P, B, C], 1)); koid.append(oo)
            keep.append(np.stack([P, C, Q], 1)); koid.append(oo)
        if want_segs:
            segs.append(np.stack([P, Q], 1)); soid.append(oo)
    V2 = np.concatenate(keep) if keep else np.zeros((0, 3, 3))
    O2 = np.concatenate(koid) if koid else np.zeros(0, int)
    S = np.concatenate(segs) if segs else np.zeros((0, 2, 3))
    SO = np.concatenate(soid) if soid else np.zeros(0, int)
    return V2, O2, S, SO


def clip_segments_z(P, Q, z, keep_below):
    d1, d2 = P[:, 2] - z, Q[:, 2] - z
    in1 = d1 <= 0 if keep_below else d1 >= 0
    in2 = d2 <= 0 if keep_below else d2 >= 0
    m = in1 | in2
    P, Q, in1, in2 = P[m].copy(), Q[m].copy(), in1[m], in2[m]
    x = in1 != in2
    if x.any():
        t = (z - P[x, 2]) / (Q[x, 2] - P[x, 2])
        C = P[x] + (Q[x] - P[x]) * t[:, None]
        Px, Qx = P[x], Q[x]
        Px[~in1[x]] = C[~in1[x]]
        Qx[~in2[x]] = C[~in2[x]]
        P[x], Q[x] = Px, Qx
    return P, Q, m


def clip_segments_rect(P, Q, hx, hy):
    """Liang-Barsky against |u|<=hx, |v|<=hy. Returns clipped P, Q and mask."""
    dx, dy = Q[:, 0] - P[:, 0], Q[:, 1] - P[:, 1]
    t0, t1 = np.zeros(len(P)), np.ones(len(P))
    ok = np.ones(len(P), bool)
    for p, q in ((-dx, P[:, 0] + hx), (dx, hx - P[:, 0]), (-dy, P[:, 1] + hy), (dy, hy - P[:, 1])):
        par = np.abs(p) < 1e-12
        ok &= ~(par & (q < 0))
        with np.errstate(divide='ignore', invalid='ignore'):
            r = q / p
        t0 = np.where(~par & (p < 0), np.maximum(t0, r), t0)
        t1 = np.where(~par & (p > 0), np.minimum(t1, r), t1)
    ok &= t0 <= t1
    D = Q - P
    P2 = P + D * t0[:, None]
    Q2 = P + D * t1[:, None]
    return P2[ok], Q2[ok], ok


def weld(V, oid, q=0.01):
    """Triangles (T,3,3) -> vertex table and (T,3) indices, per object."""
    pts = V.reshape(-1, 3)
    key = np.column_stack([np.repeat(oid, 3), np.round(pts / q).astype(np.int64)])
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return pts[first], inv.ravel().reshape(-1, 3)


def feature_edges(P, T, oid, crease):
    """Boundary, crease and silhouette edges -> (E,2) vertex ids, object ids."""
    A, B, C = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    n = np.cross(B - A, C - A)
    ln = np.linalg.norm(n, axis=1)
    good = ln > 1e-9
    T, oid, n = T[good], oid[good], n[good] / ln[good, None]
    e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    tri = np.tile(np.arange(len(T)), 3)
    a, b = e.min(1), e.max(1)
    key = a.astype(np.int64) * (len(P) + 1) + b
    order = np.argsort(key, kind='stable')
    key, a, b, tri = key[order], a[order], b[order], tri[order]
    start = np.r_[True, key[1:] != key[:-1]]
    gs = np.nonzero(start)[0]
    cnt = np.diff(np.r_[gs, len(key)])
    draw = cnt != 2
    two = cnt == 2
    n1, n2 = n[tri[gs[two]]], n[tri[gs[two] + 1]]
    s1 = np.where(np.abs(n1[:, 2]) < 1e-3, 0, np.sign(n1[:, 2]))
    s2 = np.where(np.abs(n2[:, 2]) < 1e-3, 0, np.sign(n2[:, 2]))
    d = np.abs((n1 * n2).sum(1)) < math.cos(math.radians(crease))
    draw[two] = d | (s1 != s2)
    g = gs[draw]
    return np.stack([a[g], b[g]], 1), oid[tri[g]]


class ZBuffer:
    def __init__(self, hx, hy, res):
        self.res = res
        self.x0, self.y0 = -hx - 2 * res, -hy - 2 * res
        self.W = int(math.ceil(2 * (hx + 2 * res) / res)) + 1
        self.H = int(math.ceil(2 * (hy + 2 * res) / res)) + 1
        self.z = np.full(self.W * self.H, -np.inf, np.float32)

    def tris(self, V, chunk=2000000):
        """Scan-line raster: per triangle and pixel row, the covered x span is
        computed directly, so long thin triangles cost what they cover."""
        r = self.res
        X = (V[:, :, 0] - self.x0) / r - 0.5        # pixel-centre coordinates
        Y = (V[:, :, 1] - self.y0) / r - 0.5
        Z = V[:, :, 2]
        area = (X[:, 1] - X[:, 0]) * (Y[:, 2] - Y[:, 0]) - (X[:, 2] - X[:, 0]) * (Y[:, 1] - Y[:, 0])
        j0 = np.maximum(np.ceil(Y.min(1)), 0).astype(np.int64)
        j1 = np.minimum(np.floor(Y.max(1)), self.H - 1).astype(np.int64)
        ok = (np.abs(area) > 1e-9) & (j1 >= j0) & (X.max(1) >= 0) & (X.min(1) <= self.W - 1)
        X, Y, Z, area, j0, j1 = X[ok], Y[ok], Z[ok], area[ok], j0[ok], j1[ok]
        # plane z = ax + by + c in pixel coordinates
        e1x, e1y, e1z = X[:, 1] - X[:, 0], Y[:, 1] - Y[:, 0], Z[:, 1] - Z[:, 0]
        e2x, e2y, e2z = X[:, 2] - X[:, 0], Y[:, 2] - Y[:, 0], Z[:, 2] - Z[:, 0]
        pa = (e1z * e2y - e2z * e1y) / (e1x * e2y - e2x * e1y)
        pb = (e1x * e2z - e2x * e1z) / (e1x * e2y - e2x * e1y)
        pc = Z[:, 0] - pa * X[:, 0] - pb * Y[:, 0]
        nrow = j1 - j0 + 1
        ends = np.cumsum(nrow)
        start = 0
        while start < len(nrow):
            stop = int(np.searchsorted(ends, (ends[start - 1] if start else 0) + chunk, 'right'))
            stop = max(stop, start + 1)
            sl = slice(start, stop)
            t = np.repeat(np.arange(start, stop), nrow[sl])
            j = np.arange(len(t)) - np.repeat(np.cumsum(nrow[sl]) - nrow[sl], nrow[sl]) + j0[t]
            y = j.astype(np.float64)
            xl = np.full(len(t), np.inf)
            xr = np.full(len(t), -np.inf)
            for a_, b_ in ((0, 1), (1, 2), (2, 0)):
                ya, yb, xa, xb = Y[t, a_], Y[t, b_], X[t, a_], X[t, b_]
                hit = (np.minimum(ya, yb) <= y) & (y <= np.maximum(ya, yb)) & (ya != yb)
                with np.errstate(divide='ignore', invalid='ignore'):
                    x = xa + (y - ya) * (xb - xa) / (yb - ya)
                xl = np.where(hit, np.minimum(xl, x), xl)
                xr = np.where(hit, np.maximum(xr, x), xr)
            i0 = np.maximum(np.ceil(xl - 1e-9), 0).astype(np.int64)
            i1 = np.minimum(np.floor(xr + 1e-9), self.W - 1).astype(np.int64)
            n = np.where(np.isfinite(xl) & np.isfinite(xr), np.maximum(i1 - i0 + 1, 0), 0)
            if n.sum():
                rr = np.repeat(np.arange(len(t)), n)
                i = np.arange(len(rr)) - np.repeat(np.cumsum(n) - n, n) + i0[rr]
                tt = t[rr]
                z = (pa[tt] * i + pb[tt] * j[rr] + pc[tt]).astype(np.float32)
                self._max_into(j[rr] * self.W + i, z)
            start = stop

    def _max_into(self, idx, z):
        """self.z[idx] = max(self.z[idx], z), duplicates in idx allowed."""
        order = np.lexsort((z, idx))
        idx, z = idx[order], z[order]
        last = np.r_[idx[1:] != idx[:-1], True]
        idx, z = idx[last], z[last]
        self.z[idx] = np.maximum(self.z[idx], z)

    def fill(self, area, z):
        x0, y0, x1, y1 = area.bounds
        r = self.res
        i0 = max(int(math.ceil((x0 - self.x0) / r - 0.5)), 0)
        i1 = min(int(math.floor((x1 - self.x0) / r - 0.5)), self.W - 1)
        j0 = max(int(math.ceil((y0 - self.y0) / r - 0.5)), 0)
        j1 = min(int(math.floor((y1 - self.y0) / r - 0.5)), self.H - 1)
        if i1 < i0 or j1 < j0:
            return
        I, J = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1))
        inside = shapely.contains_xy(area, self.x0 + (I + 0.5) * r, self.y0 + (J + 0.5) * r)
        idx = (J * self.W + I)[inside]
        self.z[idx] = np.maximum(self.z[idx], np.float32(z))

    def finish(self):
        z = self.z.reshape(self.H, self.W)
        m = z.copy()
        for dj in (-1, 0, 1):
            for di in (-1, 0, 1):
                if di or dj:
                    s = np.full_like(z, np.inf)
                    s[max(dj, 0):self.H + min(dj, 0), max(di, 0):self.W + min(di, 0)] = \
                        z[max(-dj, 0):self.H + min(-dj, 0), max(-di, 0):self.W + min(-di, 0)]
                    np.minimum(m, s, out=m)
        self.zmin = m

    def runs(self, P, Q, chunk=200000):
        """Visible / hidden pieces of segments: (segment index, t0, t1, visible)."""
        out = []
        for c0 in range(0, len(P), chunk):
            p, q = P[c0:c0 + chunk], Q[c0:c0 + chunk]
            L = np.hypot(q[:, 0] - p[:, 0], q[:, 1] - p[:, 1])
            n = np.maximum(2, np.ceil(L / (self.res * 0.5)).astype(np.int64) + 1)
            e = np.repeat(np.arange(len(p)), n)
            base = np.repeat(np.cumsum(n) - n, n)
            k = np.arange(n.sum()) - base
            t = k / np.repeat(n - 1, n)
            x = p[e, 0] + (q[e, 0] - p[e, 0]) * t
            y = p[e, 1] + (q[e, 1] - p[e, 1]) * t
            z = p[e, 2] + (q[e, 2] - p[e, 2]) * t
            i = np.clip(((x - self.x0) / self.res).astype(np.int64), 0, self.W - 1)
            j = np.clip(((y - self.y0) / self.res).astype(np.int64), 0, self.H - 1)
            vis = z >= self.zmin[j, i] - TOL
            st = np.r_[True, (vis[1:] != vis[:-1]) | (e[1:] != e[:-1])]
            first = np.nonzero(st)[0]
            last = np.r_[first[1:] - 1, len(e) - 1]
            ta = np.where(k[first] == 0, 0.0, (t[first] + t[np.maximum(first - 1, 0)]) / 2)
            tb = np.where(last == base[last] + n[e[last]] - 1, 1.0, (t[last] + t[np.minimum(last + 1, len(t) - 1)]) / 2)
            out.append((e[first] + c0, ta, tb, vis[first]))
        if not out:
            return np.zeros(0, int), np.zeros(0), np.zeros(0), np.zeros(0, bool)
        return tuple(np.concatenate(x) for x in zip(*out))


def cut_face(segs):
    r = lambda p: (round(float(p[0]), 2), round(float(p[1]), 2))
    lines = [LineString([r(a), r(b)]) for a, b in segs if r(a) != r(b)]
    if len(lines) < 3:
        return None
    polys = [p for p in polygonize(unary_union(lines)) if p.area > 1.0]
    if not polys:
        return None
    area = polys[0]
    for p in polys[1:]:
        area = area.symmetric_difference(p)
    return None if area.is_empty else area


def dxf_layer(name):
    s = ''.join(c if c.isascii() and (c.isalnum() or c in '_-') else '_' for c in name.replace('/', '__'))
    s = re.sub('_{3,}', '__', s).strip('_')
    return (s or 'UNNAMED')[:200]


# ---------------------------------------------------------------- plan
def plan(cache, name, frame, hx, hy, top, bottom, al, a, outdir):
    t0 = time.time()
    o, c = cache.obj, cache.crv
    org = cache.origin

    def to_frame(p_rel):
        w = p_rel.astype(np.float64) + org
        if al is not None:
            w = al.apply(w)
        return frame.to_local(w)

    # ---- pick objects by their box
    def pick(bbox, flags, is_obj):
        lo, hi = bbox[:, :3], bbox[:, 3:]
        corners = np.stack([np.stack([np.where(k & 1, hi[:, 0], lo[:, 0]),
                                      np.where(k & 2, hi[:, 1], lo[:, 1]),
                                      np.where(k & 4, hi[:, 2], lo[:, 2])], 1) for k in range(8)], 1)
        f = to_frame(corners)
        flo, fhi = f.min(1), f.max(1)
        m = (fhi[:, 0] >= -hx) & (flo[:, 0] <= hx) & (fhi[:, 1] >= -hy) & (flo[:, 1] <= hy)
        if top is not None:
            m &= flo[:, 2] <= top
        if bottom is not None:
            m &= fhi[:, 2] >= bottom
        if is_obj:
            size = (hi - lo).max(1)
            skip_bolt = ((flags & BOLT) != 0) & (not a.keep_bolts)
            # small-bore piping comes in short pieces well under the size
            # limit; dropping them would cut the lines into dashes
            piping = cache.piping_layer[o['layer']]
            skip_small = (size < a.min_size) & ~((flags & SPACE) != 0) & ~piping
            return m & ~skip_bolt & ~skip_small, (m & skip_bolt).sum(), (m & skip_small & ~skip_bolt).sum()
        return m, 0, 0

    om, nbolt, nsmall = pick(o['bbox'], o['flags'], True)
    cm, _, _ = pick(c['bbox'], c['flags'], False) if len(c.get('bbox', [])) else (np.zeros(0, bool), 0, 0)
    sel = np.nonzero(om)[0]
    space = (o['flags'][sel] & SPACE) != 0
    print('[%s] %d objects in the area (%d bolts and %d small ones left out), %d curves'
          % (name, len(sel), nbolt, nsmall, cm.sum()))

    # ---- triangles in the frame
    def load(ids):
        V, O = [], []
        for i in ids:
            vo, to, tc = o['vert_off'][i], o['tri_off'][i], o['tri_cnt'][i]
            T = np.asarray(cache.tris[to:to + tc]) + vo
            V.append(cache.verts[T.ravel()].reshape(-1, 3, 3))
            O.append(np.full(tc, i))
        if not V:
            return np.zeros((0, 3, 3)), np.zeros(0, int)
        V = np.concatenate(V)
        return to_frame(V), np.concatenate(O)

    V, O = load(sel[~space])
    segs = np.zeros((0, 2, 3)); soid = np.zeros(0, int)
    if top is not None:
        V, O, segs, soid = clip_tris(V, O, top, True, True)
    if bottom is not None:
        V, O, _, _ = clip_tris(V, O, bottom, False, False)
    print('  %d triangles after the cut, %.1fs' % (len(V), time.time() - t0))

    zb = ZBuffer(hx, hy, a.res)
    zb.tris(V)
    ncap = 0
    if len(segs):
        order = np.argsort(soid, kind='stable')
        segs, soid = segs[order], soid[order]
        cuts = np.nonzero(np.r_[True, soid[1:] != soid[:-1]])[0]
        for s0, s1 in zip(cuts, np.r_[cuts[1:], len(soid)]):
            area = cut_face(segs[s0:s1, :, :2])
            if area is not None:
                zb.fill(area, top)
                ncap += 1
    zb.finish()
    print('  visibility grid %dx%d, %d cut faces, %.1fs' % (zb.W, zb.H, ncap, time.time() - t0))

    # ---- edges
    P, T = weld(V, O)
    E, EO = feature_edges(P, T, O[:len(T)] if len(O) == len(T) else O, a.crease)
    EP, EQ = P[E[:, 0]], P[E[:, 1]]
    # curves (not centre lines): clip in z like the solids
    cids = np.nonzero(cm)[0]
    CP, CQ, CO, CL = [], [], [], []
    for i in cids:
        po, pc = c['pt_off'][i], c['pt_cnt'][i]
        pts = to_frame(np.asarray(cache.cpts[po:po + pc]))
        if c['flags'][i] & CENTRE:
            CL.append((pts[:-1], pts[1:], i))
            continue
        CP.append(pts[:-1]); CQ.append(pts[1:]); CO.append(np.full(pc - 1, i))
    if CP:
        p_, q_, o_ = np.concatenate(CP), np.concatenate(CQ), np.concatenate(CO)
        if top is not None:
            p_, q_, m = clip_segments_z(p_, q_, top, True); o_ = o_[m]
        if bottom is not None:
            p_, q_, m = clip_segments_z(p_, q_, bottom, False); o_ = o_[m]
    else:
        p_, q_, o_ = np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0, int)
    # one list of segments: (P, Q, layer index, kind 0=object 1=curve)
    SP = np.concatenate([EP, p_]); SQ = np.concatenate([EQ, q_])
    SL = np.concatenate([o['layer'][EO], c['layer'][o_] if len(o_) else np.zeros(0, int)]).astype(int)
    SP, SQ, ok = clip_segments_rect(SP, SQ, hx, hy)
    SL = SL[ok]
    L = np.hypot(SQ[:, 0] - SP[:, 0], SQ[:, 1] - SP[:, 1])
    k = L >= 0.5
    SP, SQ, SL = SP[k], SQ[k], SL[k]
    seg, ta, tb, vis = zb.runs(SP, SQ)
    print('  %d edges -> %d pieces, %.1fs' % (len(SP), len(seg), time.time() - t0))

    # ---- DXF
    doc = ezdxf.new('R2010', setup=True)
    doc.header['$INSUNITS'] = 4
    msp = doc.modelspace()
    layer_names = cache.meta['layers']
    made = {}

    def lay(ix, suffix='', lt='CONTINUOUS', col=None, off=False):
        # one DXF layer per source file (Navisworks .nwc / .dwg / .dgn ...)
        src = layer_names[ix].split('/')[0] if ix >= 0 else 'CL'
        nm = dxf_layer(src) + suffix
        if nm not in made:
            ly = doc.layers.add(nm, color=col if col else 1 + zlib.crc32(src.encode()) % 6, linetype=lt)
            if off:
                ly.off()
            made[nm] = True
        return nm

    def world2(u, v):
        x, y = frame.to_world2(u, v)
        return float(x), float(y)

    preview = []
    D = SQ - SP
    nvis = nhid = 0
    for s_, a_, b_, v_ in zip(seg, ta, tb, vis):
        if not v_ and not a.hidden:
            continue
        pa = SP[s_] + D[s_] * a_
        pb = SP[s_] + D[s_] * b_
        if math.hypot(pb[0] - pa[0], pb[1] - pa[1]) < 0.5:
            continue
        if v_:
            msp.add_line(world2(pa[0], pa[1]), world2(pb[0], pb[1]), dxfattribs={'layer': lay(SL[s_])})
            preview.append(('v', pa[0], pa[1], pb[0], pb[1]))
            nvis += 1
        else:
            msp.add_line(world2(pa[0], pa[1]), world2(pb[0], pb[1]),
                         dxfattribs={'layer': lay(SL[s_], '_HIDDEN', 'DASHED2', 8, True)})
            nhid += 1
    for p1, p2, i in CL:
        p1, p2, _ = clip_segments_rect(p1, p2, hx, hy)
        for u, w in zip(p1, p2):
            if math.hypot(w[0] - u[0], w[1] - u[1]) >= 0.5:
                msp.add_line(world2(u[0], u[1]), world2(w[0], w[1]),
                             dxfattribs={'layer': lay(c['layer'][i], '_CL', 'CENTER', 1)})
                preview.append(('c', u[0], u[1], w[0], w[1]))
    rect = Polygon([(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)])
    for i in sel[space]:
        Vs, Os = load([i])
        if top is not None:
            Vs, Os, _, _ = clip_tris(Vs, Os, top, True, False)
        if bottom is not None:
            Vs, Os, _, _ = clip_tris(Vs, Os, bottom, False, False)
        polys = [Polygon(t[:, :2]).buffer(0.01) for t in Vs if Polygon(t[:, :2]).area > 1e-3]
        if not polys:
            continue
        u = unary_union(polys).simplify(0.5).intersection(rect)
        for g in getattr(u, 'geoms', [u]):
            if g.geom_type != 'Polygon' or g.is_empty:
                continue
            for ring in [g.exterior, *g.interiors]:
                pts = list(ring.coords)
                msp.add_lwpolyline([world2(x, y) for x, y in pts], close=True,
                                   dxfattribs={'layer': lay(o['layer'][i], '_SPACE', 'DASHED', 5)})
                preview += [('s', *pts[j], *pts[j + 1]) for j in range(len(pts) - 1)]
    # the area outline
    ly = 'AREA_FRAME'
    if ly not in doc.layers:
        doc.layers.add(ly, color=8)
    msp.add_lwpolyline([world2(-hx, -hy), world2(hx, -hy), world2(hx, hy), world2(-hx, hy)],
                       close=True, dxfattribs={'layer': ly})

    fixes = doc.audit().fixes
    if fixes:
        sys.exit('DXF not written, audit had to fix:\n' + '\n'.join(f.message for f in fixes))
    tag = name
    if top is not None:
        tag += '_EL%g' % round(top)
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, re.sub(r'[\\/:*?"<>|]', '_', tag) + '.dxf')
    doc.saveas(out)
    print('  %d lines (%d hidden) -> %s, %.1fs' % (nvis, nhid, out, time.time() - t0))

    from PIL import Image, ImageDraw
    Hpx = 2400
    s = Hpx / (2 * hy * 1.04)
    Wpx = int(2 * hx * 1.04 * s)
    img = Image.new('RGB', (max(Wpx, 10), Hpx), 'white')
    dr = ImageDraw.Draw(img)
    X = lambda u: (u + hx * 1.04) * s
    Y = lambda v: Hpx - (v + hy * 1.04) * s
    col = {'v': (0, 0, 0), 'c': (220, 0, 0), 's': (80, 140, 255)}
    dr.rectangle([X(-hx), Y(hy), X(hx), Y(-hy)], outline=(160, 160, 160))
    for kk, x1, y1, x2, y2 in preview:
        dr.line([(X(x1), Y(y1)), (X(x2), Y(y2))], fill=col[kk], width=1)
    img.save(out[:-4] + '.png')


def read_boxes(path):
    out = []
    for line in open(path, encoding='utf-8-sig'):
        line = line.split('#')[0].strip()
        if not line:
            continue
        f = re.split(r'[\s,]+', line)
        nm = f[0]
        e, n, u, xl, yl, zl, xe, xn = map(float, f[1:9])
        out.append((nm, e, n, u, xl, yl, zl, math.atan2(xn, xe)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cache')
    ap.add_argument('cmd', choices=['info', 'probe', 'align', 'plan'])
    ap.add_argument('args', nargs='*')
    ap.add_argument('--align')
    ap.add_argument('--radius', type=float, default=200.0)
    ap.add_argument('--rect', nargs=4, type=float)
    ap.add_argument('--boxes')
    ap.add_argument('--cut', type=float)
    ap.add_argument('--bottom', type=float)
    ap.add_argument('--min-size', type=float, default=50.0)
    ap.add_argument('--keep-bolts', action='store_true')
    ap.add_argument('--hidden', action='store_true')
    ap.add_argument('--res', type=float, default=5.0)
    ap.add_argument('--crease', type=float, default=30.0)
    ap.add_argument('--name', default='plan')
    ap.add_argument('--out')
    a = ap.parse_args()
    cache = Cache(a.cache)
    al = None
    if a.align and a.cmd != 'align':
        P, Q, L = read_pairs(a.align)
        al = fit_align(P, Q)
    sysname = 'E3D' if al else 'model (Navisworks)'

    if a.cmd == 'info':
        bb = cache.obj['bbox']
        lo, hi = bb[:, :3].min(0) + cache.origin, bb[:, 3:].max(0) + cache.origin
        print('%d objects, %d triangles, %d curves' % (cache.meta['n_objects'], cache.meta['n_tris'], cache.meta['n_curves']))
        print('model extents  X %.0f .. %.0f   Y %.0f .. %.0f   Z %.0f .. %.0f  (mm, Navisworks coordinates)'
              % (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))
        if al:
            c = al.apply(np.array([[lo[0], lo[1], lo[2]], [hi[0], hi[1], hi[2]]]))
            print('in E3D (corners only, rotation %.3f deg): E %.0f .. %.0f  N %.0f .. %.0f  U %.0f .. %.0f'
                  % (math.degrees(al.theta), c[0, 0], c[1, 0], c[0, 1], c[1, 1], c[0, 2], c[1, 2]))
        print('layers (%d):' % len(cache.meta['layers']))
        cnt = np.bincount(cache.obj['layer'], minlength=len(cache.meta['layers']))
        for i in np.argsort(-cnt)[:60]:
            print('  %6d  %s' % (cnt[i], cache.meta['layers'][i]))
    elif a.cmd == 'align':
        P, Q, L = read_pairs(a.args[0])
        report_align(P, Q, L, fit_align(P, Q))
    elif a.cmd == 'probe':
        x, y, z = map(float, a.args[:3])
        p = np.array([x, y, z])
        if al:
            p = al.invert(p)
        rel = p - cache.origin
        bb = cache.obj['bbox']
        d = np.linalg.norm(np.maximum(np.maximum(bb[:, :3] - rel, rel - bb[:, 3:]), 0), axis=1)
        near = np.nonzero(d <= a.radius)[0]
        res = []
        for i in near:
            vo, vc = cache.obj['vert_off'][i], cache.obj['vert_cnt'][i]
            dv = np.linalg.norm(cache.verts[vo:vo + vc].astype(np.float64) - rel, axis=1)
            res.append((dv.min(), i))
        res.sort()
        print('point %s (%s coordinates): %d objects within %.0f mm of their box' % (a.args[:3], sysname, len(near), a.radius))
        for dv, i in res[:20]:
            print('  nearest vertex %8.1f mm  %s' % (dv, cache.meta['names'][cache.obj['name'][i]]))
    elif a.cmd == 'plan':
        outdir = a.out or os.path.join(os.path.dirname(os.path.abspath(a.cache)), 'plans')
        jobs = []
        if a.boxes:
            for nm, e, n, u, xl, yl, zl, ang in read_boxes(a.boxes):
                top = a.cut if a.cut is not None else u + zl / 2
                bot = a.bottom if a.bottom is not None else u - zl / 2
                jobs.append((nm, Frame(e, n, ang), xl / 2, yl / 2, top, bot))
        else:
            if a.rect:
                x1, y1, x2, y2 = a.rect
            else:
                # no area given: the whole model (its corners, in the output coordinates)
                bb = np.concatenate([cache.obj['bbox'], cache.crv['bbox']]) if len(cache.crv.get('bbox', [])) \
                    else cache.obj['bbox']
                lo, hi = bb[:, :3].min(0) + cache.origin, bb[:, 3:].max(0) + cache.origin
                corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
                if al is not None:
                    corners = al.apply(corners)
                x1, y1 = corners[:, 0].min() - 1, corners[:, 1].min() - 1
                x2, y2 = corners[:, 0].max() + 1, corners[:, 1].max() + 1
                print('no area given: the whole model, X %.0f .. %.0f  Y %.0f .. %.0f' % (x1, x2, y1, y2))
            jobs.append((a.name, Frame((x1 + x2) / 2, (y1 + y2) / 2, 0.0), abs(x2 - x1) / 2, abs(y2 - y1) / 2,
                         a.cut, a.bottom))
        for nm, fr, hx, hy, top, bot in jobs:
            plan(cache, nm, fr, hx, hy, top, bot, al, a, outdir)


if __name__ == '__main__':
    main()
