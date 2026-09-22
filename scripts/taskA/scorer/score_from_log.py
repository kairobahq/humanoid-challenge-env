# Copyright 2025.
#
# 판정 로그 -> 측정값 -> 채점표.  **Isaac 이 필요 없다.**
#
# WHY MEASURING AND SCORING ARE SEPARATE FILES
#   여기는 재기만 하고 점수는 `rubric_taskA.py` 가 매긴다.  나누는 이유는 이의 제기다 --
#   문턱을 바꿔 다시 채점하고 싶을 때 로그를 다시 만들 필요가 없어야 하고, 채점기 단위 시험이
#   시뮬레이터 없이 몇 초에 돌아야 한다.  `Task-A/scoring/{probe_pick,rubric_pick}.py` 가
#   같은 이유로 나뉘어 있다.
#
# WHY IT TAKES SEVERAL LOGS AT ONCE
#   **사용자 결정(2026-09-01): 집기·주행·놓기를 이어진 한 편이 아니라 세 조각으로 준다.**
#   그러면 한 조각이 8 항목을 다 답할 수 없다 -- 주행 로그의 첫 프레임에서 바구니는 이미 들려
#   있으므로 "탁자에서 띄웠는가" 를 물을 수 없다.  조각마다 답할 수 있는 것만 답하고 나머지는
#   `None` 으로 두면, 세 값 규칙에 따라 그 항목이 **분모에서 빠진다**.  세 조각을 같이 주면
#   빈칸이 서로 채워져 30 점 만점이 된다.
#
#   [판 내내] 인 두 항목(가구 충돌·책상 밀림)은 **세 조각 전체에서 가장 나쁜 값**을 쓴다.
#
# Run:
#   python3 Task-A/eval_kit/score_from_log.py --log gt_1_pick.npz gt_1_carry.npz gt_1_place.npz \
#       --scene Task-A/datasets/eval_kit/scenes/scene_1.json --out expected/score_1.json

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_TASKA = _HERE.parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_TASKA / "scoring"))

# **옆 폴더도 본다.**  저장소에서는 이 파일과 `scene_spec.py` 가 같은 폴더(`eval_kit/`)에
# 있지만, 전달 폴더에서는 채점기가 `score/`, 장면 스키마가 `scene/` 으로 갈라져 있다.
# 경로를 하나만 박아 두면 폴더를 옮기는 순간 `ModuleNotFoundError` 로 죽는다 -- 그리고
# 그것은 꾸러미를 받은 사람이 처음 돌려 보는 순간에 난다.
for _sib in ("scene", "scoring", "sim"):
    _d = _HERE.parent / _sib
    if _d.is_dir():
        sys.path.append(str(_d))

import grasp_geom as GG       # noqa: E402  (순수 numpy -- 크레이트 축과 기울기의 정의가 여기 있다)
import rubric_taskA as R      # noqa: E402
import grip_geom as GRIP
import scene_spec as SS

# 바구니 치수.  `sim/task_layout.BASKET_SIZE` 와 같은 값이고, 채점기는 Isaac 없이
# 돌아야 하므로 그 모듈을 import 하지 않고 `grasp_geom` 의 상수에서 가져온다.
TL_BASKET_SIZE = (GG.CRATE_ALONG, GG.CRATE_ACROSS, GG.CRATE_HEIGHT)       # noqa: E402

# 「다시 잡았다」로 셀 최소 시간 (초).
#
# 감시창은 **마지막으로 손을 뗀 순간**부터 연다 (사용자 결정 2026-09-07: "놓았다가 다시
# 들었다가 또 놓는 경우에는 마지막 놓기를 기준으로").  그러려면 「다시 잡음」을 세야 하는데,
# 접촉 판정은 손가락이 문턱(40 mm)을 스칠 때 한두 프레임 튄다:
#
#     튄 것        놓음 놓음 [잡음] 놓음 놓음 놓음        <- 0.1 초.  재파지가 아니다
#     진짜 재파지   놓음 놓음 [잡음 잡음 잡음 잡음] 놓음   <- 0.4 초.  재파지다
#
# 튄 것을 재파지로 세면 감시창이 그만큼 뒤로 밀리고, 6 초를 못 채워 0 점이 된다.
#
# 0.5 초로 잡은 근거: **손을 다시 뻗어 집는 데 그보다 짧게 걸릴 수는 없다.**  실측이 아니라
# 추정이고, 기록이 초당 10 장이므로 5 프레임이다.  값을 바꿀 일이 생기면 여기 하나만 고친다.
REGRASP_MIN_S = 0.5


def _last_release(rel, t, min_regrab_s=REGRASP_MIN_S):
    """마지막으로 손을 뗀 프레임 번호.  없으면 None.

    `rel` 은 프레임마다 「한 번 물었던 집게가 지금은 바구니를 물고 있지 않다」이다
    (2026-09-23 까지는 「로봇에게서 떨어져 있고 책상 상판 위」였다 -- `released` 머리말).
    그것이 참인 구간이 여럿이면 구간 사이가 「다시 잡고 있던 시간」이고, 그 시간이
    `min_regrab_s` 보다 짧으면 판정이 튄 것으로 보아 앞뒤를 한 번의 놓기로 잇는다.

    (놓기 횟수, 마지막 놓기의 프레임 번호) 를 돌려준다 -- 횟수도 같이 내는 이유는
    "왜 이 시점을 골랐나" 를 나중에 물어올 것이기 때문이다.
    """
    idx = np.flatnonzero(rel)
    if idx.size == 0:
        return 0, None
    starts = [int(idx[0])]
    for a_i, b_i in zip(idx[:-1], idx[1:]):
        if b_i == a_i + 1:
            continue                      # 이어진 같은 구간
        # 다시 잡고 있던 것은 **프레임 a_i+1 부터 b_i-1 까지**이므로 그 길이는
        # `t[b_i] - t[a_i]` 가 아니라 `t[b_i] - t[a_i + 1]` 이다.  앞엣것을 쓰면 한
        # 프레임(0.1 초)씩 길게 세어, 0.4 초짜리 깜빡임이 재파지로 통과한다.
        if float(t[b_i]) - float(t[a_i + 1]) >= min_regrab_s:
            starts.append(int(b_i))       # 진짜 재파지 뒤의 새 놓기
    return len(starts), starts[-1]


def load(path):
    z = np.load(path, allow_pickle=False)
    head = json.loads(str(z["header"]))
    return head, {k: z[k] for k in z.files if k != "header"}


def _speed(pos, t):
    """자리가 얼마나 빨리 변하는가 (mm/s).  **기록된 속도(`*_vel`)를 쓰지 않는다.**

    WHY NOT THE RECORDED VELOCITY (2026-09-02 실측, seed 0 의 GT 세 조각)
      바닥에 서 있는 로봇의 보고된 수직 속도가 **계속 +39 mm/s 로 떠 있다.**  세 조각에서
      각각 +38.99 / +39.21 / +38.99 mm/s (중앙값) 이고, 같은 프레임에서 **위치 차분은
      +0.00 mm/s** 다.  마지막 100 프레임(10초) 동안 로봇이 실제로 움직인 거리는 0.2 mm 인데
      보고된 속도는 39 mm/s 를 유지한다.  바구니도 로봇이 들고 있는 동안 같은 모양이고
      (+33.9 / +54.0), 책상에 내려놓은 뒤에는 -0.07 로 사라진다 -- **바닥(compliant)에
      얹힌 것에 붙는 값**으로 보인다.

      그대로 읽으면 문턱이 10 mm/s 이므로 **"멈췄다" 가 영원히 거짓이 된다.**  실제로
      seed 0 의 정답 주행이 A-2-1 에서 0 점을 받았고, 로그를 보니 3,102 프레임 전부
      39 mm/s 였다.  우리 편만의 문제가 아니라 **어느 팀의 제출물이든 같은 답을 받는다.**

      문턱은 그대로 10 mm/s 다.  바꾼 것은 **재는 방법**뿐이고, 자리가 변했는가가 곧
      "멈췄다" 의 뜻이므로 위치 차분이 그 문장에 더 가깝다.  기록된 속도는 npz 에 그대로
      남아 있으므로 다르게 판단하실 수 있다.

      두 구간의 **큰 쪽**을 그 프레임의 속도로 본다 -- 한쪽만 0 이어도 멈춘 것으로 치면
      판정이 관대해진다.
    """
    tt = np.asarray(t, dtype=np.float64)
    dt = np.diff(tt)
    good = dt > 0
    dt = np.where(good, dt, (np.median(dt[good]) if good.any() else 1.0))
    v = np.linalg.norm(np.diff(np.asarray(pos)[:, :3], axis=0), axis=1) / dt * 1000.0
    if len(v) == 0:
        return np.zeros(len(tt))
    out = np.empty(len(tt), dtype=np.float64)
    out[0], out[-1] = v[0], v[-1]
    if len(tt) > 2:
        out[1:-1] = np.maximum(v[:-1], v[1:])
    return out


