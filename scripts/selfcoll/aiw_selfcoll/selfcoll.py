"""자기 충돌 사전 검사 — 로봇에 보낼 액션 청크를 실행하기 **전에**, 실행될 경로 전체에서 로봇 부품끼리 너무 가까워지는지 판정한다.

대상: ROBOTIS AI Worker FFW-SG2 (URDF 의 충돌 형상). 경로는 로봇에 실제로 보낼 궤적과 같은 계산으로 만들고
(robot.action_targets → robot.chunk_traj → 컨트롤러 5차 스플라인), 보내는 점 사이도 촘촘히(관절 0.5° 이하 간격) 샘플한다 —
스플라인은 점 사이에서 튈 수 있다.

허용 하한(쌍마다) = 여유(padding) + SPEED_K × 두 부품의 상대 속도 상한.
  · 거리: 메시를 볼록 껍질로 바꿔 빠르게 재고(껍질 거리 ≤ 실제 거리라 보수적), 하한 근처 쌍만 원래 메시로 다시 잰다.
  · 검사에서 빼는 쌍: ① 바로 붙은 링크 ② 같은 기구 내부(손목·손가락·손목 카메라 / 몸통·리프트·바퀴 / 머리·ZED, 몸통↔머리)
    ③ 관절 한계 안에서는 닿을 수 없는 같은 팔 쌍 (kin_excluded.json, scripts/kin_separated.py 로 만든다 — 닿지 않는다는 것이지
    padding 밖이라는 것은 아니다, 가장 가까운 쌍은 0.3 cm 까지 온다).
  · ROBOTIS SRDF 의 충돌 제외 목록은 쓰지 않는다 — "Never" 쌍 대부분이 왼팔↔오른팔이고(샘플링 추정), 수정판은 두 손목까지 뺀다.

판정(gate_chunk): 통과 / 앞부분만(걸리기 전에 도착하는 점까지 궤적을 다시 만들어 재검사) / 거부.
의존: pinocchio, coal, scipy(qhull), numpy. 볼록 껍질은 scipy 로 만든다 — qhull 없이 빌드된 coal 에서도 돈다.
"""
import json
import math
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import coal
import numpy as np
import pinocchio as pin
from scipy.spatial import ConvexHull

from .robot import GRIP_KEEP_S, GRIPPERS, GROUPS, POSE_KEYS, action_targets, chunk_traj, default_urdf, description_dir

HERE = Path(__file__).resolve().parent


def _convex_hull(g):
    """BVH 메시 → coal.Convex (scipy qhull "Qt" = 삼각형 면, buildConvexHull(True, "Qt") 와 같은 껍질)."""
    V = np.array([np.asarray(g.vertex(i), float) for i in range(g.num_vertices)])
    h = ConvexHull(V, qhull_options="Qt")
    idx = {int(o): n for n, o in enumerate(h.vertices)}
    P, T = coal.StdVec_Vec3s(), coal.StdVec_Triangle()
    for p in V[h.vertices]:
        P.append(p)
    for s in h.simplices:
        T.append(coal.Triangle(*(idx[int(i)] for i in s)))
    return coal.Convex(P, T)


PADDING = 0.03          # m — 기본 여유 (모델에 없는 케이블·브래킷·추종 오차 몫)
CLOSE_PADDING = 0.02    # m — 원래 가까운 이웃 쌍(close_pairs)의 여유
STEP_RAD = math.radians(0.5)   # 경로 샘플 간격: 관절 최대 변화량
STEP_LIFT = 0.003       # m — 리프트(prismatic) 샘플 간격
MIMIC = {f"gripper_{s}_joint{k}": f"gripper_{s}_joint1" for s in "lr" for k in (2, 3, 4)}   # URDF mimic, 배율 1


def module_of(link):
    """기구 묶음. 같은 묶음 안의 쌍은 기구가 스스로 막는 내부 쌍이라 빼는 후보 (아래 internal_pairs)."""
    if link == "base_link" or "wheel" in link or link in ("lift_link", "arm_base_link"):
        return "body"              # 모바일 베이스·바퀴·리프트 기둥·몸통: 몸통은 리프트 기둥을 타고 오르내리는 구조라 서로 붙어 있다
    if link.startswith("head_") or link.startswith("zed_"):
        return "head"
    for s, side in (("l", "left"), ("r", "right")):
        if link.startswith(f"gripper_{s}_") or link in (f"arm_{s}_link7", f"camera_{side}_link"):
            return f"hand_{s}"     # 손목(link7)·손목 카메라·그리퍼 손가락: 그리퍼 기구 내부
    return link                    # 그 밖(팔 link1–6, arm_base_link)은 저마다 따로 — 같은 팔 안 접힘 충돌도 본다


