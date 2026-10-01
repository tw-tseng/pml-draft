"""
RevCloud -- find what changed between two DXF exports of the same DRAFT
sheet and answer with revision-cloud outlines for PML to draw.

    RevCloud.exe <old.dxf> <new.dxf> <out.txt> [options]

    --gap MM          changes closer than this (paper mm) share one cloud   [10]
    --move-dist MM    a vanished primitive with a twin (same text/length/
                      angle/radius) newly present within this distance is
                      a MOVE: only its new place is clouded              [150]
    --hinge MM        a vanished line segment that kept one end and moved
                      the other by no more than this is a leader (or a
                      pipe end) following the element it points at:
                      neither segment is clouded. 0 turns the rule off  [10]
    --tri-size MM     side of the revision triangle PML will draw beside
                      every outer cloud; when given, a 'tri i x y' record
                      (bottom left corner of the triangle's box) follows
                      each outer cloud, placed where it touches nothing
                      on the new sheet. 0 = no triangles                  [0]
    --canvas x1,y1,x2,y2  the drawing area of the sheet (DrawingPlan1's
                      canvas). inside it everything is compared; outside
                      it nothing is, except inside a --watch rectangle.
                      triangles are kept inside it. without it the title
                      strip is guessed from the backing sheet (below)   [none]
    --watch x1,y1,x2,y2  a rectangle outside the canvas whose content IS
                      compared -- a title field. the backing sheet's own
                      text inside it counts too, so a title that E3D
                      fills in from an attribute is caught as well as
                      one typed on the sheet. may be given more than once
    --dimlines-new F  a file of 'dimline <dir> x1 y1 x2 y2' records: the
                      dimension projection lines of the NEW sheet, as
                      DrawingPlan1DimLines lists them for BlankPos. a new
                      line lying on one is never clouded (below)      [none]
    --dimlines-old F  the same list kept beside the old DXF, for the old
                      sheet's projection lines                        [none]
    --pad MM          half width of the band the cloud draws round a change [2.5]
    --chord MM        target length of one scallop along the outline        [8]
    --bulge F         scallop height as a fraction of half the chord        [0.6]
    --arcseg N        straight segments per scallop (PML draws lines only)  [4]
    --cloud-layer L   DXF layer the previous run's clouds sit on; every
                      entity on it is dropped from BOTH files before the
                      diff, so old clouds never read as changes         [REVCLOUD]
    --old-clouds F    the clouds now on the sheet, written by PML from the
                      REVCLOUD note in the same 'cloud / v x y / end'
                      format as the output. any top-level polyline in
                      either file whose vertices match one of them is a
                      cloud and is dropped. needed because DXFOUT puts an
                      OUTL on layer 0 whatever VLAYRF says (seen 2026-09-14
                      on the first real run: both clouds came out as plain
                      POLYLINEs on layer 0, the layer rule found nothing)
    --exclude x1,y1,x2,y2   extra rectangle (paper mm) whose content is
                      ignored; may be given more than once
    --no-auto-title   do not derive the title-strip exclusion from the
                      backing sheet's own texts (implied by --canvas)

Called by draft/forms/DrawingPlan1Revision.pmlfrm (PA_pmllibE3D2.1) via
syscom, the same way DrawingPlan1 calls BlankPos. The design lives in the
"revision program (2026-09-13)" toggle on the project's Notion page,
section 6 (clouds).

Output <out.txt> (space separated, one record per line, ASCII):

    clouds <n> removed <r> added <a>
    cloud <i> <x1> <y1> <x2> <y2> <outer|hole>   bounding box of this ring
    tri <i> <x> <y>                       bottom left corner of the box of
                                          the revision triangle for outer
                                          ring i (with --tri-size)
    v <x> <y>                             outline vertices, closed (first
    ...                                   point repeated at the end)
    end

One 'cloud' record per ring, and PML makes one OUTL of each. A change
shaped like a U or a closed frame gives a band with a hole in it, so its
inner boundary comes out as a second ring flagged 'hole' (the user's
2026-09-14 sketch: the cloud hugs the changed lines on both sides, it is
not a box round everything).

<out.txt>.log carries the counts, exclusions and every cluster so a run
explains itself afterwards -- syscom swallows stdout.

How the diff works
------------------
Both files are flattened into primitives: every LINE, every segment of a
POLYLINE/LWPOLYLINE, every ARC/CIRCLE, every TEXT/MTEXT (position + string)
and every HATCH (as its bounding box), with INSERTs exploded recursively so
block contents are compared in sheet coordinates. Coordinates are rounded
to 0.05mm and each primitive becomes a hashable key. A key present in one
file and absent from the other is the change. Presence, not count: the
first real run clouded a spot where the old sheet carried a dimension
twice over (two identical arrows and lines on top of each other, left by
an earlier update-path bug) and the new sheet once -- invisible on paper,
so not a change here either (2026-09-14).

The cloud is the SHAPE of the change, not its bounding box: every changed
primitive is buffered by --pad, the buffers are unioned, and gaps narrower
than --gap are closed (morphological closing, buffer +gap/2 then -gap/2),
so a moved dimension chain gives a band that follows the chain and two
changes a few mm apart share one cloud. Within a cluster only what is NEW
is clouded -- a moved chain gets its band where it is now, not a band
smeared from where it was (user sketch 2026-09-14); a cluster that is
pure deletion, with nothing new in it, is clouded where the old geometry
stood, since that is the only place the change can be shown.

Blocks are matched BEFORE they are exploded (user's question 2026-09-14):
every top-level INSERT gets a content signature -- the primitive keys of
its block definition in block-local coordinates, nested INSERTs by their
own signature -- so a label that DXFOUT called LABEL7 last time and LABEL9
this time is still recognised as the same thing. Same signature at the
same place: unchanged, never exploded. Same signature at another place,
within --move-dist: the block moved, only its new place is clouded. No
partner: exploded into the primitive diff like everything else, so a label
whose text or leader changed is still found, and a label that vanished is
clouded where it was.

A line that only grew or shrank at one end -- the horizontal run that a
moved vertical pipe drags along -- is a different primitive from end to
end, but on paper only the stub is new. So a new segment that is
collinear with an old one (same line within 0.1mm, overlapping) keeps
only the part the old one did not cover as its cloud geometry, and the
old one likewise. The whole 80mm run was clouded on the first real run
for a 3.35mm stretch (2026-09-14).

A label pinned to the page (OSET FALSE, what DrawingPlan1Revision does to
the component labels at revision time) keeps its text where it is and
lets the leader follow the element. That is not a change of the label, it
is the element's move seen through the leader, and the element is clouded
on its own. DXFOUT writes a label as a LABELn block whose insert point is
the design point the leader starts from, so this is decided per block,
before anything is exploded: an old and a new LABEL block are a
"leader-only" pair when everything in them that does NOT touch the insert
point -- text, symbol, frame, the far part of a bent leader -- is the same
primitives at the same absolute place. Then neither block joins the
primitive diff and nothing of either is clouded: the element the leader
points at is clouded on its own, and a blob at the design point read as
"the leader is clouded" to the user (2026-09-15, the FE/FV 115 bubbles).
The label end of the leader is free to slide along the
frame (E3D re-attaches it as the angle changes), which is why the pairing
looks at the rest of the block and not at the leader itself. Without this
the whole leader was clouded and the band ran out to the support tags
(user, 2026-09-15, first run with pinned labels).

Where the border is concerned there is no rule for what is a TEXP and
what the backing sheet fills in -- every project's border is different
(user, 2026-09-15). So the border is not read, it is declared: the canvas
(DrawingPlan1's printable area, written into the DRWG's DESC by
DrawingPlan1 or given as a CANVAS line in the project's sequence file)
says where the drawing is, and inside it everything is compared as before.
Outside it -- the border -- nothing is compared unless a --watch rectangle
says so; in a watched rectangle the backing sheet is exploded too, so the
title is caught whether it is a TEXP or an attribute. A drafter's name or
a date changing in an unwatched field never clouds. Without a canvas the
older guess stays: backing sheet excluded whole, title strip derived from
its texts.

The revision triangle (user, 2026-09-15: one beside every cloud, and it
must not sit on anything). PML draws it, RevCloud says where, because
RevCloud is the one that knows what is on the new sheet: every loose
primitive, every block whether it changed or not, and the excluded blocks
too (the backing sheet is an obstacle even though it is never compared).

Every candidate near the ring -- the scallop tips in four directions, and
a grid out to --tri-reach beyond the ring's box -- is scored by how much
of the triangle's box would overlap something (an obstacle, another
ring's cloud, a triangle already placed) and by real distance to the
ring; the candidate with the least overlap wins, ties broken by distance.
A clean (zero overlap) candidate right at the scallops is usually found
in the first few tried and the rest are never scored.

Earlier versions ranked candidates by how close to the top right corner
they were within each widening ring of a fixed search radius, which
could walk straight past a clean, near candidate on one side to reach a
top-right one much farther off (a vessel and its nozzles crowded a
cloud, 2026-09-18: the triangle ended up on the far side of a grid
line). Scoring by actual distance and overlap together removes that
bias: nearest-and-cleanest wins outright, and when the neighbourhood
truly has no clean spot within reach the triangle still lands as close
as the crowding allows, touching only as little as it must, rather than
jumping to nurse a lower score that happens to be far away.

The same idea one level down, for lines that are not inside a label (the
oblique tick of a dimension, a pipe end): a new segment hinged on an old
one -- one end within 0.1mm, the other within --hinge -- drops both from
the clouds: the moved end belongs to whatever moved, and that is clouded
on its own.
--hinge is small on purpose: a branch deleted at a tee and a different
branch added there also share an end, and only when its far end is within
a few mm is it the same branch.

Dimension projection lines are not clouded at all (--dimlines-new /
--dimlines-old, 2026-09-17). A pipe moved sideways takes its projection
line with it: the pipe is clouded, the dimension figures that changed are
clouded, and the projection line between them -- a helper, broken by the
match line text and by any label laid across it -- is a consequence, not a
change. Left in, it drew a narrow band from the dimension chain through
the match line text down to the pipe (user, 2026-09-17). PML knows exactly
which lines these are (the same list BlankPos gets), so the DXF lines lying
on a listed segment -- same depth within 0.5mm, at least half their length
inside it, as BlankPos matches them -- are dropped from both sides of the
diff before anything else looks at them. A dimension that was deleted
outright still clouds: its figures are gone and those are texts.

A move further than --gap would otherwise split into an "added" cluster
at the new place and a "deleted" cluster at the old one, and the old one
would get a cloud of its own (the 5192 dimension text, 2026-09-14). So
before clustering every vanished primitive looks for a twin among the new
ones -- same text and rotation, or same length and angle, or same radius
and sweep -- within --move-dist; a twin found means the primitive moved,
and the old copy is dropped from the diff. Each new primitive can be the
twin of one old one. The distance cap keeps a deleted valve at one end of
the sheet from pairing with an unrelated new one at the other. Each resulting ring -- outer
boundary and any holes -- is then scalloped: the ring is resampled every
--chord mm and a circular arc of height --bulge x chord/2 is bulged away
from the band on every chord (a full semicircle looked like a row of
thorns where the ring bends round a moved text).
The first version boxed the whole cluster, which for a 300mm dimension
chain clouded the entire view (2026-09-14).

This is deliberately a picture diff, not an element diff -- the same thing
E3D's own SETCOMPDATE / UPDATE DESIGN SHOW CHANGES does, so a cloud lands
wherever E3D would have shown red/green.

What is ignored
---------------
* block PICT_OWNER (frame + BackingSheet, whose texts carry the save date
  and refnos and so change on every save)
* blocks OLAY* (static overlays: north arrow, key plan frame) and anything
  lying entirely inside their extent (the key plan highlight OUTL is a
  top-level POLYLINE+HATCH drawn over OLAY1)
* the title strip along the bottom: everything below the highest
  BackingSheet text that sits in the bottom 15% of the sheet and clear of
  the side margins (+3mm; the margins carry the frame's zone numbers).
  that is where DrawingPlan1 puts the drawing-name TEXP and where a
  revision table would go. needs at least three such texts, otherwise no
  strip is assumed. --no-auto-title switches this off, --exclude adds
  rectangles of your own
* everything on --cloud-layer

Coordinates: DXFOUT writes the sheet in mm with the sheet's own origin, so
DXF x/y == the XYPO PML writes on a NOTE. verified against BlankPos1.dxf
(841 x 594, PICT_OWNER inserted at 420.5, 297).
"""

