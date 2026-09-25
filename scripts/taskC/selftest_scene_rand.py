# Copyright 2026.
#
# 랜덤 방위 씬 생성기(`taskC_deal_rand`)와 생성기 선택기(`taskC_scene_gen`)의 자체 시험.
# Isaac 없이 돈다 -- 상품 치수·QR 타일 법선만 에셋에서 읽는다.
#
#     cd scripts && TASKC_ASSETS=<에셋 뿌리> python3 -m taskC.selftest_scene_rand [--seeds 300]
#
# 보는 것 (하나라도 어긋나면 종료 코드 1)
#   1. 선택기: auto 는 회차(시드 % 3) 0·1 -> qr_right, 2 -> rand. qr_right 는 원본 모듈 그대로.
#   2. 접촉면 불변: 같은 난수로 뽑은 원본 자세와 rand 자세는 **세계 z 성분이 같다**
#      (회전 행렬의 셋째 행 = 상품 각 축의 세계 z 성분 -> 어느 면이 바닥에 닿는지와 높이가 같다).
#   3. 방위 분포: QR 타일 법선의 세계 방위가 360 도 전체에 퍼진다 (45 도 구간 8 개 모두 5 % 이상).
#   4. 자리 규칙: 띠 안쪽 · 상품 표면-표면 >= MIN_GAP · 스토우 그리퍼 반경 밖 (딜이 쓰는 반치수로 잰다).
#   5. 딜 성공: 모든 시드가 MAX_REDEAL 안에 딜된다 (원본 생성기와 성공률을 나란히 찍는다).
#   6. 정착 검사: `taskC_check_rand` 는 QR 방위 말고는 원본과 판정이 같고, rand 장면은 원본 검사의
#      QR 방위에 걸리며, 재딜로 통과 판을 찾는 비율이 원본과 비슷하다 (원본 대비 5 %p 안).

import argparse
import math
import random
import sys

import numpy as np

from . import taskC_check as K
from . import taskC_deal as D
from . import taskC_layout as L
from . import taskC_products as P

FAIL = []


def check(name, ok, detail=""):
    print("  %s %s %s" % ("ok  " if ok else "FAIL", name, detail), flush=True)
    if not ok:
        FAIL.append(name)


def deal_until_ok(mod, seed, slugs):
    """데모처럼 Infeasible 이면 다음 attempt 로. (attempt, 결과) 또는 (None, None)."""
    for a in range(L.MAX_REDEAL):
        try:
            return a, mod.deal(seed, a, slugs)
        except mod.Infeasible:
            continue
    return None, None


