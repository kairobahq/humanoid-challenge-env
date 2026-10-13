# Copyright 2025.
#
# 일 주변의 매장 -- 씨앗으로 흩뿌리는 배경 기물.
#
# 일 자체(로봇·책상·크레이트·선반)는 몇 제곱미터의 깨끗한 바닥이다. 그것만 본 정책은
# 배경을 하나만 본 것이라 배경을 단서로 쓸 수 있다. 그래서 **매장 자신의 기물**을 주변에
# 흩뿌린다 -- 곤돌라, 냉장 진열대, 쇼케이스, 계산대, 바닥에 뒹구는 바구니. 전부 ConvStore
# 장면을 짜는 그 기물들이고, 씨앗이 어느 것을 몇 개 어디에 둘지 정한다.
#
# 기물의 치수는 `store_fixtures.json` 에 구워 두었다 (`bake_taskD_tables.py`). 스폰은
# `convstore_store.fixture_cfg()` 가 한다 -- 레포 자신의 스포너이고, 운동학 고정, SDF
# 콜라이더 유지, 냉장고 문은 움직이게, 스케일은 손대지 않는다.
#
# **자리는 중심으로 지정한다.** 이 자산들은 원점이 중심이 아니다 -- `shelf_8by3` 의 덩치는
# 원점에서 0.90 m 옆에 있고 `cash_table` 은 0.56 m 다. 원점으로 놓으면 1 m 가까이 엉뚱한
# 데 간다. `convstore_store._origin_for()` 가 매니페스트의 `center` 로 그것을 되돌린다.
#
# 자리를 정하는 규칙 셋:
#
#   1. **작업영역 금지.** 로봇·책상·크레이트·선반 네 상자(`taskD_layout.work_boxes()`)에
#      여유 350 mm 를 더한 구역. 선반을 관통한 곤돌라는 배경이 아니라 깨진 장면이다.
#   2. **카메라 금지.** 미리보기 눈마다 반경 1.25 m. 안 막으면 렌즈 안에 냉장고가 생겨
#      화면이 텍스처 벽이 된다.
#   3. **서로 겹침 금지.** 사각형이 아니라 외접원으로 재는데, yaw 를 90 도 격자에서 일부러
#      비틀어 놓기 때문이다 -- 정확히 각 잡힌 매장은 배치로 읽히고, 요청은 어질러 달라는
#      것이었다.
#
# 어기는 추첨은 밀어내지 않고 **버리고 다시 뽑는다.** 밀어내면 매번 선반에 딱 붙어 서게
# 되고, 그것도 일종의 단서다.
#
# **왜 기하로만 막는가** -- 기물은 운동학 고정이다. 겹쳐도 PhysX 가 밀어내지 않고 조용히
# 파고든 채 있다. 눈으로는 틀렸고 로그로는 정상인 상태가 되므로 기하가 유일한 방어선이고,
# 그래서 여유를 매번 찍고 0 이하면 멈춘다. 작업영역 상자를 손으로 적었을 때 로봇 뒤쪽이
# 100 mm 모자랐던 것이 이 규칙이 생긴 이유다 (2026-10-12).
#
# 큰 기물은 더 멀리 둔다 -- 3.65 m 쇼케이스를 2 m 에 두면 화면을 막는 벽이고 4 m 에 두면
# 배경이다.
#
# 씨앗은 `taskD_scene_seed.spec(seed)["clutter_seed"]` 를 받는다.
#
# 혼자 돌려 볼 수 있다:
#     python3 scripts/taskD/taskD_clutter.py --clutter_seed 499776

import json as _json
import math as _math
import os as _os
import random as _random

import taskD_layout as _L

_HERE = _os.path.dirname(_os.path.abspath(__file__))

with open(_os.path.join(_HERE, "store_fixtures.json"), encoding="utf-8") as _f:
    FIXTURES = _json.load(_f)

