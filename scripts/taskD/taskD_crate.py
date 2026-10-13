# Copyright 2025.
#
# 파란 크레이트에 무엇이 어디에 들어 있는지.
#
# **상품은 하나이고, 그것은 `taskD_stock.carried_item()` 이 돌려주는 것이다** -- 선반에서
# 빈 자리가 생긴 열의 상품. 여기서 따로 뽑지 않는다. 로봇이 채워야 하는 것이 바로 그
# 상품이므로 둘은 한 뽑기의 두 면이고, 따로 뽑으면 "크레이트에 든 것과 빈 칸이 다른 상품"
# 이라는, 과제가 성립하지 않는 장면이 나온다. 종속 관계가 이 한 줄에서 닫힌다.
#
# 어디에 놓는가는 과제 B 의 규칙을 그대로 쓴다:
#
#   * 크레이트 안쪽 길이를 **상품 수만큼** 구역으로 나눈다. 하나면 안쪽 전체가 한 구역이다
#     (세 개짜리의 3 분의 1 에 놓고 나머지를 비워 두는 것이 아니다)
#   * 그 구역 안에서 자리를 뽑되, 상품이 자기 반지름만큼은 벽에서 떨어지게 한다
#   * **떨어뜨리지 않고 놓는다.** 크레이트 안쪽 바닥에 닿는 높이로 바로 놓는다 --
#     떨어뜨리면 굴러서, 계획이 조준한 자리와 실제 자리가 달라진다
#   * 세울지 눕힐지, 뒤집을지는 `taskD_products.json` 의 `crate_upright` / `crate_flip`
#     (과제 B 의 `taskb_orientation.json` 에서 사람이 정한 값)
#
# 진열 각도(`display_yaw_deg`)는 **쓰지 않는다.** 그것은 선반에 섰을 때 어느 면이 통로를
# 보는가이고, 크레이트 안에서 상품을 돌리면 GraspGen 이 찾아 둔 파지가 전부 움직인다.
#
# 씨앗은 `taskD_scene_seed.spec(seed)["crate_seed"]` 를 받는다.
#
# 혼자 돌려 볼 수 있다:
#     python3 scripts/taskD/taskD_crate.py --shelf_seed 710540 --crate_seed 769109

import math as _math
import random as _random

import taskD_layout as _L
import taskD_stock as _ST

RULES = _ST.RULES["crate"]
PRODUCTS = _ST.PRODUCTS

INSIDE_X = tuple(RULES["inside_x"])     # 크레이트 자기 좌표의 안쪽 범위 (짧은 쪽)
INSIDE_Y = tuple(RULES["inside_y"])     # 긴 쪽
WALL_GAP = float(RULES["wall_gap"])     # 벽에서 띄우는 최소 거리

# 자세. 과제 B 와 같은 쿼터니언.
UPRIGHT = (1.0, 0.0, 0.0, 0.0)
ON_SIDE = (0.70710678, -0.70710678, 0.0, 0.0)      # 월드 X 로 -90 도: 축을 +Y 로
FLIP_QUAT = (0.0, 1.0, 0.0, 0.0)


