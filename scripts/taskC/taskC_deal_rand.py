# Copyright 2026.
#
# 랜덤 방위 씬 생성기 (2026-09-26 추가). `taskC_deal.py`(QR 정 오른쪽 생성기)와 **같은 API**다.
# 쓰는 쪽은 import 이름만 바꾸면 된다:
#
#     from taskC import taskC_deal as D          # 종전: QR 면이 세계 -Y(정 오른쪽)
#     from taskC import taskC_deal_rand as D     # 이것: QR 면이 무작위 방위 (360 도)
#
# 또는 `taskC_scene_gen` 이 회차·플래그로 둘 중 하나를 골라 준다 (task_c_demo.py --scene-gen).
#
# 원본 `taskC_deal.py` 는 고치지 않는다. 쿼터니언 도구·자리 뽑기(`pick_spot`)·상품 뽑기는 원본의
# 것을 **그대로 가져다 쓰고**, 이 파일에는 원본과 달라지는 두 가지만 있다.
#
#   1. 자세 (`rand_yaw_pose`): 원본 `qr_right_pose` 가 고른 자세(바닥에 닿는 면 · 원통 직립과
#      뒤집기 · 상자의 허용 바닥면 · 스폰 높이)를 그대로 두고, 그 위에 **세계 z 축 둘레 무작위 요**
#      를 앞에서 곱한다. 세계 z 둘레 회전은 회전 행렬의 셋째 행(상품 각 축의 세계 z 성분)을
#      바꾸지 않으므로, 어느 면이 바닥에 닿는지와 높이는 원본과 같고 QR 이 보는 방위만 달라진다.
#   2. 난수 흐름: 자리·자세를 `"{seed}-{attempt}-rand"` 로 뽑는다. 같은 시드라도 원본 장면과
#      자리까지 겹치지 않게 한다. 상품 3 종은 `pick_products` 가 그대로 정한다(같은 시드 -> 같은 상품).
#
# 그대로 지키는 규칙 (원본 머리말의 규칙 번호)
#   * V4-32 원통 직립(반은 뒤집음) · QR-73/81 상자는 허용 바닥면으로 눕힘 -- 자세 1 번이 보장.
#   * QR-11/81 띠 안쪽, 상품 표면-표면 >= `L.MIN_GAP` (8 cm, 축정렬 사각형으로 잰다).
#     상자를 비스듬히 돌리면 차지하는 사각형이 커지는데, 간격도 **돌려 놓은 사각형**으로 잰다.
#   * QR-35 스토우 자세의 왼손 그리퍼 아래 반경 0.14 m 비움 · QR-128 슬롯 0 상자의 근측 편향.
#
# 빠지는 규칙
#   * QR-21 (QR 면을 세계 -Y 로 조준) -- 이 생성기의 목적이 그것을 푸는 것이다.
#   * 정착 후 QR-62 (방위 -90 +-3 도) 검사 -- `taskC_check_rand.check_settled` 를 짝으로 쓴다.
#     원본 `taskC_check.check_settled` 로 검사하면 방위 때문에 끝없이 재딜된다.

import math
import random

import numpy as np

from . import taskC_deal as _Q
from . import taskC_layout as L
from . import taskC_products as P
# 원본과 같은 이름으로 다시 내보낸다 -- `except D.Infeasible` 같은 쓰는 쪽 코드가 두 모듈에서
# 똑같이 돈다. 특히 `Infeasible` 은 **같은 클래스**여야 원본을 잡던 except 가 이것도 잡는다.
from .taskC_deal import (FLIP_P, NEAR_BIAS, RECT_GAP, TRIES, GAP_TARGET, GRID_STEP,  # noqa: F401
                         Infeasible, axis_down_quat, flip_upright, gap_target, long_axis, mat_to_quat,
                         pick_products, pick_spot, quat_mul, quat_to_mat, rand_q, rect_gap, rotate,
                         upright_quat, yaw_quat)

SCENE_GEN = "rand"    # 장면 JSON 의 "scene_gen" 에 적는 이름