# (기물 이름, 한 장면에 몇 개까지, 작업 중심에서 떨어질 거리 범위 m)
#
# 거리는 취향이 아니라 덩치의 함수다 -- 그만큼 떨어져야 방해물이 아니라 배경으로 읽힌다.
POOL = (
    # 큰 가구 -- 바깥 고리에만
    ("showcase",         1, (3.4, 5.4)),
    ("cash_table",       1, (3.2, 5.2)),
    ("table",            1, (3.2, 5.2)),
    ("shelf_7by3",       2, (3.0, 5.2)),
    ("shelf_8by3",       2, (3.0, 5.2)),
    # 중간 -- 배경의 몸통
    ("shelf_7by1",       3, (2.0, 4.4)),
    ("shelf_8by1",       2, (2.0, 4.4)),
    ("fridger_2doors",   2, (2.2, 4.6)),
    ("fridger_w_shelf",  1, (2.4, 4.6)),
    ("fridger_oneblock", 2, (2.0, 4.4)),
    ("icecream_fridger", 1, (2.2, 4.6)),
    ("trash_table",      1, (1.9, 4.0)),
    ("basetable",        2, (1.8, 4.0)),
    ("cigarette_shelf",  1, (1.9, 4.0)),
    # 작은 것 -- 어질러 보이게 하는 건 사실 이것들
    ("basket",           4, (1.3, 3.4)),
    ("big_basket",       3, (1.3, 3.4)),
    ("can_coke",         5, (1.2, 3.0)),
)

COUNT = tuple(_L.MEASURED["clutter"]["count"])
WORK_MARGIN = float(_L.MEASURED["clutter"]["work_margin"])
CAM_CLEAR = float(_L.MEASURED["clutter"]["cam_clear"])
MAX_TRIES = 400

# 금지 구역과 흩뿌리는 중심은 작업물 네 상자에서 **계산한다.** 손으로 적지 않는다.
_BOXES = _L.work_boxes()
_xs = [v for b in _BOXES.values() for v in b[:2]]
_ys = [v for b in _BOXES.values() for v in b[2:]]
WORK_BOX = (min(_xs) - WORK_MARGIN, max(_xs) + WORK_MARGIN,
            min(_ys) - WORK_MARGIN, max(_ys) + WORK_MARGIN)
WORK_CENTRE = ((min(_xs) + max(_xs)) / 2.0, (min(_ys) + max(_ys)) / 2.0)


def _circle(name):
    """기물의 평면 외접원 반지름. 발자국의 대각선 절반 -- yaw 가 비틀려 있으니."""
    sx, sy, _sz = FIXTURES[name]["size"]
    return 0.5 * _math.hypot(sx, sy)


def _hits_box(x, y, r, box):
    x0, x1, y0, y1 = box
    return (x + r > x0) and (x - r < x1) and (y + r > y0) and (y - r < y1)


def scatter(clutter_seed, cam_eyes=()):
    """[(기물, 프림 이름, (cx, cy), yaw_deg)] -- 이 씨앗의 방."""
    rng = _random.Random(int(clutter_seed))
    want = rng.randint(*COUNT)
    budget = {name: cap for name, cap, _band in POOL}
    bands = {name: band for name, _cap, band in POOL}
    names = [name for name, _cap, _band in POOL if name in FIXTURES]

    placed, out, tries = [], [], 0
    while len(out) < want and tries < MAX_TRIES:
        tries += 1
        name = rng.choice(names)
        if budget[name] <= 0:
            continue
        lo, hi = bands[name]
        r = _circle(name)
        ang = rng.uniform(0.0, 2.0 * _math.pi)
        dist = rng.uniform(lo, hi)
        cx = WORK_CENTRE[0] + dist * _math.cos(ang)
        cy = WORK_CENTRE[1] + dist * _math.sin(ang)
        if _hits_box(cx, cy, r, WORK_BOX):
            continue
        if any((cx - ex) ** 2 + (cy - ey) ** 2 < (CAM_CLEAR + r) ** 2 for ex, ey, _ez in cam_eyes):
            continue
        if any((cx - px) ** 2 + (cy - py) ** 2 < (r + pr) ** 2 for px, py, pr in placed):
            continue
        yaw = rng.choice((0.0, 90.0, 180.0, 270.0)) + rng.uniform(-22.0, 22.0)
        budget[name] -= 1
        placed.append((cx, cy, r))
        out.append((name, "Clutter_%02d_%s" % (len(out), name), (cx, cy), yaw))
    return out


