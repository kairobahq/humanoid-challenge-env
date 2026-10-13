# Copyright 2025.
#
# 태스크 D 장면 규칙의 자기 시험. Isaac Sim 없이 돈다.
#
# 무엇을 지키는가 -- 다섯 가지이고, 전부 씨앗 전수로 센다:
#
#   1. **종속 랜덤**: 크레이트 상품 == 빈 자리가 생긴 열의 상품. 따로 뽑지 않는다
#   2. **빈 자리가 실제로 빈다**, 그리고 같은 열 뒷줄에 같은 상품이 있다 (한 개 모자란 진열)
#   3. 선반에 5 개, 전부 맨 위 판 (지워진 판에 서면 받쳐 주는 것이 없다)
#   4. 크레이트 상품이 크레이트 안, 바닥에 닿음, 림 아래
#   5. **배경 기물이 작업물과 겹치지 않는다** -- 운동학 고정이라 물리가 안 밀어낸다
#
# 더해서 같은 씨앗이 같은 장면을 내는지(재현), 다른 씨앗이 다른 장면을 내는지(변화)를 센다.
#
# 틀이 없다. 전역 `FAIL` 과 `check()` 뿐이고, 깨지면 종료코드 1 이다.
# 새 규칙을 넣거나 문턱을 고칠 때 **이 파일이 먼저 깨져야 한다.**
#
#     python3 scripts/taskD/selftest_taskD.py                # 씨앗 500
#     python3 scripts/taskD/selftest_taskD.py --seeds 2000

import argparse
import math

import taskD_clutter as CL
import taskD_crate as CR
import taskD_layout as L
import taskD_scene_seed as SD
import taskD_shelf as SH
import taskD_stock as ST

FAIL = []


def check(name, cond, detail=""):
    if not cond:
        FAIL.append("%s%s" % (name, (" -- " + detail) if detail else ""))


def main():
    ap = argparse.ArgumentParser(description="태스크 D 장면 규칙 자기 시험.")
    ap.add_argument("--seeds", type=int, default=500, help="볼 씨앗 수 (0 부터)")
    a = ap.parse_args()
    n = a.seeds

    print("[0] 고정 기하 -- 씨앗과 무관해야 한다")
    for s in SH.problems():
        check("선반 기하", False, s)
    boxes = L.work_boxes()
    check("작업물 상자 4 개", len(boxes) == 4, repr(sorted(boxes)))
    # 작업물끼리 겹치지 않는가.  책상과 크레이트는 겹치는 것이 정상(위에 올려 놓았다).
    pairs = (("robot", "shelf"), ("robot", "table"), ("table", "shelf"), ("crate", "shelf"),
             ("robot", "crate"))
    for p, q in pairs:
        b1, b2 = boxes[p], boxes[q]
        ox = min(b1[1], b2[1]) - max(b1[0], b2[0])
        oy = min(b1[3], b2[3]) - max(b1[2], b2[2])
        check("%s vs %s 겹침" % (p, q), not (ox > 0 and oy > 0),
              "x %+.0f mm, y %+.0f mm" % (ox * 1000, oy * 1000))
    # 크레이트가 책상 상판 안에 있는가
    tb, cb = boxes["table"], boxes["crate"]
    check("크레이트가 책상 안",
          tb[0] <= cb[0] and cb[1] <= tb[1] and tb[2] <= cb[2] and cb[3] <= tb[3],
          "책상 %s / 크레이트 %s" % (tb, cb))
    print("    선반까지 %.0f mm,  작업물 상자 %d 개" % (L.SHELF_GAP * 1000.0, len(boxes)))

    print("[1~5] 씨앗 0 ~ %d 전수" % (n - 1))
    scenes, rooms, gaps_worst, counts = set(), set(), [], []
    carried_hist, gapcol_hist = {}, {}
    for seed in range(n):
        spec = SD.spec(seed)
        ss, cs, ls = spec["shelf_seed"], spec["crate_seed"], spec["clutter_seed"]

        for s in ST.problems(ss):
            check("선반 seed %d" % seed, False, s)
        for s in CR.problems(ss, cs):
            check("크레이트 seed %d" % seed, False, s)
        for s in CL.problems(ls):
            check("배경 seed %d" % seed, False, s)

        # 종속: 크레이트 상품 == 빈 열 상품 (problems 안에서도 보지만 여기서 한 번 더 센다)
        cols, empty = ST.layout(ss)
        (gl, gs), = empty
        want = cols[(gl, gs % ST.COLS)]
        got = CR.poses(ss, cs)[0][0]
        check("종속 seed %d" % seed, got == want, "크레이트 %s, 빈 열 %s" % (got, want))

        items = ST.stock(ss)
        scenes.add(tuple(sorted((nm, round(p[0], 4), round(p[1], 4)) for nm, p, _l, _s in items))
                   + (got,))
        room = CL.scatter(ls)
        rooms.add(tuple(sorted((nm, round(cx, 2), round(cy, 2)) for nm, _p, (cx, cy), _y in room)))
        counts.append(len(room))
        g = CL.clearances(ls)
        if g:
            gaps_worst.append(min(x[2] for x in g))
        carried_hist[got] = carried_hist.get(got, 0) + 1
        gapcol_hist[gs] = gapcol_hist.get(gs, 0) + 1

    check("장면이 전부 다름", len(scenes) > n * 0.8, "%d / %d" % (len(scenes), n))
    check("방이 전부 다름", len(rooms) > n * 0.8, "%d / %d" % (len(rooms), n))
    check("배경 여유가 전부 양수", min(gaps_worst) > 0, "최악 %.0f mm" % (min(gaps_worst) * 1000))
    check("빈 열이 고르게 흩어짐", min(gapcol_hist.values()) > n / ST.COLS * 0.7,
          repr(dict(sorted(gapcol_hist.items()))))

    print("    서로 다른 장면 %d / %d,  서로 다른 방 %d / %d" % (len(scenes), n, len(rooms), n))
    print("    배경 여유 최악 %.0f mm,  가운데값 %.0f mm"
          % (min(gaps_worst) * 1000.0, sorted(gaps_worst)[len(gaps_worst) // 2] * 1000.0))
    print("    기물 수 %d ~ %d (평균 %.1f)" % (min(counts), max(counts), sum(counts) / len(counts)))
    print("    빈 열 분포 %s" % dict(sorted(gapcol_hist.items())))
    print("    크레이트 상품 %s" % dict(sorted(carried_hist.items(), key=lambda kv: -kv[1])))

    print("[6] 재현")
    for seed in (0, 7, 1000, 20260805):
        s = SD.spec(seed)
        check("씨앗 %d 재현" % seed,
              SD.spec(seed) == s
              and ST.stock(s["shelf_seed"]) == ST.stock(s["shelf_seed"])
              and CR.poses(s["shelf_seed"], s["crate_seed"])
              == CR.poses(s["shelf_seed"], s["crate_seed"])
              and CL.scatter(s["clutter_seed"]) == CL.scatter(s["clutter_seed"]))

    print()
    if FAIL:
        print("판정: %d 건" % len(FAIL))
        for f in FAIL[:20]:
            print("  ! %s" % f)
        if len(FAIL) > 20:
            print("  ... %d 건 더" % (len(FAIL) - 20))
        raise SystemExit(1)
    print("판정: 문제 없음")


if __name__ == "__main__":
    main()
