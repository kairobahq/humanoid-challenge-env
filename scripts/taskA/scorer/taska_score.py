# Copyright 2025.
#
# **시연 기록 한 판을 평가표대로 채점한다.**
#
#     python3 scripts/taskA/scorer/taska_score.py scripts/taskA/demos/demo_00.npz
#
# Isaac Sim 이 필요 없다. numpy 만 있으면 돈다 -- 채점이 보는 것은 전부 **자리**이지 힘이
# 아니기 때문이다. 과제 B 의 `taskb_score.py` 를 npz 하나로 돌리는 것과 같은 꼴이다.
#
# 과제 A 의 평가표는 **여섯 항목 21 점**이고, 시도 3 회를 합해 63 점이 최종 만점이다.
#
#     매장 가구와 부딪히지 않았는가          판 내내        4   (책상 둘레에 들고 도착한 판만)
#     바구니를 띄웠고 그때 그리퍼가 물었는가   한 번이라도     3
#     목적지에 도착해 멈췄는가               한 번이라도     3
#     그 시점에 로봇이 들고 있었는가          그 시점에       4
#     책상 상판에 얹었는가                   한 번이라도     3
#     손을 뗀 뒤 6 초 동안 잘 놓여 있었는가    손 뗀 뒤 6초    4
#
# **떨림은 채점 항목이 아니다.** 로봇이 덜덜거리며 가도 도착하면 점수는 같다.
#
# 이 파일이 하는 일은 시연 파일을 채점기가 아는 모양으로 바꿔 주는 것뿐이다.
#   * `score/*` 열여섯 갈래를 세 토막(집기·주행·놓기)으로 자르고
#   * 토막마다 `score_from_log.measure_one()` 을 부르고
#   * `merge()` 로 합쳐 `rubric_taskA.score()` 에 넣는다
# 판정식은 한 줄도 여기 없다. 문턱과 산식은 `rubric_taskA.py` 와 `score_from_log.py` 에 있다.
#
# 「쥐고 있나」를 힘이 아니라 자리로 보는 이유
#   힘으로 재려면 물리를 다시 돌려야 하는데, 긴 주행에서는 그 재계산이 원래 기록과 다르게
#   흘러가 바구니를 놓치는 일이 생긴다. 자리로 재면 기록만 있으면 된다. 믿을 만한지는
#   확인했다 -- 화면 7,041 장에서 힘으로 잰 답과 99.9 % 같았다 (어긋난 것 9 장).

import argparse
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import log_check as LC            # noqa: E402
import rubric_taskA as R          # noqa: E402
import score_from_log as SFL      # noqa: E402

THRESHOLD_KEYS = ("LIFT_OK_MM", "ARRIVE_ZONE_M", "STOP_MM_S", "CONTACT_N",
                  "SEAT_ON_MAX_MM", "SEAT_SINK_MAX_MM", "SEAT_NEAR_MM",
                  "OVERHANG_OK_MM", "TILT_OK_DEG",
                  "WATCH_S", "WATCH_TAIL_S", "DESK_OK_MM", "TIME_LIMIT_S")