#: 머리는 몸통 목 위에 얹힌 구조라 볼록 껍질끼리 겹친다 (리셋 포즈에서 −2.2 cm). 몸통↔머리는 기구가 스스로 막는 쌍으로 뺀다.
MOUNTED = {frozenset(("arm_base_link", h)) for h in ("head_link1", "head_link2", "zed_camera_center")}


def internal_pairs(links):
    return {frozenset((a, b)) for a in links for b in links if a < b and module_of(a) == module_of(b)} | MOUNTED


def close_pairs(pairs):
    """원래 가까운 이웃 쌍 → close_padding 을 쓴다.
    ① 손목 관절 옆 팔 link5·6 ↔ 같은 손 부품, 리프트 기둥 ↔ 머리: 기준 자세에서도 5.4–6.5 cm 라 padding 을 키우면
       손목·목을 조금만 돌려도 걸린다 (실기 녹화 약 49,000 청크 재생, padding 5 cm: 막힌 청크의 75 %).
    ② 같은 팔 link1–7 끼리: 팔꿈치를 접으면 위팔↔팔뚝이 3 cm 안으로 들어온다. padding 3 cm 면 녹화 재생에서
       막힘 3.6 %(한 과제는 36.6 %), 2 cm 면 1.1 % (0.1 %)."""
    def close(a, b):
        return (a == "lift_link" and module_of(b) == "head") or any(
            a in (f"arm_{s}_link5", f"arm_{s}_link6") and module_of(b) == f"hand_{s}"
            or a.startswith(f"arm_{s}_link") and b.startswith(f"arm_{s}_link") for s in "lr")
    return [p for p in pairs if close(*p) or close(*p[::-1])]


def _collision_links(urdf):
    """링크 → 부모 링크 (URDF 트리), 충돌 형상이 있는 링크 집합."""
    root = ET.parse(urdf).getroot()
    parent = {j.find("child").get("link"): j.find("parent").get("link") for j in root.findall("joint")}
    coll = {l.get("name") for l in root.findall("link") if l.find("collision") is not None}
    return parent, coll


def adjacent_pairs(urdf):
    """충돌 링크마다 충돌 형상이 있는 가장 가까운 조상과의 쌍 (사이의 형상 없는 링크는 건너뛴다)."""
    parent, coll = _collision_links(urdf)
    out = set()
    for l in coll:
        p = parent.get(l)
        while p is not None and p not in coll:
            p = parent.get(p)
        if p is not None:
            out.add(frozenset((l, p)))
    return out



def _step_scale():
    return np.array([STEP_LIFT if k == "lift_joint" else STEP_RAD for k in POSE_KEYS])


def chunk_path(q0, chunk, period, home, limits, grip_cmd=None):
    """로봇에 보낼 청크가 실행할 관절 경로를 촘촘히 → (times[M], Q[M, 19] POSE_KEYS 순서), 그리고 목표점 Qt[N, 19].
    q0 = 지금 관절(19, POSE_KEYS 순서, 정지 가정). grip_cmd = 직전 그리퍼 지령 {이름: 값} (없으면 q0)."""
    Qt = np.array([[t[k] for k in POSE_KEYS] for t in (action_targets(a, home, limits) for a in chunk)])
    q0 = np.asarray(q0, float)
    t, V, Acc, _last = chunk_traj(q0, Qt, float(period))
    J = len(POSE_KEYS)
    # 컨트롤러별 점 목록 — 팔 그룹은 맨 앞에 GRIP_KEEP_S 점(팔 관절 = q0, 그리퍼 = 직전 지령)이 붙는다 (실제 전송과 같다)
    knots = {}
    for ctrl, js in GROUPS.items():
        c = [POSE_KEYS.index(j) for j in js]
        pts = [(0.0, q0[c], np.zeros(len(c)), np.zeros(len(c)))]   # JTC 시작 상태 = 실측 위치, 정지
        if any(j in GRIPPERS for j in js):
            keep = np.array([(grip_cmd or {}).get(j, q0[POSE_KEYS.index(j)]) if j in GRIPPERS else q0[POSE_KEYS.index(j)]
                             for j in js])
            pts.append((GRIP_KEEP_S, keep, np.zeros(len(c)), np.zeros(len(c))))
        pts += [(t[i], Qt[i, c], V[i, c], Acc[i, c]) for i in range(len(t))]
        knots[ctrl] = (c, pts)
    # 컨트롤러마다 구간 계수를 한 번에 → 시각 배열에서 벡터로 평가
    segs = []
    for c, pts in knots.values():
        tk = np.array([p[0] for p in pts])
        P0, V0, A0 = (np.array([p[i] for p in pts[:-1]]) for i in (1, 2, 3))
        P1, V1, A1 = (np.array([p[i] for p in pts[1:]]) for i in (1, 2, 3))
        T = np.diff(tk)[:, None]
        coef = [P0, V0, A0 / 2,
                (20 * (P1 - P0) - (8 * V1 + 12 * V0) * T - (3 * A0 - A1) * T ** 2) / (2 * T ** 3),
                (30 * (P0 - P1) + (14 * V1 + 16 * V0) * T + (3 * A0 - 2 * A1) * T ** 2) / (2 * T ** 4),
                (12 * (P1 - P0) - 6 * (V1 + V0) * T - (A0 - A1) * T ** 2) / (2 * T ** 5)]
        segs.append((c, tk, coef, pts[-1][1]))
    t_end = max(tk[-1] for _c, tk, _co, _p in segs)

    def eval_at(ts):
        out = np.empty((len(ts), J))
        for c, tk, coef, p_last in segs:
            k = np.clip(np.searchsorted(tk, ts, side="right") - 1, 0, len(tk) - 2)
            s = (ts - tk[k])[:, None]
            v = coef[5][k]
            for co in coef[4::-1]:
                v = co[k] + s * v
            v[ts >= tk[-1]] = p_last
            out[:, c] = v
        return out

    # 균등 시각 격자: 이웃 샘플 사이 관절 변화가 STEP 이하가 될 때까지 촘촘히 (스플라인 오버슈트 포함)
    scale = _step_scale()
    n = max(16, int(t_end / 0.004) + 1)
    while True:
        times = np.linspace(0.0, t_end, n)
        Q = eval_at(times)
        worst = (np.abs(np.diff(Q, axis=0)) / scale).max() if n > 1 else 0.0
        if worst <= 1.0 or n > 200_000:
            return times, Q, Qt
        n = int(n * worst * 1.1) + 1


