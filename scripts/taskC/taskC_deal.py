# Copyright 2026.
#
# seed 하나가 정하는 것: 계산대 위 상품 3 종과 그 스폰 자세·자리. 대회 환경 저장소
# `taskC/qr_scene.py` 의 `deal()` / `_qr_right_pose()` 를 Isaac 없이 돌게 옮긴 것이다.
# 규칙 번호(QR-xx, V4-xx)는 원본의 것이고, 난수 호출 순서까지 원본과 같아서 같은 seed·같은
# 상품이면 같은 자리와 자세가 나온다.
#
# 규칙 요약
#   * 상품 3 종: slugs[0] 이 집을 상품(슬롯 0), 나머지 둘은 배경. seed 로 뽑거나 --products 로 준다.
#   * QR-21: 모든 상품의 QR 면 법선이 세계 -Y(정 오른쪽)를 향하도록 요를 조준한다.
#   * V4-32: 원통은 직립. 반은 뒤집어 세운다(윗면이 바닥). 옆으로 눕는 것은 없다.
#   * QR-73/81: 상자는 허용된 바닥면으로 **눕혀** 놓는다(긴 축이 위로 서지 않는다).
#   * QR-11/81: 빨간 띠 안쪽(테이프 제외)에, 상품 표면-표면 >= 10 cm (축정렬 사각형으로 잰다).
#   * QR-35: 스토우 자세의 왼손 그리퍼 아래(로봇 좌표 (0.19, 0.30), 반경 0.14) 에는 놓지 않는다.
#   * QR-128: 슬롯 0 이 상자면 앞 400 시도를 로봇 근측(y 하위 절반, x 하위 2/3)으로 편향한다.
#
# 자리·자세는 **로봇 좌표**다(taskC_layout 참조). 세계 좌표로 옮기는 것은 데모 스크립트가 한다.

import math
import random

import numpy as np

from . import taskC_layout as L
from . import taskC_products as P

FLIP_P = 0.5        # V4-32: 원통을 뒤집어 세울 확률 (원본 TASKC_FLIP_P 기본값)
RECT_GAP = True     # QR-81: 간격을 원이 아니라 축정렬 사각형으로 잰다
NEAR_BIAS = True    # QR-128: 슬롯 0 상자의 근측 편향
TRIES = 800         # 자리 뽑기 시도 수 (원본과 동일)


# --------------------------------------------------------------------------- 쿼터니언 도구
def rotate(q, v):
    """q * v * q^-1. (w, x, y, z)."""
    w, x, y, z = q
    return ((1 - 2 * (y * y + z * z)) * v[0] + 2 * (x * y - w * z) * v[1] + 2 * (x * z + w * y) * v[2],
            2 * (x * y + w * z) * v[0] + (1 - 2 * (x * x + z * z)) * v[1] + 2 * (y * z - w * x) * v[2],
            2 * (x * z - w * y) * v[0] + 2 * (y * z + w * x) * v[1] + (1 - 2 * (x * x + y * y)) * v[2])


def quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                     w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def quat_to_mat(q):
    """(w,x,y,z) -> 3x3."""
    w, x, y, z = (float(v) for v in q)
    n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def mat_to_quat(R):
    """회전행렬 -> (w,x,y,z). 4 분기 Shepperd -- trace 한 갈래만 쓰면 180 도 회전이 퇴화한다(QR-61)."""
    t = float(np.trace(R))
    if t > 0:
        s2 = math.sqrt(t + 1.0) * 2
        return np.array([0.25 * s2, (R[2, 1] - R[1, 2]) / s2,
                         (R[0, 2] - R[2, 0]) / s2, (R[1, 0] - R[0, 1]) / s2])
    if R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s2 = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        return np.array([(R[2, 1] - R[1, 2]) / s2, 0.25 * s2,
                         (R[0, 1] + R[1, 0]) / s2, (R[0, 2] + R[2, 0]) / s2])
    if R[1, 1] > R[2, 2]:
        s2 = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        return np.array([(R[0, 2] - R[2, 0]) / s2, (R[0, 1] + R[1, 0]) / s2,
                         0.25 * s2, (R[1, 2] + R[2, 1]) / s2])
    s2 = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
    return np.array([(R[1, 0] - R[0, 1]) / s2, (R[0, 2] + R[2, 0]) / s2,
                     (R[1, 2] + R[2, 1]) / s2, 0.25 * s2])


def rand_q(rng):
    """균일 랜덤 쿼터니언 (w, x, y, z)."""
    u1, u2, u3 = rng.random(), rng.random(), rng.random()
    a, b = math.sqrt(1 - u1), math.sqrt(u1)
    t2, t3 = 2 * math.pi * u2, 2 * math.pi * u3
    return np.array([b * math.cos(t3), a * math.sin(t2), a * math.cos(t2), b * math.sin(t3)])


def yaw_quat(yaw):
    return np.array([math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)])


