"""같은 팔에서 '관절 한계 안에서는 닿을 수 없는 쌍' / '항상 붙어 있는 쌍'을 찾는다 → 검사에서 뺀다.
    python kin_separated.py [출력 경로]   (scripts/selfcoll 에서, 기본: aiw_selfcoll/kin_excluded.json, 코어 수만큼 병렬)

① 관절 1~2개를 사이에 둔 쌍 (엄밀): 두 부품의 상대 자세는 사이 관절에만 달렸다. 그 관절들을 가동 범위 전체에서 격자로
   돌려 최소 거리를 재고, 격자 사이에서 더 가까워질 수 있는 최대량(관절마다 레버 W × 격자 반 칸)을 빼도 > 0 이면
   '닿을 수 없음'. 모든 격자에서 0 이하면 '항상 붙어 있음'(기구 구조). 그 밖은 실제로 닿을 수 있는 쌍이라 계속 검사한다.
② 팔꿈치(joint4) 아래 부품끼리(link4–7·손목 카메라·그리퍼) 중 ①에서 안 본 쌍 (사이 관절 3~4개 — 위 하한이 너무 거칠다):
   격자 + 최소 근처 국소 탐색으로 최소 거리를 찾아 SEP_MIN(1 cm) 이상이면 '닿을 수 없음'(method "refined",
   수치 탐색이라 엄밀한 하한은 아니다 — 그래서 여유를 둔다). 손목 link6 ↔ 그리퍼 몸체는 joint7 끝에서 실제로 닿으므로 남는다.

주의: '닿을 수 없음'은 거리 > 0 이라는 뜻이지 padding 밖이라는 뜻이 아니다 (lower_bound_m·min_m 을 본다).
가정: 관절이 URDF 한계 밖으로 못 간다 (모터 위치 한계가 같은 값). URDF 가 바뀌면 다시 만든다.
"""
import itertools
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aiw_selfcoll.robot import POSE_KEYS, urdf_limits  # noqa: E402
from aiw_selfcoll.selfcoll import MIMIC, SelfCollision  # noqa: E402

N = 121          # ① 관절마다 격자 수
SEP_MIN = 0.01   # m — ② 를 '닿을 수 없음'으로 볼 최소 거리
_ctx = None      # 작업 프로세스마다 한 번 만든다 (검사기·한계)


def ctx():
    global _ctx
    if _ctx is None:
        c = SelfCollision(kin_excluded=False)
        _ctx = (c, urdf_limits(), np.zeros(len(POSE_KEYS)))   # 사이에 없는 관절 값은 이 쌍의 상대 자세와 무관하다
    return _ctx


def chain(m, j):
    out = set()
    while j > 0:
        out.add(j)
        j = m.parents[j]
    return out


def between(c, k):
    """쌍 k 를 움직이는 관절 (두 체인의 대칭차, 그리퍼 mimic 은 gripper_joint1 축으로)."""
    m, G = c.model, c.geom.geometryObjects
    ia, ib = int(c._pa[k]), int(c._pb[k])
    return sorted({MIMIC.get(m.names[j], m.names[j]) for j in chain(m, G[ia].parentJoint) ^ chain(m, G[ib].parentJoint)}
                  & set(POSE_KEYS))


def strict(k):
    """① 엄밀한 격자 하한 → 판정 dict."""
    c, lim, H = ctx()
    a, b = c.pairs[k]
    bt = between(c, k)
    idx = [POSE_KEYS.index(x) for x in bt]
    D = []
    for vals in itertools.product(*[np.linspace(lim[x][0], lim[x][1], N) for x in bt]):
        q = H.copy()
        q[idx] = vals
        D.append(c.distances(q, exact=True)[k])
    D = np.array(D)
    half = sum(c.W[POSE_KEYS.index(x), k] * (lim[x][1] - lim[x][0]) / (N - 1) / 2 for x in bt)
    lower = D.min() - half
    e = {"pair": [a, b], "between": bt, "min_grid_m": round(float(D.min()), 4)}
    if lower > 0:
        return e | {"lower_bound_m": round(float(lower), 4), "why": "never"}
    if D.max() <= 0:
        return e | {"max_grid_m": round(float(D.max()), 4), "why": "always_touching"}
    return e | {"max_grid_m": round(float(D.max()), 4), "lower_bound_m": round(float(lower), 4)}


