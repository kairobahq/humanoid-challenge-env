"""같은 팔에서 관절 1~2개를 사이에 둔 쌍 중 '관절 한계 안에서는 닿을 수 없는 쌍' / '항상 붙어 있는 쌍'을 찾는다.
    python kin_separated.py [출력 경로]   (scripts/selfcoll 에서, 기본: aiw_selfcoll/kin_excluded.json)

두 부품의 상대 자세는 사이 관절에만 달렸다. 그 관절들을 가동 범위 전체에서 격자로 돌려 최소 거리를 재고,
격자 사이에서 더 가까워질 수 있는 최대량(관절마다 레버 W × 격자 반 칸)을 빼도 > 0 이면 '닿을 수 없음'.
모든 격자에서 0 이하면 '항상 붙어 있음'(기구 구조). 그 밖은 실제로 닿을 수 있는 쌍이라 계속 검사한다.

주의: '닿을 수 없음'은 거리 > 0 이라는 뜻이지 padding 밖이라는 뜻이 아니다 (lower_bound_m 을 본다).
가정: 관절이 URDF 한계 밖으로 못 간다 (모터 위치 한계가 같은 값). URDF 가 바뀌면 다시 만든다.
"""
import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aiw_selfcoll.robot import POSE_KEYS, urdf_limits
from aiw_selfcoll.selfcoll import SelfCollision

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "aiw_selfcoll" / "kin_excluded.json"
N = 121   # 관절마다 격자 수

c = SelfCollision(kin_excluded=False)
lim = urdf_limits()
H = np.zeros(len(POSE_KEYS))   # 사이에 없는 관절의 값은 이 쌍의 상대 자세에 영향이 없다
m, G = c.model, c.geom.geometryObjects


def chain(j):
    out = set()
    while j > 0:
        out.add(j)
        j = m.parents[j]
    return out


key_of = {m.getJointId(n): n for n in POSE_KEYS}
excluded, kept = [], []
for k, (a, b) in enumerate(c.pairs):
    ca, cb = chain(G[c.link_of.index(a)].parentJoint), chain(G[c.link_of.index(b)].parentJoint)
    between = sorted({key_of[j] for j in ca ^ cb if j in key_of})
    if not (1 <= len(between) <= 2 and all(x.startswith(("arm_l", "arm_r", "gripper")) for x in between)):
        continue
    idx = [POSE_KEYS.index(x) for x in between]
    grids = [np.linspace(lim[x][0], lim[x][1], N) for x in between]
    D = []
    for vals in itertools.product(*grids):
        q = H.copy()
        q[idx] = vals
        D.append(c.distances(q, exact=True)[k])
    D = np.array(D)
    half = sum(c.W[POSE_KEYS.index(x), k] * (lim[x][1] - lim[x][0]) / (N - 1) / 2 for x in between)
    lower = D.min() - half
    if lower > 0:
        excluded.append({"pair": [a, b], "between": between, "min_grid_m": round(float(D.min()), 4),
                         "lower_bound_m": round(float(lower), 4), "why": "never"})
    elif D.max() <= 0:
        excluded.append({"pair": [a, b], "between": between, "min_grid_m": round(float(D.min()), 4),
                         "max_grid_m": round(float(D.max()), 4), "why": "always_touching"})
    else:
        kept.append({"pair": [a, b], "between": between, "min_grid_m": round(float(D.min()), 4),
                     "max_grid_m": round(float(D.max()), 4), "lower_bound_m": round(float(lower), 4)})
json.dump({"excluded": excluded, "kept": kept}, open(OUT, "w"), ensure_ascii=False, indent=1)
print(f"→ {OUT}: 제외(닿을 수 없음) {sum(e['why'] == 'never' for e in excluded)}, "
      f"제외(항상 붙음) {sum(e['why'] == 'always_touching' for e in excluded)}, 계속 검사 {len(kept)}")
for e in excluded:
    print(f"  제외 {e['why']:16s} {e['pair'][0]:26s} {e['pair'][1]:26s} 격자 최소 {e['min_grid_m'] * 100:5.2f} cm"
          + (f", 하한 {e['lower_bound_m'] * 100:5.2f} cm" if 'lower_bound_m' in e else ""))
for e in kept:
    print(f"  유지 {e['pair'][0]:26s} {e['pair'][1]:26s} 격자 {e['min_grid_m'] * 100:5.2f}~{e['max_grid_m'] * 100:5.2f} cm,"
          f" 하한 {e['lower_bound_m'] * 100:5.2f} cm")