def axis_down_quat(axis_key, yaw):
    """V4-113: 상품 축(±X/±Y/±Z)이 세계 아래(-Z)를 향하는 기본자세 + 세계 Z 요."""
    ax = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0),
          "-Y": (0, -1, 0), "+Z": (0, 0, 1), "-Z": (0, 0, -1)}[axis_key]
    d = (0.0, 0.0, -1.0)
    dot = ax[0] * d[0] + ax[1] * d[1] + ax[2] * d[2]
    if dot > 0.9999:
        qb = np.array([1.0, 0.0, 0.0, 0.0])
    elif dot < -0.9999:
        qb = np.array([0.0, 1.0, 0.0, 0.0])
    else:
        cx = ax[1] * d[2] - ax[2] * d[1]
        cy = ax[2] * d[0] - ax[0] * d[2]
        cz = ax[0] * d[1] - ax[1] * d[0]
        n = math.sqrt(cx * cx + cy * cy + cz * cz)
        ang = math.acos(max(-1.0, min(1.0, dot)))
        sh, ch = math.sin(ang / 2), math.cos(ang / 2)
        qb = np.array([ch, sh * cx / n, sh * cy / n, sh * cz / n])
    return quat_mul(yaw_quat(yaw), qb)


def long_axis(slug):
    """원통의 회전축 = 지름 두 축(근사 동일)이 아닌 나머지 축 (수리 31호-b)."""
    e = [float(v) for v in P.size_mm(slug)]
    pairs = [(abs(e[0] - e[1]), 2), (abs(e[1] - e[2]), 0), (abs(e[0] - e[2]), 1)]
    return min(pairs)[1]


def upright_quat(slug, yaw):
    """원통의 회전축을 세로로 세우는 자세 + 요."""
    qyaw = yaw_quat(yaw)
    la = long_axis(slug)
    if la == 2:
        return qyaw
    h = math.pi / 4
    qup = (np.array([math.cos(h), 0.0, math.sin(h), 0.0]) if la == 0
           else np.array([math.cos(h), math.sin(h), 0.0, 0.0]))
    return quat_mul(qyaw, qup)


def flip_upright(q):
    """V4-32: 직립 자세를 x 축 180 도 돌려 뒤집어 세운다 ((0,1,0,0) ⊗ q)."""
    return np.array([-q[1], q[0], -q[3], q[2]])


def rect_gap(ax, ay, ahx, ahy, bx, by, bhx, bhy):
    """축정렬 두 사각형의 표면-표면 거리 (겹치면 0)."""
    dx = max(0.0, abs(ax - bx) - (ahx + bhx))
    dy = max(0.0, abs(ay - by) - (ahy + bhy))
    return math.hypot(dx, dy)


# --------------------------------------------------------------------------- 자세
def _vis_entry(slug):
    """V4-101: 렌더 실측 캘리(_qr_tiles_vis.json)의 항목. 없으면 {}."""
    return P.optional_json("_qr_tiles_vis.json").get(slug, {}) or {}


