# Copyright 2026.
#
# 트레이스와 채점 결과가 스스로 모순되지 않는지 본다. 시뮬 없이 몇 초에 돈다.
#
# 채점기를 고칠 때마다 이것을 돌린다. 재생을 다시 돌릴 필요가 없다 --
# 트레이스는 고정된 기록이고, 여기서 걸리는 것은 전부 트레이스나 채점기의 문제다.
#
#     python check_trace.py <trace 폴더>
#
# 검사는 두 갈래다. 트레이스 자체의 무결성과, 채점 결과가 트레이스와 맞는가.

import json
import math
import os
import sys

FAIL = []
OKN = [0]


def ck(name, cond, detail=""):
    if cond:
        OKN[0] += 1
    else:
        FAIL.append((name, detail))


def load(d):
    tr = [json.loads(l) for l in open(os.path.join(d, "trace.jsonl"), encoding="utf-8") if l.strip()]
    sc = json.load(open(os.path.join(d, "scene.json"), encoding="utf-8"))
    de = json.load(open(os.path.join(d, "decode.json"), encoding="utf-8"))
    return tr, sc, de


def check_trace(tr, sc, de):
    n = len(tr)
    ck("프레임이 있다", n > 0, "0 줄")
    if not n:
        return

    # 시간 -- 단조 증가이고 30 Hz 에 맞아야 한다
    ts = [r["t"] for r in tr]
    ck("시각이 단조 증가", all(b >= a for a, b in zip(ts, ts[1:])),
       "역행 %d 곳" % sum(1 for a, b in zip(ts, ts[1:]) if b < a))
    dur = ts[-1] - ts[0]
    ck("길이가 30Hz 와 맞다", abs(dur - (n - 1) / 30.0) < 0.5,
       "%d 프레임인데 %.1f 초 (30Hz 라면 %.1f 초)" % (n, dur, (n - 1) / 30.0))

    # 슬롯 -- 판에 등장한 슬롯만큼 상품이 처리된다
    slots = sorted({r["slot"] for r in tr if r["slot"] >= 0})
    ck("슬롯이 관측된다", bool(slots), "전부 -1")
    ck("슬롯이 상품 수를 안 넘는다", not slots or max(slots) < len(sc["products"]),
       "슬롯 %s, 상품 %d개" % (slots, len(sc["products"])))

    # 좌표계 -- 상품이 띠 근처에 있어야 한다 (로봇 좌표)
    b = sc["band"]
    p0 = tr[0]["products"][0]["pos"]
    ck("상품이 로봇 좌표다", b[0] - 0.3 <= p0[0] <= b[1] + 0.3 and b[2] - 0.3 <= p0[1] <= b[3] + 0.3,
       "첫 상품 %s, 띠 %s -- 세계 좌표를 넣지 않았는가" % ([round(v, 3) for v in p0], b))

    # 속도 -- 첫 프레임은 정지
    v0 = tr[0]["products"][0]["vel"]
    ck("첫 프레임 속도가 0", max(abs(v) for v in v0) < 0.05,
       "%s -- 벡터를 점 변환하지 않았는가" % [round(v, 3) for v in v0])

    # 빔 -- 방향이 단위벡터
    bd = tr[0]["bd"]
    ck("빔 방향이 단위벡터", abs(math.sqrt(sum(v * v for v in bd)) - 1.0) < 0.05,
       "|bd| = %.3f" % math.sqrt(sum(v * v for v in bd)))

    # 빔 -- 대상에 가장 가까워지는 순간이 판독 시점과 맞아야 한다
    for d in de.get("decode", []):
        i = min(int(d["frame"]), n - 1)
        row = tr[i]
        ck("판독 프레임의 슬롯이 맞다", row["slot"] == d["slot"],
           "판독 슬롯 %s 인데 트레이스 슬롯 %s (f%d)" % (d["slot"], row["slot"], d["frame"]))

    # 그리퍼 -- 명령과 실측이 둘 다 있고, 판 안에서 닫힘이 관측된다
    ck("그리퍼 명령이 있다", any(r["grip_cmd"] > 0.1 for r in tr), "닫힘 명령이 한 번도 없다")
    ck("빈손 닫힘을 쟀다", de.get("q_free_close") is not None, "q_free_close 미측정")

    # 빈손 닫힘은 파지 중 관절값보다 **커야** 한다. 물체를 물면 덜 닫히기 때문이다.
    qf = de.get("q_free_close")
    if qf is not None:
        qmax = max(r["grip_q"] for r in tr)
        ck("빈손 닫힘이 파지 중보다 크다", qf >= qmax - 1e-6,
           "빈손 %.4f < 파지 중 최대 %.4f -- 측정이 끝까지 안 닫힌 것" % (qf, qmax))