import sys
import math
import argparse
import collections
import datetime

import ezdxf
from ezdxf.math import Matrix44
from shapely.geometry import LineString, Polygon, MultiPolygon
from shapely.ops import unary_union
from shapely.geometry.polygon import orient

ROUND = 0.05
EXCLUDE_BLOCKS_EXACT = {'PICT_OWNER'}
EXCLUDE_BLOCKS_PREFIX = ('OLAY',)
TITLE_PAD = 3.0


def rnd(v):
    return round(v / ROUND) * ROUND


class Prim:
    __slots__ = ('key', 'bbox', 'geom', 'new')

    def __init__(self, key, bbox, geom):
        self.key = key
        self.bbox = bbox
        self.geom = geom          # shapely geometry in sheet mm, for the band
        self.new = False          # set by diff(): True = only in the new file

    def shape(self):
        """what the primitive IS regardless of where it is, for move
        detection: text + rotation, line length + angle, arc radius +
        sweep, otherwise the box size"""
        k = self.key
        t = k[0]
        if t == 'T':
            return ('T', k[3], k[4])
        if t in ('L', 'P'):
            dx, dy = k[3] - k[1], k[4] - k[2]
            ang = math.degrees(math.atan2(dy, dx)) % 180.0
            return (t, round(math.hypot(dx, dy), 1), round(ang, 0) % 180.0)
        if t in ('A', 'C'):
            sweep = round(k[5] - k[4], 0) if len(k) > 5 else 360.0
            return (t, k[3], sweep)
        b = self.bbox
        return (t, round(b[2] - b[0], 1), round(b[3] - b[1], 1))

    def centre(self):
        b = self.bbox
        return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def box_geom(bb):
    # a plain rectangle from the bbox -- except a bbox that is zero-width
    # or zero-height (a straight horizontal/vertical line, or a point)
    # turns into a zero-area sliver, and shapely's .intersection().area
    # between a zero-area sliver and anything is always 0 even when the
    # sliver genuinely runs straight through the other shape. that made
    # place_triangles() blind to a grid reference line crossing a
    # candidate triangle box: the line was in the obstacle map (correct
    # bbox and all), scored as clean anyway because "overlap area" of a
    # 1-D line has no area to measure (2026-09-18, a revision triangle
    # sat straddling a grid line with a "0 sq mm" score). half a mm each
    # side is the same padding a true point already got below
    x1, y1, x2, y2 = bb
    if x2 - x1 < 1e-6:
        x1, x2 = x1 - 0.5, x2 + 0.5
    if y2 - y1 < 1e-6:
        y1, y2 = y1 - 0.5, y2 + 0.5
    return Polygon([(x1, y1), (x2, y1), (x2, y2), (x1, y2)])


def bbox_union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def bbox_inside(inner, outer):
    return (inner[0] >= outer[0] and inner[1] >= outer[1]
            and inner[2] <= outer[2] and inner[3] <= outer[3])


def bbox_near(a, b, gap):
    return (a[0] <= b[2] + gap and a[2] >= b[0] - gap
            and a[1] <= b[3] + gap and a[3] >= b[1] - gap)


def entity_layer(e):
    try:
        return (e.dxf.layer or '').upper()
    except Exception:
        return ''


class Ins:
    """a top-level INSERT, kept whole until the block matching decides
    whether it needs exploding at all"""
    __slots__ = ('entity', 'name', 'sig', 'pos', 'rot', 'scale')

    def __init__(self, entity, name, sig):
        self.entity = entity
        self.name = name
        self.sig = sig
        i = entity.dxf.insert
        self.pos = (rnd(i.x), rnd(i.y))
        self.rot = round(float(entity.dxf.rotation or 0.0), 1)
        self.scale = (round(float(entity.dxf.xscale or 1.0), 4), round(float(entity.dxf.yscale or 1.0), 4))

    def exact(self):
        return (self.sig, self.pos, self.rot, self.scale)

    def same(self):
        return (self.sig, self.rot, self.scale)


class CloudIndex:
    """the vertices of one cloud PML reported, in 1mm cells, so a DXF
    vertex can be matched to within a tolerance rather than exactly:
    the values come back through 'var !xy xypo of <vrtx>' and a
    project's display precision decides how many decimals that keeps"""
    __slots__ = ('n', 'cells')

    def __init__(self, pts):
        self.n = len(pts)
        self.cells = collections.defaultdict(list)
        for x, y in pts:
            self.cells[(int(math.floor(x)), int(math.floor(y)))].append((x, y))

    def near(self, x, y, tol):
        cx, cy = int(math.floor(x)), int(math.floor(y))
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for px, py in self.cells.get((cx + i, cy + j), ()):
                    if abs(px - x) <= tol and abs(py - y) <= tol:
                        return True
        return False


def read_clouds(path):
    """the clouds PML says are on the sheet, one CloudIndex per cloud"""
    clouds = []
    cur = None
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                w = line.split()
                if not w:
                    continue
                if w[0] == 'cloud':
                    cur = []
                elif w[0] == 'v' and cur is not None and len(w) >= 3:
                    try:
                        cur.append((float(w[1]), float(w[2])))
                    except ValueError:
                        pass
                elif w[0] == 'end' and cur:
                    clouds.append(CloudIndex(cur))
                    cur = None
    except OSError:
        return []
    return [c for c in clouds if c.n >= 4]