def refined(k):
    """② 격자 + 국소 탐색 최소 메시 거리 → 판정 dict."""
    import coal
    import pinocchio as pin

    c, lim, H = ctx()
    m = c.model
    a, b = c.pairs[k]
    ia, ib = int(c._pa[k]), int(c._pb[k])
    bt = between(c, k)
    ix = [POSE_KEYS.index(x) for x in bt]
    lo, hi = np.array([lim[x][0] for x in bt]), np.array([lim[x][1] for x in bt])
    data, gd = m.createData(), pin.GeometryData(c.geom)

    def dist(v):
        q = H.copy()
        q[ix] = v
        pin.updateGeometryPlacements(m, data, c.geom, gd, c.q(q))
        M = gd.oMg
        return coal.distance(c._mesh[ia], coal.Transform3s(M[ia].rotation, M[ia].translation),
                             c._mesh[ib], coal.Transform3s(M[ib].rotation, M[ib].translation),
                             coal.DistanceRequest(), coal.DistanceResult())

    n = {1: 721, 2: 121, 3: 31}.get(len(bt), 15)
    pts = np.array(list(itertools.product(*[np.linspace(x, y, n) for x, y in zip(lo, hi)])))
    D = np.array([dist(v) for v in pts])
    step, cand = (hi - lo) / (n - 1), pts[np.argsort(D)[:20]]
    best = (float(D.min()), pts[int(D.argmin())])
    for _ in range(2):   # 가장 가까운 후보 20개 주변을 두 번 더 촘촘히
        out = []
        for v0 in cand:
            g = [np.linspace(max(x, v - s), min(y, v + s), 9) for v, s, x, y in zip(v0, step, lo, hi)]
            out += [(dist(np.array(v)), np.array(v)) for v in itertools.product(*g)]
        out.sort(key=lambda r: r[0])
        cand, step = [o[1] for o in out[:20]], step / 4
        best = min(best, (out[0][0], out[0][1]), key=lambda r: r[0])
    e = {"pair": [a, b], "between": bt, "min_m": round(best[0], 4), "at": dict(zip(bt, np.round(best[1], 3).tolist())),
         "method": "refined"}
    return e | {"why": "never"} if best[0] >= SEP_MIN else e


def below_elbow(link):
    return any(link == f"arm_{s}_link{i}" for s in "lr" for i in (4, 5, 6, 7)) or link.startswith(("gripper_", "camera_"))


def side(link):
    return "l" if link == "camera_left_link" or link.startswith(("arm_l_", "gripper_l_")) else "r"


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "aiw_selfcoll" / "kin_excluded.json"
    c = ctx()[0]
    first = [k for k in range(len(c.pairs))
             if 1 <= len(bt := between(c, k)) <= 2 and all(x.startswith(("arm_l", "arm_r", "gripper")) for x in bt)]
    with ProcessPoolExecutor() as ex:
        res = list(ex.map(strict, first))
        done = {frozenset(c.pairs[k]) for k in first}
        second = [k for k, (a, b) in enumerate(c.pairs)
                  if frozenset((a, b)) not in done and below_elbow(a) and below_elbow(b) and side(a) == side(b)]
        res += list(ex.map(refined, second))
    excluded = [e for e in res if "why" in e]
    kept = [e for e in res if "why" not in e]
    json.dump({"excluded": excluded, "kept": kept}, open(out, "w"), ensure_ascii=False, indent=1)
    print(f"→ {out}: 제외(닿을 수 없음) {sum(e['why'] == 'never' for e in excluded)}, "
          f"제외(항상 붙음) {sum(e['why'] == 'always_touching' for e in excluded)}, 계속 검사 {len(kept)}")
    for e in excluded + kept:
        tag = "제외 " + e["why"] if "why" in e else "유지"
        if "min_m" in e:
            print(f"  {tag:22s} {e['pair'][0]:26s} {e['pair'][1]:26s} 탐색 최소 {e['min_m'] * 100:5.2f} cm @ {e['at']}")
        else:
            print(f"  {tag:22s} {e['pair'][0]:26s} {e['pair'][1]:26s} 격자 최소 {e['min_grid_m'] * 100:5.2f} cm"
                  + (f", 하한 {e['lower_bound_m'] * 100:5.2f} cm" if "lower_bound_m" in e else ""))


if __name__ == "__main__":
    main()