def check_qr(sc, de):
    """이미지 판독기가 규칙대로 돌았는가. 켜고 돌린 판에서만 본다."""
    qr = de.get("qr")
    if not qr:
        return
    recs = [d for d in de.get("decode", []) if d.get("ok")]
    for d in recs:
        ck("판독은 그림으로: %s" % d.get("slug"), d.get("by") == "image",
           "by=%r -- 기하 판정이 점수로 새어 들어갔다" % (d.get("by"),))
        ck("읽힌 문자열이 있다: %s" % d.get("slug"), bool(d.get("text")))
    # 판독 창 밖에서 셔터가 눌리지 않았는가. 기본값은 qr_decode.py 와 같다 (2026-09-16 횡이탈 60 · 축거리 40~150).
    lim = float(qr.get("lat_max_mm") or 60.0)
    dlo = float(qr.get("d_min_mm") or 40.0)
    dhi = float(qr.get("d_max_mm") or 150.0)
    for d in recs:
        ck("판독 창 안에서 읽었다: %s" % d.get("slug"),
           float(d.get("lat_mm", 1e9)) <= lim + 1e-6,
           "횡이탈 %.1fmm > 창 %.1fmm" % (float(d.get("lat_mm", -1)), lim))
        ck("판독 거리가 창 안이다: %s" % d.get("slug"),
           dlo - 1e-6 <= float(d.get("dist_mm", -1)) <= dhi + 1e-6,
           "축거리 %.0fmm 가 %.0f~%.0fmm 밖" % (float(d.get("dist_mm", -1)), dlo, dhi))
    # 냉각. 같은 상품을 냉각 시간 안에 두 번 읽었으면 점수가 부풀 여지가 생긴다.
    cd = float(qr.get("cooldown_s") or 5.0)
    by_slot = {}
    for d in recs:
        by_slot.setdefault(d.get("slot"), []).append(float(d.get("frame", 0)) / 30.0)
    for sl, ts in by_slot.items():
        ts.sort()
        gap = min((b - a for a, b in zip(ts, ts[1:])), default=None)
        ck("냉각을 지켰다: 슬롯 %s" % sl, gap is None or gap >= cd - 1e-6,
           "%.2f초 간격 -- 냉각 %.0f초보다 짧다" % (gap or 0.0, cd))
    # 읽힌 값이 그 상품의 코드인가. 재생기가 이미 견주지만 기록으로 다시 본다.
    for d in recs:
        want = (sc.get("products", [])[int(d["slot"])].get("code")
                if d.get("slot") is not None and int(d["slot"]) < len(sc.get("products", []))
                else None)
        if want is not None and d.get("text") is not None:
            ck("읽힌 코드가 그 상품 것이다: %s" % d.get("slug"), str(want) == str(d["text"]),
               "읽힘 %s != 기대 %s" % (d["text"], want))


def check_score(rep, tr, sc):
    slots = sorted({r["slot"] for r in tr if r["slot"] >= 0})
    handled = {sc["products"][s]["slug"] for s in slots}
    for p in rep["products"]:
        got = p["points"]
        if p["slug"] not in handled:
            ck("처리 안 한 상품은 0점: %s" % p["slug"], got == 0.0, "%.1f점" % got)
        # 항목 사이의 앞뒤 관계
        it = p["items"]
        if it["sub1_2_lift"]["pass"] is True:
            ck("들었으면 쥐었다: %s" % p["slug"], it["sub1_1_grip"]["pass"] is True)
        if it["sub2_2_decode"]["pass"] is True:
            ck("읽었으면 향했다: %s" % p["slug"], it["sub2_1_aim"]["pass"] is True)
            ck("읽었으면 들었다: %s" % p["slug"], it["sub1_2_lift"]["pass"] is True)
        if it["sub3_place"]["pass"] is True:
            ck("놓았으면 읽었다: %s" % p["slug"], it["sub2_2_decode"]["pass"] is True)
        # 시각 순서
        tg, tl = it["sub1_1_grip"]["t"], it["sub1_2_lift"]["t"]
        if tg is not None and tl is not None:
            ck("쥔 시각 <= 든 시각: %s" % p["slug"], tg <= tl + 1e-6,
               "쥠 t=%.2f, 듦 t=%.2f" % (tg, tl))
    # 상품마다 쥔 시각이 달라야 한다 (하나씩 처리하는 판이다)
    tgs = [p["items"]["sub1_1_grip"]["t"] for p in rep["products"]
           if p["items"]["sub1_1_grip"]["t"] is not None]
    ck("상품별 쥔 시각이 다르다", len(set(round(v, 2) for v in tgs)) == len(tgs),
       "시각 %s -- 슬롯이 안 갈리는가" % [round(v, 2) for v in tgs])


def main(d):
    tr, sc, de = load(d)
    check_trace(tr, sc, de)
    check_qr(sc, de)
    sp = os.path.join(os.path.dirname(d.rstrip("/")), "score.json")
    if os.path.isfile(sp):
        check_score(json.load(open(sp, encoding="utf-8")), tr, sc)
    else:
        print("(채점 결과 없음 -- 트레이스만 검사했다)")
    for name, detail in FAIL:
        print("  FAIL  %s%s" % (name, ("  -- " + detail) if detail else ""))
    print("통과 %d · 실패 %d" % (OKN[0], len(FAIL)))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