def is_old_cloud(e, clouds):
    """a top-level polyline whose vertices are (nearly all) the vertices
    of one of the clouds PML reported -- DXFOUT writes an OUTL out as one
    POLYLINE with exactly the VRTX positions, so the match is tight"""
    if not clouds:
        return False
    t = e.dxftype()
    if t not in ('POLYLINE', 'LWPOLYLINE'):
        return False
    try:
        pts = [(v.x, v.y) for v in (e.points() if t == 'POLYLINE' else e.vertices_in_wcs())]
    except Exception:
        return False
    if len(pts) < 8:
        return False
    for c in clouds:
        # 0.75mm: enough for a value PML handed over with no decimals at
        # all, far too little to confuse one cloud with another
        hit = sum(1 for x, y in pts if c.near(x, y, 0.75))
        if hit >= 0.9 * len(pts):
            return True
    return False


def flatten(doc, cloud_layer, log, old_clouds=None):
    """modelspace -> (prims, inserts, ...): every non-INSERT entity as a
    Prim in sheet coordinates, every top-level INSERT as an Ins carrying
    its content signature. explode() turns an Ins into Prims later, for
    the inserts the block matching could not pair off.

    also returns the extents of every excluded OLAY* insert and the top
    of the backing sheet's title strip (see _title_scan), for the region
    exclusions applied afterwards.
    """
    prims = []
    inserts = []
    excluded = []
    olay_boxes = []
    sigcache = {}
    title_y = [None]
    title_n = [0]
    dropped_layer = [0]
    dropped_block = [0]
    sheet_h = None
    sheet_w = None
    try:
        ext = doc.header.get('$EXTMAX')
        sheet_w = float(ext[0])
        sheet_h = float(ext[1])
    except Exception:
        pass

    def add(key, bbox, geom=None):
        prims.append(Prim(key, bbox, geom if geom is not None else box_geom(bbox)))

    def block_sig(name):
        """content signature of a block definition: its primitive keys in
        block-local coordinates, nested blocks by their own signature"""
        if name in sigcache:
            return sigcache[name]
        sigcache[name] = 0            # guard against a self-referencing block
        saved = list(prims)
        del prims[:]
        try:
            # DXFOUT writes every LABELn / VIEWn block with its base point
            # AT the insert point and the entities in absolute sheet
            # coordinates, so block-local means minus the base point --
            # without that a label that merely moved has a different
            # signature every time
            blk = doc.blocks[name]
            bp = blk.base_point
            walk(list(blk), Matrix44.translate(-bp[0], -bp[1], 0), name, nested='ref')
            keys = tuple(sorted(str(q.key) for q in prims))
        except Exception:
            keys = ('?', name)
        del prims[:]
        prims.extend(saved)
        sig = hash(keys)
        sigcache[name] = sig
        return sig

    def walk(entities, m, blockname, nested='explode'):
        for e in entities:
            t = e.dxftype()
            if cloud_layer and entity_layer(e) == cloud_layer:
                dropped_layer[0] += 1
                continue
            if nested == 'defer' and old_clouds and is_old_cloud(e, old_clouds):
                dropped_layer[0] += 1
                continue
            if t == 'INSERT' and nested == 'ref':
                # inside a block definition: the nested block by identity
                i = m.transform(e.dxf.insert)
                add(('I', block_sig(e.dxf.name), rnd(i.x), rnd(i.y), round(float(e.dxf.rotation or 0.0), 1)),
                    (i.x, i.y, i.x, i.y), None)
                continue
            if t == 'INSERT' and nested == 'defer':
                name = e.dxf.name
                uname = name.upper()
                if not (uname in EXCLUDE_BLOCKS_EXACT or uname.startswith(EXCLUDE_BLOCKS_PREFIX)):
                    inserts.append(Ins(e, name, block_sig(name)))
                    continue
            if t == 'INSERT':
                name = e.dxf.name
                uname = name.upper()
                if uname in EXCLUDE_BLOCKS_EXACT or uname.startswith(EXCLUDE_BLOCKS_PREFIX):
                    dropped_block[0] += 1
                    if nested == 'defer':
                        excluded.append(Ins(e, name, 0))
                    if uname.startswith(EXCLUDE_BLOCKS_PREFIX):
                        try:
                            from ezdxf import bbox as _bb
                            ex = _bb.extents(e.virtual_entities(), fast=True)
                            olay_boxes.append((ex.extmin.x, ex.extmin.y, ex.extmax.x, ex.extmax.y))
                        except Exception:
                            pass
                    if uname in EXCLUDE_BLOCKS_EXACT:
                        # remember where the backing sheet's texts are, the
                        # title strip is derived from them
                        try:
                            for ve in e.virtual_entities():
                                _title_scan(ve, m)
                        except Exception:
                            pass
                    continue
                try:
                    for ve in e.virtual_entities():
                        walk([ve], m, name)
                except Exception as ex:
                    log('  warn: cannot explode INSERT %s: %s' % (name, ex))
                continue
            if t == 'LINE':
                a = m.transform(e.dxf.start)
                b = m.transform(e.dxf.end)
                pa = (rnd(a.x), rnd(a.y))
                pb = (rnd(b.x), rnd(b.y))
                if pb < pa:
                    pa, pb = pb, pa
                add(('L',) + pa + pb, (min(pa[0], pb[0]), min(pa[1], pb[1]), max(pa[0], pb[0]), max(pa[1], pb[1])), LineString([pa, pb]))
            elif t in ('POLYLINE', 'LWPOLYLINE'):
                # a segment with a bulge is an arc, and DXFOUT draws every
                # circle as a closed polyline of two bulge-1 vertices (a
                # vessel, 2026-09-18). the vertices alone make that one
                # chord across the middle: the outline was neither an
                # obstacle for the triangle -- it landed on the vessel --
                # nor properly compared. so a polyline with any bulge is
                # taken apart into its lines and arcs and those are read
                # like any other LINE / ARC
                try:
                    if t == 'POLYLINE':
                        bulged = any(float(v.dxf.bulge or 0.0) != 0.0 for v in e.vertices)
                    else:
                        bulged = any(float(q[4] or 0.0) != 0.0 for q in e.get_points())
                except Exception:
                    bulged = False
                if bulged:
                    try:
                        for ve in e.virtual_entities():
                            walk([ve], m, blockname)
                    except Exception as ex:
                        log('  warn: bulged polyline skipped: %s' % ex)
                    continue
                try:
                    if t == 'POLYLINE':
                        pts = [m.transform(p) for p in e.points()]
                        closed = e.is_closed
                    else:
                        pts = [m.transform(p) for p in e.vertices_in_wcs()]
                        closed = e.closed
                except Exception as ex:
                    log('  warn: polyline skipped: %s' % ex)
                    continue
                pts = [(rnd(p.x), rnd(p.y)) for p in pts]
                if closed and len(pts) > 2:
                    pts = pts + pts[:1]
                for a, b in zip(pts, pts[1:]):
                    pa, pb = (a, b) if a <= b else (b, a)
                    add(('P',) + pa + pb, (min(pa[0], pb[0]), min(pa[1], pb[1]), max(pa[0], pb[0]), max(pa[1], pb[1])), LineString([pa, pb]))
            elif t in ('ARC', 'CIRCLE'):
                c = m.transform(e.dxf.center)
                r = float(e.dxf.radius)
                key = (t[0], rnd(c.x), rnd(c.y), rnd(r))
                a0, a1 = 0.0, 360.0
                if t == 'ARC':
                    a0, a1 = float(e.dxf.start_angle), float(e.dxf.end_angle)
                    if a1 <= a0:
                        a1 += 360.0
                    key = key + (round(a0, 1), round(a1, 1))
                # sampled arc for the band; the matrix is applied to the
                # centre only (a rotated/scaled INSERT of an arc is rare
                # on these sheets and only shifts the cloud by its radius)
                n = max(4, int((a1 - a0) / 15.0) + 1)
                arcpts = [(c.x + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
                           c.y + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
                # the box of the arc itself, not of its whole circle: a
                # semicircle (half of every DXFOUT circle) would otherwise
                # block the entire disc for the triangle and pull anything
                # within --gap of the disc into the vessel's cluster
                add(key, (min(q[0] for q in arcpts), min(q[1] for q in arcpts), max(q[0] for q in arcpts), max(q[1] for q in arcpts)), LineString(arcpts))
            elif t in ('TEXT', 'MTEXT'):
                p = m.transform(e.dxf.insert)
                if t == 'TEXT':
                    txt = e.dxf.text
                    h = float(e.dxf.height or 2.5)
                else:
                    txt = e.plain_text()
                    h = float(e.dxf.char_height or 2.5)
                # DXFOUT writes MTEXT rotation as a text_direction vector,
                # not the rotation attribute; get_rotation() understands
                # both. read as 0 it laid every vertical support tag out
                # sideways, 26mm to the right of where it stands, and the
                # band grew a lobe there (first real run, 2026-09-14)
                try:
                    rot = float(e.get_rotation()) if t == 'MTEXT' else float(e.dxf.rotation or 0.0)
                except Exception:
                    rot = 0.0
                # ezdxf 1.4 leaves the MTEXT escapes in plain_text(): '\~'
                # is a hard space, '\P' a line break. only the width and
                # the line count care; the key keeps the raw string
                meas = txt.replace('\\~', ' ').replace('\\P', '\n') if txt else ''
                lines = meas.split('\n') if meas else ['']
                w = max(len(s) for s in lines) * h * 0.8
                hh = h * 1.2 * len(lines)
                # the box the text occupies, turned with the text: a
                # dimension value standing along a vertical chain must
                # bulge the band along the chain, not sideways off it
                # (2026-09-14). where the insert point sits on that box is
                # the attachment: DXFOUT uses all nine for MTEXT (a sheet
                # counted 79 middle-centre, 74 top-left, 26 middle-left, 25
                # top-centre, ...) and treating every one as top-left put
                # the box of a bottom-centre MATCH LINE text to the right
                # of and below where the text is, so the revision
                # triangle landed on the text (2026-09-15). TEXT has the
                # same idea in halign/valign with the anchor in
                # align_point when either is set
                if t == 'MTEXT':
                    ap = int(e.dxf.attachment_point or 1)
                    col = (ap - 1) % 3          # 0 left, 1 centre, 2 right
                    row = (ap - 1) // 3         # 0 top, 1 middle, 2 bottom
                    x0 = (0.0, -w / 2, -w)[col]
                    y0 = (-hh, -hh / 2, 0.0)[row]
                else:
                    ha = int(e.dxf.halign or 0)
                    va = int(e.dxf.valign or 0)
                    if (ha or va) and e.dxf.hasattr('align_point'):
                        p = m.transform(e.dxf.align_point)
                    x0 = {1: -w / 2, 2: -w, 4: -w / 2}.get(ha, 0.0)
                    y0 = {2: -h / 2, 3: -h, 4: -h / 2}.get(va if ha != 4 else 4, 0.0)
                    hh = h
                local = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + hh), (x0, y0 + hh)]
                cr, sr = math.cos(math.radians(rot)), math.sin(math.radians(rot))
                corners = [(p.x + lx * cr - ly * sr, p.y + lx * sr + ly * cr) for lx, ly in local]
                xs = [q[0] for q in corners]
                ys = [q[1] for q in corners]
                add(('T', rnd(p.x), rnd(p.y), round(rot, 1), txt), (min(xs), min(ys), max(xs), max(ys)), Polygon(corners))
            elif t == 'HATCH':
                # a boundary path is a PolylinePath (has .vertices) or an
                # EdgePath (line/arc/ellipse/spline edges, no .vertices at
                # all -- the fill of a support symbol's icon is drawn this
                # way). the hand-rolled loop this used to be only read
                # .vertices, so an EdgePath hatch measured nothing, bb
                # stayed None and the whole hatch was dropped: invisible
                # to both the obstacle map (a revision triangle landed
                # square on a support icon's fill, 2026-09-18) and the
                # diff (a hatch that moved was never clouded either).
                # ezdxf's own bbox already walks every path/edge type
                # correctly, so this uses that instead of any of its own
                try:
                    from ezdxf import bbox as _bb
                    ex = _bb.extents([e], fast=True)
                    if ex.has_data:
                        q0 = m.transform((ex.extmin.x, ex.extmin.y, 0))
                        q1 = m.transform((ex.extmax.x, ex.extmax.y, 0))
                        bb = (min(q0.x, q1.x), min(q0.y, q1.y), max(q0.x, q1.x), max(q0.y, q1.y))
                    else:
                        bb = None
                except Exception:
                    bb = None
                if bb:
                    add(('H',) + tuple(rnd(v) for v in bb), bb)
            elif t in ('POINT', 'SOLID', 'ELLIPSE', 'SPLINE'):
                try:
                    from ezdxf import bbox as _bb
                    ex = _bb.extents([e], fast=True)
                    bb = (ex.extmin.x, ex.extmin.y, ex.extmax.x, ex.extmax.y)
                    add((t[0] + t[1],) + tuple(rnd(v) for v in bb), bb)
                except Exception:
                    pass
            # anything else (ATTDEF, DIMENSION stubs, ...) is ignored

    def _title_scan(ve, m):
        # the title block is the band of backing-sheet texts along the
        # bottom. the frame also carries zone letters/numbers round all
        # four borders (A..N at the top, 1..9 down both sides at x~22 and
        # x~815 on an A1), so only texts in the bottom 15% AND clear of
        # the side margins count -- taking the highest lower-half text
        # instead swallowed half the drawing (y 276) on the first try
        t = ve.dxftype()
        if t not in ('TEXT', 'MTEXT'):
            if t == 'INSERT':
                try:
                    for x in ve.virtual_entities():
                        _title_scan(x, m)
                except Exception:
                    pass
            return
        p = m.transform(ve.dxf.insert)
        if sheet_h is None or sheet_w is None:
            return
        if p.y < sheet_h * 0.15 and sheet_w * 0.04 < p.x < sheet_w * 0.96:
            title_n[0] += 1
            if title_y[0] is None or p.y > title_y[0]:
                title_y[0] = p.y

    walk(doc.modelspace(), Matrix44(), None, nested='defer')
    if title_n[0] < 3:
        title_y[0] = None       # no recognisable title block, do not guess

    def explode(ins):
        """the Prims of one deferred INSERT, in sheet coordinates"""
        saved = list(prims)
        del prims[:]
        try:
            walk(list(ins.entity.virtual_entities()), Matrix44(), ins.name)
        except Exception as ex:
            log('  warn: cannot explode INSERT %s: %s' % (ins.name, ex))
        out = [q for q in prims if q.geom is not None]
        del prims[:]
        prims.extend(saved)
        return out

    return prims, inserts, explode, olay_boxes, title_y[0], sheet_h, dropped_layer[0], dropped_block[0], excluded