def qr_right_pose(slug, rng):
    """QR 면이 세계 -Y 를 정확히 보는 스폰 자세 (q, z). 면 정보가 없으면 (None, 0.0).

    원본 `_qr_right_pose`. 원통: 직립(V4-32 로 반은 뒤집음) + 타일 법선을 조준하는 요.
    상자: 캘리 등록 자세(V4-110)가 있으면 그중 하나, 없으면 축정렬 24 자세 중 타일 법선이
    수평이고 바닥면이 허용된(QR-73b) 것 가운데 바닥이 가장 넓은 자세를 골라 조준한다.
    """
    ext_mm = [float(v) for v in P.size_mm(slug)]
    try:
        tn = list(P.tile_normal(slug))
    except KeyError:
        return None, 0.0
    tgt = math.radians(L.QR_TARGET_YAW_DEG)
    vis = _vis_entry(slug)
    va = vis.get("vis_az_deg")
    if va is not None and not isinstance(va, dict):
        tn = [math.cos(math.radians(float(va))), math.sin(math.radians(float(va))), 0.0]
    taz = math.atan2(tn[1], tn[0])
    top = L.COUNTER_TOP_Z

    def _h_m(v):
        return v / 1000.0 if max(ext_mm) > 10 else v

    if P.is_cylinder(slug):
        flip = rng.random() < FLIP_P
        qb = upright_quat(slug, 0.0)
        if flip:
            qb = flip_upright(qb)
        if isinstance(va, dict):                      # V4-107b: 자세별 캘리
            vp = va.get("flip" if flip else "up")
            if vp is not None:
                tn = [math.cos(math.radians(float(vp))), math.sin(math.radians(float(vp))), 0.0]
                taz = math.atan2(tn[1], tn[0])
        nrt = rotate(tuple(qb), tuple(tn))
        if math.hypot(nrt[0], nrt[1]) >= 0.35:
            yw = tgt - math.atan2(nrt[1], nrt[0])
            q = quat_mul(yaw_quat(yw), qb)
            return q, top + _h_m(max(ext_mm)) / 2.0 + 0.02
        return None, 0.0

    # 상자
    poses = vis.get("poses")
    if isinstance(poses, dict) and poses:
        keys = sorted(poses.keys())
        k = keys[rng.randrange(len(keys))]
        q = axis_down_quat(k, math.radians(float(poses[k])))
        ax = {"X": 0, "Y": 1, "Z": 2}[k[1]]
        return q, top + _h_m(ext_mm[ax]) / 2.0 + 0.02
    sf = P.optional_json("_spawn_faces.json").get(slug) or {}
    allow = set(sf.get("allow", [])) if sf.get("shape") in ("box", "oct8") else None
    axes = [np.array(v, dtype=float) for v in
            [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]]
    down = np.array([0.0, 0.0, -1.0])
    best = None
    n = np.asarray(tn, dtype=float)
    for xw in axes:
        for zw in axes:
            if abs(float(np.dot(xw, zw))) > 1e-6:
                continue
            yw = np.cross(zw, xw)
            R = np.stack([xw, yw, zw], axis=1)       # 열 = 상품축의 세계 방향
            nw = R @ n
            if abs(nw[2]) > 0.05:                    # QR-73: 타일 법선이 수평이어야 조준 가능
                continue
            if allow is not None:                    # QR-73b/d: 바닥에 닿는 면은 허용 목록에서
                dn0 = int(np.argmax(np.abs(R.T @ down)))
                sgn = "+" if float((R.T @ down)[dn0]) > 0 else "-"
                if f"{sgn}{'XYZ'[dn0]}" not in allow:
                    continue
            dn = int(np.argmax(np.abs(R.T @ down)))
            dims = [_h_m(v) for v in ext_mm]
            support = 1.0
            for i in range(3):
                if i != dn:
                    support *= dims[i]
            if best is None or support > best[0]:
                best = (support, R, nw, dn, dims)
    if best is None:
        return None, 0.0
    _, R, nw, dn, dims = best
    psi = tgt - math.atan2(nw[1], nw[0])
    q = quat_mul(yaw_quat(psi), mat_to_quat(R))
    return q, top + dims[dn] / 2.0 + 0.02


# --------------------------------------------------------------------------- 딜
def pick_products(seed, products=None):
    """상품 3 종. products 가 있으면 그대로(코드용 이름, 쉼표), 없으면 seed 로 8 종에서 뽑는다."""
    if products:
        out = [s for s in products.split(",") if s]
        for s in out:
            if s not in P.PRODUCTS:
                raise ValueError(f"모르는 상품: {s} (8 종: {', '.join(P.PRODUCTS)})")
        return out
    return random.Random(f"{seed}-products").sample(sorted(P.PRODUCTS), 3)


def _foot(slug):
    es = sorted(float(v) / 1000.0 for v in P.size_mm(slug))
    return es[1] * es[1] if P.is_cylinder(slug) else es[2] * es[1]


def deal(seed, attempt, slugs):
    """attempt 번째 딜. 돌려주는 것: [{slug, pos(로봇 좌표), quat(w,x,y,z)}] -- **slugs 순서 그대로**.

    QR-81b: 바닥 면적이 큰 것부터 자리를 잡지만 결과 순서는 바꾸지 않는다(슬롯 0 = 집을 상품).
    """
    rng = random.Random(f"{seed}-{attempt}")
    in_x0, in_x1, in_y0, in_y1 = L.band_inner()
    placed = []
    by_slug = {}
    for slug in sorted(slugs, key=_foot, reverse=True):
        ext = np.array(P.size_mm(slug), dtype=float) / 1000.0
        es = sorted(float(v) for v in ext)
        q, z = qr_right_pose(slug, rng)
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
        hw = np.abs(quat_to_mat(q)) @ (ext / 2.0)          # QR-80: 놓인 자세의 세계 반치수
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
        pos = None
        for t in range(TRIES):
            if near and t < TRIES // 2:
                x = rng.uniform(x0, min(xm, x1))
                y = rng.uniform(y0, min(ym, y1))
            else:
                x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
            if rect_gap(x, y, hx, hy, gx, gy, 0.0, 0.0) < L.STOW_GRIP_CLEAR:
                continue
            if all(rect_gap(x, y, hx, hy, px, py, phx, phy) >= L.MIN_GAP
                   for px, py, phx, phy in placed):
                pos = (x, y)
                break
        if pos is None:
            print(f"[SCENE] {slug}: 간격 10cm 만족 위치 실패 ({TRIES} 시도) -- 재딜 유도", flush=True)
            pos = (rng.uniform(x0, x1), rng.uniform(y0, y1))     # 정착 검사가 기각한다
        placed.append((pos[0], pos[1], hx, hy))
        by_slug[slug] = dict(slug=slug, pos=(float(pos[0]), float(pos[1]), float(z)),
                             quat=tuple(float(v) for v in q))
    return [by_slug[s] for s in slugs if s in by_slug]