def _reported_speed(vel6):
    """기록된 선속도 크기 (mm/s).  **채점에 안 쓴다** -- 위 참조.  출력에 같이 남겨
    두 방법이 얼마나 다른지 보이기 위한 것이다."""
    return np.linalg.norm(vel6[:, :3], axis=1) * 1000.0


def _yaw(q):
    return np.arctan2(2.0 * (q[:, 0] * q[:, 3] + q[:, 1] * q[:, 2]),
                      1.0 - 2.0 * (q[:, 2] ** 2 + q[:, 3] ** 2))


def _corners(pos, quat):
    """바구니 밑면 네 모서리의 월드 xy.  축의 정의는 `grasp_geom.crate_axes` 것을 쓴다 --
    여기서 다시 정하면 두 곳이 갈라진다."""
    out = np.zeros((len(pos), 4, 2), dtype=np.float64)
    for i in range(len(pos)):
        along, across, _ = GG.crate_axes(quat[i])
        for j, (sa, sc) in enumerate(((1, 1), (1, -1), (-1, -1), (-1, 1))):
            p = (pos[i, :2] + along[:2] * (sa * GG.CRATE_ALONG / 2.0)
                 + across[:2] * (sc * GG.CRATE_ACROSS / 2.0))
            out[i, j] = p
    return out


def _overhang_mm(corners, desk_xy, desk_size):
    """상판 밖으로 나간 최대 거리 (mm).  안에 다 들어가면 0."""
    hx, hy = desk_size[0] / 2.0, desk_size[1] / 2.0
    dx = np.abs(corners[:, :, 0] - desk_xy[:, None, 0]) - hx
    dy = np.abs(corners[:, :, 1] - desk_xy[:, None, 1]) - hy
    out = np.sqrt(np.maximum(dx, 0.0) ** 2 + np.maximum(dy, 0.0) ** 2)
    return out.max(axis=1) * 1000.0


def _overhang_round_mm(corners, centre_xy, radius_m):
    """**원형** 상판 밖으로 나간 최대 거리 (mm).  안에 다 들어가면 0.

    `_overhang_mm` 의 원형판이다 -- 식사공간 탁상은 사각이 아니라 원이고, 씬이 중심과
    반지름으로 준다 (`furniture.tables`).  **두 함수는 같은 것을 재므로 한쪽만 고치지 말 것.**
    """
    c = np.asarray(centre_xy, dtype=np.float64)[None, None, :]
    d = np.linalg.norm(corners - c, axis=2)
    return np.maximum(d.max(axis=1) - float(radius_m), 0.0) * 1000.0