def bbox_touches(b, r):
    return b[0] <= r[2] and b[2] >= r[0] and b[1] <= r[3] and b[3] >= r[1]


def apply_canvas(prims, canvas, watches):
    """with a canvas: a primitive counts when its box touches the canvas
    or a watched rectangle. returns (kept, dropped)"""
    if canvas is None:
        return prims, 0
    keep = []
    dropped = 0
    for p in prims:
        if bbox_touches(p.bbox, canvas) or any(bbox_touches(p.bbox, r) for r in watches):
            keep.append(p)
        else:
            dropped += 1
    return keep, dropped


def watched_from_excluded(excl, explode, watches):
    """the primitives of the excluded blocks (the backing sheet) that
    lie in a watched rectangle: those are compared like anything else"""
    if not watches:
        return []
    out = []
    for ins in excl:
        for q in explode(ins):
            if any(bbox_touches(q.bbox, r) for r in watches):
                out.append(q)
    return out


def apply_regions(prims, regions):
    if not regions:
        return prims, 0
    keep = []
    dropped = 0
    for p in prims:
        if any(bbox_inside(p.bbox, r) for r in regions):
            dropped += 1
        else:
            keep.append(p)
    return keep, dropped


def diff(old, new):
    ko = set(p.key for p in old)
    kn = set(p.key for p in new)
    removed = [p for p in old if p.key not in kn]
    added = [p for p in new if p.key not in ko]
    for p in added:
        p.new = True
    return removed, added


def _seg(p):
    k = p.key
    return (k[1], k[2]), (k[3], k[4])


def trim_collinear(removed, added, tol=0.1):
    """new and old line segments that lie on the same line and overlap:
    each keeps as cloud geometry only what the other side did not cover.
    a segment left with nothing keeps geom None and adds no band"""
    def is_line(p):
        return p.key[0] in ('L', 'P')
    old_lines = [p for p in removed if is_line(p)]
    new_lines = [p for p in added if is_line(p)]
    if not old_lines or not new_lines:
        return 0
    # bucket old segments by direction so the search stays cheap
    buckets = collections.defaultdict(list)
    for p in old_lines:
        (x1, y1), (x2, y2) = _seg(p)
        ang = round(math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0)
        buckets[ang % 180].append(p)
    trimmed = 0
    cover_old = collections.defaultdict(list)     # old prim -> [(t0,t1)] covered by new
    for q in new_lines:
        (ax, ay), (bx, by) = _seg(q)
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        if L < 1e-6:
            continue
        ux, uy = dx / L, dy / L
        ang = round(math.degrees(math.atan2(dy, dx)) % 180.0)
        cands = buckets.get(ang % 180, []) + buckets.get((ang + 1) % 180, []) + buckets.get((ang - 1) % 180, [])
        covered = []
        for o in cands:
            (cx, cy), (ex, ey) = _seg(o)
            # perpendicular distance of both old endpoints from the new line
            d1 = abs((cx - ax) * uy - (cy - ay) * ux)
            d2 = abs((ex - ax) * uy - (ey - ay) * ux)
            if d1 > tol or d2 > tol:
                continue
            t0 = (cx - ax) * ux + (cy - ay) * uy
            t1 = (ex - ax) * ux + (ey - ay) * uy
            lo, hi = max(0.0, min(t0, t1)), min(L, max(t0, t1))
            if hi - lo <= tol:
                continue
            covered.append((lo, hi))
            # and the reverse: which part of the old one the new one covers
            oL = math.hypot(ex - cx, ey - cy)
            if oL > 1e-6:
                ox, oy = (ex - cx) / oL, (ey - cy) / oL
                s0 = (ax - cx) * ox + (ay - cy) * oy
                s1 = (bx - cx) * ox + (by - cy) * oy
                cover_old[id(o)].append((max(0.0, min(s0, s1)), min(oL, max(s0, s1))))
        if not covered:
            continue
        q.geom = _uncovered((ax, ay), (ux, uy), L, covered)
        trimmed += 1
    for o in old_lines:
        iv = cover_old.get(id(o))
        if not iv:
            continue
        (cx, cy), (ex, ey) = _seg(o)
        oL = math.hypot(ex - cx, ey - cy)
        if oL < 1e-6:
            continue
        o.geom = _uncovered((cx, cy), ((ex - cx) / oL, (ey - cy) / oL), oL, iv)
        trimmed += 1
    return trimmed