class SelfCollision:
    def __init__(self, urdf=None, padding=PADDING, close_padding=CLOSE_PADDING, structural=None, env=None,
                 kin_excluded=True):
        """urdf = FFW-SG2 follower URDF (기본: robot.default_urdf()). close_padding = close_pairs 의 여유 (None 이면 padding).
        env = [(이름, (크기 x, y, z) m, base 기준 4×4 자세)] 움직이지 않는 상자 모양 장애물(선택). 로봇 부품 ↔ 장애물 쌍도 같은
        방식으로 검사한다 (장애물끼리는 뺀다). kin_excluded = False 면 kin_excluded.json 을 읽지 않는다 (그 목록을 다시 만들 때)."""
        urdf = str(urdf or default_urdf())
        self.model = pin.buildModelFromUrdf(urdf)
        self.geom = pin.buildGeomFromUrdf(self.model, urdf, pin.COLLISION, package_dirs=[str(description_dir())])
        # 메시 → 볼록 껍질 (보수적: 오목한 곳을 메워 키운다, GJK 로 빠르다). 반드시 buildConvexHull(qhull 로 껍질 계산).
        # buildConvexRepresentation 은 껍질을 계산하지 않고 메시를 볼록이라고 '간주'만 한다 — 오목한 몸통에서 GJK 가
        # 엉뚱한 면에 걸려 거리를 크게 부풀렸다 (가슴 1 cm 앞을 15.9 cm 로 — 실기 접촉 사례와 어긋나 발견).
        # 원래 메시(BVH)는 따로 둔다: 볼록 껍질은 오목한 곳을 메워 부풀리므로 (팔꿈치↔손목처럼) 거짓 경보를 낸다.
        # 껍질 거리 ≤ 메시 거리라 껍질은 빠른 거르기·건너뛰기에 안전하고, padding 근처 쌍만 메시로 다시 잰다 (_refine).
        self._mesh = [go.geometry for go in self.geom.geometryObjects]
        for go in self.geom.geometryObjects:
            g = go.geometry
            if isinstance(g, coal.BVHModelBase):
                go.geometry = _convex_hull(g)
        self.env_names = []
        for name, size, T in (env or []):
            box = coal.Box(*size)
            go = pin.GeometryObject(name, 0, 0, pin.SE3(np.asarray(T)[:3, :3], np.asarray(T)[:3, 3]), box)
            self.geom.addGeometryObject(go)
            self._mesh.append(box)
            self.env_names.append(name)
        self._default_pad, self._pad_over, self._close_pad = float(padding), {}, None
        self.link_of = [self.model.frames[go.parentFrame].name for go in self.geom.geometryObjects]
        for i, go in enumerate(self.geom.geometryObjects):          # 장애물은 프레임(universe) 대신 제 이름으로
            if go.name in self.env_names:
                self.link_of[i] = go.name
        self.adjacent = adjacent_pairs(urdf)
        self.internal = internal_pairs(set(self.link_of))
        self.structural = set(structural or ())
        # 관절 한계 때문에 닿을 수 없는 같은 팔 쌍 (scripts/kin_separated.py 가 사이 관절의 가동 범위 전체 격자 + 격자 사이
        # 하한으로 계산). 검사하면 속도 여유와 겹쳐 오탐만 낸다 (녹화 재생에서 이 쌍들로만 3,543 건).
        kin = HERE / "kin_excluded.json"
        self.kin_excluded = ({frozenset(e["pair"]) for e in json.load(open(kin))["excluded"] if e["why"] == "never"}
                             if kin_excluded and kin.exists() else set())
        self.excluded = (self.adjacent | self.internal | self.structural | self.kin_excluded
                         | {frozenset((a, b)) for a in self.env_names for b in self.env_names if a != b})
        self.geom.addAllCollisionPairs()
        keep = [cp for cp in self.geom.collisionPairs
                if frozenset((self.link_of[cp.first], self.link_of[cp.second])) not in self.excluded
                and self.link_of[cp.first] != self.link_of[cp.second]]
        self.geom.removeAllCollisionPairs()
        for cp in keep:
            self.geom.addCollisionPair(cp)
        self.data, self.gdata = self.model.createData(), pin.GeometryData(self.geom)
        self.pairs = [(self.link_of[cp.first], self.link_of[cp.second]) for cp in self.geom.collisionPairs]
        self._rebuild_pad()
        if close_padding is not None:
            self.close_padding = close_padding
        # 사전 거르기용 경계구 (형상 좌표계의 AABB 중심 + 반지름): 구 사이 거리는 실제 거리의 하한이다
        ctr, rad = [], []
        for go in self.geom.geometryObjects:
            go.geometry.computeLocalAABB()
            ctr.append(np.array(go.geometry.aabb_local.center()))
            rad.append(float(go.geometry.aabb_radius))
        self._ctr, self._rad = ctr, np.array(rad)
        self._pa = np.array([cp.first for cp in self.geom.collisionPairs])
        self._pb = np.array([cp.second for cp in self.geom.collisionPairs])
        self._req, self._res = coal.DistanceRequest(), coal.DistanceResult()
        self._idx = {n: (self.model.joints[self.model.getJointId(n)].idx_q) for n in POSE_KEYS + list(MIMIC)}
        self._vidx = {n: (self.model.joints[self.model.getJointId(n)].idx_v) for n in POSE_KEYS + list(MIMIC)}
        self._gR = np.array([np.linalg.norm(go.placement.translation) + np.linalg.norm(self._ctr[i]) + self._rad[i]
                             for i, go in enumerate(self.geom.geometryObjects)])   # 프레임 원점 → 형상 점 최대 거리
        self.W = self._pair_levers()

    def _pair_levers(self):
        """W[19, 쌍]: 관절 k 가 |Δq| 움직일 때 그 쌍의 두 형상이 서로 가까워질 수 있는 거리의 상한 계수.
        두 형상의 공통 조상 관절은 둘을 같이 움직여 거리를 못 바꾸므로 뺀다 (조상 집합의 대칭차만).
        회전 관절 j 의 계수 = j 원점에서 그 아래 형상 점까지 거리의 상한(체인 관절 위치 길이 합 + 형상 중심 거리 + 반지름).
        직선 관절(리프트)은 1. 그리퍼 mimic 관절은 원래 관절(gripper_*_joint1)의 몫으로 더한다."""
        m, G = self.model, self.geom.geometryObjects
        key_of = {m.getJointId(n): POSE_KEYS.index(n) for n in POSE_KEYS}
        key_of.update({m.getJointId(mm): POSE_KEYS.index(src) for mm, src in MIMIC.items()})

        def chain(j):            # 루트까지 조상 관절 (자신 포함)
            out = []
            while j > 0:
                out.append(j)
                j = m.parents[j]
            return out

        reach = {}               # (관절 j, 형상 g) → j 원점에서 g 의 어떤 점까지 거리 상한
        for g, go in enumerate(G):
            anc = chain(go.parentJoint)                         # [parentJoint, ..., 루트 쪽]
            tail = np.linalg.norm(go.placement.act(self._ctr[g])) + self._rad[g]
            acc = tail
            for j in anc:                                       # j 원점 → g: j 보다 아래 관절들의 위치 길이 합 + tail
                reach[(j, g)] = acc
                acc += np.linalg.norm(m.jointPlacements[j].translation)
        W = np.zeros((len(POSE_KEYS), len(self._pa)))
        for p, (a, b) in enumerate(zip(self._pa.tolist(), self._pb.tolist())):
            ca, cb = set(chain(G[a].parentJoint)), set(chain(G[b].parentJoint))
            for j in ca ^ cb:
                if j not in key_of:
                    continue                                    # 액션이 못 움직이는 관절(바퀴 등)은 고정
                g = a if j in ca else b
                lever = 1.0 if m.joints[j].shortname().startswith("JointModelP") else reach[(j, g)]
                W[key_of[j], p] += lever
        return W

    def q(self, q19):
        """POSE_KEYS 순서 19값 → pinocchio q (나머지 관절 = 중립, 그리퍼 mimic 반영)."""
        q = pin.neutral(self.model)
        for k, v in zip(POSE_KEYS, q19):
            q[self._idx[k]] = v
        for m, src in MIMIC.items():
            q[self._idx[m]] = q[self._idx[src]]
        return q

    # --- 여유(padding): 기본값 하나 + 쌍별 덮어쓰기 (close_padding 도 이것으로 쓴다)
    @property
    def padding(self):
        return self._default_pad

    @padding.setter
    def padding(self, v):
        self._default_pad = float(v)
        self._rebuild_pad()

    @property
    def close_padding(self):
        return self._close_pad

    @close_padding.setter
    def close_padding(self, v):
        """close_pairs 의 여유 (m)."""
        self._close_pad = float(v)
        self.set_pair_padding({p: self._close_pad for p in close_pairs(self.pairs)})

    def set_pair_padding(self, overrides):
        """{(링크a, 링크b): 여유 m} — 순서 무관. 빈 dict 면 모두 기본값."""
        self._pad_over = {frozenset(k): float(v) for k, v in overrides.items()}
        unknown = set(self._pad_over) - {frozenset(p) for p in self.pairs}
        if unknown:
            raise ValueError(f"검사하지 않는 쌍: {[tuple(u) for u in unknown]}")
        self._rebuild_pad()

    def _rebuild_pad(self):
        self._pad = np.array([self._pad_over.get(frozenset(p), self._default_pad) for p in self.pairs])

    NEAR = 0.05        # m — 경계구 하한이 padding + NEAR 아래인 쌍만 볼록 껍질(GJK) 거리를 잰다
    MESH_NEAR = 0.005  # m — 껍질 거리가 padding + MESH_NEAR 아래인 쌍만 원래 메시로 다시 잰다

    def _refine(self, d, M, limit=None):
        """하한(기본 padding, 속도 여유가 붙으면 그 값) 근처 쌍을 원래 메시(오목한 곳 그대로) 거리로 바꾼다.
        메시 거리 ≥ 껍질 거리라 판정만 정확해진다."""
        lim = self._pad if limit is None else np.maximum(self._pad, limit)
        for k in np.nonzero(d < lim + self.MESH_NEAR)[0]:
            a, b = int(self._pa[k]), int(self._pb[k])
            self._res.clear()
            d[k] = coal.distance(self._mesh[a], coal.Transform3s(M[a].rotation, M[a].translation),
                                 self._mesh[b], coal.Transform3s(M[b].rotation, M[b].translation), self._req, self._res)
        return d

    def distances(self, q19, exact=False, limit=None):
        """활성 쌍마다 거리(m, 겹치면 0 이하). padding 근처 쌍은 원래 메시 거리, 그 위는 볼록 껍질 거리(≤ 실제),
        exact=False 면 먼 쌍은 경계구 하한(≤ 실제 거리, padding + NEAR 위)."""
        pin.updateGeometryPlacements(self.model, self.data, self.geom, self.gdata, self.q(q19))
        M = self.gdata.oMg
        if exact:
            pin.computeDistances(self.geom, self.gdata)
            return self._refine(np.array([r.min_distance for r in self.gdata.distanceResults]), M, limit)
        c = np.array([M[i].act(self._ctr[i]) for i in range(len(self._ctr))])
        d = np.linalg.norm(c[self._pa] - c[self._pb], axis=1) - self._rad[self._pa] - self._rad[self._pb]
        G = self.geom.geometryObjects
        far = self._pad if limit is None else np.maximum(self._pad, limit)
        for k in np.nonzero(d < far + self.NEAR)[0]:
            a, b = int(self._pa[k]), int(self._pb[k])
            self._res.clear()
            d[k] = coal.distance(G[a].geometry, coal.Transform3s(M[a].rotation, M[a].translation),
                                 G[b].geometry, coal.Transform3s(M[b].rotation, M[b].translation), self._req, self._res)
        return self._refine(d, M, limit)

    HARD_FLOOR = 0.005   # m — 이미 padding 안에서 시작해도 이 아래로는 절대 허용하지 않는다
    # 속도 비례 여유 (s): 하한 = padding + SPEED_K × (그 순간 두 부품의 상대 속도 상한 v, m/s — pair_speeds).
    # 빠를수록 실제 팔이 계획 경로에서 벗어나는 양(경로 이탈·끝점 넘침)이 커지는 몫. 실기 속도 시험(왼팔, 관절 상태 100 Hz
    # 기록)에서 손 0.7 m/s 까지 경로 이탈 최대 1.6 cm (속도와 거의 무관 — 청크 경계에서 정지 출발 계획과 실제 관성의 차이).
    # 그보다 빠른 속도는 재지 못했다. 0.05 s 면 녹화 재생 오탐 9.6 %, 0.02 s 면 1.2 %.
    SPEED_K = 0.02

    def pair_speeds(self, Q, times, n_grid=60):
        """[M, 쌍] 두 부품이 서로 가까워질 수 있는 속도 상한 (m/s) — **상대 속도**. 부품 a 에 붙어서 본 b 의 점 속도:
            |v_rel(p)| ≤ |v_Ob − v_Oa − ω_a × (O_b − O_a)| + |ω_b − ω_a| · R_b     (O = 프레임 원점, R_b = b 형상 점까지 최대 거리)
        두 부품을 같이 움직이는 관절(예: 같은 팔의 어깨)은 둘 사이 거리를 못 바꾸므로 여기서 저절로 빠진다.
        (절대 속도의 합은 어깨를 빨리 돌리면 팔꿈치↔손목처럼 거리가 안 변하는 쌍까지 막는다.)
        순기구학 속도로 n_grid 개 시각에서 재고, 사이 샘플은 이웃 두 격자의 큰 값 (5차 스플라인이라 속도가 매끄럽다).
        주의: 격자 사이의 값은 근사다 (엄밀한 상한이 아니다)."""
        Pm, seg = self._speed_grid(Q, times, n_grid)
        return Pm[seg]

    def _speed_grid(self, Q, times, n_grid=60):
        """pair_speeds 의 압축형 → (Pm[구간, 쌍], seg[M]): 샘플 i 의 값 = Pm[seg[i]]. [M, 쌍] 전체를 펼치지 않는다."""
        M = len(Q)
        qd = np.gradient(Q, times, axis=0)
        gi = np.unique(np.linspace(0, M - 1, min(M, n_grid)).round().astype(int))
        if not hasattr(self, "_vel_map"):     # 프레임은 형상끼리 겹친다 → 고유 프레임만 재고 형상으로 펼친다
            frames = [go.parentFrame for go in self.geom.geometryObjects]
            uf, inv = np.unique(frames, return_inverse=True)
            self._vel_map = (np.array([self._vidx[k] for k in POSE_KEYS]),
                             np.array([self._vidx[m] for m in MIMIC]), np.array([self._vidx[s] for s in MIMIC.values()]),
                             [int(f) for f in uf], inv)
        vk, vm, vs, uf, inv = self._vel_map
        O, V, W = (np.empty((len(gi), len(uf), 3)) for _ in range(3))
        for r, i in enumerate(gi):
            v = np.zeros(self.model.nv)
            v[vk] = qd[i]
            v[vm] = v[vs]
            pin.forwardKinematics(self.model, self.data, self.q(Q[i]), v)
            pin.updateFramePlacements(self.model, self.data)
            for u, f in enumerate(uf):
                O[r, u] = self.data.oMf[f].translation
                tw = pin.getFrameVelocity(self.model, self.data, f, pin.LOCAL_WORLD_ALIGNED)
                V[r, u], W[r, u] = tw.linear, tw.angular
        O, V, W = O[:, inv], V[:, inv], W[:, inv]                   # [격자, 형상, 3]
        a, b = self._pa, self._pb
        # 기준을 a 로 잡든 b 로 잡든 상한이다 → 둘 중 작은 값 (장애물처럼 원점이 멀리 있는 형상을 기준으로 잡으면
        # 레버가 1 m 가까이 되어 상한이 몇 배로 부푼다 — 상자 벽 장애물에서 거짓 거부로 확인)
        Ob_a, dW = O[:, b] - O[:, a], np.linalg.norm(W[:, b] - W[:, a], axis=2)
        ab = np.linalg.norm(V[:, b] - V[:, a] - np.cross(W[:, a], Ob_a), axis=2) + dW * self._gR[b]
        ba = np.linalg.norm(V[:, a] - V[:, b] + np.cross(W[:, b], Ob_a), axis=2) + dW * self._gR[a]
        P = np.minimum(ab, ba)
        Pm = np.maximum(P[:-1], P[1:]) if len(gi) > 1 else P     # 격자 구간마다 양 끝의 큰 값
        seg = np.clip(np.searchsorted(gi, np.arange(M), side="right") - 1, 0, max(len(gi) - 2, 0))
        return Pm, seg

    def thresholds(self, q_start):
        """쌍마다 허용 하한. 보통은 padding. 시작 자세에서 이미 padding 안인 쌍은 '지금보다 가까워지지만 않으면' 허용
        (빠져나오는 청크까지 막혀 얼어붙지 않게) — 단 HARD_FLOOR 아래는 안 된다 (조금씩 파고드는 것 방지)."""
        d0 = self.distances(q_start)
        return np.minimum(self._pad, np.maximum(d0, self.HARD_FLOOR))

    def check_path(self, Q, stop_at_first=False, deadline=None, times=None):
        """경로 Q[M, 19] → (최소 거리 m, 그 쌍, 그 샘플 번호, 하한을 깬 첫 샘플 번호 | None, 거리 잰 샘플 수, 시간 초과,
        하한을 처음 깬 (쌍, 거리, 하한) | None).
        하한 = thresholds(Q[0]) (보통 padding). deadline(perf_counter 시각)을 넘기면 그 자리를 하한 위반으로 친다
        (못 끝낸 검사는 안전하다고 보지 않는다). times(샘플 시각 s)를 주면 속도 비례 여유(SPEED_K)를 더한다 — 단
        시작부터 이미 padding 안인 쌍은 빼고 '지금보다 가까워지지 말 것' 규칙만 (빠져나오기가 막히지 않게).

        보수적 전진 (쌍마다): 샘플 i 에서 쌍 p 의 거리가 d_p 면, 그 뒤 그 쌍의 누적 접근 상한 Σ W[:, p]·|Δq| 이
        d_p − 하한_p 에 닿기 전까지 p 는 하한 아래로 못 들어온다. 다음 잴 샘플 = 어느 쌍이든 처음 닿는 샘플.
        건너뛴 구간의 '최소 거리'는 모르지만 하한 위인 것은 보장된다 (판정이 바뀌지 않는다).

        닿을 수 있는 쌍만 (Jetson Orin 에서 시간의 대부분이 [M 샘플, 574 쌍] 표 계산이었다): 시작 거리 − 경로 전체
        누적 접근 상한 ≥ 경로 중 하한의 최댓값인 쌍은 경로 내내 하한 위가 보장되므로 표에서 뺀다. 판정·첫 위반 샘플은
        같다 (위반 여부는 메시 거리로 재고, 건너뛰기는 위반 샘플을 넘지 못한다). 최소 거리는 잰 샘플 기준이라 달라질 수 있다."""
        d0 = self.distances(Q[0])
        thr0 = np.minimum(self._pad, np.maximum(d0, self.HARD_FLOOR))       # = thresholds(Q[0])
        dQ = np.abs(np.diff(Q, axis=0))
        speed = times is not None and self.SPEED_K > 0 and len(Q) > 1
        if speed:
            Pm, seg = self._speed_grid(Q, times)                               # 두 부품 상대 속도 상한 m/s (압축형)
            k_on = self.SPEED_K * (thr0 >= self._pad)                          # 시작부터 안인 쌍은 속도 몫 없음
            thr_max = thr0 + k_on * Pm.max(0)
        else:
            thr_max = thr0
        act = np.nonzero(d0 - dQ.sum(0) @ self.W < thr_max)[0]               # 하한에 닿을 수 있는 쌍
        if speed:
            thr_t = thr0[act] + k_on[act] * Pm[:, act][seg]                    # [M, 닿을 수 있는 쌍]
        else:
            thr_t = np.broadcast_to(thr0[act], (len(Q), len(act)))
        thr_suf = np.maximum.accumulate(thr_t[::-1], axis=0)[::-1]          # i 이후 하한의 최댓값 (건너뛰기용, 보수적)
        reach = np.vstack([np.zeros((1, len(act))), np.cumsum(dQ @ self.W[:, act], axis=0)])
        lim = thr0.copy()            # distances 의 정밀 계산 범위 — 못 닿는 쌍은 시작 하한 그대로
        best, arg, first, i, n = np.inf, (None, -1), None, 0, 0
        bad_pair = None            # 하한을 처음 깬 쌍과 그때 거리 (최소 거리 쌍과 다를 수 있다 — 쌍마다 하한이 달라서)
        while i < len(Q):
            if deadline is not None and time.perf_counter() > deadline:
                return best, arg[0], max(arg[1], 0), (first if first is not None else i), n, True, bad_pair
            if i == 0 and (not len(act) or (thr_t[0] <= thr0[act]).all()):
                d = d0                                                         # 시작 자세는 이미 잼 (하한이 같다)
            else:
                lim[act] = thr_t[i]
                d = self.distances(Q[i], limit=lim)
            n += 1
            j = int(d.argmin())
            if d[j] < best:
                best, arg = float(d[j]), (self.pairs[j], i)
            thr = thr_t[i]
            da = d[act]
            if (da < thr).any():
                if first is None:
                    first = i
                    k = int(np.argmax(thr - da))
                    bad_pair = (self.pairs[act[k]], float(da[k]), float(thr[k]))
                if stop_at_first:
                    break
                i += 1
                continue
            # 다음 잴 샘플: 어느 쌍이든 누적 접근이 (d − 하한) 에 처음 닿는 샘플. 끝까지 안 닿으면 남은 경로는 안전
            hit = (reach[i + 1:] >= reach[i] + da - thr_suf[i]).any(1)
            i = i + 1 + int(hit.argmax()) if hit.any() else len(Q)
        return best, arg[0], arg[1], first, n, False, bad_pair

    def check_chunk(self, q0, chunk, period, home, limits, grip_cmd=None, stop_at_first=True, deadline=None):
        """청크 하나의 경로 판정. → dict(ok, min_dist_m, pair, t_s, first_bad_t_s, n_samples, n_checked, ms, timeout, bad_pair).
        min_dist_m 은 실제로 잰 샘플 중 최솟값이다 (건너뛴 구간은 padding 위가 보장될 뿐)."""
        t0 = time.perf_counter()
        times, Q, _Qt = chunk_path(q0, chunk, period, home, limits, grip_cmd)
        best, pair, i, first, n, late, bad = self.check_path(Q, stop_at_first, deadline, times)
        return {"ok": first is None, "min_dist_m": round(best, 4), "pair": pair, "t_s": round(float(times[i]), 3),
                "first_bad_t_s": None if first is None else round(float(times[first]), 3),
                "n_samples": len(times), "n_checked": n, "ms": round((time.perf_counter() - t0) * 1e3, 1),
                "timeout": late, "bad_pair": None if bad is None else
                {"pair": bad[0], "dist_m": round(bad[1], 4), "limit_m": round(bad[2], 4)}}

    BUDGET_S = 0.3   # 관문 한 번의 시간 상한 (Jetson Orin 실측: 20 점 청크 최대 0.21 s, 전체의 0.1 % 가 넘음)
    TRUNC_EXTRA = 0.5   # 시간 초과 뒤 '확인된 앞부분' 재검사에 더 주는 시간 (BUDGET 대비 비율)

    def gate_chunk(self, q0, chunk, period, home, limits, grip_cmd=None, budget_s=None):
        """관문: 청크를 통과 / 앞부분만 / 거부로 가른다. → dict(verdict, reason, n_exec, chunk, full, final).
        q0 = 지금 관절(19, POSE_KEYS 순서, 정지로 가정), home = 기준 자세 {POSE_KEYS: 값}, limits = robot.urdf_limits(),
        grip_cmd = 직전 그리퍼 지령 {그리퍼: 값} (없으면 q0).

        통과 = 그대로 실행. 걸리면 padding 진입 시각보다 앞에 도착하는 점까지만 남겨(앞부분만) 경로를 **다시 만들어**
        검사한다 — 자르면 마지막 점에서 서도록 감속 구간이 바뀌어 곡선이 달라지기 때문이다. 통과할 때까지 한 점씩 더
        자르고, 한 점도 못 남기면 거부(직전 자세 유지). full = 원래 청크 판정, final = 실행할 청크 판정.
        시간 상한(budget_s, 기본 BUDGET_S)을 넘기면 통째로 거부하지 않고 그때까지 검사를 마친 구간 —
        안전이 확인된 구간 — 안에 도착하는 점까지만 남겨 같은 방식으로 자른다 (reason "timeout"). 재검사에는
        budget × TRUNC_EXTRA 를 더 주고, 그것도 넘기면 거부한다."""
        chunk = np.asarray(chunk, float)
        budget = self.BUDGET_S if budget_s is None else budget_s
        dl = time.perf_counter() + budget
        full = self.check_chunk(q0, chunk, period, home, limits, grip_cmd, deadline=dl)
        if full["ok"]:
            return {"verdict": "pass", "reason": None, "n_exec": len(chunk), "chunk": chunk, "full": full, "final": full}
        reason = "timeout" if full["timeout"] else "collision"
        if full["timeout"]:
            dl = time.perf_counter() + budget * self.TRUNC_EXTRA
        Qt = np.array([[t[k] for k in POSE_KEYS] for t in (action_targets(a, home, limits) for a in chunk)])
        t_knot = chunk_traj(np.asarray(q0, float), Qt, float(period))[0]
        n = int(np.searchsorted(t_knot, full["first_bad_t_s"], side="left"))   # 진입(또는 미확인) 시각 전에 도착하는 점 수
        while n >= 1:
            r = self.check_chunk(q0, chunk[:n], period, home, limits, grip_cmd, deadline=dl)
            if r["timeout"]:
                return {"verdict": "reject", "reason": "timeout", "n_exec": 0, "chunk": chunk[:0], "full": full,
                        "final": None}
            if r["ok"]:
                return {"verdict": "truncate", "reason": reason, "n_exec": n, "chunk": chunk[:n], "full": full, "final": r}
            n -= 1
        return {"verdict": "reject", "reason": reason, "n_exec": 0, "chunk": chunk[:0], "full": full, "final": None}


def structural_pairs(checker, limits, n=2000, frac=0.99, seed=0):
    """관절 한계 안 무작위 자세 n 개에서 (padding 없이) 겹친 비율이 frac 이상인 쌍 = 구조적으로 붙은 쌍."""
    rng = np.random.default_rng(seed)
    lo = np.array([limits[k][0] for k in POSE_KEYS])
    hi = np.array([limits[k][1] for k in POSE_KEYS])
    hits = np.zeros(len(checker.pairs))
    for _ in range(n):
        hits += checker.distances(rng.uniform(lo, hi)) <= 0
    return {frozenset(p) for p, h in zip(checker.pairs, hits) if h >= frac * n}, dict(zip(checker.pairs, hits / n))
