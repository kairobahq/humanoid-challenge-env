# Copyright 2026.
#
# 정착한 장면이 규칙에 맞는지, 그리고 Isaac 을 띄우기 전에 알 수 있는 문제가 없는지.
#
# 두 종류의 검사가 있다.
#   check_settled   물리 정착 뒤 상품마다: 띠 안쪽인가, 상판을 뚫었나, 서 있나(원통) / 평평한가
#                   (상자), QR 면이 바닥을 보나, QR 방위 오차가 3 도 안인가, 상품끼리 10 cm
#                   떨어졌나. 하나라도 어긋나면 그 seed 는 다음 attempt 로 재딜한다.
#                   원본 `qr_scene.settle_and_check` 의 검사부를 그대로 옮겼다.
#   check_static    `--check` 용. 에셋(상품 8 종 USD·info.json·타일 json·스캐너·매장 USD)이
#                   제자리에 있는지와 띠 기하가 성한지. 1 초면 끝난다.
#
# 자리·자세는 로봇 좌표로 받는다. isaaclab 을 쓰지 않는 순수 파이썬이다.

import math
import pathlib

import numpy as np

from . import taskC_deal as D
from . import taskC_layout as L
from . import taskC_products as P


def rotated_half_extents(quat, ext_m):
    """세계 AABB 반치수: |R| @ (ext/2)."""
    return np.abs(D.quat_to_mat(quat)) @ (np.asarray(ext_m, dtype=float) / 2.0)


def _upright(slug, q):
    if P.is_cylinder(slug):
        ax = np.zeros(3)
        ax[D.long_axis(slug)] = 1.0
        return abs(float((D.quat_to_mat(q) @ ax)[2])) > 0.85
    # 평평 정착 (수리 28호): 상자는 어느 축이든 세계 z 와 0.97(14 도) 이상 정렬돼야 한다
    return float(np.abs(D.quat_to_mat(q)[2, :]).max()) > 0.97


def check_settled(entries):
    """entries: [{slug, pos, quat, sq}] (로봇 좌표, 정착 후 pos/quat, 스폰 자세 sq).

    돌려주는 것: (전체 통과, [항목 dict + inside/sunk/upright/cyl/qr_up/he/qr_az_err]).
    """
    in_x0, in_x1, in_y0, in_y1 = L.band_inner()
    tol = L.QR_AZ_TOL_DEG
    tgt_az = L.QR_TARGET_YAW_DEG
    vis = P.optional_json("_qr_tiles_vis.json")
    res = []
    ok = True
    for k, e in enumerate(entries):
        slug, p, q = e["slug"], np.asarray(e["pos"], dtype=float), tuple(e["quat"])
        ext = np.array(P.size_mm(slug), dtype=float) / 1000.0
        he = rotated_half_extents(q, ext)
        inside = bool(p[0] - he[0] >= in_x0 and p[0] + he[0] <= in_x1
                      and p[1] - he[1] >= in_y0 and p[1] + he[1] <= in_y1)
        sunk = bool(p[2] < L.COUNTER_TOP_Z - 0.01)
        upright = bool(_upright(slug, q))
        qr_up = True
        if k == 0:
            try:
                n_w = D.quat_to_mat(q) @ np.asarray(P.tile_normal(slug), dtype=float)
                qr_up = bool(float(n_w[2]) > -0.5)          # 바닥을 보면 재딜
            except KeyError:
                pass
        r = dict(e)
        r.update(slug=slug, pos=[float(v) for v in p], quat=[float(v) for v in q],
                 inside=inside, sunk=sunk, upright=upright, cyl=bool(P.is_cylinder(slug)),
                 qr_up=qr_up, he=[float(v) for v in he])
        res.append(r)
        ok = ok and inside and not sunk and upright and qr_up

    # QR-62: 정착 후 모든 상품의 QR 방위가 목표(-90 도)에서 3 도 안이어야 한다
    for r in res:
        sq = r.get("sq")
        if sq is not None and r["slug"] in vis:
            # QR-139: 캘리 품목은 "스폰 시 목표를 향하던 로컬 벡터"로 정착 드리프트만 잰다
            tv = (math.cos(math.radians(tgt_az)), math.sin(math.radians(tgt_az)), 0.0)
            qc = (sq[0], -sq[1], -sq[2], -sq[3])
            nl = D.rotate(tuple(qc), tv)
            nw = np.asarray(D.rotate(tuple(r["quat"]), tuple(nl)), dtype=float)
        else:
            try:
                n0 = np.asarray(P.tile_normal(r["slug"]), dtype=float)
            except KeyError:
                continue
            nw = np.asarray(D.rotate(tuple(r["quat"]), tuple(n0)), dtype=float)
        az = math.degrees(math.atan2(nw[1], nw[0]))
        err = abs((az - tgt_az + 180.0) % 360.0 - 180.0)
        r["qr_az_err"] = round(err, 2)
        if err > tol:
            r["inside"] = False
            ok = False

    # QR-11: 정착 후 표면-표면(AABB) 간격 >= 10 cm
    for i in range(len(res)):
        for j in range(i + 1, len(res)):
            dx = abs(res[i]["pos"][0] - res[j]["pos"][0]) - res[i]["he"][0] - res[j]["he"][0]
            dy = abs(res[i]["pos"][1] - res[j]["pos"][1]) - res[i]["he"][1] - res[j]["he"][1]
            gap = math.hypot(max(0.0, dx), max(0.0, dy))
            res[i]["gap_min"] = min(res[i].get("gap_min", 9.0), gap)
            res[j]["gap_min"] = min(res[j].get("gap_min", 9.0), gap)
            if gap < L.MIN_GAP:
                res[i]["inside"] = False
                res[j]["inside"] = False
                ok = False
    return ok, res