def measure_one(head, a, scene, th):
    """조각 하나에서 답할 수 있는 것만 답한다.  못 답하는 것은 열쇠를 아예 안 넣는다."""
    seg = head.get("segment", "?")
    out = {"segment": seg, "frames": int(len(a["t"])), "notes": [],
           "elapsed_s": float(a["t"][-1] - a["t"][0]) if len(a["t"]) else 0.0}

    # ── 무엇이 바구니를 받치고 있나 ─────────────────────────────────────────────────────
    #
    # 새 평가표(2026-09-02)는 두 물음을 **다른 범위**로 묻는다.
    #
    #   Sub 1# 집기   「**그리퍼**가 물고 있었나」   -> grip_max
    #   Sub 2# 이동   「**로봇**이 들고 있었나」     -> robot_touch   (나르는 방식은 안 본다)
    #
    # 그래서 둘을 따로 읽는다.  `crate_robot_force` / `crate_nonrobot_force` 는 이 시트를 위해
    # 2026-09-02 에 로그에 들어간 열이다.  **옛 로그에는 없다** -- 그때는 그리퍼로 대신 읽고
    # 그 사실을 메모에 남긴다.  조용히 대신 읽으면 그리퍼로 물지 않은 판이 0점으로 찍히고
    # 이유가 로그 어디에도 안 남는다.
    grip_max = a["grip_force"].max(axis=1)
    other = a["crate_other_force"]

    # ── 물리를 안 돌린 로그는 접촉을 **기하로** 읽는다 ──────────────────────────────────
    #
    # `gt_replay.py --kinematic` 이 만든 로그에는 접촉력이 전부 0 이다 -- 물리를 한 스텝도
    # 안 돌렸기 때문이다.  대신 손가락 자리와 벌림으로 판정한다.  물리로 잰 것과 7,041
    # 프레임에서 **99.9% 일치**하는 것이 확인돼 있다 (`grip_geom.py` 머리말: 집기 99.5 /
    # 주행 100.0 / 놓기 99.9, 오탐 5 · 미탐 4).
    #
    # 왜 물리를 버렸나: 재생이 긴 주행에서 재현되지 않았다.  스워브가 잠겼다 풀리며 베이스가
    # 명령 상한의 3 배로 튀고 그때 바구니가 손에서 뜯긴다.  쥐는 힘 네 값·속도 상한 두 값·
    # 베이스 방식 두 가지를 다 돌려도 안 풀렸다 (2026-09-02).
    if head.get("kinematic"):
        _held, _per_hand, _near_mm, _gap_mm = GRIP.held(
            a["grip_pos"], a["crate_pos"], a["crate_quat"], TL_BASKET_SIZE)
        on_robot = on_grip = _held
        free = np.ones(len(_held), bool)
        # 「로봇이 아닌 것이 받치나」는 힘으로만 나오는 값이라 기하로는 직접 못 잰다.
        # **대신 결과로 읽는다**: 로봇이 안 쥐고 있는데 바구니가 멈춰 있으면 무언가가 받치는
        # 것이다.  공중에 있는 바구니는 계속 떨어지므로 안 멈춘다.  이 대용값은 낙하 판정에만
        # 쓰이고(`dropped`), 쥐고 있는 동안의 판정에는 관여하지 않는다.
        _cspd = _speed(a["crate_pos"], a["t"])
        robot_touch = np.where(_held, 1.0, 0.0)
        nonrobot = np.where((~_held) & (_cspd < th["STOP_MM_S"]), 1.0, 0.0)
        out["geom_grip"] = {
            "near_mm": float(GRIP.NEAR_MM), "gap_mm": float(GRIP.GAP_MM),
            "held_frames": int(_held.sum()), "frames": int(len(_held)),
            # 어느 손이 얼마나 잡고 있었는지 -- 이의가 오면 이 숫자로 답한다
            "left_frames": int(_per_hand[:, 0].sum()), "right_frames": int(_per_hand[:, 1].sum()),
            "near_min_mm": [float(_near_mm[:, 0].min()), float(_near_mm[:, 1].min())],
            "gap_min_mm": [float(_gap_mm[:, 0].min()), float(_gap_mm[:, 1].min())],
        }
        out["contact_source"] = "기하 (grip_geom, 물리와 99.9% 일치)"
        out["notes"].append(
            "물리를 안 돌린 로그다 — 접촉을 손가락 자리와 벌림으로 판정했다 "
            f"(문턱 {GRIP.NEAR_MM:.0f} mm / {GRIP.GAP_MM:.0f} mm)")
    elif "crate_robot_force" in a and "crate_nonrobot_force" in a:
        robot_touch = a["crate_robot_force"]
        nonrobot = a["crate_nonrobot_force"]
        on_robot = robot_touch > th["CONTACT_N"]
        on_grip = grip_max > th["CONTACT_N"]
        free = nonrobot <= th["CONTACT_N"]
    else:
        robot_touch = grip_max
        nonrobot = other
        on_robot = robot_touch > th["CONTACT_N"]
        on_grip = grip_max > th["CONTACT_N"]
        free = nonrobot <= th["CONTACT_N"]
        out["notes"].append(
            "이 로그에는 로봇 전체 접촉(crate_robot_force)이 없어 **그리퍼로 대신 읽었다** — "
            "그리퍼로 물지 않고 나른 판이라면 「들고 있었는가」가 틀리게 나온다")
    held = on_robot & free                             # Sub 2# 의 「들고 있다」
    gripped = on_grip & free                           # Sub 1# 의 「물고 있다」

    # ── 「놓았다」는 **집게가 풀렸는가**로 본다 (사용자 결정 2026-09-23) ──────────────────
    #
    # 앞 판은 「로봇 어느 부위도 안 닿는다」(`~on_robot`)였다.  job122 는 세 판 모두 집게를
    # 끝까지 열었는데(벌림 114.5 mm) ep0·ep1 은 **편 손이 바구니 테두리에 얹혀** 접촉력
    # 35~38 N 이 잡혔고, 그래서 얹기·6 초가 0 점이었다.  우리 학습 데이터 2,492 편도 전부
    # 집게만 열고 팔을 그 자리에 둔 채 기다린다 -- 참가자는 그것을 따라 했다.  사용자 결정:
    # "그냥 얹으면 되는 걸로 하자" -- 손·팔이 얹혀 있는 것은 괜찮다.
    #
    # **새 판정을 만들지 않는다.**  `grip_geom.held()`(근접 40 mm, 벌림 60 mm)는 기하 경로가
    # 이미 쓰고, 실시간 판정기의 `grip_state()` 도 같은 두 값이다.  숫자의 출처는 우리 궤적이
    # 아니라 물리와 기구다:
    #
    #   물고 있을 때 벌림        27.4 ~ 34.1 mm   11,116 프레임 (참가자 판도 같은 폭)
    #   물리가 접촉을 잡은 최대   50.9 mm          7,041 프레임 대조 (grip_geom 머리말)
    #   끝까지 연 벌림           114.0 ~ 114.7 mm
    #
    # 벌림 52~80 × 근접 30~60 mm 로 흔들어도 완결된 로그의 판정이 한 번도 안 바뀐다
    # (2026-09-23 실측).  그래서 60·40 은 고르는 값이 아니라 **유지하는 값**이다.
    #
    # `& free` 를 붙이지 않는다 -- 그러면 책상에 놓인 채 쥐고 있는 바구니가 「안 문다」가
    # 된다.  **빈 값(NaN)은 「물고 있다」로 본다**: `held()` 는 NaN 에서 거짓을 내므로 그냥
    # 두면 못 읽은 프레임이 「놓았다」로 **유리하게 샌다**.
    #
    # **한 번 물었던 뒤로만** 놓은 것으로 센다 -- 실시간 판정기의 `rel and was_gripped` 와
    # 같은 뜻이다.  안 그러면 한 번도 안 잡은 판이 첫 프레임에 「놓았다」가 된다.
    _gp = np.asarray(a["grip_pos"], dtype=np.float64)
    _nan = (~np.isfinite(_gp).reshape(len(_gp), -1).all(axis=1)
            | ~np.isfinite(np.asarray(a["crate_pos"], np.float64)).all(axis=1)
            | ~np.isfinite(np.asarray(a["crate_quat"], np.float64)).all(axis=1))
    _clamp = GRIP.held(_gp, a["crate_pos"], a["crate_quat"], TL_BASKET_SIZE)[0] & ~_nan
    grip_held = _clamp | _nan
    released = (~grip_held) & (np.maximum.accumulate(_clamp) if len(_clamp) else _clamp)
    out["release_rule"] = {"by": "grip_geom", "near_mm": float(GRIP.NEAR_MM),
                           "gap_mm": float(GRIP.GAP_MM), "ever_clamped": bool(_clamp.any()),
                           "nan_frames": int(_nan.sum())}
    if _nan.any():
        out["notes"].append(
            f"손가락·바구니 좌표가 빈 프레임 {int(_nan.sum())}개는 「놓았다고 확인 못 함」"
            "(= 물고 있음)으로 보았다")

    # ── [판 내내] 두 항목은 어느 조각에서나 잰다 ────────────────────────────────────────
    # **충돌은 배열로 판정한다.  머리말을 믿지 않는다.**
    #
    # 예전에는 `hit.get("hit", <배열로 계산>)` 이라 머리말에 값이 있으면 배열을 보지
    # 않았다.  머리말은 로그를 만든 쪽이 쓰는 것이고, 채점받는 쪽이 만들 수도 있다.
    # 실측 2026-09-08: 배열이 "1449 프레임 내내 부딪혔다" 라고 하는데 머리말만
    # `{"hit": false}` 로 바꾸면 「가구와 부딪히지 않았다」 4 점을 그대로 받았다.
    #
    # 머리말은 **무엇에** 부딪혔는지(`fixture`, `part`)에만 쓴다.  둘이 어긋나면 조용히
    # 한쪽을 고르지 않고 메모에 남긴다 -- 어긋난다는 사실 자체가 알아야 할 정보다.
    hit = head.get("hit") or {}
    hit_from_log = bool(a["hit_now"].max() > 0.5)
    if "hit" in hit and bool(hit["hit"]) != hit_from_log:
        out["notes"].append(
            "머리말은 충돌을 %s 라고 하는데 기록은 %s 다 -- **기록을 따랐다**"
            % ("있다" if hit["hit"] else "없다", "있다" if hit_from_log else "없다"))
    out["furniture"] = {"hit": hit_from_log,
                        "worst_mm": float(a["hit_depth_mm"].max()),
                        "what": hit.get("fixture"), "part": hit.get("part"),
                        "frames": int(a["hit_now"].sum())}
    d0 = a["desk_pos"][0, :2]
    out["desk"] = {"worst_mm": float(np.max(
        np.linalg.norm(a["desk_pos"][:, :2] - d0[None, :], axis=1)) * 1000.0)}

    # ── 책상 상판 높이는 매 프레임 따라간다 ─────────────────────────────────────────────
    # **상수로 쓰지 않는다** -- 책상은 밀리기만 하는 것이 아니라 들리는 일도 있다
    # (CLAUDE.md 57 절).
    #
    # **원점 + 높이다.**  앞 판은 `scene["desk"]["top_z"]` 를 월드 높이로 쓰고 그 뒤 움직인
    # 만큼을 더했다.  그런데 그 값은 `taskA_layout.desk_top_z()` 가 주던 `DESK_SIZE[2]`,
    # 즉 책상의 **치수**였다.  책상 원점이 0 일 때만 우연히 맞고, 원점이 다르면 조용히
    # 틀린다 -- 그리고 실제로 달랐다:
    #
    #     수집 환경   책상 원점 0.002 (동적 강체가 매장 바닥에 가라앉아 선다)
    #     배포 환경   책상 원점 0.000 (kinematic 으로 못 박아 바닥에 2 mm 박혀 있었다)
    #
    # 기준면이 그 2 mm 를 안 따라가서, 배포 환경의 정상적인 놓기가 seat -0.673 mm 로 읽혀
    # 「얹힘 아님」-> 「낙하」가 됐다 (참가자 이슈 #3, 2026-09-10.  재현: 같은 로그를 책상
    # 높이만 바꿔 채점하면 18/21 ok 대 11/21 dropped).
    #
    # 과제 B 는 처음부터 `TABLE_TOP = TABLE_POS[2] + TABLE_SIZE[2]` 였다 (taskB_table.py:103).
    # 우리가 그 상수를 가져오면서 `+ TABLE_POS[2]` 를 빠뜨린 것이고, 여기서 되돌린다.
    #
    # 로그의 `desk_pos` 를 직접 쓰므로 책상이 밀리든 들리든 매 프레임 저절로 따라간다 --
    # 앞 판의 「씬 값 + 움직인 차이」 보정이 필요 없어진다.
    desk_h = float(scene["desk"]["size"][2])          # 치수다.  월드 높이가 아니다
    top = a["desk_pos"][:, 2] + desk_h
    seat_mm = (a["crate_pos"][:, 2] - top) * 1000.0
    corners = _corners(a["crate_pos"], a["crate_quat"])
    over_mm = _overhang_mm(corners, a["desk_pos"][:, :2], scene["desk"]["size"])

    # 바구니가 얼마나 빨리 움직이나.  **`seated` 보다 먼저 만들어야 한다** -- 아래에서 쓴다.
    c_speed = _speed(a["crate_pos"], a["t"])
    c_speed_reported = _reported_speed(a["crate_vel"])

    # 「책상에 있나, 바닥에 있나」.  **얹힘 판정과 다른 물음이고 다른 자를 쓴다.**
    #
    # 이 배열은 낙하 판정(`dropped`)과 감시창을 여는 자리(`rel`)에만 쓰인다.  둘 다 묻는 것은
    # 「바구니가 책상에 있나」이지 「제대로 얹혔나」가 아니다.  바닥은 상판보다 **725 mm**
    # 아래이므로 이 물음에 5 mm 자를 댈 이유가 없다.
    #
    # 앞 판은 얹힘 판정과 **같은 식**을 썼고, 그래서 잔여 겹침(0.3~1.4 mm)이나 적분 오버슛
    # 한 프레임이 곧바로 「낙하」가 됐다.
    #
    # **여기에는 멈춤 조건을 걸지 않는다.**  튕기는 중인 바구니가 낙하로 찍히면 안 된다.
    on_top = (np.abs(seat_mm) <= th["SEAT_NEAR_MM"]) & (over_mm <= 500.0)

    # **목표 책상만이 「놓아도 되는 자리」인 것이 아니다** (사용자 결정 2026-09-22).
    #
    # 앞 판은 이 배열이 `scene["desk"]` 하나만 알았다.  그래서 로봇이 바구니를 집었다가
    # **출발할 때 놓여 있던 식탁에 도로 내려놓고 손을 떼면**, 바구니가 멀쩡히 탁상 위에
    # 있는데도 「책상도 아닌 데서 손을 놨다 = 낙하」로 읽혀 판이 끝났다.  실측: 쥐고
    # 106 mm 들었다가 탁상(0.750 m)에 도로 놓는 합성 판이 11.4 초에 `dropped` 로 끝났고
    # **두 번째 파지는 시작도 못 했다.**  한 번 놨다가 다시 잡는 것은 정책이 흔히 하는
    # 정상 동작이라, 이대로 두면 멀쩡한 시도가 계속 잘려 나간다.
    #
    # 씬이 식사공간 탁상 세 개를 **중심·반지름·상판높이로 이미 준다**
    # (`furniture.tables` -- 꾸러미 씬과 실제 평가 씬 양쪽에 들어 있다).  그러니 새 값을
    # 실을 필요도, 새 문턱을 지어낼 필요도 없다 -- **책상에 쓰는 두 자(`SEAT_NEAR_MM` 와
    # 500 mm)를 그대로** 원형 탁상에 댄다.
    #
    # 실측(같은 식을 그대로 걸어 본 것): 꾸러미 집기 로그는 첫 프레임 참 -> 들어올리면
    # 거짓(80/170), 주행 0/1034, 놓기 0/269.  실제 평가 로그(job122-ep0)는 288/2089 로
    # 첫 프레임 참 -> z 0.800 에서 거짓.  **헛되이 켜지는 구간이 없다.**
    #
    # 탁상 목록이 없는 옛 씬이면 지금까지와 똑같이 동작하고, 그 사실을 메모에 남긴다.
    _tables = ((scene.get("furniture") or {}).get("tables")
               if isinstance(scene, dict) else None) or []
    if _tables:
        for _tb in _tables:
            _tz, _c, _r = _tb.get("top_z"), _tb.get("centre"), _tb.get("radius")
            if _tz is None or _c is None or _r is None:
                continue
            _seat_tb = np.abs(a["crate_pos"][:, 2] - float(_tz)) * 1000.0
            _over_tb = _overhang_round_mm(corners, _c, _r)
            on_top = on_top | ((_seat_tb <= th["SEAT_NEAR_MM"]) & (_over_tb <= 500.0))
    else:
        out["notes"].append(
            "씬에 식사공간 탁상 목록(`furniture.tables`)이 없어 **목표 책상만 「놓아도 되는 "
            "자리」로 보았다** — 출발 탁상에 도로 내려놓는 판이 낙하로 찍힐 수 있다")

    # **「제대로 얹혔다」를 한 곳에서만 정한다.**
    #
    # 「책상 상판에 얹었는가」와 「목적지에 도착했는가」가 둘 다 이 배열을 쓴다 (도착은
    # 2026-09-09 결정으로 놓기 성공을 요구한다).  두 항목이 서로 다른 기준으로 「얹혔다」를
    # 판단하면 "얹혔는데 도착이 아니다" 같은 답이 나온다.
    #
    # 높이와 자세를 **같은 프레임에서** 함께 본다 -- 뒤집어 엎어 놓아도 높이는 맞기 때문이다.
    #
    # **멈춰 있을 것을 함께 요구한다.**  이것이 「떨어진 것」과 「파고든 것」을 가르는 자리다.
    #
    #   얹힌 바구니     속도 0            (정답 주행 실측: 창 끝 0.3 mm/s)
    #   떨어지는 바구니   낙하 속도 그대로
    #   오버슛 프레임    낙하 속도 그대로   (실측: seat -5.344 mm 인 프레임의 vz 가 -2.779 m/s.
    #                                    한 적분 스텝 8.3 ms 에 23 mm 를 지나간 위치이지
    #                                    눌려 들어간 것이 아니다.  다음 스텝에 -1.075 로 올라온다)
    #
    # 이 조건이 없으면 아래쪽 여유를 넓히는 것이 곧 「통과 중인 프레임도 얹힘으로 센다」가
    # 된다.  조건이 있으면 여유는 **정말로 받쳐진 채 겹친 양**만 흡수한다.
    tilt_all = np.array([GG.tilt_deg(q) for q in a["crate_quat"]], dtype=np.float64)
    seated = ((seat_mm >= -th["SEAT_SINK_MAX_MM"]) & (seat_mm <= th["SEAT_ON_MAX_MM"])
              & (c_speed < th["STOP_MM_S"]))
    upright = tilt_all <= th["TILT_OK_DEG"]
    placed_ok = seated & upright
    # **놓았는가를 같이 본다** (2026-09-16).
    #
    # 위 셋(높이·멈춤·똑바름)만 보면 바구니를 **쥔 채** 상판 5 mm 위에 가만히 대고 있는 것이
    # 「얹음」으로 통과한다.  재현했다: 상판에 닿은 65 프레임 내내 턱을 문 사본(벌림 24.8 mm,
    # 기하 파지 65/65)이 얹힘 3 점을 받았다.  이 과제의 뜻은 **놓는 것**이다.
    #
    # 「놓았다」는 **집게가 풀렸는가**(`released`, 위 「놓았다」 머리말)다 -- 2026-09-23 까지는
    # `~on_robot`(로봇 어느 부위도 안 닿음)이었고, 편 손을 얹어 둔 판이 0 점이 됐다.
    #
    # **`placed_ok` 자체를 좁히지 않는다.**  좁히면 손을 안 뗀 판의 `out["place"]` 가 숫자
    # 없는 가지로 빠져 채점이 0 점이 아니라 **「못 읽었다」(None)** 가 된다 -- 못 잰 것과
    # 못 한 것은 다른 뜻이고, 그 혼동이 이 채점기가 앞서 새던 방식이다.  그래서 숫자
    # (seat/tilt/overhang)는 그대로 두고 불리언만 따로 낸다.
    placed_free = placed_ok & released

    # ── 판이 끝나는 자리 ────────────────────────────────────────────────────────────────
    #
    # **사용자 결정 2026-09-01: 부딪히면 아예 평가 중지.**  낙하와 같은 구조다 -- 그 프레임에서
    # 끝내고 그때까지 얻은 점수만 남긴다.  자르지 않으면 부딪힌 뒤에 우연히 목표 근처를
    # 지나간 것이 "도착" 으로 잡힌다.
    #
    # 실측이 그 필요를 보여준다: 일부러 부딪히게 만든 편은 96초에 부딪힌 뒤 283초를 더
    # 굴렀고, 그 사이 목표까지 1.59 m 를 더 좁혔다.  자르지 않으면 그 1.59 m 가 점수가 된다.

    # ── 낙하 -- 놓기와 **같은 측정이고 자리로만 갈린다** ────────────────────────────────
    #
    # **한 번도 쥔 적이 없으면 떨어뜨릴 수도 없다.**  이 한 줄이 없으면 집기 조각의 첫
    # 프레임이 낙하로 찍힌다 -- 그때 바구니는 탁상 위에 그냥 놓여 있고, 그것은
    # "그리퍼와 안 닿음 + 다른 것이 받침 + 멈춤 + 책상 아님" 을 모두 만족한다.
    # 2026-09-01 실측: 집기 로그가 "0.0초에 낙하" 로 찍혔고, 조각을 합치면 그 한 줄이
    # Sub A-3 의 10 점을 통째로 날린다.
    # 시트의 정의는 둘뿐이다 -- ① 로봇 어느 부위와도 안 닿음 ② 로봇 아닌 것과 닿음.
    # **거기에 ③ 책상 상판 위가 아닐 것을 보탠다** (사용자 승인 2026-09-02).  안 보태면
    # 책상에 잘 내려놓는 순간이 정확히 ①②를 만족해 성공한 놓기가 낙하로 찍히고, Sub 3# 를
    # 아무도 못 받는다.  낙하와 놓기는 같은 측정이고 **자리로만 갈린다.**
    #
    # 옛 판에 있던 「멈췄고」 조건은 뺐다 -- 시트에 없고, ②가 이미 "무언가에 닿았다" 를
    # 요구하므로 공중에 뜬 순간은 어차피 안 잡힌다.
    #
    # **한 번도 로봇에 닿은 적이 없으면 떨어뜨릴 수도 없다.**  이 한 줄이 없으면 집기 조각의
    # 첫 프레임이 낙하로 찍힌다 -- 그때 바구니는 탁상 위에 그냥 놓여 있고, 그것은 ①②를
    # 만족한다.  2026-09-01 실측: 집기 로그가 "0.0초에 낙하" 로 찍혔다.
    ever_held = np.maximum.accumulate(on_robot.astype(np.int8)) > 0
    # **한 번도 쥐고 들어올린 적이 없으면 떨어뜨릴 수도 없다** (2026-09-22, 참가자 이슈).
    #
    # 앞 판에서는 `on_top` 이 **목표 책상 하나만** 알았다 (`scene["desk"]`).  출발 탁상은
    # 거기서 10 m 밖이라 `over_mm` 이 9,849~10,294 mm 로 나온다 -- 그것은 결함이 아니라
    # 맞는 값이다 (바구니가 정말로 책상 밖에 있다).  그래서 **집기 구간 내내 `~on_top` 이
    # 참**이었고, 낙하를 막는 것은 `on_robot` 하나뿐이었다.
    #
    # 그런데 `nonrobot` 은 그 구간에서 **언제나 문턱 위**다.  탁상이 바구니 무게를 받치고
    # 있기 때문이다 -- 실측 `gt/kin_0_pick.npz` 170 프레임 전부 11.772 N (1.2 kg x 9.81),
    # 문턱은 0.5 N.  그러니 집게를 한 번 오므렸다(`ever_held` 가 켜진다) 펴는 순간 네 조건이
    # 동시에 참이 되어, 바구니가 탁상 위에 **가만히 놓여 있는데도** 낙하로 판이 끝났다.
    # 실측: 2.2~5.0 초에 종료, 0/21.
    #
    # **구멍이 둘이고, 고치는 자리가 다르다.**
    #   들기 **전**에 스치는 것      -> 이 문(`_lifted`).  한 번도 쥐고 든 적이 없으면 못 떨어뜨린다
    #   들고 **난 뒤** 도로 놓는 것  -> 위의 `on_top`.  등록된 탁상 위도 「놓아도 되는 자리」다
    # 이 문은 한 번 열리면 안 닫히므로 뒤엣것을 못 막는다.  둘 다 필요하다.
    #
    # **앞서 이 자리에 틀린 말이 적혀 있었다.**  "출발 탁상을 등록하려면 씬에 새 값을 실어야
    # 하고 반경 문턱을 새로 지어내야 한다"고 적었는데 **아니다** -- `furniture.tables` 에 세
    # 탁상이 중심·반지름·상판높이로 **이미 채워져 있다**.  `scene_spec.py` 의 `tables: None`
    # 은 **서식의 빈칸**이지 "아무도 안 채운다"는 뜻이 아니었고, 데이터를 안 보고 서식을
    # 보고 단정했다.
    #
    # **문은 `A1_lift_grip` 그 자체다.  새 규칙도 새 문턱도 없다.**  평가표의 그 항목이
    # 「바구니가 `LIFT_OK_MM` 이상 떠올랐고 같은 프레임에 그리퍼가 물었나」이고, 라이브
    # 판정기도 낙하를 그 항목이 잠긴 뒤에만 본다
    # (`cstore-challenge` `mdp/taska_judge.py:593` -- `self.passed["1_lift_grip"] and …`).
    #
    # **기준면은 씬이 말하는 스폰 높이다.**  라이브 판정기가 쓰는 값과 같은 것이다
    # (`taska_events.py:262` -> `measured["crate_start_z"]`, `taska_judge.py:527`).
    # *그 조각의* 첫 프레임을 기준으로 삼으면 안 된다 -- 앞 조각에서 이미 들어올린 판은
    # 상승이 잡히지 않는다.  실측 꾸러미 로그: `carry`·`place` 는 첫 프레임부터 스폰보다
    # 102~148 mm 위인데 **조각 기준으로는 최대 0.4~17.5 mm** 다.  그 상태로 두면 나르다·
    # 놓다 떨어뜨린 판이 낙하로 안 찍힌다.
    #
    # 씬이 안 말해 주면 로그 첫 프레임으로 떨어진다.  **판 전체 로그에서는 첫 프레임이 곧
    # 스폰이라 같은 값**이고(실측 `demos/demo_06.npz` 차이 0.00 mm), 조각 로그는 스폰을
    # 알 길이 없으므로 그 사실을 메모로 남긴다.
    _crate_spawn = (scene.get("crate") or {}).get("pos")
    if _crate_spawn is not None:
        _start_z = float(_crate_spawn[2])
    else:
        _start_z = float(a["crate_pos"][0, 2])
        out["notes"].append(
            "씬에 바구니 스폰 높이(`crate.pos`)가 없어 **로그 첫 프레임을 기준면으로 삼았다** — "
            "판 전체 로그면 같은 값이지만, 앞 조각에서 이미 들어올린 조각이라면 들림이 "
            "안 잡혀 낙하를 놓칠 수 있다")
    _rise_mm = (a["crate_pos"][:, 2] - _start_z) * 1000.0
    _lift_here = _rise_mm >= th["LIFT_OK_MM"]
    # **쥠을 읽을 수 있는 로그에서만 쥠 조건을 건다.  그리고 경로를 보고 가른다.**
    # 이 파일은 접촉을 세 경로로 읽고, 그리퍼 신호의 출처가 경로마다 다르다:
    #
    #   기하 경로(`head["kinematic"]`)  on_grip = 손가락 근접·벌림   -> 언제나 측정값이다
    #   힘 경로 / 대체 경로             on_grip = grip_max > 문턱    -> `grip_force` 가 있어야 한다
    #
    # `grip_max` 만 보면 **기하 경로가 「그리퍼 열 없음」으로 잘못 빠진다** -- 꾸러미 판정
    # 로그들은 물리를 안 돌려 `grip_force` 가 통째로 0 이지만 기하 신호는 멀쩡하다.  실제로
    # 한 번 그렇게 짰고, 정답지 대조에서 메모가 3 판 x 3 조각 = 9 건 붙어 드러났다
    # (점수는 그대로라 숫자만 봐서는 안 보인다).
    #
    # 힘 경로에서 `grip_force` 가 판 내내 정확히 0 이면 그것은 「0 이라는 측정」이 아니라
    # **「빠진 열」**이다 -- `demos/demo_06.npz` 는 바구니가 163 mm 올라가는데 `grip_force` 와
    # `crate_robot_force` 최대가 둘 다 0.000 이고, 바구니가 저절로 올라갈 수는 없다.
    # 이 파일이 접촉 열이 없을 때 쓰는 방식(위쪽 "그리퍼로 대신 읽었다" 메모)과 같게,
    # 대신 읽고 메모를 남긴다.
    #
    # **남는 한계를 적어 둔다**: 그 대체 상태에서는 「쥐고 들었다」와 「부딪혀 튀어 올랐다」를
    # 가를 방법이 없다 (평가 서버 몽키패치도 같은 한계다 -- `3beed43`).  실제 평가 트레이스는
    # `grip_force` 를 싣고 운영 씬은 `crate` 를 실으므로(`scene_from_seed.py:203`) 운영
    # 채점에는 이 가지가 안 닿는다.
    if bool(head.get("kinematic")) or float(np.max(grip_max)) > 0.0:
        _lift_here = _lift_here & gripped
    else:
        out["notes"].append(
            "이 로그에는 그리퍼 힘(grip_force)이 통째로 0 이다 — **들림을 높이로만 판정했다**. "
            "부딪혀 튀어 오른 것과 쥐고 들어올린 것을 가르지 못한다")
    _lifted = np.maximum.accumulate(_lift_here.astype(np.int8)) > 0
    dropped = (ever_held & ~on_robot & (nonrobot > th["CONTACT_N"]) & (~on_top) & _lifted)
    hit_now = a["hit_now"] > 0.5

    # ── 매장 이탈 -- 발자국이 안쪽 면을 넘으면 그 프레임에서 판을 끝낸다 ──────────────
    #
    # 사용자 결정 2026-09-10.  앞 판은 이것을 **위생 검사로만** 봤고, 그래서 두 가지가
    # 어긋나 있었다: 매장 밖 2 m 까지는 아무 벌칙이 없었고, 2 m 를 넘으면 「채점 거부」가
    # 되면서 "로그가 깨진 것과 로봇이 못한 것은 다른 일" 이라고 찍혔다.
    # **로봇이 나간 것은 로봇이 못한 것이다.**
    #
    # 기준이 중심이 아니라 발자국인 이유: 다른 기물의 충돌과 같은 잣대여야 한다 (겹치면
    # 끝, 문턱 없음).  대가는 **벽을 스치기만 해도 판이 끝난다**는 것이고, 사용자가 그
    # 대가를 보고 고른 것이다.  정답 주행 세 판의 여유는 0.975 / 0.360 / 0.340 m 다.
    # 자르기 **전에** 재야 한다 -- 자르는 자리를 정하는 것이 이 값이다.
    yaw_all = _yaw(a["base_quat"])
    out_mm = np.array([R.out_of_store_mm(a["base_pos"][i, :2], yaw_all[i])
                       for i in range(len(a["t"]))], dtype=np.float64)
    outside = out_mm > 0.0

    stop_i, stop_why = None, None
    if dropped.any():
        stop_i, stop_why = int(np.argmax(dropped)), "dropped"
    if hit_now.any():
        j = int(np.argmax(hit_now))
        if stop_i is None or j < stop_i:
            stop_i, stop_why = j, "hit"
    if outside.any():
        j = int(np.argmax(outside))
        if stop_i is None or j < stop_i:
            stop_i, stop_why = j, "out_of_store"
    # **제한 시간을 넘긴 프레임은 없는 것으로 본다.**
    #
    # 하네스가 한 시도를 제한 시간에 자르므로 채점기도 같은 자리에서 잘라야 한다.
    # 예전에는 넘겨도 벌칙이 없었다 -- 실측 2026-09-08: 시계를 100 배로 늘려 판이
    # 5 시간짜리가 되어도 17/21 이 나왔다.
    over = a["t"] > th["TIME_LIMIT_S"]
    if over.any():
        j = int(np.argmax(over))
        if stop_i is None or j < stop_i:
            stop_i, stop_why = max(j - 1, 0), "time_limit"
    if stop_i is not None:
        out["stopped_at_s"] = float(a["t"][stop_i])
        out["stopped_why"] = stop_why
        out["notes"].append(
            f"{a['t'][stop_i]:.1f}초에 "
            + ("바구니가 그리퍼를 벗어나 상판 밖에서 멈췄다 — 판 종료" if stop_why == "dropped"
               else f"제한 시간 {th['TIME_LIMIT_S']:.0f}초를 넘겼다 — 판 종료"
               if stop_why == "time_limit"
               else (f"로봇 발자국이 매장 안쪽 면을 {out_mm[stop_i]:.0f} mm 넘어갔다 "
                     f"— 판 종료") if stop_why == "out_of_store"
               else f"{out['furniture'].get('what') or '매장 가구'} 에 부딪혔다 — 판 종료")
            + f" (기록은 {a['t'][-1]:.1f}초까지 있으나 여기서 자른다)")
        # **여기서 자른다.**  뒤 항목들은 잘린 구간만 본다.
        sl = slice(0, stop_i + 1)
        for _k in ("t", "crate_pos", "crate_quat", "crate_vel", "base_pos", "base_quat",
                   "base_vel", "grip_pos", "grip_force", "crate_net_force",
                   "crate_other_force", "crate_robot_force", "crate_nonrobot_force",
                   "desk_pos", "desk_quat", "hit_now", "hit_depth_mm",
                   "body_force", "body_link"):
            if _k in a:
                a = {**a, _k: a[_k][sl]}
        grip_max, other = grip_max[sl], other[sl]
        out_mm, outside = out_mm[sl], outside[sl]
        robot_touch, nonrobot = robot_touch[sl], nonrobot[sl]
        on_robot, on_grip, free = on_robot[sl], on_grip[sl], free[sl]
        held, gripped, on_top = held[sl], gripped[sl], on_top[sl]
        tilt_all, seated, upright, placed_ok = (tilt_all[sl], seated[sl],
                                                upright[sl], placed_ok[sl])
        # `placed_free` 도 같이 자른다 -- 빼먹으면 길이가 어긋나 아래 `.any()` 가 판 전체를
        # 본다.  이 목록에 새 배열을 더할 때마다 여기도 같이 더해야 한다.
        placed_free = placed_free[sl]
        grip_held, released = grip_held[sl], released[sl]
        seat_mm, over_mm, c_speed = seat_mm[sl], over_mm[sl], c_speed[sl]
        c_speed_reported = c_speed_reported[sl]
        corners = corners[sl]
        out["frames_scored"] = int(stop_i + 1)

    # 벽까지 얼마나 넘었나.  채점에는 「넘었나 아닌가」만 쓰지만, 숫자는 남긴다 -- 이의가
    # 오면 이것으로 답한다 (걸침·속도를 재기만 하는 것과 같은 이유).
    out["store"] = {"left": bool(outside.any()),
                    "worst_out_mm": float(out_mm.max()),
                    "frames_outside": int(outside.sum())}

    # ── 집기 조각만 답할 수 있는 것 ─────────────────────────────────────────────────────
    # **예전에는 토막 이름이 이 문을 열었다** (`if seg == "..."`).  그러면 무엇을 잴지를
    # 로그의 이름표가 정하고, 그 이름표는 채점받는 쪽이 만든다.  실측 2026-09-08:
    # 토막 이름을 지우면 여섯 항목 중 다섯이 아예 안 재져 **4/4 = 100 %** 가 나왔고,
    # 전부 'place' 라고 붙이면 18/18 = 100 % 가 나왔다.
    #
    # 이제 한 시도를 한 타임라인으로 보고 **언제나 다 잰다.**  못 한 일은 「못 잰 것」이
    # 아니라 0 점이다 (`rubric_taskA` 의 분모 고정과 짝이다).
    if True:                     # 들어올림
        z0 = float(a["crate_pos"][0, 2])
        rise = (a["crate_pos"][:, 2] - z0) * 1000.0
        cand = rise >= th["LIFT_OK_MM"]
        out["lift"] = {"peak_mm": float(rise.max())}
        if cand.any():
            ok = cand & gripped
            out["lift"]["gripped"] = bool(ok.any())
            if not ok.any():
                i = int(np.argmax(rise))
                out["lift"]["why_grip"] = (
                    f"{th['LIFT_OK_MM']:.0f} mm 를 넘은 프레임 {int(cand.sum())}개 가운데 "
                    f"그리퍼가 물고 있던 프레임이 없다 (가장 높은 순간 그리퍼 "
                    f"{grip_max[i]:.2f} N, 로봇 아닌 것 {nonrobot[i]:.2f} N)")
        else:
            out["lift"]["gripped"] = False

    # ── 주행 조각만 답할 수 있는 것 ─────────────────────────────────────────────────────
    # **도착은 주행과 놓기 두 조각에서 다 본다.**  평가표는 "[한 번이라도] 목표 지점에
    # 조금이라도 안에 들어가 멈춰 선 적이 있으면 통과" 라고 판 전체를 묻는데, 우리 데이터는
    # 조각으로 나뉘어 있어 주행만 보면 판이 잘린다.
    #
    # 실측 2026-09-02: 주행 기록은 **로봇이 아직 움직이는 동안 끝난다** (seed 0 의 마지막
    # 4 초 중앙 속도 85 mm/s, seed 1 은 56).  실제로 멈추는 것은 그 다음 조각인 놓기의
    # 첫 국면 -- 책상 쪽으로 제자리에서 도는 동안이고, 그때도 목표 구역 안에 있다.
    if True:                     # 도착과 「그 시점에 들고 있었나」
        # ── 도착 구역은 **책상 중심**의 원이다 (사용자 결정 2026-09-09) ──────────────
        #
        # 예전에는 우리가 정한 목표점 반경 0.10 m 원이었다.  그러면 로봇 중심이 목표에서
        # 0.325 m 안에 있어야 하는데, 책상은 목표에서 0.900 m 떨어져 있고 팔은 0.79 m 를
        # 뻗는다 -- **책상에 팔이 닿으면서 구역 밖인 자리가 실제로 있었다**(기하로 확인).
        # 거기 서서 바구니를 잘 놓아도 도착 3점 + 들고 4점을 못 받았다.
        #
        # 반지름은 **씬에서 계산한다**: `|목표 − 책상|`.  우리 씬에서 0.900 m 이고, 팔
        # 도달 거리 0.79 m 보다 크므로 **책상에 놓을 수 있는 자리는 전부 원 안에 들어온다.**
        # 상수로 박지 않는 이유는 책상이나 목적지가 움직이면 구역이 따라가야 하기 때문이다.
        #
        # `scene["goal"]["xy"]` 는 이제 **반지름을 구하는 데만** 쓰인다.  목표점 자체는
        # 판정에 안 들어간다 -- 안 적어 두면 다음 사람이 "목표점을 왜 안 쓰지?" 하고 되돌린다.
        goal = np.asarray(scene["goal"]["xy"], dtype=np.float64)
        desk_xy = np.asarray(scene["desk"]["pos"][:2], dtype=np.float64)
        # **한계를 둔다.**  씬이 책상을 목표에서 멀리 두면 반지름이 그만큼 커진다 -- 시험
        # 삼아 책상을 4 m 옮겼더니 구역이 4.35 m 가 됐고, 그러면 매장 절반이 「도착」이다.
        #
        # 위는 로봇이 서서 책상에 손이 닿을 수 있는 최대 거리에서 왔다: 팔 도달 0.79 m 에
        # 발자국 절반(앞 0.225 / 뒤 0.403) 을 더하면 1.2 m 남짓이고, 1.5 m 면 넉넉하다.
        # 아래는 책상과 목표가 겹친 씬에서 구역이 0 이 되지 않게 하는 바닥이다.
        zone = float(np.clip(np.linalg.norm(goal - desk_xy),
                             R.ARRIVE_ZONE_MIN_M, R.ARRIVE_ZONE_MAX_M))
        # **중심 거리가 아니라 발자국 겹침이다** (사용자 결정 2026-09-02).  규칙 자체는
        # `rubric_taskA.zone_gap_mm` 에 있다 -- 재는 일이 아니라 평가표가 정한 것이므로.
        yaw = _yaw(a["base_quat"])
        edge_mm = np.array([R.zone_gap_mm(a["base_pos"][i, :2], yaw[i], desk_xy, zone)
                            for i in range(len(yaw))], dtype=np.float64)
        in_zone = edge_mm <= 0.0
        gap = np.linalg.norm(a["base_pos"][:, :2] - desk_xy[None, :], axis=1)
        b_speed = _speed(a["base_pos"], a["t"])
        b_speed_reported = _reported_speed(a["base_vel"])

        # ── 멈춤은 **안 본다** (사용자 결정 2026-09-09) ──────────────────────────────
        #
        # 예전에는 구역 안에서 베이스 속도가 10 mm/s 미만인 프레임이 하나라도 있어야 했다.
        # 실측: 구역 안에서 계속 30 mm/s 이상이면 도착·들고 둘 다 실패해 7 점을 잃었다 --
        # 바구니를 잘 놓아도 그랬다.  부드럽게 이어서 놓는 로봇이 손해를 보는 규칙이었다.
        #
        # 속도는 계속 재서 출력에 남긴다.  채점에 안 쓰지만 이의가 오면 그 숫자로 답한다
        # (걸침을 재기만 하는 것과 같은 이유).
        out["arrive"] = {"zone_m": zone, "zone_centre": "desk",
                         "stopped_ever": bool((b_speed < th["STOP_MM_S"]).any()),
                         "nearest_edge_mm": float(edge_mm.min()),
                         "nearest_centre_m": float(gap.min()),
                         "in_zone_frames": int(in_zone.sum()),
                         # 두 방법을 나란히 남긴다 -- 위 `_speed` 머리말의 실측이 이것이다
                         "speed_min_mm_s": float(b_speed.min()),
                         "speed_min_reported_mm_s": float(b_speed_reported.min())}

        # ── 도착은 **구역에 들어왔는가**만 본다 (사용자 결정 2026-09-09) ─────────────
        #
        # 한때 「놓기에 성공해야 도착도 인정」으로 갈 뻔했으나, 그러면 **주행을 다 하고
        # 놓기만 실패한 로봇이 도착 3 점도 못 받는다.**  10 m 를 완주해 책상 앞까지 바구니를
        # 들고 갔는데 마지막에 떨어뜨린 판이 그렇다.  주행 과제이므로 거기까지 간 것 자체를
        # 인정한다 -- 사용자가 그 대가를 보고 되돌렸다.
        #
        # 그래서 도착에는 조건이 하나뿐이다: **발자국이 책상 둘레 구역에 걸친 적이 있는가.**
        # 멈춤도, 놓기도 요구하지 않는다.
        #
        # 빈손으로 가도 3 점을 받는다.  「가져갔는가」는 아래 `held` 4 점이 따로 본다.
        out["arrive"]["reached"] = bool(in_zone.any())
        # 채점에는 안 쓰지만 남긴다 -- "구역 안에서 실제로 얹은 적이 있나" 는 이의가 왔을 때
        # 답이 되는 숫자다.
        out["arrive"]["placed_in_zone_frames"] = int((in_zone & placed_ok).sum())
        if not in_zone.any():
            out["arrive"]["why"] = (
                f"책상 둘레 {zone:.2f} m 구역에 발자국이 한 번도 안 걸쳤다 "
                f"(가장 가까웠던 것이 {edge_mm.min():.0f} mm)")

        # ── 「그 시점에 들고 있었나」는 **구역 안에서** 본다 ─────────────────────────
        #
        # 놓는 프레임에 걸면 안 된다 -- 실측 2026-09-09: 「가장 잘 얹힌 프레임」이 손을 뗀
        # 뒤일 수 있다 (seed 2 는 그 프레임에서 턱이 114.7 mm 벌어져 있었다).  거기 걸면
        # 우리 정답 주행이 깨진다.
        #
        # 뜻은 「가져갔는가」다 -- 바닥으로 밀거나 던져서 올린 로봇은 여기서 걸린다.
        held_in_zone = in_zone & held
        out["arrive"]["held"] = bool(held_in_zone.any())
        out["arrive"]["held_frames"] = int(held_in_zone.sum())
        if in_zone.any() and not held_in_zone.any():
            i = int(np.argmin(np.where(in_zone, gap, np.inf)))
            out["arrive"]["why_held"] = (
                f"구역 안 {int(in_zone.sum())} 프레임 가운데 로봇이 바구니에 닿아 있던 것이 "
                f"없다 (가장 가까운 순간 로봇 {robot_touch[i]:.2f} N, "
                f"로봇 아닌 것 {nonrobot[i]:.2f} N)")
        elif not in_zone.any():
            out["arrive"]["why_held"] = "구역에 들어온 적이 없어 볼 프레임이 없다"

    # ── 놓기 조각만 답할 수 있는 것 ─────────────────────────────────────────────────────
    if True:                     # 책상에 얹었나 + 손 뗀 뒤 6 초
        near_desk = over_mm < 1000.0
        if not near_desk.any():
            out["place"] = {"seat_mm": None, "overhang_mm": None, "tilt_deg": None,
                            "reached_desk": False}
        else:
            # **얹힘과 똑바름을 같은 프레임에서 둘 다 본다** (사용자 결정 2026-09-07:
            # "뒤집어서 놓으면 점수 없어", 판정은 "같은 프레임에서 둘 다").
            #
            # 따로 보면 뒤집힌 채 얹혔다가 나중에 공중에서 똑바로 선 판도 통과한다.
            # 이 항목의 뜻은 「똑바로 얹힌 순간이 한 번이라도 있었나」다.
            #
            # 기울기 문턱은 6 초 창과 **같은 상수**(`TILT_OK_DEG`)를 쓴다.  같은 물음에
            # 문턱을 두 개 두면 언젠가 갈라진다.
            good = placed_ok          # 위에서 한 번만 정했다 -- 도착도 같은 배열을 쓴다
            if good.any():
                i = int(np.argmin(np.where(good, over_mm, np.inf)))
            else:
                i = int(np.argmin(np.abs(seat_mm)))
            out["place"] = {"seat_mm": float(seat_mm[i]), "overhang_mm": float(over_mm[i]),
                            "tilt_deg": float(tilt_all[i]), "reached_desk": True,
                            "at_s": float(a["t"][i]),
                            # 실패했을 때 **무엇 때문인지** 가리려고 둘을 따로 남긴다.
                            "seated_any": bool(seated.any()),
                            "upright_any": bool((seated & upright).any()),
                            # 똑바로 얹힌 **그 순간에 손을 놓고 있었나.**  거짓이면 쥔 채
                            # 댄 것이다 -- 높이·자세가 맞아도 얹은 것이 아니다.
                            "released_any": bool(placed_free.any())}

        # 감시창은 **집게가 풀린 순간**부터 센다 (사용자 결정 2026-09-23: "손 뗀 순간부터",
        # 평가표 문구 「손 뗀 뒤 6초」 그대로).
        #
        # 앞 판은 「로봇 어느 부위와도 안 닿고(`~on_robot`) 상판 ±50 mm 안」이었다.  둘 다 뺐다.
        #   - 로봇 전체 접촉: 편 손을 얹어 둔 판이 창을 영영 못 열었다 (위 「놓았다」 머리말).
        #   - 상판 ±50 mm: 책상 5 cm 넘는 곳에서 놓으면 **떨어지는 도중 어느 프레임이 찍히느냐**
        #     로 결과가 갈렸다.  빼면 공중에서 놓은 판은 늘 높이 검사에서 걸린다.  완결된
        #     여섯 판(GT 3 + job122 3)은 빼도 손 뗀 시각이 한 프레임도 안 바뀐다.
        # 상판 밖에서 놓아 떨어진 것은 위에서 이미 낙하로 판을 끝냈다.
        rel = released
        n_rel, r = _last_release(rel, a["t"])
        if r is None:
            out["watch"] = {"opened": False}
        else:
            w = (a["t"] >= a["t"][r]) & (a["t"] <= a["t"][r] + th["WATCH_S"])
            # **창의 마지막 WATCH_TAIL_S 초** (시트 Sub 3# ④: "창 마지막 0.5초 동안").
            # 창이 6초를 다 못 채우고 로그가 끝났으면 있는 것의 꼬리를 본다.
            t_end = float(a["t"][w].max())
            tail = w & (a["t"] >= t_end - th["WATCH_TAIL_S"])
            s = seat_mm[w]
            # **위아래를 둘 다 보고, 한계를 더 많이 넘은 쪽**을 최악으로 고른다.
            #
            # 앞 판은 「0 아래가 하나라도 있으면 최솟값, 아니면 최댓값」이었다.  하한이 0 일
            # 때는 맞았지만, 하한이 -3 mm 가 된 뒤로는 정상 안착이 늘 -0.8 mm 쯤으로 읽혀서
            # 최솟값만 보게 되고 **위로 들썩인 순간(+5.1 mm)을 한 번도 안 봤다** -- 「5 mm
            # 넘게 뜨면 0 점」이 사실상 꺼져 있었다 (2026-09-11 발견, test_attack ②-c).
            lo, hi = float(s.min()), float(s.max())
            worst_seat = (lo if (-th["SEAT_SINK_MAX_MM"] - lo) > (hi - th["SEAT_ON_MAX_MM"])
                          else hi)
            tilt = np.array([GG.tilt_deg(q) for q in a["crate_quat"][w]])
            # **창 안에서 다시 잡으면 안 된다** (사용자 결정 2026-09-08).
            #
            # 창은 시간만 보고 그 안에서 다시 잡았는지 보지 않았다.  실측 2026-09-08:
            # 놓고 2 초 뒤 다시 잡고 끝까지 들고 있어도 **통과**했다 -- 가만히 붙잡고만
            # 있으면 바구니가 안 움직이기 때문이다.  「손 뗀 뒤 6 초 동안 잘 **놓여**
            # 있었는가」인데 손을 대고 있는 것이다.
            #
            # 바로잡으려고 다시 잡는 것은 상관없다 -- 바로잡고 **다시 놓으면** 그 마지막
            # 놓기부터 창을 새로 세기 때문이다.  걸리는 것은 다시 잡고 끝까지 안 놓는
            # 판뿐이고, 그것은 정렬이 아니라 아직 안 놓은 것이다.
            #
            # 2026-09-23 부터 「다시 잡았다」는 **집게가 다시 물었다**는 뜻이다 -- 편 손을 얹어
            # 두는 것은 괜찮다(사용자 결정).  다만 기하는 벽을 끼웠는지까지는 못 보므로, 바구니
            # 옆에서 빈 집게를 닫아도 다시 문 것으로 읽힌다 (참가자 문서에 알린다).
            hands_off = bool(rel[w].all())

            # **누르다가 바구니가 움직였나** (사용자 결정 2026-09-23: "누르다가 상자가 움직이면,
            # 가점을 부여하지 않는 걸로 하자").
            #
            # 높이·기울기·**마지막 0.5 초 속도**만 보면 옆으로 5 cm 밀려도 끝에 멈춰 있으면
            # 통과한다.  그래서 창 안에서 **처음 제대로 앉은 프레임**(`seated`: 높이 -3~+5 mm
            # 그리고 속도 < 10 mm/s -- 둘 다 기존 기준)의 밑면 네 모서리를 기준으로, 창 끝까지
            # **가장 많이 움직인 모서리**의 수평 거리를 잰다.  중심이 아니라 모서리인 이유:
            # 제자리에서 돌려도 움직인 것이다 (중심만 보면 30 도를 돌려도 0 mm).
            #
            # 실측 (첫 안착 뒤 모서리 최대 이동):
            #   GT 3 판                        0.002 mm
            #   job122 ep2 (손 뗀 뒤 안 건드림)  0.011 mm   -- 실물리 잡음 바닥
            #   job122 ep0 (얹고 누름 32~64 N)   1.95 mm
            #   job122 ep1 (얹고 누름 1~78 N)   14.56 mm   (중심 5.90 mm, 1.4 도 돌음)
            # 문턱은 채점표에서 `DESK_OK_MM` 을 그대로 쓴다 -- 평가표 책상 조항 「2 cm 이상
            # 움직였을 시 가점을 부여하지 않는다」와 같은 형식이다.  15 mm 이상이면 어느 값이든
            # 여섯 판 판정이 같다.  앉은 프레임이 없으면 None -- 높이 검사가 이미 걸러낸다.
            _ws = np.flatnonzero(w & seated)
            if _ws.size:
                _c = corners[_ws[0]:int(np.flatnonzero(w)[-1]) + 1]
                moved_mm = float(np.linalg.norm(_c - _c[0], axis=2).max() * 1000.0)
            else:
                moved_mm = None
            out["watch"] = {"opened": True, "t_release_s": float(a["t"][r]),
                            "hands_off": hands_off,
                            # 몇 번 놓았고 그중 몇 번째를 썼는가.  언제나 마지막이지만
                            # 숫자를 남겨 두어야 "왜 이 시점인가" 에 답할 수 있다.
                            "releases": int(n_rel), "release_index": int(n_rel),
                            "seat_mm": worst_seat,
                            "overhang_mm": float(over_mm[w].max()),
                            "tilt_deg": float(tilt.max()),
                            "tail_speed_mm_s": float(c_speed[tail].max()
                                                     if tail.any() else c_speed[w][-1]),
                            "moved_mm": moved_mm,
                            "window_s": float(t_end - a["t"][r]),
                            "window_frames": int(w.sum())}
            if t_end - a["t"][r] < th["WATCH_S"] - 1e-6:
                out["notes"].append(
                    f"감시창이 {t_end - a['t'][r]:.1f}초밖에 안 된다 "
                    f"(요구 {th['WATCH_S']:.0f}초) — 기록이 먼저 끝났다")
    return out