def _uncovered(a, u, L, intervals):
    """the parts of a segment of length L from a along unit u that no
    interval covers, as a shapely geometry (None when nothing is left)"""
    intervals = sorted(intervals)
    parts = []
    pos = 0.0
    for lo, hi in intervals:
        if lo > pos + 0.05:
            parts.append((pos, lo))
        pos = max(pos, hi)
    if L > pos + 0.05:
        parts.append((pos, L))
    if not parts:
        return None
    lines = [LineString([(a[0] + u[0] * t0, a[1] + u[1] * t0), (a[0] + u[0] * t1, a[1] + u[1] * t1)]) for t0, t1 in parts]
    if len(lines) == 1:
        return lines[0]
    return unary_union(lines)


def trim_hinged(removed, added, hinge, log=None, tol=0.1):
    """new and old line segments that share one end within tol and have
    the other ends within hinge of each other: both are dropped from the
    clouds (geom None). returns how many pairs were hinged"""
    if hinge <= 0:
        return 0

    def is_line(p):
        return p.key[0] in ('L', 'P') and p.geom is not None
    old_lines = [p for p in removed if is_line(p)]
    new_lines = [p for p in added if is_line(p)]
    if not old_lines or not new_lines:
        return 0
    # old segments by their (rounded) endpoints, so the shared end is a
    # dictionary hit rather than a scan
    by_end = collections.defaultdict(list)
    for o in old_lines:
        for pt in _seg(o):
            by_end[(round(pt[0], 1), round(pt[1], 1))].append(o)
    used = set()
    n = 0
    for q in new_lines:
        a, b = _seg(q)
        best = None
        for shared, far_new in ((a, b), (b, a)):
            for o in by_end.get((round(shared[0], 1), round(shared[1], 1)), []):
                if id(o) in used:
                    continue
                c, d = _seg(o)
                if math.hypot(c[0] - shared[0], c[1] - shared[1]) <= tol:
                    far_old = d
                elif math.hypot(d[0] - shared[0], d[1] - shared[1]) <= tol:
                    far_old = c
                else:
                    continue
                dd = math.hypot(far_old[0] - far_new[0], far_old[1] - far_new[1])
                if dd <= hinge and (best is None or dd < best[0]):
                    best = (dd, o, far_new)
        if best is None:
            continue
        dd, o, far_new = best
        used.add(id(o))
        o.geom = None
        q.geom = None
        n += 1
        if log:
            (c, d) = _seg(o)
            log('  hinged: old %.1f,%.1f-%.1f,%.1f -> new %.1f,%.1f-%.1f,%.1f, end moved %.1fmm'
                % (c[0], c[1], d[0], d[1], a[0], a[1], b[0], b[1], dd))
    return n


def read_dimlines(path):
    """'dimline <dir> x1 y1 x2 y2' records (DrawingPlan1DimLines), the
    file PML also feeds BlankPos. missing or unreadable = no records"""
    segs = []
    if not path:
        return segs
    try:
        with open(path, encoding='utf-8-sig', errors='ignore') as f:
            for ln in f:
                p = ln.split()
                if len(p) >= 6 and p[0].lower() == 'dimline':
                    try:
                        segs.append((p[1].lower(), float(p[2]), float(p[3]), float(p[4]), float(p[5])))
                    except ValueError:
                        pass
    except OSError:
        pass
    return segs


DIM_TOL = 0.5            # depth (a horizontal line's y, a vertical one's x)
DIM_OVERLAP_FRAC = 0.5   # of the DXF line's length inside the listed segment
DIM_MIN_OVERLAP = 1.0    # mm


def on_dimline(p, segs):
    """is this LINE primitive lying on one of the listed projection lines.
    the test BlankPos uses (is_soft_dim_line): overlap, not containment --
    the DXF line overshoots the dimension line by the 2mm extension, and a
    GAP may have cut it into pieces"""
    if p.key[0] != 'L' or not segs:
        return False
    (sx, sy), (tx, ty) = _seg(p)
    for _d, x1, y1, x2, y2 in segs:
        if abs(y1 - y2) <= DIM_TOL:
            depth = (y1 + y2) * 0.5
            if abs(sy - depth) > DIM_TOL or abs(ty - depth) > DIM_TOL:
                continue
            lo, hi = min(x1, x2), max(x1, x2)
            a, b = min(sx, tx), max(sx, tx)
        elif abs(x1 - x2) <= DIM_TOL:
            depth = (x1 + x2) * 0.5
            if abs(sx - depth) > DIM_TOL or abs(tx - depth) > DIM_TOL:
                continue
            lo, hi = min(y1, y2), max(y1, y2)
            a, b = min(sy, ty), max(sy, ty)
        else:
            continue
        overlap = min(hi, b) - max(lo, a)
        if overlap >= DIM_MIN_OVERLAP and overlap >= DIM_OVERLAP_FRAC * (b - a):
            return True
    return False


def drop_dimlines(removed, added, old_segs, new_segs):
    """projection lines out of the diff altogether -- not geom None, which
    would still glue the dimension figures' cluster to the pipe's through
    the line's bbox. returns (removed, added, n_old_dropped, n_new_dropped)"""
    r2 = [p for p in removed if not on_dimline(p, old_segs)]
    a2 = [p for p in added if not on_dimline(p, new_segs)]
    return r2, a2, len(removed) - len(r2), len(added) - len(a2)


def drop_moved(removed, added, move_dist):
    """removed primitives that reappear, same shape, within move_dist of
    where they were -- a move, not a deletion. returns (kept, moved)"""
    if move_dist <= 0:
        return removed, []
    pool = collections.defaultdict(list)
    for a in added:
        pool[a.shape()].append(a)
    kept = []
    moved = []
    for r in removed:
        cands = pool.get(r.shape())
        hit = None
        if cands:
            rx, ry = r.centre()
            best = None
            for i, a in enumerate(cands):
                ax, ay = a.centre()
                dd = math.hypot(ax - rx, ay - ry)
                if dd <= move_dist and (best is None or dd < best[0]):
                    best = (dd, i)
            if best is not None:
                hit = cands.pop(best[1])
        if hit is None:
            kept.append(r)
        else:
            moved.append(r)
    return kept, moved


def cluster(prims, gap):
    """group changed primitives whose bounding boxes lie within gap of each
    other. coarse and cheap; the band stage below decides the final shape"""
    items = [(p.bbox, [p]) for p in prims]
    clusters = []
    while items:
        cur, members = items.pop()
        changed = True
        while changed:
            changed = False
            rest = []
            for b, mem in items:
                if bbox_near(cur, b, gap):
                    cur = bbox_union(cur, b)
                    members = members + mem
                    changed = True
                else:
                    rest.append((b, mem))
            items = rest
        clusters.append((cur, members))
    merged = True
    while merged:
        merged = False
        out = []
        while clusters:
            c, mem = clusters.pop()
            for i, (d, dm) in enumerate(out):
                if bbox_near(c, d, gap):
                    out[i] = (bbox_union(c, d), dm + mem)
                    merged = True
                    break
            else:
                out.append((c, mem))
        clusters = out
    return [mem for _, mem in clusters]


def band(prims, pad, gap):
    """the band round a cluster's changed geometry: union of every
    primitive buffered by pad, then closed with gap/2 so pieces nearer
    than gap join and holes narrower than gap fill. a list of polygons"""
    use = [p for p in prims if p.new]
    if not use:
        use = prims                  # pure deletion: cloud where it was
    shapes = [p.geom.buffer(pad) for p in use if p.geom is not None]
    if not shapes:
        return []
    u = unary_union(shapes)
    if gap > 0:
        u = u.buffer(gap / 2.0).buffer(-gap / 2.0)
    u = u.simplify(0.5)
    if u.is_empty:
        return []
    if isinstance(u, Polygon):
        return [u]
    if isinstance(u, MultiPolygon):
        return list(u.geoms)
    return [g for g in getattr(u, 'geoms', []) if isinstance(g, Polygon)]


