# Copyright 2026.
#
# 랜덤 방위 씬(`taskC_deal_rand`)의 정착 검사 (2026-09-26 추가). `taskC_check.py` 와 같은 API 다.
#
# 원본 `taskC_check.check_settled` 는 정착 뒤 모든 상품의 QR 방위가 목표(-90 도, 정 오른쪽)에서
# 3 도 안인지 본다(QR-62). 랜덤 방위 장면은 그 검사에 늘 걸려 끝없이 재딜되므로, **그 검사 하나만
# 뺀** 판이 여기 있다. 나머지 검사 -- 띠 안쪽 · 상판 관통 · 원통 직립 / 상자 평평 · 슬롯 0 의 QR 이
# 바닥을 보지 않음 · 상품끼리 표면-표면 8 cm -- 는 원본과 한 글자도 다르지 않게 옮겼다.
# 방위 오차(`qr_az_err`)는 기록만 하고 판정에 쓰지 않는다 (보고서가 그대로 찍을 수 있게).
#
# 원본 `taskC_check.py` 는 고치지 않는다. 재딜 사유·기움 구제·에셋 검사는 원본 것을 그대로 쓴다.

import math

import numpy as np

from . import taskC_deal as D
from . import taskC_layout as L
from . import taskC_products as P
from .taskC_check import _upright, check_static, fail_open_ok, redeal_reason, rotated_half_extents  # noqa: F401


def check_settled(entries):
    """entries: [{slug, pos, quat, sq}] (로봇 좌표, 정착 후 pos/quat, 스폰 자세 sq).

    돌려주는 것: (전체 통과, [항목 dict + inside/sunk/upright/cyl/qr_up/he/qr_az_err]) -- 원본과 같은 모양.
    """
    in_x0, in_x1, in_y0, in_y1 = L.band_inner()
    tgt_az = L.QR_TARGET_YAW_DEG
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
                qr_up = bool(float(n_w[2]) > -0.5)          # 바닥을 보면 재딜 (원본과 같다)
            except KeyError:
                pass
        r = dict(e)
        r.update(slug=slug, pos=[float(v) for v in p], quat=[float(v) for v in q],
                 inside=inside, sunk=sunk, upright=upright, cyl=bool(P.is_cylinder(slug)),
                 qr_up=qr_up, he=[float(v) for v in he])
        # rand: QR-62 방위 검사는 뺀다. 목표(-90 도)에서 얼마나 돌았는지는 기록만 한다.
        try:
            nw = D.quat_to_mat(q) @ np.asarray(P.tile_normal(slug), dtype=float)
            az = math.degrees(math.atan2(nw[1], nw[0]))
            r["qr_az_err"] = round(abs((az - tgt_az + 180.0) % 360.0 - 180.0), 2)
        except KeyError:
            pass
        res.append(r)
        ok = ok and inside and not sunk and upright and qr_up

    # QR-11: 정착 후 표면-표면(AABB) 간격 >= MIN_GAP (원본과 같다)
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