# --------------------------------------------------------------------------- 자세
def rand_yaw_pose(slug, rng):
    """원본 자세에 세계 z 둘레 무작위 요(-pi..pi, 균일)를 앞곱한 스폰 자세 (q, z).

    원본 `qr_right_pose` 를 **먼저** 같은 rng 로 부른다 -- 원통의 뒤집기, 상자의 캘리 자세 고르기가
    원본과 같은 난수 호출로 정해진다. 요는 그 다음 한 번 뽑는다. 원본에 QR 자세가 없으면
    (None, 0.0) 을 그대로 돌려주고, `deal` 이 원본과 같은 대체 규칙을 쓴다.
    """
    q0, z = _Q.qr_right_pose(slug, rng)
    if q0 is None:
        return None, 0.0
    psi = rng.uniform(-math.pi, math.pi)
    return quat_mul(yaw_quat(psi), q0), z


# --------------------------------------------------------------------------- 딜
def _foot(slug):
    return _Q._foot(slug)


def deal(seed, attempt, slugs):
    """attempt 번째 딜. 원본 `taskC_deal.deal` 과 같은 입력·출력 -- 자세만 `rand_yaw_pose` 다.

    돌려주는 것: [{slug, pos(로봇 좌표), quat(w,x,y,z)}], **slugs 순서 그대로** (슬롯 0 = 집을 상품).
    아래 본문은 원본 딜을 옮긴 것이고 바뀐 줄에는 `# rand:` 를 달았다.
    """
    rng = random.Random(f"{seed}-{attempt}-rand")        # rand: 원본 장면과 다른 난수 흐름
    in_x0, in_x1, in_y0, in_y1 = L.band_inner()
    placed = []
    by_slug = {}
    for slug in sorted(slugs, key=_foot, reverse=True):
        ext = np.array(P.size_mm(slug), dtype=float) / 1000.0
        es = sorted(float(v) for v in ext)
        q, z = rand_yaw_pose(slug, rng)                   # rand: QR 조준 대신 무작위 방위
        tumble = False
        if q is None:
            if P.is_cylinder(slug):
                q = upright_quat(slug, rng.uniform(-math.pi, math.pi))
                if rng.random() < FLIP_P:
                    q = flip_upright(q)
                z = L.COUNTER_TOP_Z + float(max(ext)) / 2 + 0.02
            else:
                q = rand_q(rng)
                z = L.COUNTER_TOP_Z + float(max(ext)) / 2 + 0.20
                tumble = True
        hw = np.abs(quat_to_mat(q)) @ (ext / 2.0)          # QR-80: 놓인 자세의 세계 반치수 (돌린 상자는 커진다)
        hx, hy = float(hw[0]), float(hw[1])
        if P.is_cylinder(slug):
            hx = hy = es[1] / 2.0
        elif tumble:
            hx = hy = math.hypot(es[2], es[1]) / 2.0
        if not RECT_GAP:
            hx = hy = math.hypot(hx, hy)
        x0, x1 = in_x0 + hx, in_x1 - hx
        y0, y1 = in_y0 + hy, in_y1 - hy
        if x1 <= x0 or y1 <= y0:
            print(f"[SCENE] {slug}: 반치수 {hx:.3f}x{hy:.3f} 가 띠 안에 안 들어감", flush=True)
            continue
        gx, gy = L.STOW_GRIP_XY
        near = NEAR_BIAS and slug == slugs[0] and not P.is_cylinder(slug)
        ym = y0 + 0.5 * (y1 - y0)
        xm = x0 + 0.67 * (x1 - x0)
        pos = pick_spot(rng, x0, x1, y0, y1, hx, hy, placed, (gx, gy), near, xm, ym,
                        gap_target(attempt))
        if pos is None:
            print(f"[SCENE] {slug}: 규칙을 지킬 자리가 없다 -- 다시 딜한다", flush=True)
            raise Infeasible(slug)
        placed.append((pos[0], pos[1], hx, hy))
        by_slug[slug] = dict(slug=slug, pos=(float(pos[0]), float(pos[1]), float(z)),
                             quat=tuple(float(v) for v in q))
    return [by_slug[s] for s in slugs if s in by_slug]