def half_xy(slug, q):
    """딜이 자리 규칙에 쓰는 세계 반치수 (원통은 지름/2, 상자는 돌린 AABB)."""
    ext = np.array(P.size_mm(slug), dtype=float) / 1000.0
    if P.is_cylinder(slug):
        r = sorted(float(v) for v in ext)[1] / 2.0
        return r, r
    hw = np.abs(D.quat_to_mat(q)) @ (ext / 2.0)
    return float(hw[0]), float(hw[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=300)
    a = ap.parse_args()

    from . import taskC_check_rand as KR
    from . import taskC_deal_rand as DR
    from . import taskC_scene_gen as SG

    print("[1] 선택기")
    check("auto 회차 0 -> qr_right", SG.resolve("auto", 0) == "qr_right")
    check("auto 회차 1 -> qr_right", SG.resolve("auto", 1) == "qr_right")
    check("auto 회차 2 -> rand", SG.resolve("auto", 2) == "rand")
    check("auto 시드 1000 (회차 1) -> qr_right", SG.resolve("auto", 1000) == "qr_right")
    check("auto 시드 1001 (회차 2) -> rand", SG.resolve("auto", 1001) == "rand")
    check("명시 모드는 시드와 무관", SG.resolve("qr_right", 2) == "qr_right" and SG.resolve("rand", 0) == "rand")
    check("qr_right 는 원본 모듈", SG.modules("qr_right") == (D, K))
    check("rand 는 새 모듈", SG.modules("rand") == (DR, KR))
    check("Infeasible 은 같은 클래스", DR.Infeasible is D.Infeasible)
    try:
        SG.resolve("nope", 0)
        check("모르는 모드는 거부", False)
    except ValueError:
        check("모르는 모드는 거부", True)

    print("[2] 접촉면 불변 (같은 난수 -> 세계 z 성분 동일)")
    worst = 0.0
    n_pose = 0
    for slug in sorted(P.PRODUCTS):
        for s in range(40):
            q0, z0 = D.qr_right_pose(slug, random.Random("pose-%d" % s))
            q1, z1 = DR.rand_yaw_pose(slug, random.Random("pose-%d" % s))
            if q0 is None:
                check("%s: 원본에 QR 자세 없음 -> rand 도 없음" % slug, q1 is None)
                break
            r0, r1 = D.quat_to_mat(q0)[2, :], D.quat_to_mat(q1)[2, :]
            worst = max(worst, float(np.abs(r0 - r1).max()), abs(z0 - z1))
            n_pose += 1
    check("바닥면·높이 동일 (%d 자세)" % n_pose, worst < 1e-9, "최대차 %.2e" % worst)

    print("[3][4][5] 딜 %d 시드" % a.seeds)
    in_x0, in_x1, in_y0, in_y1 = L.band_inner()
    gx, gy = L.STOW_GRIP_XY
    bins = np.zeros(8, dtype=int)
    ok_r = ok_o = 0
    bad_rule = []
    samples = []
    for seed in range(a.seeds):
        slugs = D.pick_products(seed)
        check_o, _ = deal_until_ok(D, seed, slugs)
        ok_o += check_o is not None
        att, res = deal_until_ok(DR, seed, slugs)
        if res is None:
            bad_rule.append("시드 %d 딜 실패" % seed)
            continue
        ok_r += 1
        check_slugs = [d["slug"] for d in res] == slugs
        if not check_slugs:
            bad_rule.append("시드 %d 순서" % seed)
        boxes = []
        for d in res:
            slug, (x, y, z), q = d["slug"], d["pos"], d["quat"]
            hx, hy = half_xy(slug, q)
            if not (x - hx >= in_x0 - 1e-9 and x + hx <= in_x1 + 1e-9 and y - hy >= in_y0 - 1e-9 and y + hy <= in_y1 + 1e-9):
                bad_rule.append("시드 %d %s 띠 밖" % (seed, slug))
            if D.rect_gap(x, y, hx, hy, gx, gy, 0.0, 0.0) < L.STOW_GRIP_CLEAR - 1e-9:
                bad_rule.append("시드 %d %s 그리퍼 아래" % (seed, slug))
            for (bx, by, bhx, bhy, bs) in boxes:
                g = D.rect_gap(x, y, hx, hy, bx, by, bhx, bhy)
                if g < L.MIN_GAP - 1e-9:
                    bad_rule.append("시드 %d %s-%s 간격 %.3f" % (seed, slug, bs, g))
            boxes.append((x, y, hx, hy, slug))
            try:
                n = D.quat_to_mat(q) @ np.asarray(P.tile_normal(slug), dtype=float)
                if math.hypot(n[0], n[1]) > 0.3:
                    az = math.degrees(math.atan2(n[1], n[0])) % 360.0
                    bins[int(az // 45.0) % 8] += 1
            except KeyError:
                pass
        if len(samples) < 12:
            samples.append((seed, att, res))
    print("  딜 성공: rand %d/%d, 원본 %d/%d" % (ok_r, a.seeds, ok_o, a.seeds))
    check("모든 시드 딜 성공 (rand)", ok_r == a.seeds)
    check("자리 규칙 (띠·간격·그리퍼)", not bad_rule, "; ".join(bad_rule[:5]))
    tot = int(bins.sum())
    print("  QR 방위 45 도 구간별 개수:", bins.tolist())
    check("방위 360 도 분포 (구간마다 5 % 이상)", tot > 0 and bins.min() >= 0.05 * tot,
          "최소 %.1f %%" % (100.0 * bins.min() / max(tot, 1)))

    print("[6] 정착 검사")
    # (a) 방위 검사 말고는 원본과 같은가: QR 정 오른쪽 장면(방위 오차 0)에서는 두 검사가 판마다 같아야 한다.
    same = True
    n_o = min(a.seeds, 60)
    for seed in range(n_o):
        _, res = deal_until_ok(D, seed, D.pick_products(seed))
        ent = [dict(slug=d["slug"], pos=list(d["pos"]), quat=list(d["quat"])) for d in res]
        ok_o_, ro = K.check_settled([dict(e) for e in ent])
        ok_r_, rr = KR.check_settled([dict(e) for e in ent])
        keys = ("inside", "sunk", "upright", "qr_up", "gap_min")
        same = same and ok_o_ == ok_r_ and all(x[k] == y[k] for x, y in zip(ro, rr) for k in keys)
    check("방위 외 판정은 원본과 동일 (정 오른쪽 장면 %d 판)" % n_o, same)
    # (b) rand 장면은 원본 검사에 QR 방위로 걸린다 -- rand 검사에서 뺀 것이 그 검사다.
    n_az = 0
    for seed, att, res in samples:
        ent = [dict(slug=d["slug"], pos=list(d["pos"]), quat=list(d["quat"])) for d in res]
        _, ro = K.check_settled(ent)
        n_az += any(r.get("qr_az_err", 0.0) > L.QR_AZ_TOL_DEG for r in ro)
    check("rand 장면은 원본 검사의 QR 방위에 걸린다 (%d/%d 판)" % (n_az, len(samples)), n_az == len(samples))
    # (c) 재딜로 통과 판을 찾는 비율이 원본과 비슷한가. 데모는 정착 뒤 검사에 걸리면 다음 attempt 로
    #     재딜한다(최대 MAX_REDEAL). 딜은 원통을 지름/2 로, 검사는 돌린 AABB 로 재서 스폰 자세 그대로는
    #     원본도 자주 걸린다 -- 그래서 절대값이 아니라 **원본 대비**로 본다 (스폰 자세를 정착 자세로 본 근사).
    def first_pass(mod, kk, seed):
        slugs = D.pick_products(seed)
        for at in range(L.MAX_REDEAL):
            try:
                res = mod.deal(seed, at, slugs)
            except mod.Infeasible:
                continue
            ok_, rr_ = kk.check_settled([dict(slug=d["slug"], pos=list(d["pos"]), quat=list(d["quat"])) for d in res])
            if ok_ or kk.fail_open_ok(rr_):
                return at
        return None
    n_c = min(a.seeds, 100)
    p_o = sum(first_pass(D, K, s) is not None for s in range(n_c))
    p_r = sum(first_pass(DR, KR, s) is not None for s in range(n_c))
    check("재딜 %d 회 안 통과: rand %d/%d, 원본 %d/%d" % (L.MAX_REDEAL, p_r, n_c, p_o, n_c), p_r >= p_o - 0.05 * n_c)

    print("SELFTEST_%s" % ("OK" if not FAIL else "FAIL: " + ", ".join(FAIL)))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
