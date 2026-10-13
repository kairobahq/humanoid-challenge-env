# Copyright 2025.
#
# 맨 위 판에 무엇이 서는지, 그리고 **어느 한 자리가 비는지**.
#
# 판이 하나뿐이라 열은 셋이고, 각 열은 앞줄과 뒷줄 두 자리를 갖는다. 그 중 **한 열의
# 앞자리 하나**가 빈다 (사용자 지정 2026-10-12). 그래서 선반에 5 개가 서고 1 개가 크레이트에
# 실린다.
#
#   뒷줄    [ 0 열 ] [ 1 열 ] [ 2 열 ]
#   앞줄    [ 빈칸 ] [ 1 열 ] [ 2 열 ]      <- 비는 열은 씨앗이 고른다
#            └──> 이 열의 상품이 그대로 크레이트로 간다 (taskD_crate.py)
#
# **빈 칸과 크레이트는 따로 뽑지 않는다.** 로봇이 채워야 하는 것이 바로 그 상품이므로 둘은
# 한 뽑기의 두 면이다. 따로 뽑으면 과제가 성립하지 않는 장면이 나온다.
#
# 칸 간격·잔떨림·진열 각도는 **과제 B 의 것을 그대로 쓴다.** `taskD_stock_rules.json` 과
# `taskD_products.json` 에 구워져 있고, 굽는 스크립트는 `bake_taskD_tables.py` 다.
# 손으로 옮기지 않은 이유는 그 파일 머리말에 있다.
#
# 씨앗은 `taskD_scene_seed.spec(seed)["shelf_seed"]` 가 md5 로 파생한 것을 받는다. 그 아래
# 이 파일 안에서 `random.Random` 을 쓰는 것은 관례 위반이 아니다 -- 과제 A 도 그렇게 한다
# (`taskA_seats.py:178`). 자세한 구분은 `taskD_scene_seed.py` 머리말에 있다.
#
# isaaclab 은 `attach()` 안에서만 import 한다.
#
# 혼자 돌려 볼 수 있다:
#     python3 scripts/taskD/taskD_stock.py --shelf_seed 710540

import json as _json
import os as _os
import random as _random

import taskD_layout as _L
import taskD_shelf as _SH

_HERE = _os.path.dirname(_os.path.abspath(__file__))

with open(_os.path.join(_HERE, "taskD_stock_rules.json"), encoding="utf-8") as _f:
    RULES = _json.load(_f)
with open(_os.path.join(_HERE, "taskD_products.json"), encoding="utf-8") as _f:
    PRODUCTS = _json.load(_f)

ROWS, COLS = RULES["rows"], RULES["cols"]
FRONT_MARGIN = RULES["front_margin"]
ROW_PITCH, COL_PITCH = RULES["row_pitch"], RULES["col_pitch"]
SLOT_JITTER = RULES["slot_jitter"]
PRINGLES, COLA = RULES["pringles"], RULES["cola"]
FILLERS = [n for n in RULES["fillers"] if n in PRODUCTS]

LAYER = _SH.LAYERS[0]        # 상품이 설 수 있는 유일한 판


def slot_positions(board_top, front_x=None):
    """한 판의 모든 자리 중심. 앞줄 먼저, 줄 안에서는 왼쪽부터."""
    fx = _L.SHELF_FRONT_X if front_x is None else front_x
    y0 = -(COLS - 1) * COL_PITCH / 2.0
    return [(fx + FRONT_MARGIN + r * ROW_PITCH, y0 + c * COL_PITCH, board_top)
            for r in range(ROWS) for c in range(COLS)]


def layout(shelf_seed):
    """(columns, empty) -- 세 열의 상품과, 비는 한 자리.

    `columns` 는 {(layer, col): 상품}, 세 항목.
    `empty` 는 [(layer, slot)], **한 항목**. 빈 자리는 언제나 앞줄이므로 slot == col 이다.

    비는 열의 상품은 과제 B 가 실제로 파지를 계획해 둔 둘(프링글스·콜라제로) 중에서 뽑고,
    나머지 두 열은 과제 B 의 필러 풀에서 뽑는다. 필러 풀은 스캔이 제대로 나온 것과 열 사이에
    들어가는 크기로 이미 걸러져 있다.
    """
    rng = _random.Random(int(shelf_seed))
    carried = rng.choice([PRINGLES, COLA])
    cols = [carried] + rng.sample(FILLERS, COLS - 1)
    rng.shuffle(cols)
    columns = {(LAYER, i): name for i, name in enumerate(cols)}
    return columns, [(LAYER, cols.index(carried))]


def carried_item(shelf_seed):
    """크레이트가 실어야 하는 상품 하나 -- 빈 자리가 생긴 열의 상품.

    `taskD_crate.py` 가 이것을 읽는다. 두 모듈이 각자 뽑지 않고 **여기 한 곳에서** 나온다.
    """
    columns, empty = layout(shelf_seed)
    (layer, slot), = empty
    return columns[(layer, slot % COLS)]


def _jitter(rng, x, y):
    """자리 중심에서 축당 `SLOT_JITTER` 안으로 밀어 놓는다. 진열은 자로 재어 놓지 않는다."""
    if not SLOT_JITTER:
        return x, y
    return x + rng.uniform(-SLOT_JITTER, SLOT_JITTER), y + rng.uniform(-SLOT_JITTER, SLOT_JITTER)


