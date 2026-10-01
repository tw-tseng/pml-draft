"""Minimal ASCII FBX 7.x reader: node tree, models, meshes, curves, world transforms."""
import re
import numpy as np

TOK = re.compile(r'''
    (?P<str>"(?:[^"\\]|\\.)*")          |
    (?P<key>[A-Za-z_][A-Za-z0-9_|]*):   |
    (?P<arr>\*\d+)                      |
    (?P<num>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?) |
    (?P<lb>\{) | (?P<rb>\}) | (?P<comma>,) |
    (?P<word>[A-Za-z_][A-Za-z0-9_]*)
''', re.X)


class Node:
    __slots__ = ('name', 'props', 'children')

    def __init__(self, name):
        self.name, self.props, self.children = name, [], []

    def find(self, name):
        for c in self.children:
            if c.name == name:
                return c
        return None

    def findall(self, name):
        return [c for c in self.children if c.name == name]


def parse(path):
    with open(path, 'rb') as fp:
        if fp.read(18) == b'Kaydara FBX Binary':
            raise SystemExit('%s is a binary FBX; export it from Navisworks as ASCII FBX' % path)
    text = open(path, encoding='utf-8', errors='replace').read()
    text = re.sub(r'^\s*;.*$', '', text, flags=re.M)
    root = Node('ROOT')
    stack = [root]
    cur = None
    for m in TOK.finditer(text):
        k = m.lastgroup
        v = m.group(k)
        if k == 'key':
            cur = Node(m.group('key'))
            stack[-1].children.append(cur)
        elif k == 'str':
            cur.props.append(v[1:-1])
        elif k == 'num':
            cur.props.append(float(v) if ('.' in v or 'e' in v or 'E' in v) else int(v))
        elif k == 'word':
            cur.props.append(v)
        elif k == 'lb':
            stack.append(cur)
        elif k == 'rb':
            stack.pop()
            cur = stack[-1]
        # arr / comma: ignore
    return root


def p70(node):
    out = {}
    pp = node.find('Properties70')
    if pp:
        for p in pp.findall('P'):
            out[p.props[0]] = p.props[4:]
    return out


def arr(node, name):
    n = node.find(name)
    if n is None:
        return None
    a = n.find('a')
    return np.array(a.props if a else n.props, dtype=float)


def euler(rx, ry, rz, order=0):
    """FBX eRotationOrder 0 = XYZ: R = Rz*Ry*Rx (column vectors)."""
    rx, ry, rz = np.radians([rx, ry, rz])
    X = np.array([[1, 0, 0], [0, np.cos(rx), -np.sin(rx)], [0, np.sin(rx), np.cos(rx)]])
    Y = np.array([[np.cos(ry), 0, np.sin(ry)], [0, 1, 0], [-np.sin(ry), 0, np.cos(ry)]])
    Z = np.array([[np.cos(rz), -np.sin(rz), 0], [np.sin(rz), np.cos(rz), 0], [0, 0, 1]])
    if order != 0:
        raise ValueError('rotation order %d not handled' % order)
    return Z @ Y @ X


def m4(R=None, t=None, s=None):
    M = np.eye(4)
    if R is not None:
        M[:3, :3] = R
    if s is not None:
        M[:3, :3] = M[:3, :3] @ np.diag(s)
    if t is not None:
        M[:3, 3] = t
    return M


def T(v):
    return m4(t=v)


def local_matrix(pr):
    g = lambda k, d: np.array(pr.get(k, d), dtype=float)
    Lt = g('Lcl Translation', [0, 0, 0])
    Lr = g('Lcl Rotation', [0, 0, 0])
    Ls = g('Lcl Scaling', [1, 1, 1])
    Roff = g('RotationOffset', [0, 0, 0])
    Rp = g('RotationPivot', [0, 0, 0])
    Soff = g('ScalingOffset', [0, 0, 0])
    Sp = g('ScalingPivot', [0, 0, 0])
    Pre = g('PreRotation', [0, 0, 0])
    Post = g('PostRotation', [0, 0, 0])
    order = int(pr.get('RotationOrder', [0])[0])
    R = m4(euler(*Lr, order))
    Rpre = m4(euler(*Pre))
    Rpost = m4(euler(*Post))
    S = m4(s=Ls)
    # FBX SDK: T * Roff * Rp * Rpre * R * Rpost^-1 * Rp^-1 * Soff * Sp * S * Sp^-1
    return (T(Lt) @ T(Roff) @ T(Rp) @ Rpre @ R @ np.linalg.inv(Rpost) @ T(-Rp)
            @ T(Soff) @ T(Sp) @ S @ T(-Sp))


def geometric_matrix(pr):
    g = lambda k, d: np.array(pr.get(k, d), dtype=float)
    return (T(g('GeometricTranslation', [0, 0, 0]))
            @ m4(euler(*g('GeometricRotation', [0, 0, 0])))
            @ m4(s=g('GeometricScaling', [1, 1, 1])))


class Scene:
    def __init__(self, path):
        self.root = parse(path)
        self.gs = p70(self.root.find('GlobalSettings'))
        objs = self.root.find('Objects')
        self.models, self.geoms = {}, {}
        for n in objs.children:
            if n.name == 'Model':
                self.models[n.props[0]] = dict(id=n.props[0], name=n.props[1].split('::', 1)[-1],
                                               kind=n.props[2], pr=p70(n), node=n)
            elif n.name == 'Geometry':
                self.geoms[n.props[0]] = dict(id=n.props[0], kind=n.props[2], node=n)
        self.parent, self.geom_of = {}, {}
        for c in self.root.find('Connections').findall('C'):
            if c.props[0] != 'OO':
                continue
            child, par = c.props[1], c.props[2]
            if child in self.models:
                self.parent[child] = par
            elif child in self.geoms and par in self.models:
                self.geom_of[par] = child
        self._world = {}

    def world(self, mid):
        if mid in self._world:
            return self._world[mid]
        M = local_matrix(self.models[mid]['pr'])
        par = self.parent.get(mid)
        if par in self.models:
            M = self.world(par) @ M
        self._world[mid] = M
        return M

    def path(self, mid):
        names = []
        while mid in self.models:
            names.append(self.models[mid]['name'])
            mid = self.parent.get(mid)
        return '/'.join(reversed(names))

    def items(self):
        """Yield (model, kind, world points Nx3, faces as list of index arrays or None)."""
        for mid, gid in self.geom_of.items():
            g = self.geoms[gid]
            M = self.world(mid) @ geometric_matrix(self.models[mid]['pr'])
            n = g['node']
            if g['kind'] == 'Mesh':
                v = arr(n, 'Vertices').reshape(-1, 3)
                idx = arr(n, 'PolygonVertexIndex').astype(np.int64)
                faces, cur = [], []
                for i in idx:
                    if i < 0:
                        cur.append(-i - 1)
                        faces.append(np.array(cur))
                        cur = []
                    else:
                        cur.append(i)
            elif g['kind'] == 'NurbsCurve':
                v = arr(n, 'Points').reshape(-1, 4)[:, :3]
                faces = None
            else:
                continue
            w = (M @ np.c_[v, np.ones(len(v))].T).T[:, :3]
            yield self.models[mid], g['kind'], w, faces