def merge(parts):
    """조각들을 한 벌로.  [판 내내] 는 가장 나쁜 것, 나머지는 답한 조각의 것."""
    m = {"ended": "time_limit"}
    worst_hit, worst_desk = None, None
    for p in parts:
        for k in ("place", "watch"):
            if k in p:
                m[k] = p[k]
        # 들어올림도 **더 나은 쪽**을 남긴다 (`arrive` 와 같은 이유).
        #
        # 예전에는 `if seg == "pick":` 가 이 값을 집기 조각에서만 냈기 때문에 마지막-승자로
        # 덮어써도 해가 없었다.  위쪽에서 토막 이름을 **안 믿기로** 바꾸면서(그 이름이 곧
        # 공격면이었다) 모든 조각이 `lift` 를 내게 됐는데, 그때 여기를 같이 안 고쳤다.
        # 그래서 놓기 조각의 들림(책상에 내려놓는 동안의 2.77 mm, 안 물고 있음)이 집기
        # 조각의 것(106.37 mm, 물고 있음)을 덮어 `picked` 3 점이 통째로 사라졌다 --
        # 꾸러미 정답지 대조 실측 2026-09-22: seed 0·2·6 이 21/21 이어야 하는데 18/21 이고
        # 여섯 항목 중 어긋난 것은 `picked` 하나였다.
        #
        # 「한 번이라도 쥐고 들었으면」이므로 한 조각에서 통과했으면 판 전체로 통과다.
        if "lift" in p:
            cur = m.get("lift")
            if cur is None or (p["lift"].get("gripped") and not cur.get("gripped")) or (
                    bool(p["lift"].get("gripped")) == bool(cur.get("gripped"))
                    and (p["lift"].get("peak_mm") or -1e9) > (cur.get("peak_mm") or -1e9)):
                m["lift"] = p["lift"]
        # 도착은 두 조각에서 나오므로 **더 나은 쪽**을 남긴다.  [한 번이라도] 이므로
        # 한 조각에서 통과했으면 판 전체로 통과다.
        if "arrive" in p:
            cur = m.get("arrive")
            if cur is None or (p["arrive"].get("reached") and not cur.get("reached")) or (
                    p["arrive"].get("reached") == cur.get("reached")
                    and (p["arrive"].get("nearest_edge_mm") or 1e9)
                    < (cur.get("nearest_edge_mm") or 1e9)):
                m["arrive"] = p["arrive"]
        f = p["furniture"]
        if worst_hit is None or f["worst_mm"] > worst_hit["worst_mm"] or (
                f["hit"] and not worst_hit["hit"]):
            worst_hit = f
        d = p["desk"]
        if worst_desk is None or d["worst_mm"] > worst_desk["worst_mm"]:
            worst_desk = d
        if p.get("stopped_why"):
            m["ended"] = p["stopped_why"]
    m["furniture"] = worst_hit
    m["desk"] = worst_desk
    # **한 판이 세 조각이므로 경과 시간은 조각의 합이다.**  조각마다 스폰에서 다시 시작하니
    # 시계도 0 부터 다시 간다 -- 마지막 조각의 t 만 보면 판이 80초짜리로 보인다.
    m["elapsed_s"] = float(sum(p.get("elapsed_s") or 0.0 for p in parts))
    if m["ended"] == "time_limit" and m["elapsed_s"] <= R.TIME_LIMIT_S:
        # 시간이 남았는데 아무 일도 안 일어나 끝난 것.  시트에는 이 이름이 없지만 `ended` 를
        # 비워 두면 "왜 끝났나" 가 사라진다.
        m["ended"] = "ok" if (m.get("watch") or {}).get("opened") else "time_limit"
    return m