def load(path):
    """시연 파일 하나 -> (meta, 머리말, 배열사전).  **한 시도는 하나의 타임라인이다.**

    파일 안에서는 집기·주행·놓기가 토막으로 나뉘어 있고 **토막마다 시계가 0 부터 다시
    시작한다** (조각마다 따로 찍었기 때문이다).  여기서 누적 오프셋을 더해 한 줄로 잇는다.

    왜 이어 붙이나 -- 실측 2026-09-08
      예전에는 토막마다 따로 재고 나중에 합쳤는데, **무엇을 잴지를 토막 이름이 정했다**
      (`score_from_log.py` 의 `if seg == "pick"` 따위).  그래서 이름을 지우거나 바꾸면
      항목이 통째로 안 재지고, 안 잰 항목은 분모에서 빠져 **비율이 100 % 가 됐다**:

          토막 이름을 지운다        4 / 4   = 100 %
          전부 'place' 라고 한다   18 / 18  = 100 %
          집기만 내고 끝            7 / 7   = 100 %

      한 시도를 한 타임라인으로 보면 이름이 판정에 끼어들 자리가 없다.  평가받는 쪽이
      만든 이름표가 채점 범위를 정해서는 안 된다.
    """
    z = np.load(path, allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    if "scoring" not in meta:
        raise SystemExit(
            "이 시연 파일에는 채점용 데이터가 없다: %s\n"
            "`score/*` 갈래를 담은 판만 채점할 수 있다." % os.path.basename(path))
    seg = np.asarray(z["segment"], dtype=np.int64)
    names = meta["segment_names"]
    fields = meta["scoring"]["fields"]
    cols = {f: np.asarray(z["score/" + f]) for f in fields}
    z.close()

    order, kin, hit_any = [], True, False
    for i, name in enumerate(names):
        m = np.flatnonzero(seg == i)
        if m.size == 0:
            continue
        order.append((name, m))
        h = meta["scoring"]["segments"].get(name) or {}
        kin = kin and bool(h.get("kinematic"))
        hit_any = hit_any or bool((h.get("hit") or {}).get("hit"))
    if not order:
        raise SystemExit("이 파일에는 프레임이 하나도 없다: %s" % os.path.basename(path))

    out, offset = {f: [] for f in fields}, 0.0
    for name, m in order:
        t = np.asarray(cols["t"][m], dtype=np.float64)
        for f in fields:
            v = cols[f][m]
            out[f].append((t - t[0] + offset) if f == "t" else v)
        # 다음 토막은 이 토막이 끝난 **한 프레임 뒤**에 시작한다.  간격은 이 토막의
        # 중앙값을 쓴다 -- 마지막 두 프레임 차이를 쓰면 그 하나가 튀었을 때 시계가 튄다.
        dt = float(np.median(np.diff(t))) if t.size > 1 else 0.1
        offset += float(t[-1] - t[0]) + dt

    arrays = {f: np.concatenate(v, axis=0) for f, v in out.items()}
    head = {"segment": "attempt", "frames": int(len(arrays["t"])),
            "kinematic": kin,
            # 충돌은 4 층에서 배열로 다시 판정하므로 여기 값은 「무엇에 부딪혔나」에만
            # 쓰인다.  그래도 어느 토막에서든 부딪혔으면 참으로 남긴다.
            "hit": {"hit": hit_any},
            "segments": [name for name, _m in order]}
    return meta, head, arrays


def scene_of(meta):
    """채점기가 씬 파일에서 읽던 값. 시연 파일이 그대로 싣고 있다."""
    sc = meta["scoring"]["scene"]
    return {"meta": {"name": sc["name"], "seat": meta["seat"],
                     "corridor": sc.get("corridor")},
            "desk": sc["desk"], "goal": sc["goal"]}


class Unscorable(SystemExit):
    """이 로그로는 채점할 수 없다.  0 점과 다르다 -- 아래 `score_one` 의 주석 참조."""


def score_one(path, quiet=False):
    meta, head, arrays = load(path)
    scene = scene_of(meta)
    th = {k: getattr(R, k) for k in THRESHOLD_KEYS}

    # **채점하기 전에 로그가 채점할 만한 물건인지 본다.**
    #
    # 점수를 0 으로 매기지 않고 아예 안 내는 이유: 로그가 깨진 것과 로봇이 못한 것은
    # 다른 일이다.  하네스나 시뮬레이터가 튀어 깨졌을 수도 있고, 그때 0 점을 주면
    # 참가자가 억울하다.  채점기는 「채점할 수 없다 + 왜」까지만 말하고 판단은 사람이 한다.
    probs = LC.problems(arrays, head, scene)
    if probs:
        print(LC.report(probs, os.path.basename(path)))
        raise Unscorable(2)

    measured = SFL.measure_one(head, arrays, scene, th)
    m = SFL.merge([measured])
    result = R.score(m)

    if not quiet:
        print("\n[채점] %s  --  seed %d, 좌석 %d, %d 프레임 (%.1f 초)"
              % (os.path.basename(path), meta["seed"], meta["seat"],
                 meta["frames"], meta["frames"] / meta["fps"]))
        print("       한 판으로 이어 붙임: %s" % ", ".join(head.get("segments") or ["?"]))
        print()
        print(R.render(result))
        for note in measured.get("notes", []):
            print("  * %s" % note)
    return {"file": os.path.basename(path), "seed": meta["seed"], "seat": meta["seat"],
            "measured": m, "per_segment": [measured], "score": result}


def main():
    ap = argparse.ArgumentParser(
        description="과제 A 의 시연 기록을 평가표대로 채점한다. Isaac Sim 이 필요 없다.")
    ap.add_argument("demo", nargs="+", help="scripts/taskA/demos/demo_NN.npz")
    ap.add_argument("--out", type=str, default=None, help="결과를 JSON 으로 저장")
    ap.add_argument("--quiet", action="store_true", help="표를 찍지 않는다")
    a = ap.parse_args()

    out = [score_one(p, quiet=a.quiet) for p in a.demo]

    if len(out) > 1:
        tot = sum(o["score"]["total"] for o in out)
        pos = sum(o["score"]["possible"] for o in out)
        print("\n════ %d 판 합계 %g / %g 점 ════" % (len(out), tot, pos))
        for o in out:
            print("  seed %-3d 좌석 %-3d %g / %g"
                  % (o["seed"], o["seat"], o["score"]["total"], o["score"]["possible"]))

    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        print("\n결과: %s" % a.out)


if __name__ == "__main__":
    main()