def scallop_ring(coords, chord, arcseg, bulge=0.6):
    """scallop one ring. coords must run with the band on the LEFT (outer
    ring counter-clockwise, hole clockwise, as shapely's orient() gives),
    so the right-hand normal points away from the band and every bulge
    goes outward -- into open paper on the outside, into the hole on the
    inside. the ring is resampled every ~chord mm; the source vertices do
    not matter. closed, first point repeated at the end"""
    ring = LineString(list(coords))
    length = ring.length
    if length < chord:
        return []
    n = max(3, int(round(length / chord)))
    c = length / n
    base = [ring.interpolate(i * c) for i in range(n)]
    base.append(base[0])
    pts = []
    for i in range(n):
        p0, p1 = base[i], base[i + 1]
        ex, ey = p1.x - p0.x, p1.y - p0.y
        d = math.hypot(ex, ey)
        if d < 1e-9:
            continue
        tx, ty = ex / d, ey / d
        nx, ny = ty, -tx                 # right-hand normal = away from band
        mx, my = (p0.x + p1.x) / 2.0, (p0.y + p1.y) / 2.0
        half = d / 2.0
        h = max(0.05, bulge * half)      # sagitta
        R = (half * half + h * h) / (2.0 * h)
        cx, cy = mx - nx * (R - h), my - ny * (R - h)     # centre on the band side
        a = math.asin(min(1.0, half / R))                  # half the arc angle
        for sgm in range(arcseg + 1):
            if sgm == 0 and pts:
                continue
            th = -a + 2.0 * a * sgm / arcseg               # from p0 to p1
            # rotate the outward normal by th towards the chord direction
            ux = nx * math.cos(th) + tx * math.sin(th)
            uy = ny * math.cos(th) + ty * math.sin(th)
            pts.append((cx + R * ux, cy + R * uy))
    if pts and pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


def cloud_rings(poly, chord, arcseg, bulge):
    """(is_hole, bbox, points) for the outer ring and every hole of poly"""
    poly = orient(poly, 1.0)             # exterior CCW, holes CW
    out = []
    rings = [(False, poly.exterior)] + [(True, r) for r in poly.interiors]
    for hole, ring in rings:
        pts = scallop_ring(ring.coords, chord, arcseg, bulge)
        if not pts:
            continue
        xs = [q[0] for q in pts]
        ys = [q[1] for q in pts]
        out.append((hole, (min(xs), min(ys), max(xs), max(ys)), pts))
    return out


class ObstacleMap:
    """axis aligned boxes in 20mm cells, so 'does this box touch
    anything' is a few cells and not the whole sheet"""
    CELL = 20.0
    __slots__ = ('cells', 'n')

    def __init__(self, boxes=()):
        self.cells = collections.defaultdict(list)
        self.n = 0
        for b in boxes:
            self.add(b)

    def _span(self, b):
        c = self.CELL
        return (int(math.floor(b[0] / c)), int(math.floor(b[1] / c)),
                int(math.floor(b[2] / c)), int(math.floor(b[3] / c)))

    def add(self, b):
        if b is None:
            return
        i0, j0, i1, j1 = self._span(b)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                self.cells[(i, j)].append(b)
        self.n += 1

    def hits(self, b):
        i0, j0, i1, j1 = self._span(b)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                for o in self.cells.get((i, j), ()):
                    if o[0] <= b[2] and o[2] >= b[0] and o[1] <= b[3] and o[3] >= b[1]:
                        return True
        return False

    def near(self, b):
        # boxes sharing a cell with b, touching or not -- for scoring how
        # bad a not-quite-free spot is, not just whether one exists
        i0, j0, i1, j1 = self._span(b)
        seen = set()
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                for o in self.cells.get((i, j), ()):
                    if id(o) not in seen:
                        seen.add(id(o))
                        yield o