def clearances(clutter_seed, cam_eyes=()):
    """[(기물, 가장 가까운 작업물, 여유 m)]. 매 실행마다 찍는다."""
    out = []
    for name, _prim, (cx, cy), _yaw in scatter(clutter_seed, cam_eyes):
        r = _circle(name)
        worst, who = None, None
        for label, (x0, x1, y0, y1) in _BOXES.items():
            dx = max(x0 - cx, 0.0, cx - x1)
            dy = max(y0 - cy, 0.0, cy - y1)
            gap = _math.hypot(dx, dy) - r
            if worst is None or gap < worst:
                worst, who = gap, label
        out.append((name, who, worst))
    return out


def attach(cfg, clutter_seed, cam_eyes=(), log=print):
    """배경 기물을 `cfg` 에 단다. 단 개수를 돌려준다."""
    from cyclo_lab.simulation_tasks.manager_based.manipulation.pick_place import convstore_store

    items = scatter(clutter_seed, cam_eyes)
    for name, prim, (cx, cy), yaw in items:
        rot = (_math.cos(_math.radians(yaw) / 2.0), 0.0, 0.0,
               _math.sin(_math.radians(yaw) / 2.0))
        pos = convstore_store._origin_for(name, cx, cy, rot)
        setattr(cfg, prim.lower(), convstore_store.fixture_cfg(name, pos, rot, prim=prim))
    log("[배경] 기물 %d 개" % len(items))
    return len(items)


def store_floor_cfg(size=13.0, prim="StoreFloor"):
    """매장 바닥 한 장을 방에 맞춰 늘린다. 회색 격자 대신.

    머리 카메라가 보는 것의 대부분이 바닥이라, 격자 평면은 빈 방과 똑같이 정책이 외울 수
    있는 배경이다. 물리적으로 서는 바닥은 이것이 아니라 `GroundPlane` 쪽이다 -- 이 판은
    얇은 시각용 타일이다.
    """
    from cyclo_lab.simulation_tasks.manager_based.manipulation.pick_place import convstore_store

    e = convstore_store.FIXTURES["floors"]
    sx = size / e["size"][0]
    sy = size / e["size"][1]
    cx, cy, _ = e["center"]
    return convstore_store.floor_cfg(prim, WORK_CENTRE[0] - cx * sx,
                                     WORK_CENTRE[1] - cy * sy, sx, sy)


def problems(clutter_seed, cam_eyes=()):
    """`--check` 가 보는 것. 여유가 0 이하인 기물이 있으면 그것이 전부다."""
    out = []
    items = scatter(clutter_seed, cam_eyes)
    if not (COUNT[0] <= len(items) <= COUNT[1]):
        out.append("기물이 %d 개다 (기대 %d~%d) -- 거절 추첨이 자리를 못 찾았다"
                   % (len(items), COUNT[0], COUNT[1]))
    for name, who, gap in clearances(clutter_seed, cam_eyes):
        if gap <= 0:
            out.append("%s 가 %s 와 %.0f mm -- 운동학 고정이라 물리가 밀어내지 않는다"
                       % (name, who, gap * 1000.0))
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description="배경씨앗이 어떤 방이 되는지 보여준다.")
    ap.add_argument("--clutter_seed", type=int, nargs="*", default=[499776])
    a = ap.parse_args()
    print("금지 구역 x %+.3f..%+.3f  y %+.3f..%+.3f   (작업물 네 상자 + 여유 %.0f mm)"
          % (WORK_BOX[0], WORK_BOX[1], WORK_BOX[2], WORK_BOX[3], WORK_MARGIN * 1000.0))
    print("흩뿌리는 중심 (%.3f, %.3f)" % WORK_CENTRE)
    for sd in a.clutter_seed:
        items = scatter(sd)
        gaps = clearances(sd)
        print("\n배경씨앗 %d -- 기물 %d 개" % (sd, len(items)))
        for (n, _p, (cx, cy), yaw), (_n2, who, gap) in zip(items, gaps):
            d = _math.hypot(cx - WORK_CENTRE[0], cy - WORK_CENTRE[1])
            print("  %-18s (%+.2f, %+.2f) %4.1f m  yaw %+6.1f  %s 와 %6.0f mm%s"
                  % (n, cx, cy, d, yaw, who, gap * 1000.0, "  <<< 충돌!" if gap <= 0 else ""))
        p = problems(sd)
        print("  최소 여유 %.0f mm   판정: %s"
              % (min(g for _n, _w, g in gaps) * 1000.0 if gaps else 0.0,
                 "문제 없음" if not p else "%d 건" % len(p)))


if __name__ == "__main__":
    main()