def _qmul(a, b):
    """해밀턴 곱 (w, x, y, z)."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw)


def _yaw_quat(deg):
    r = _math.radians(deg) / 2.0
    return (_math.cos(r), 0.0, 0.0, _math.sin(r))


def regions(n):
    """안쪽 긴 쪽을 `n` 등분한 구간들. n == 1 이면 전체가 하나다."""
    lo, hi = INSIDE_Y
    step = (hi - lo) / float(n)
    return [(lo + i * step, lo + (i + 1) * step) for i in range(n)]


def radius(name):
    """상품이 자기 중심에서 평면으로 뻗는 거리. 어느 방향을 볼지 모르므로 대각선의 절반."""
    e = PRODUCTS[name]
    sx, sy, sz = e["size"]
    a, b = (sx, sy) if e["crate_upright"] else (sy, sz)
    return 0.5 * _math.hypot(a, b)


def rest_height(name):
    """크레이트 안쪽 바닥에서 상품 중심까지. 세우면 절반 높이, 눕히면 반지름."""
    e = PRODUCTS[name]
    sx, sy, sz = e["size"]
    return 0.5 * sz if e["crate_upright"] else 0.5 * max(sx, sy)


def orientation(name):
    """크레이트 안에서의 자세 쿼터니언. 진열 각도는 쓰지 않는다 (머리말 참조)."""
    e = PRODUCTS[name]
    quat = UPRIGHT if e["crate_upright"] else ON_SIDE
    if e["crate_flip"]:
        # 상품 자기 X 에 대해 돌린다 -- 오른쪽 곱. "캔을 뒤집는다" 는 반대쪽 끝으로 선다는 뜻.
        quat = _qmul(quat, FLIP_QUAT)
    return quat


def poses(shelf_seed, crate_seed, names=None):
    """[(상품, 월드 위치, 월드 쿼터니언)]. 기본은 한 개."""
    names = (_ST.carried_item(shelf_seed),) if names is None else tuple(names)
    rng = _random.Random(int(crate_seed))
    cx, cy, _cz = _L.CRATE_POS
    floor = _L.CRATE_FLOOR_Z
    yaw = _L.CRATE_ROT_DEG[2]
    turn = _yaw_quat(yaw)

    out = []
    for slot, name in enumerate(names):
        r = radius(name)
        (ylo, yhi) = regions(len(names))[slot]
        # 구역 안에서, 벽과 자기 반지름을 빼고 남은 데서 뽑는다. 남는 것이 없으면 구역 중앙.
        def _draw(lo, hi):
            a, b = lo + r + WALL_GAP, hi - r - WALL_GAP
            return rng.uniform(a, b) if b > a else 0.5 * (lo + hi)
        ly = _draw(ylo, yhi)
        lx = _draw(*INSIDE_X)
        # 크레이트 자기 좌표 -> 월드. yaw 90 이면 안쪽 긴 쪽(y)이 월드 x 로 간다.
        c, s = _math.cos(_math.radians(yaw)), _math.sin(_math.radians(yaw))
        wx = cx + (lx * c - ly * s)
        wy = cy + (lx * s + ly * c)
        out.append((name, (wx, wy, floor + rest_height(name)),
                    _qmul(turn, orientation(name))))
    return out


def attach(cfg, shelf_seed, crate_seed, log=print):
    """크레이트 안 상품을 `cfg` 에 단다. 단 개수를 돌려준다.

    **동역학이다.** 과제 B 의 책상 장면은 크레이트를 빼낼 때 상품이 뚫고 내려가지 않게
    운동학으로 얼려 두는데, 여기서는 크레이트를 빼내지 않고 로봇이 집어야 하므로 진짜
    리지드 바디여야 한다.
    """
    from cyclo_lab.simulation_tasks.manager_based.manipulation.pick_place import convstore_store

    items = poses(shelf_seed, crate_seed)
    for i, (name, pos, quat) in enumerate(items):
        setattr(cfg, "crate%d" % i,
                convstore_store.product_cfg("Crate%d" % i, name, pos, rot=quat))
    log("[크레이트] %d 개: %s" % (len(items), ", ".join(n for n, _p, _q in items)))
    return len(items)


def cfg(prim_path="{ENV_REGEX_NS}/Crate"):
    """크레이트 자체. 운동학 고정 -- 일이 시작되는 자리이고 걷어차일 것이 아니다."""
    import isaaclab.sim as sim_utils
    from isaaclab.assets import AssetBaseCfg

    return AssetBaseCfg(
        prim_path=prim_path,
        init_state=AssetBaseCfg.InitialStateCfg(
            pos=_L.CRATE_POS, rot=_yaw_quat(_L.CRATE_ROT_DEG[2])),
        spawn=sim_utils.UsdFileCfg(
            usd_path=_L.crate_usd(),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
        ),
    )


def table_cfg(prim_path="{ENV_REGEX_NS}/Desk"):
    """검정 책상. 운동학 고정 -- 가구는 닻이고, 동역학으로 두면 팔에 밀린다."""
    import isaaclab.sim as sim_utils
    from isaaclab.assets import AssetBaseCfg

    return AssetBaseCfg(
        prim_path=prim_path,
        init_state=AssetBaseCfg.InitialStateCfg(
            pos=(_L.TABLE_POS[0], _L.TABLE_POS[1], _L.TABLE_POS[2] + 0.003),
            rot=_yaw_quat(_L.TABLE_YAW_DEG)),
        spawn=sim_utils.UsdFileCfg(
            usd_path=_L.table_usd(),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
        ),
    )


def problems(shelf_seed, crate_seed):
    """`--check` 가 보는 것."""
    out = []
    items = poses(shelf_seed, crate_seed)
    if len(items) != 1:
        out.append("크레이트에 %d 개다 (기대 1)" % len(items))
    want = _ST.carried_item(shelf_seed)
    for name, pos, _q in items:
        if name != want:
            out.append("크레이트 상품 %s 가 빈 자리의 상품 %s 와 다르다 -- 종속이 깨졌다"
                       % (name, want))
        x0, x1, y0, y1 = _L.box("crate")
        r = radius(name)
        if not (x0 + r <= pos[0] <= x1 - r) or not (y0 + r <= pos[1] <= y1 - r):
            out.append("%s 가 크레이트 벽을 넘었다 (%.3f, %.3f)" % (name, pos[0], pos[1]))
        want_z = _L.CRATE_FLOOR_Z + rest_height(name)
        if abs(pos[2] - want_z) > 1e-9:
            out.append("%s 가 바닥에 닿아 있지 않다 (%.4f, 기대 %.4f)" % (name, pos[2], want_z))
        top = pos[2] + 0.5 * PRODUCTS[name]["size"][2]
        if top > _L.CRATE_RIM_Z:
            out.append("%s 가 림(%.4f) 위로 %.0f mm 솟았다"
                       % (name, _L.CRATE_RIM_Z, (top - _L.CRATE_RIM_Z) * 1000.0))
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description="크레이트에 무엇이 어디 들어가는지 보여준다.")
    ap.add_argument("--shelf_seed", type=int, default=710540)
    ap.add_argument("--crate_seed", type=int, default=769109)
    a = ap.parse_args()
    print("크레이트 중심 %s  안쪽 바닥 %.4f  림 %.4f"
          % (_L.CRATE_POS, _L.CRATE_FLOOR_Z, _L.CRATE_RIM_Z))
    for name, pos, quat in poses(a.shelf_seed, a.crate_seed):
        e = PRODUCTS[name]
        print("  %-30s (%+.4f, %+.4f, %+.4f)  %s  바닥에서 %+.1f mm  림까지 %+.0f mm"
              % (name, pos[0], pos[1], pos[2],
                 "세움" if e["crate_upright"] else "눕힘",
                 (pos[2] - _L.CRATE_FLOOR_Z) * 1000.0,
                 (_L.CRATE_RIM_Z - (pos[2] + 0.5 * e["size"][2])) * 1000.0))
    p = problems(a.shelf_seed, a.crate_seed)
    print("판정: %s" % ("문제 없음" if not p else "%d 건" % len(p)))
    for s in p:
        print("  ! %s" % s)


if __name__ == "__main__":
    main()