def place_triangles(rings, obstacles, side, bounds, log, margin=0.5, gap=0.8, reach=40.0):
    """where the revision triangle of every outer ring goes: {ring index:
    (x, y)} with (x, y) the bottom left corner of the triangle's box.
    rings are (cluster, hole, bbox, pts) in output order. see the module
    docstring for how a candidate is scored"""
    from shapely.geometry import box as _box
    w = side
    h = side * 0.866
    step = max(1.5, w / 4.0)
    polys = []
    for k, hole, bb, pts in rings:
        try:
            polys.append(Polygon(pts))
        except Exception:
            polys.append(None)
    placed = ObstacleMap()
    placed_polys = []
    out = {}
    for idx, (k, hole, bb, pts) in enumerate(rings):
        if hole:
            continue
        cx, cy = (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0
        this_poly = polys[idx]
        other_polys = [p for j, p in enumerate(polys) if j != idx and p is not None]

        def score(x, y):
            # None if outside the sheet/canvas, else (overlap area,
            # distance to the ring's centre) -- smaller is better, overlap
            # compared first so any clean spot always beats any dirty one.
            #
            # overlap is measured against the box padded by `margin`, not
            # the bare box -- a first version measured the bare box here
            # and only used the padded one to decide which obstacles were
            # worth fetching from the spatial index, so a candidate that
            # merely grazed something (missed by a fraction of a mm) came
            # back as perfectly clean and was never pushed away from it. a
            # support icon's fill sat 0.04mm from a "clean" triangle this
            # way and still read as a collision on paper (2026-09-18: this
            # padded box is the one the module docstring already promised)
            box = (x, y, x + w, y + h)
            if box[0] < bounds[0] or box[1] < bounds[1] or box[2] > bounds[2] or box[3] > bounds[3]:
                return None
            mb = (x - margin, y - margin, x + w + margin, y + h + margin)
            mshp = _box(*mb)
            pen = 0.0
            if obstacles is not None:
                for ob in obstacles.near(mb):
                    ib = box_geom(ob).intersection(mshp)
                    if not ib.is_empty:
                        pen += ib.area
            for p in other_polys:
                ib = p.intersection(mshp)
                if not ib.is_empty:
                    pen += ib.area
            for p in placed_polys:
                ib = p.intersection(mshp)
                if not ib.is_empty:
                    pen += ib.area
            # the ring itself is the one thing tested with the BARE box:
            # every candidate hangs a bare `gap` off one of its own
            # scallops, so the padded box always grazes the tip it came
            # from, and padding here would reject every candidate outright
            if this_poly is not None:
                shp = _box(*box)
                ib = this_poly.intersection(shp)
                if not ib.is_empty:
                    pen += ib.area
            dist = math.hypot(x + w / 2.0 - cx, y + h / 2.0 - cy)
            return (pen, dist)

        # candidate anchors: the scallop tips, four offsets each -- cheap,
        # and where a clean spot almost always is
        cands = []
        for tx, ty in set(pts[::max(1, len(pts) // 60)]):
            for dx, dy in ((gap, gap), (-w - gap, gap), (gap, -h - gap), (-w - gap, -h - gap)):
                cands.append((tx + dx, ty + dy))
        best = None
        for x, y in cands:
            sc = score(x, y)
            if sc is None:
                continue
            if best is None or sc < best[0]:
                best = (sc, x, y)
            if sc[0] <= 1e-6:
                break
        # nothing clean at the scallops: widen out from the ring's own box,
        # a ring of candidates every `step` at each growing distance, up to
        # `reach`. only runs while best is still dirty, so a clean scallop
        # candidate never pays for this
        if best is None or best[0][0] > 1e-6:
            d = gap + step
            while d <= reach:
                x0, y0, x1, y1 = bb[0] - d - w, bb[1] - d - h, bb[2] + d, bb[3] + d
                found_clean = False
                x = x0
                while x <= x1 + 1e-9:
                    for y in (y1, y0):
                        sc = score(x, y)
                        if sc is not None and (best is None or sc < best[0]):
                            best = (sc, x, y)
                            if sc[0] <= 1e-6:
                                found_clean = True
                    x += step
                y = y0
                while y <= y1 + 1e-9:
                    for x in (x1, x0):
                        sc = score(x, y)
                        if sc is not None and (best is None or sc < best[0]):
                            best = (sc, x, y)
                            if sc[0] <= 1e-6:
                                found_clean = True
                    y += step
                if found_clean:
                    break
                d += step
        if best is None:
            found = (bb[2] + gap, bb[3] + gap)
            log('  ring %d: nowhere inside the sheet/canvas near the cloud, top right corner of the box used (%.1f, %.1f)' % (idx + 1, found[0], found[1]))
        else:
            (pen, dist), fx, fy = best
            found = (fx, fy)
            if pen > 1e-6:
                log('  ring %d: triangle at %.1f, %.1f, %.1fmm from the cloud -- the cleanest spot found within %.0fmm still overlaps %.1f sq mm of something' % (idx + 1, fx, fy, dist, reach, pen))
            else:
                log('  ring %d: triangle at %.1f, %.1f, %.1fmm from the cloud' % (idx + 1, fx, fy, dist))
        placed.add((found[0], found[1], found[0] + w, found[1] + h))
        try:
            placed_polys.append(_box(found[0], found[1], found[0] + w, found[1] + h))
        except Exception:
            pass
        out[idx] = found
    return out


def main(argv):
    ap = argparse.ArgumentParser(prog='RevCloud', add_help=True)
    ap.add_argument('old')
    ap.add_argument('new')
    ap.add_argument('out')
    ap.add_argument('--gap', type=float, default=10.0)
    ap.add_argument('--move-dist', type=float, default=150.0)
    ap.add_argument('--hinge', type=float, default=10.0)
    ap.add_argument('--tri-size', type=float, default=0.0)
    ap.add_argument('--tri-reach', type=float, default=40.0)
    ap.add_argument('--canvas', default='')
    ap.add_argument('--watch', action='append', default=[])
    ap.add_argument('--pad', type=float, default=2.5)
    ap.add_argument('--chord', type=float, default=8.0)
    ap.add_argument('--bulge', type=float, default=0.6)
    ap.add_argument('--arcseg', type=int, default=4)
    ap.add_argument('--cloud-layer', default='REVCLOUD')
    ap.add_argument('--exclude', action='append', default=[])
    ap.add_argument('--no-auto-title', action='store_true')
    ap.add_argument('--old-clouds', default='')
    ap.add_argument('--dimlines-new', default='')
    ap.add_argument('--dimlines-old', default='')
    a = ap.parse_args(argv)

    logf = open(a.out + '.log', 'w', encoding='utf-8')

    def log(s):
        logf.write(s + '\n')

    log('RevCloud %s' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    log('old %s' % a.old)
    log('new %s' % a.new)
    log('gap %.1f pad %.1f chord %.1f bulge %.2f arcseg %d cloud-layer %s' % (a.gap, a.pad, a.chord, a.bulge, a.arcseg, a.cloud_layer))

    cloud_layer = (a.cloud_layer or '').upper()
    old_clouds = read_clouds(a.old_clouds) if a.old_clouds else []
    log('old clouds listed by PML: %d (%s)' % (len(old_clouds), a.old_clouds or '-'))
    docs = []
    for path in (a.old, a.new):
        try:
            docs.append(ezdxf.readfile(path))
        except Exception as ex:
            log('ERROR cannot read %s: %s' % (path, ex))
            logf.close()
            return 2

    sides = []
    regions_extra = []
    for spec in a.exclude:
        try:
            x1, y1, x2, y2 = [float(v) for v in spec.split(',')]
            regions_extra.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
        except Exception:
            log('  warn: bad --exclude %r ignored' % spec)
    canvas = None
    if a.canvas:
        try:
            c = [float(v) for v in a.canvas.split(',')]
            canvas = (min(c[0], c[2]), min(c[1], c[3]), max(c[0], c[2]), max(c[1], c[3]))
        except Exception:
            log('  warn: bad --canvas %r ignored' % a.canvas)
    watches = []
    for spec in a.watch:
        try:
            x1, y1, x2, y2 = [float(v) for v in spec.split(',')]
            watches.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
        except Exception:
            log('  warn: bad --watch %r ignored' % spec)
    if canvas:
        log('canvas x %.1f..%.1f y %.1f..%.1f: compared inside, outside only in %d watched rectangle(s)'
            % (canvas[0], canvas[2], canvas[1], canvas[3], len(watches)))
        for r in watches:
            log('  watched: x %.1f..%.1f y %.1f..%.1f' % (r[0], r[2], r[1], r[3]))
    elif watches:
        log('  warn: --watch without --canvas has no effect')

    flat = []
    for label, doc in zip(('old', 'new'), docs):
        prims, inserts, explode, olays, title_y, sheet_h, dl, db, excl = flatten(doc, cloud_layer, log, old_clouds)
        regions = list(regions_extra) + list(olays)
        if canvas is None and not a.no_auto_title and title_y is not None and sheet_h:
            try:
                w = float(doc.header.get('$EXTMAX')[0])
            except Exception:
                w = 1e6
            regions.append((-1e6, -1e6, w + 1e6, title_y + TITLE_PAD))
        log('%s: %d loose primitives, %d blocks; dropped %d as old clouds (layer or listed), %d excluded blocks'
            % (label, len(prims), len(inserts), dl, db))
        for r in regions:
            if r[0] < -1e5:
                log('  %s excluded: title strip, everything below y %.1f' % (label, r[3]))
            else:
                log('  %s excluded: x %.1f..%.1f y %.1f..%.1f' % (label, r[0], r[2], r[1], r[3]))
        flat.append((prims, inserts, explode, regions, excl, sheet_h))

    # ---- blocks first, whole. unchanged ones are never exploded; a block
    # that only moved is clouded at its new place; the rest join the
    # primitive diff below
    o_prims, o_ins, o_explode, o_regions, o_excl, _ = flat[0]
    n_prims, n_ins, n_explode, n_regions, n_excl, n_sheet_h = flat[1]
    # everything on the new sheet, for the triangle placement: the loose
    # primitives as they are now (before any region is dropped), every
    # block, changed or not, and the excluded ones
    obstacles = None
    if a.tri_size > 0:
        obstacles = ObstacleMap([q.bbox for q in n_prims])
        for ins in list(n_ins) + list(n_excl):
            for q in n_explode(ins):
                obstacles.add(q.bbox)
        log('triangle obstacles: %d boxes on the new sheet' % obstacles.n)
    # presence, not count, same as the primitive diff: a block stacked
    # twice on the old sheet and once on the new one looks the same on
    # paper (the doubled dimension arrows of the first real run)
    o_exact = set(ins.exact() for ins in o_ins)
    n_exact = set(ins.exact() for ins in n_ins)
    o_rest = [ins for ins in o_ins if ins.exact() not in n_exact]
    n_rest = [ins for ins in n_ins if ins.exact() not in o_exact]
    same_n = len(o_ins) - len(o_rest)
    n_by_same = collections.defaultdict(list)
    for ins in n_rest:
        n_by_same[ins.same()].append(ins)
    moved_blocks = []
    o_unpaired = []
    for ins in o_rest:
        cands = n_by_same.get(ins.same())
        best = None
        if cands and a.move_dist > 0:
            for i, c in enumerate(cands):
                dd = math.hypot(c.pos[0] - ins.pos[0], c.pos[1] - ins.pos[1])
                if dd <= a.move_dist and (best is None or dd < best[0]):
                    best = (dd, i)
        if best is None:
            o_unpaired.append(ins)
        else:
            moved_blocks.append((ins, cands.pop(best[1])))
    n_unpaired = [ins for lst in n_by_same.values() for ins in lst]
    log('blocks: %d unchanged, %d moved (clouded at the new place only), %d old / %d new left for the primitive diff'
        % (same_n, len(moved_blocks), len(o_unpaired), len(n_unpaired)))
    for ins, to in moved_blocks:
        log('  block %s -> %s moved %.1f,%.1f -> %.1f,%.1f' % (ins.name, to.name, ins.pos[0], ins.pos[1], to.pos[0], to.pos[1]))

    # ---- leader-only labels: pinned text, leader following its element.
    # paired on everything in the block that does not touch the insert
    # point (see the docstring); the leader itself is never compared
    def split_leader(ins, explode_fn):
        # a piece touching the insert point is the leader. a piece that
        # lies on the same line, beyond a gap, is the leader too: since
        # 2026-09-18 DrawingPlan1MatchGaps breaks a component label's
        # leader where it runs through another label's text (GAP on the
        # GLAB/SLAB), so the leader arrives as two collinear LINEs, and
        # the far one touches nothing. it used to land in the core, and
        # a gap that slid along with its element clouded the label. the
        # far segment of a BENT leader is not collinear and stays core
        ax, ay = ins.pos
        qs = explode_fn(ins)

        def touches(k):
            return k[0] in ('L', 'P') and (math.hypot(k[1] - ax, k[2] - ay) <= 0.1 or math.hypot(k[3] - ax, k[4] - ay) <= 0.1)

        leader = [q for q in qs if touches(q.key)]
        dirs = []
        for q in leader:
            k = q.key
            fx, fy = (k[3], k[4]) if math.hypot(k[1] - ax, k[2] - ay) <= 0.1 else (k[1], k[2])
            d = math.hypot(fx - ax, fy - ay)
            if d > 0.1:
                dirs.append(((fx - ax) / d, (fy - ay) / d))

        def along(k):
            # both ends within 0.1mm of a leader's line, on the far side of the insert point
            if k[0] not in ('L', 'P'):
                return False
            for dx, dy in dirs:
                ok = True
                for px, py in ((k[1], k[2]), (k[3], k[4])):
                    rx, ry = px - ax, py - ay
                    if abs(rx * dy - ry * dx) > 0.1 or rx * dx + ry * dy <= 0:
                        ok = False
                        break
                if ok:
                    return True
            return False

        core = []
        for q in qs:
            if touches(q.key):
                continue
            if dirs and along(q.key):
                leader.append(q)
            else:
                core.append(q)
        return leader, core

    # split every unpaired LABEL once; the exact-key pass below and the
    # shape pass further down both read from this instead of re-exploding
    o_split = {}
    for ins in o_unpaired:
        if not ins.name.upper().startswith('LABEL'):
            continue
        o_split[id(ins)] = split_leader(ins, o_explode)
    n_split = {}
    for ins in n_unpaired:
        if not ins.name.upper().startswith('LABEL'):
            continue
        n_split[id(ins)] = split_leader(ins, n_explode)

    o_by_core = collections.defaultdict(list)
    for ins in o_unpaired:
        leader, core = o_split.get(id(ins), (None, None))
        if leader and core:
            o_by_core[frozenset(q.key for q in core)].append(ins)
    leader_only = []
    for ins in n_unpaired:
        leader, core = n_split.get(id(ins), (None, None))
        if not (leader and core):
            continue
        lst = o_by_core.get(frozenset(q.key for q in core))
        if lst:
            leader_only.append((lst.pop(), ins))
    if leader_only:
        done_o = set(id(o) for o, _ in leader_only)
        done_n = set(id(n) for _, n in leader_only)
        o_unpaired = [ins for ins in o_unpaired if id(ins) not in done_o]
        n_unpaired = [ins for ins in n_unpaired if id(ins) not in done_n]
    for o, n in leader_only:
        log('  label %s -> %s leader only: design point %.1f,%.1f -> %.1f,%.1f, text unchanged, not clouded'
            % (o.name, n.name, o.pos[0], o.pos[1], n.pos[0], n.pos[1]))
    log('%d label(s) whose leader alone follows a moved element: not clouded' % len(leader_only))

    # the label's own text moved too (BlankPos laid it out somewhere else
    # on the sheet) but still says the same thing -- matched above by an
    # EXACT core key, so this never caught it (the core's key encodes its
    # position, and the position is exactly what changed). matched here
    # by shape instead (rotation + content, same test drop_moved uses),
    # within the same move_dist as drop_moved so an unrelated label with
    # coincidentally identical text elsewhere isn't paired up. the text
    # still goes through the ordinary diff below and gets drop_moved's
    # own handling (old place not clouded, new place is) -- only the
    # leader stretching to follow it is dropped, since a cloud already
    # around the relocated text says everything the leader would add
    # (2026-09-18: a label 16mm relocation left its leader clouded on
    # its own, a second red blob the text's own cloud didn't explain)
    def core_mid(core):
        bb = None
        for q in core:
            bb = q.bbox if bb is None else bbox_union(bb, q.bbox)
        return ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0) if bb else (0.0, 0.0)

    o_by_shape = collections.defaultdict(list)
    for ins in o_unpaired:
        leader, core = o_split.get(id(ins), (None, None))
        if leader and core:
            o_by_shape[frozenset(q.shape() for q in core)].append((ins, leader, core))
    leader_relocated = []
    for ins in n_unpaired:
        leader, core = n_split.get(id(ins), (None, None))
        if not (leader and core):
            continue
        cands = o_by_shape.get(frozenset(q.shape() for q in core))
        if not cands:
            continue
        nx, ny = core_mid(core)
        best = None
        for i, (o_ins, o_leader, o_core) in enumerate(cands):
            ox, oy = core_mid(o_core)
            dd = math.hypot(ox - nx, oy - ny)
            if dd <= a.move_dist and (best is None or dd < best[0]):
                best = (dd, i)
        if best is not None:
            o_ins, o_leader, o_core = cands.pop(best[1])
            leader_relocated.append((o_ins, o_leader, o_core, ins, leader, core))
    relocated_o = {}
    relocated_n = {}
    for o_ins, o_leader, o_core, n_ins, n_leader, n_core in leader_relocated:
        relocated_o[id(o_ins)] = o_core
        relocated_n[id(n_ins)] = n_core
        log('  label %s -> %s: text relaid out, leader following it not clouded (text itself still is, at its new place)'
            % (o_ins.name, n_ins.name))
    log('%d label(s) whose text relaid out (same content): the leader following it not clouded' % len(leader_relocated))

    for ins in o_unpaired:
        core = relocated_o.get(id(ins))
        o_prims.extend(core if core is not None else o_explode(ins))
    for ins in n_unpaired:
        core = relocated_n.get(id(ins))
        n_prims.extend(core if core is not None else n_explode(ins))
    o_prims, o_dr = apply_regions(o_prims, o_regions)
    n_prims, n_dr = apply_regions(n_prims, n_regions)
    o_prims, o_dc = apply_canvas(o_prims, canvas, watches)
    n_prims, n_dc = apply_canvas(n_prims, canvas, watches)
    if canvas is not None and watches:
        ow = watched_from_excluded(o_excl, o_explode, watches)
        nw = watched_from_excluded(n_excl, n_explode, watches)
        o_prims.extend(ow)
        n_prims.extend(nw)
        log('watched rectangles: %d old / %d new primitives of the backing sheet compared' % (len(ow), len(nw)))
    moved_new = []
    for ins, to in moved_blocks:
        moved_new.extend(n_explode(to))
    moved_new, _ = apply_regions(moved_new, n_regions)
    moved_new, _ = apply_canvas(moved_new, canvas, watches)
    for q in moved_new:
        q.new = True
    log('old: %d primitives in the diff (%d inside excluded regions, %d outside the canvas); new: %d (%d, %d)'
        % (len(o_prims), o_dr, o_dc, len(n_prims), n_dr, n_dc))

    removed, added = diff(o_prims, n_prims)
    removed, moved = drop_moved(removed, added, a.move_dist)
    log('%d vanished primitive(s) have a twin within %.0fmm: moves, old place not clouded' % (len(moved), a.move_dist))
    dim_old = read_dimlines(a.dimlines_old)
    dim_new = read_dimlines(a.dimlines_new)
    removed, added, nd_old, nd_new = drop_dimlines(removed, added, dim_old, dim_new)
    log('dimension projection lines listed by PML: %d old (%s), %d new (%s); %d old / %d new line(s) on them dropped from the diff'
        % (len(dim_old), a.dimlines_old or '-', len(dim_new), a.dimlines_new or '-', nd_old, nd_new))
    ntrim = trim_collinear(removed, added)
    log('%d segment(s) collinear with the other side: only the uncovered part is clouded' % ntrim)
    nhinge = trim_hinged(removed, added, a.hinge, log)
    log('%d segment(s) hinged on an old one (far end within %.0fmm): a leader following its element, not clouded' % (nhinge, a.hinge))
    added = added + moved_new
    clusters = cluster(removed + added, a.gap)
    rings = []
    for k, members in enumerate(clusters, 1):
        for poly in band(members, a.pad, a.gap):
            for hole, bb, pts in cloud_rings(poly, a.chord, a.arcseg, a.bulge):
                rings.append((k, hole, bb, pts))
    rings.sort(key=lambda r: (r[2][1], r[2][0], r[1]))
    tris = {}
    if a.tri_size > 0 and rings:
        try:
            sheet_w = float(docs[1].header.get('$EXTMAX')[0])
            sheet_hh = float(docs[1].header.get('$EXTMAX')[1])
        except Exception:
            sheet_w, sheet_hh = 841.0, 594.0
        bounds = canvas if canvas is not None else (0.0, 0.0, sheet_w, sheet_hh)
        tris = place_triangles(rings, obstacles, a.tri_size, bounds, log, reach=a.tri_reach)
    ndel = sum(1 for mem in clusters if not any(p.new for p in mem))
    log('removed %d added %d -> %d cluster(s) (%d deletion-only), %d ring(s)' % (len(removed), len(added), len(clusters), ndel, len(rings)))

    with open(a.out, 'w', encoding='ascii', newline='\r\n') as f:
        f.write('clouds %d removed %d added %d\n' % (len(rings), len(removed), len(added)))
        for i, (k, hole, bb, pts) in enumerate(rings, 1):
            f.write('cloud %d %.3f %.3f %.3f %.3f %s\n' % ((i,) + bb + ('hole' if hole else 'outer',)))
            if (i - 1) in tris:
                f.write('tri %d %.3f %.3f\n' % ((i,) + tris[i - 1]))
            for x, y in pts:
                f.write('v %.3f %.3f\n' % (x, y))
            f.write('end\n')
            log('  cloud %d  cluster %d %s  x %.1f..%.1f  y %.1f..%.1f  (%.0f x %.0f mm, %d vertices)'
                % (i, k, 'hole ' if hole else 'outer', bb[0], bb[2], bb[1], bb[3], bb[2] - bb[0], bb[3] - bb[1], len(pts)))
    logf.close()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as ex:          # never die silently under syscom
        try:
            with open((sys.argv[3] if len(sys.argv) > 3 else 'RevCloud') + '.log', 'a', encoding='utf-8') as f:
                f.write('ERROR %r\n' % (ex,))
        except Exception:
            pass
        sys.exit(1)