def main():
    ap = argparse.ArgumentParser(description="판정 로그를 채점한다.")
    ap.add_argument("--log", nargs="+", required=True)
    ap.add_argument("--scene", type=str, default=None,
                    help="비우면 로그 머리말이 적어 둔 씬 파일을 쓴다.")
    ap.add_argument("--out", type=str, default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    th = {k: getattr(R, k) for k in ("LIFT_OK_MM", "ARRIVE_ZONE_M", "STOP_MM_S", "CONTACT_N",
                                     "SEAT_ON_MAX_MM", "SEAT_SINK_MAX_MM", "SEAT_NEAR_MM",
                                     "OVERHANG_OK_MM", "TILT_OK_DEG",
                                     "WATCH_S", "WATCH_TAIL_S", "DESK_OK_MM", "TIME_LIMIT_S")}
    parts, heads = [], []
    scene = None
    for p in args.log:
        head, a = load(p)
        heads.append(head)
        if scene is None:
            scene = SS.load(args.scene or head["scene"])
        parts.append(measure_one(head, a, scene, th))

    m = merge(parts)
    result = R.score(m)
    out = {"scene": scene["meta"]["name"], "seat": scene["meta"]["seat"],
           "corridor": scene["meta"]["corridor"],
           "logs": [{"file": str(Path(p).name), "segment": h.get("segment"),
                     "frames": h.get("frames"), "gpu": h.get("gpu"),
                     "injected": h.get("injected"),
                     "drift_from_source": h.get("drift_from_source")}
                    for p, h in zip(args.log, heads)],
           "measured": m, "per_log": parts, "score": result}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    if not args.quiet:
        print(f"씬 {out['scene']}  좌석 {out['seat']}  통로 {out['corridor']}")
        print(f"조각 {len(parts)}개: "
              + ", ".join(f"{p['segment']}({p['frames']}프레임)" for p in parts))
        for p in parts:
            for nte in p["notes"]:
                print(f"  * {p['segment']}: {nte}")
        print()
        print(R.render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