def redeal_reason(res):
    """재딜 사유가 있는 상품 이름들."""
    return [r["slug"] for r in res
            if not r["inside"] or r["sunk"] or not r.get("upright", True) or not r.get("qr_up", True)]


def fail_open_ok(res):
    """수리 28호-c: 재딜 소진 시 위반이 **비원통의 기움뿐**이면 수용한다 (둥근 어깨 형상 구제)."""
    return all(r["inside"] and not r["sunk"] and r.get("qr_up", True)
               and (r["upright"] or not r["cyl"]) for r in res)


def check_static(assets_root, require_store=True):
    """`--check` 검사. 문제 목록을 돌려준다 (빈 리스트 = 문제 없음)."""
    a = pathlib.Path(assets_root)
    out = []
    pdir = P.products_dir() if a == P.assets_root() else a / "products_c"
    for s in P.PRODUCTS:
        d = pdir / s
        for f in (f"{s}_phys.usd", "info.json"):
            if not (d / f).is_file():
                out.append(f"상품 파일 없음: {pdir.name}/{s}/{f}")
    if not (pdir / "_qr_tiles.json").is_file():
        out.append(f"타일 json 없음: {pdir.name}/_qr_tiles.json")
    if not (a / "fixtures" / "scanner" / "scanner_taskC.usd").is_file():
        out.append("스캐너 USD 없음: fixtures/scanner/scanner_taskC.usd")
    if require_store and not (a / "store" / "scene" / "fixture_kit" / "out" / "store_scene.usd").is_file():
        out.append("매장 USD 없음: store/scene/fixture_kit/out/store_scene.usd")
    x0, x1, y0, y1 = L.band_inner()
    if not (x0 < x1 and y0 < y1):
        out.append("띠 안쪽 영역이 비었다")
    gx, gy = L.STOW_GRIP_XY
    if x1 - gx < L.STOW_GRIP_CLEAR and gy - y0 < L.STOW_GRIP_CLEAR:
        out.append("스토우 금지 원반이 띠를 덮는다")
    cx, cy = L.COUNTER_CENTRE_WORLD
    for x, y in ((x0, y0), (x1, y1)):
        wx, wy = L.robot_to_world((x, y))
        if abs(wx - cx) > L.COUNTER_SIZE_XY[0] / 2 or abs(wy - cy) > L.COUNTER_SIZE_XY[1] / 2:
            out.append(f"띠 모서리 ({x:.3f},{y:.3f}) 가 계산대 밖: 세계 ({wx:.3f},{wy:.3f})")
    return out