def stock(shelf_seed, front_x=None):
    """[(상품, 위치, layer, slot)] -- 처음부터 채워져 있는 자리 전부. 다섯 개."""
    columns, empty = layout(shelf_seed)
    gaps = set(empty)
    rng = _random.Random(int(shelf_seed) * 40503 + 7)
    spots = slot_positions(_SH.BOARD_TOPS[LAYER], front_x)
    out = []
    for (layer, col), name in sorted(columns.items()):
        for row in range(ROWS):
            slot = row * COLS + col
            if (layer, slot) in gaps:
                continue
            x, y, z = spots[slot]
            x, y = _jitter(rng, x, y)
            e = PRODUCTS[name]
            # 세우면 밑동 높이, 눕히면 가장 넓은 단면의 절반. 과제 B 와 같은 식이다.
            h = e["base_offset"] if e["shelf_upright"] else 0.5 * max(e["size"][0], e["size"][1])
            out.append((name, (x, y, z + h + 0.002), layer, slot))
    return out


def attach(cfg, shelf_seed, front_x=None, log=print):
    """상품마다 `RigidObjectCfg` 를 `cfg` 에 단다. 단 개수를 돌려준다.

    `InteractiveScene` 은 `cfg.__dict__` 를 훑어 자산을 만드므로, 여기서 다는 것은 필드로
    선언하는 것과 같다. 개수가 씨앗에 따라 달라질 수 있는 자산은 이렇게 단다.

    **자세는 구워 둔 `shelf_quat` 을 그대로 쓴다.** `rot` 을 빼면 "선호 없음" 이 아니라
    "그 상품 USD 가 저작된 대로" 가 된다 -- 과제 B 가 그것으로 기록 한 벌을 잃었다.
    """
    from cyclo_lab.simulation_tasks.manager_based.manipulation.pick_place import convstore_store

    items = stock(shelf_seed, front_x)
    for name, pos, layer, slot in items:
        prim = "L%d_S%02d" % (layer, slot)
        quat = tuple(PRODUCTS[name]["shelf_quat"])
        setattr(cfg, prim.lower(), convstore_store.product_cfg(prim, name, pos, rot=quat))
    log("[진열] 맨 위 판에 %d 개" % len(items))
    return len(items)


def problems(shelf_seed):
    """`--check` 가 보는 것."""
    out = []
    columns, empty = layout(shelf_seed)
    items = stock(shelf_seed)
    if len(columns) != COLS:
        out.append("열이 %d 개다 (기대 %d)" % (len(columns), COLS))
    if len(empty) != 1:
        out.append("빈 자리가 %d 개다 (기대 1)" % len(empty))
    want = ROWS * COLS - 1
    if len(items) != want:
        out.append("선반에 %d 개가 섰다 (기대 %d)" % (len(items), want))
    filled = {(l, s): n for n, _p, l, s in items}
    (gl, gs), = empty
    if (gl, gs) in filled:
        out.append("빈 자리 %r 에 %s 가 서 있다" % ((gl, gs), filled[(gl, gs)]))
    back = (gl, gs + COLS)
    if filled.get(back) != carried_item(shelf_seed):
        out.append("빈 자리의 뒷줄 %r 에 같은 상품이 없다 -- '한 개 모자란 진열'로 안 읽힌다"
                   % (back,))
    if {l for _n, _p, l, _s in items} != {LAYER}:
        out.append("지워진 판에 상품이 섰다 -- 받쳐 주는 것이 없다")
    # 상품이 선반 밖으로 나가지 않는지
    x0, x1, y0, y1 = _L.box("shelf")
    for n, p, _l, _s in items:
        if not (x0 <= p[0] <= x1) or not (y0 <= p[1] <= y1):
            out.append("%s 가 선반 밖이다 (%.3f, %.3f)" % (n, p[0], p[1]))
    # 유효 높이를 넘는 상품이 없는지 (맨 위는 열려 있으니 None)
    clear = _SH.CLEAR_HEIGHTS[LAYER]
    if clear is not None:
        for n, _p, _l, _s in items:
            if PRODUCTS[n]["size"][2] >= clear:
                out.append("%s 높이 %.3f 가 유효 높이 %.3f 를 넘는다"
                           % (n, PRODUCTS[n]["size"][2], clear))
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description="선반씨앗이 어떤 진열이 되는지 보여준다.")
    ap.add_argument("--shelf_seed", type=int, nargs="*", default=[710540],
                    help="taskD_scene_seed.spec(seed)['shelf_seed'] 값")
    a = ap.parse_args()
    for sd in a.shelf_seed:
        columns, empty = layout(sd)
        (gl, gs), = empty
        print("선반씨앗 %d" % sd)
        print("  열      %s" % [columns[(LAYER, i)] for i in range(COLS)])
        print("  빈 자리 %d 열 앞줄   크레이트 %s" % (gs, carried_item(sd)))
        for n, p, l, s in sorted(stock(sd), key=lambda t: t[3]):
            print("    L%d S%d  %-30s (%+.3f, %+.3f, %+.3f)" % (l, s, n, p[0], p[1], p[2]))
        p = problems(sd)
        print("  판정: %s" % ("문제 없음" if not p else "%d 건" % len(p)))
        for s in p:
            print("    ! %s" % s)


if __name__ == "__main__":
    main()
