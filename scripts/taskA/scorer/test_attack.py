# Copyright 2025.
#
# **채점기를 공격한다.**  진짜 만점 로그를 비틀어 넣고, 한 일보다 많은 점수가 나오는지 본다.
#
# 왜 이 파일이 있나
#   채점기는 이제 우리 정답 주행이 아니라 **남의 로봇이 만든 로그**를 읽는다.  "우리 GT 로
#   21/21 이 나온다" 는 더 이상 충분한 검증이 아니다.  2026-09-08 에 열여섯 가지를 넣어 봤고,
#   **비율 100 % 를 공짜로 얻는 길이 다섯 개** 있었다:
#
#       토막 이름을 지운다         4 / 4  = 100 %      ← 항목 다섯이 아예 안 재졌다
#       전부 'place' 라고 한다   18 / 18 = 100 %
#       집기만 하고 끝            7 / 7  = 100 %
#       베이스를 순간이동          21 / 21 = 100 %      ← 주행 없이 도착
#       놓기 토막만 낸다          18 / 18 = 100 %
#
#   뿌리는 하나였다 -- **채점기가 「무엇을 잴지」를 로그더러 정하게 했다.**  그리고 그 로그는
#   채점받는 쪽이 만든다.
#
#   2026-09-14 에 하나 더 막았다 -- **아무것도 안 한 판이 4 / 21** 이었다.  「매장 가구와
#   부딪히지 않았는가」가 부딪힌 적만 없으면 참이었기 때문이다.  이제 그 4 점은 책상 둘레 구역에
#   바구니를 들고 도착한 판만 받는다 (위 표의 「집기만 하고 끝 7」도 그래서 3 이 되었다).
#
# 아래 기대값은 그 구멍을 막은 뒤의 것이다.  **이 파일이 깨지면 구멍이 다시 열린 것이다.**
#
# Run:  python3 scripts/taskA/scorer/test_attack.py

import copy
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import log_check as LC          # noqa: E402
import rubric_taskA as R        # noqa: E402
import score_from_log as SFL    # noqa: E402
import taska_score as T         # noqa: E402

DEMO = os.path.join(os.path.dirname(_HERE), "demos", "demo_06.npz")
if not os.path.isfile(DEMO):
    print("시연 파일이 없다: %s" % DEMO)
    raise SystemExit(1)

META, HEAD, A = T.load(DEMO)
SCENE = T.scene_of(META)
TH = {k: getattr(R, k) for k in T.THRESHOLD_KEYS}
FAIL = []


def attack(label, head=None, a=None, scene=None):
    """공격 하나를 넣고 (점수, 만점, 거부사유) 를 돌려준다.  거부면 점수가 None 이다."""
    head = copy.deepcopy(head if head is not None else HEAD)
    a = {k: np.array(v, copy=True) for k, v in (a if a is not None else A).items()}
    scene = scene if scene is not None else SCENE
    probs = LC.problems(a, head, scene)
    if probs:
        return None, None, probs[0]
    r = R.score(SFL.merge([SFL.measure_one(head, a, scene, TH)]))
    return r["total"], r["possible"], None


def want_score(label, total, possible=21.0, **kw):
    got, pos, why = attack(label, **kw)
    if why is not None:
        FAIL.append("%s: 채점 거부됐다(%s) -- %g/%g 이 나와야 한다" % (label, why[:50], total, possible))
    elif got != total or pos != possible:
        FAIL.append("%s: %s/%s 가 나왔는데 %g/%g 이어야 한다" % (label, got, pos, total, possible))


def want_reject(label, needle, **kw):
    got, _pos, why = attack(label, **kw)
    if why is None:
        FAIL.append("%s: 채점 거부돼야 하는데 %g 점이 나왔다" % (label, got))
    elif needle not in why:
        FAIL.append("%s: 거부는 됐는데 이유가 다르다 -- %r" % (label, why[:70]))


def mut(**over):
    a = {k: np.array(v, copy=True) for k, v in A.items()}
    a.update(over)
    return a


def nan_in(key):
    a = {k: np.array(v, copy=True) for k, v in A.items()}
    a[key] = a[key].astype(np.float64)
    a[key][...] = np.nan
    return a


# ── 0. 기준 ──────────────────────────────────────────────────────────────────────────
want_score("정직한 만점 판", 21.0)

# ── 1. 이름표로 채점 범위를 정하려는 공격 ─────────────────────────────────────────────
# **한 시도는 한 타임라인이다.**  이름표는 판정에 끼어들지 않는다.
want_score("토막 이름을 지운다", 21.0, head={**HEAD, "segment": "?"})
want_score("전부 'place' 라고 한다", 21.0, head={**HEAD, "segment": "place"})
want_score("토막 이름이 아예 없다", 21.0, head={k: v for k, v in HEAD.items() if k != "segment"})

# ── 2. 덜 하고 비율을 벌려는 공격 ─────────────────────────────────────────────────────
# **분모는 언제나 21 이다.**  덜 하면 비율이 나빠진다.
n = len(A["t"])
# 2026-09-14: 둘 다 7 -> 3.  「매장 가구와 부딪히지 않았는가」 4 점은 이제 책상 둘레 구역에
# 바구니를 들고 도착한 판만 받는다.  65 % 에서 자른 로그는 구역에 닿기 전이라(앞 판에서도 도착
# 3 점과 들고 있음 4 점이 안 나와 7 이었다) 집기 3 점만 남는다.
want_score("집기만 하고 끝낸다", 3.0, a={k: v[:int(n * 0.12)] for k, v in A.items()})
want_score("집기+주행만 낸다", 3.0, a={k: v[:int(n * 0.65)] for k, v in A.items()})

# **아무것도 안 한다** -- 로봇도 바구니도 첫 프레임 자리에 가만히 있는 200 프레임(시계만 간다).
# 예전에는 부딪힌 적이 없다는 이유로 4 점이 공짜로 나왔다 (세 판이면 12 / 63).
_idle = {k: (np.array(v[:200], copy=True) if k == "t" or len(v) != n
             else np.repeat(v[:1], 200, axis=0)) for k, v in A.items()}
want_score("아무것도 안 한다", 0.0, a=_idle)

# ── 3. 값을 위조하는 공격 ────────────────────────────────────────────────────────────
# **충돌은 배열로 판정한다.**  머리말이 아니라고 해도 배열이 부딪혔다면 부딪힌 것이다.
got, pos, why = attack("머리말 충돌 위조",
                       head={**HEAD, "hit": {"hit": False}},
                       a=mut(hit_now=np.ones_like(A["hit_now"]),
                             hit_depth_mm=np.full_like(A["hit_depth_mm"], 99.0)))
if why is not None:
    FAIL.append("머리말 충돌 위조: 채점 거부됐다 -- 점수가 나와야 한다")
elif got >= 4.0:
    FAIL.append("머리말 충돌 위조: %g 점이 나왔다 -- 충돌을 인정해 4점 미만이어야 한다" % got)

# ── 4. 로그가 물리적으로 말이 안 되는 공격 -> 채점 거부 ───────────────────────────────
for _k in ("base_pos", "crate_pos", "grip_pos", "desk_pos", "hit_now", "crate_quat"):
    want_reject("%s 가 전부 NaN" % _k, "숫자가 아닌", a=nan_in(_k))
want_reject("시계가 전부 0", "앞으로 가지 않는", a=mut(t=np.zeros_like(A["t"])))
want_reject("시계가 거꾸로 간다", "앞으로 가지 않는", a=mut(t=A["t"][::-1].copy()))
_tel = {k: np.array(v, copy=True) for k, v in A.items()}
_tel["base_pos"][len(_tel["base_pos"]) // 2:] = _tel["base_pos"][0] + 5.0
want_reject("베이스를 순간이동시킨다", "순간이동", a=_tel)
_telc = {k: np.array(v, copy=True) for k, v in A.items()}
_telc["crate_pos"][len(_telc["crate_pos"]) // 2:] = _telc["crate_pos"][0] + 5.0
want_reject("바구니를 순간이동시킨다", "순간이동", a=_telc)
want_reject("쿼터니언을 정규화 안 함", "정규화", a=mut(crate_quat=A["crate_quat"] * 3.0))
want_reject("프레임이 하나뿐", "프레임이", a={k: v[:1] for k, v in A.items()})
want_reject("필수 값이 없다", "필요한 값이 없다",
            a={k: v for k, v in A.items() if k != "desk_pos"})
_far = {k: np.array(v, copy=True) for k, v in A.items()}
_far["base_pos"][:, 0] += 100.0
want_reject("매장 밖으로 나간다", "매장 밖", a=_far)

# ── 5. 시간 ──────────────────────────────────────────────────────────────────────────
# 간격이 일정하면 위생 검사는 통과한다 -- 그것은 **제한 시간**이 잡을 일이다.
got, pos, why = attack("시계를 100배 느리게", a=mut(t=A["t"] * 100.0))
if why is not None:
    FAIL.append("시계 100배: 위생 검사가 잡았다 -- 제한 시간이 잡아야 한다")
elif got is None or got >= 21.0:
    FAIL.append("시계 100배: %s 점이 나왔다 -- 제한 시간에 잘려 만점보다 낮아야 한다" % got)
if R.TIME_LIMIT_S != 600.0:
    FAIL.append("제한 시간이 %g 초다 -- 한 시도 10 분이므로 600 이어야 한다" % R.TIME_LIMIT_S)

# ── 6. 분모가 정말 고정인가 ──────────────────────────────────────────────────────────
for _lab, _a in (("집기만", {k: v[:int(n * 0.12)] for k, v in A.items()}),
                 ("절반만", {k: v[:n // 2] for k, v in A.items()})):
    _t, _p, _w = attack(_lab, a=_a)
    if _w is None and _p != 21.0:
        FAIL.append("%s: 만점이 %s 다 -- 언제나 21 이어야 한다" % (_lab, _p))

# ── 7. 정직한 판이 검사에 걸리지 않는가 ───────────────────────────────────────────────
# **문턱이 좁으면 여기가 먼저 깨진다.**  공격을 막느라 정상을 막으면 안 된다.
for _s in (0, 2, 6):
    _f = os.path.join(os.path.dirname(_HERE), "demos", "demo_%02d.npz" % _s)
    if not os.path.isfile(_f):
        continue
    _m, _h, _arr = T.load(_f)
    _p = LC.problems(_arr, _h, T.scene_of(_m))
    if _p:
        FAIL.append("정답 주행 seed %d 가 위생 검사에 걸렸다: %s" % (_s, _p[0][:70]))
    _r = R.score(SFL.merge([SFL.measure_one(_h, _arr, T.scene_of(_m), TH)]))
    if (_r["total"], _r["possible"]) != (21.0, 21.0):
        FAIL.append("정답 주행 seed %d 가 %g/%g 이다 -- 21/21 이어야 한다"
                    % (_s, _r["total"], _r["possible"]))

# ── 8. 도착 판정 (2026-09-09 결정) ───────────────────────────────────────────────────
# 구역은 **책상 중심** 원이고 반지름은 씬에서 계산한다 (`|목표 − 책상|`, 우리 씬 0.900 m).
# 멈춤도 놓기도 요구하지 않는다.


def _items(a=None, head=None, scene=None):
    a = {k: np.array(v, copy=True) for k, v in (a if a is not None else A).items()}
    head = copy.deepcopy(head if head is not None else HEAD)
    scene = scene if scene is not None else SCENE
    if LC.problems(a, head, scene):
        return None
    return R.score(SFL.merge([SFL.measure_one(head, a, scene, TH)]))["items"]


def want_item(label, key, want, **kw):
    it = _items(**kw)
    if it is None:
        FAIL.append("%s: 채점 거부됐다 -- 점수가 나와야 한다" % label)
    elif it[key]["got"] is not want:
        FAIL.append("%s: %s 가 %s 인데 %s 여야 한다 (%s)"
                    % (label, key, it[key]["got"], want, it[key]["why"][:60]))


# 안 멈추고 지나가며 놓는다 -- 예전에는 도착 실패였다
_dt = float(np.median(np.diff(A["t"])))
_jit = np.zeros_like(A["base_pos"]); _jit[1::2, 1] = 0.200 * _dt      # 200 mm/s 로 계속 흔든다
want_item("안 멈추고 놓는다", "arrived", True, a=mut(base_pos=A["base_pos"] + _jit))

# 책상 둘레 구역 밖에 선다.
#
# **씬의 책상이 아니라 로봇을 옮긴다.**  앞 판은 책상을 매장 반대편 구석에 두었는데, 그
# 씬은 이제 위생 검사가 거부한다 -- 책상은 매장 붙박이라 거기 있을 수 없기 때문이다
# (`log_check.scene_problems`).  시험이 잡으려는 것은 「구역 밖에 선 로봇」이지 「말이 안
# 되는 씬」이 아니므로, 옮겨야 할 것은 로봇 쪽이다.
#
# 앞 판의 주석은 "경로가 남쪽 통로에서 y = -2.75 까지 내려가므로 로봇을 어디로 밀어도
# 책상을 스치거나 매장 밖으로 나간다" 고 적었다.  **틀렸다.**  이동 격자를 전수로 훑어
# 확인했다 (2026-09-09):
#
#     이동 (-1.50, -3.00) m
#       구역 밖 여유 1.43 m   (발자국이 닿는 한계 1.403 m 를 그만큼 넘어선다)
#       매장 안 여유 1.34 m   (위생 검사의 범위 + 2 m 안에 그만큼 남는다)
#       옮긴 뒤 경로  x -11.76 ~ -1.51,  y -5.69 ~ -0.44
#
# 둘 중 나쁜 쪽이 1.34 m 로 가장 큰 이동을 골랐다 -- 문턱을 아슬아슬하게 넘는 시험은
# 나중에 문턱이 조금만 움직여도 조용히 무의미해진다.
#
# 바구니와 손가락도 같이 옮긴다.  로봇만 옮기면 손이 바구니에서 3 m 떨어져 「들고 있다」가
# 기하로 깨지고, 그러면 이 시험이 구역을 재는 것인지 파지를 재는 것인지 흐려진다.
_far = {k: np.array(v, copy=True) for k, v in A.items()}
for _k in ("base_pos", "crate_pos"):
    _far[_k][:, 0] -= 1.50
    _far[_k][:, 1] -= 3.00
_far["grip_pos"][:, :, 0] -= 1.50
_far["grip_pos"][:, :, 1] -= 3.00
want_item("책상 구역 밖에 선다", "arrived", False, a=_far)
want_item("구역 밖이면 들고도 볼 시점이 없다", "held", False, a=_far)

# 구역 안에 들어왔지만 놓기를 실패한다 -> **도착과 들고는 받는다** (2026-09-09 되돌림)
_nodrop = {k: np.array(v, copy=True) for k, v in A.items()}
# 바구니를 상판보다 30 cm 위로 -- 얹힌 적이 없다.  **손가락도 같이 올린다** (안 그러면
# 「들고 있다」까지 같이 깨져서 무엇을 시험하는지 흐려진다).
_nodrop["crate_pos"][:, 2] += 0.30
_nodrop["grip_pos"][:, :, 2] += 0.30
want_item("놓기를 실패해도 도착은 받는다", "arrived", True, a=_nodrop)
want_item("놓기를 실패해도 들고는 받는다", "held", True, a=_nodrop)
want_item("그래도 얹기는 실패", "placed", False, a=_nodrop)
# **6 초 항목도 같이 본다** (2026-09-16).  앞 판은 `placed` 만 단언했는데, 한 번도 안 얹은
# 판이 4 점짜리 이 항목을 받으면 그것도 같은 크기의 구멍이다.  단언하지 않으면 안 잡힌다.
want_item("얹은 적이 없으면 6 초 항목도 없다", "stayed", False, a=_nodrop)

# 바구니를 한 번도 안 들고 구역에 간다 (손가락을 멀리 둔다)
_never = {k: np.array(v, copy=True) for k, v in A.items()}
_never["grip_pos"] = np.tile(_never["crate_pos"][:, None, :]
                             + np.array([0.0, 0.0, 5.0], np.float32),
                             (1, A["grip_pos"].shape[1], 1)).astype(A["grip_pos"].dtype)
want_item("구역 안에서 한 번도 안 들었다", "held", False, a=_never)

# 쥔 채로 상판에 대고만 있는다 -- **놓아야 얹은 것이다** (2026-09-16).
#
# `_never` 와 같은 방식으로 손가락을 옮기되, 이번에는 멀리 두는 대신 **바구니에 붙인다.**
# 바구니 중심에서 ±15 mm 면 표면 안쪽이라 「가깝다」(40 mm)가 늘 참이고, 한 손의 두 끝마디
# 사이가 30 mm 라 「물었다」(60 mm)도 늘 참이다 -- 즉 판 내내 쥐고 있고 손을 뗀 순간이 없다.
#
# 앞 판은 높이·멈춤·똑바름 셋만 봐서 이것을 얹힘으로 통과시켰다.  재현했다: 상판에 닿은
# 65 프레임 내내 턱을 문 사본이 얹힘 3 점을 받았다.
_hold = {k: np.array(v, copy=True) for k, v in A.items()}
_noff = np.zeros((A["grip_pos"].shape[1], 3), np.float32)
_noff[:, 1] = ((np.arange(A["grip_pos"].shape[1]) % 4) // 2) * 0.030 - 0.015
_hold["grip_pos"] = (_hold["crate_pos"][:, None, :]
                     + _noff[None, :, :]).astype(A["grip_pos"].dtype)
want_item("쥔 채 상판에 대고만 있으면 얹힘이 아니다", "placed", False, a=_hold)
want_item("쥔 채로는 감시창도 안 열린다", "stayed", False, a=_hold)
# **헛통과 방지.**  「쥔 채」를 시험하려면 판 내내 쥐고 있어야 한다.  손가락을 잘못 놓아
# 파지가 안 잡히면 위 둘은 여전히 초록이지만 **다른 이유로** 초록이고, 그러면 이 시험은
# 아무것도 지키지 못한다.
# **`HEAD` 여야 한다, `_HD` 가 아니다.**  `_HD`(:501)는 자리띠 시험용으로 `kinematic` 을
# False 로 뒤집어 둔 머리말이라 힘 열로 접촉을 읽는다.  이 시험은 손가락 위치로 만든 것이라
# 기하 경로여야 하고, 무엇보다 위 `want_item` 이 쓰는 머리말과 같아야 같은 것을 잰다.
_phold = SFL.measure_one(copy.deepcopy(HEAD), _hold, SCENE, TH)
_gh = _phold.get("geom_grip") or {}
if not _gh:
    FAIL.append("시험이 틀렸다: 기하 파지 기록이 없어 「쥔 채」를 시험하지 못한다")
elif _gh.get("held_frames") != _gh.get("frames"):
    FAIL.append("시험이 틀렸다: 손가락을 붙였는데 쥔 프레임이 %s/%s 뿐이다 -- 손을 뗀 순간이 "
                "있으면 「쥔 채」를 시험하는 것이 아니다"
                % (_gh.get("held_frames"), _gh.get("frames")))

# 책상을 밀어붙인다 -- **6 초 항목에도 걸려야 한다** (2026-09-16).
#
# 앞 판은 밀림 검사가 「얹음」 가지에만 있어서, 주행 중에 0.5 m 를 밀고도 이 4 점이 그대로
# 나왔다 (재현: 얹음 0 / 6 초 4).
#
# 두 가지를 조심해서 만든다.
#   * **0 번 프레임은 그대로 둔다.**  위생 검사가 장면의 책상과 기록 첫 프레임을 20 mm 로
#     대조하므로, 처음부터 밀어 두면 시험이 「채점 거부」로 끝나 아무것도 못 본다.
#   * **50 mm 만 민다.**  문턱(20 mm)은 확실히 넘되 상판은 안 벗어나는 크기다.  0.5 m 를
#     밀면 바구니가 상판 밖으로 나가 **낙하로 판이 끝나고**, 그러면 이 시험은 통과하되
#     밀림 때문이 아니라 낙하 때문에 통과한다 -- 엉뚱한 이유로 초록인 시험이 제일 나쁘다.
_shove = {k: np.array(v, copy=True) for k, v in A.items()}
_shove["desk_pos"][len(_shove["t"]) // 2:, 0] += 0.050
want_item("책상을 밀면 얹힘이 취소된다", "placed", False, a=_shove)
want_item("책상을 밀면 6 초 항목도 취소된다", "stayed", False, a=_shove)
# **헛통과 방지.**  위 둘이 초록인 이유가 정말 「밀림」인지 확인한다.  많이 밀면 바구니가
# 상판 밖으로 나가 **낙하로 판이 끝나고**, 그러면 같은 초록이 나오되 밀림과는 무관해진다.
# 실측(2026-09-16): 50 mm 에서는 판이 `ok` 로 끝나고 두 항목만 "책상이 50.0 mm 밀렸다" 로
# 떨어진다 -- 나머지 네 항목은 만점 그대로다.
_pshv = SFL.measure_one(copy.deepcopy(HEAD), _shove, SCENE, TH)   # 위 `want_item` 과 같은 머리말
_dshv = (_pshv.get("desk") or {}).get("worst_mm")
if _pshv.get("stopped_why"):
    FAIL.append("시험이 틀렸다: 책상 밀기 판이 %s 로 끝나 밀림을 시험하지 못한다"
                % _pshv["stopped_why"])
elif _dshv is None or _dshv <= TH["DESK_OK_MM"]:
    FAIL.append("시험이 틀렸다: 잰 밀림이 %s mm 라 문턱(%.0f)을 안 넘는다 -- 시험이 무의미하다"
                % (_dshv, TH["DESK_OK_MM"]))

# 구역 반지름이 씬에서 계산되고, **한계 안에 머무는가.**
#
# 반지름은 `|목표 − 책상|` 인데 씬이 책상을 멀리 두면 그만큼 커진다 -- 시험 삼아 4 m 옮겼더니
# 4.35 m 가 나왔고, 그러면 매장 절반이 「도착」이 된다.  그래서 위아래로 한계를 뒀다.
_wide = copy.deepcopy(SCENE)
_wide["desk"]["pos"] = [_wide["desk"]["pos"][0] + 4.0, _wide["desk"]["pos"][1],
                        _wide["desk"]["pos"][2]]
_m = SFL.measure_one(copy.deepcopy(HEAD), {k: np.array(v, copy=True) for k, v in A.items()},
                     _wide, TH)
if _m["arrive"]["zone_m"] > R.ARRIVE_ZONE_MAX_M + 1e-9:
    FAIL.append("책상을 4 m 옮겼더니 구역이 %.2f m 다 -- 한계 %.2f m 를 넘으면 안 된다"
                % (_m["arrive"]["zone_m"], R.ARRIVE_ZONE_MAX_M))
_tight = copy.deepcopy(SCENE)
_tight["desk"]["pos"] = [_tight["goal"]["xy"][0], _tight["goal"]["xy"][1],
                         _tight["desk"]["pos"][2]]
_m2 = SFL.measure_one(copy.deepcopy(HEAD), {k: np.array(v, copy=True) for k, v in A.items()},
                      _tight, TH)
if _m2["arrive"]["zone_m"] < R.ARRIVE_ZONE_MIN_M - 1e-9:
    FAIL.append("책상과 목표가 겹친 씬에서 구역이 %.2f m 다 -- 바닥 %.2f m 아래로 가면 안 된다"
                % (_m2["arrive"]["zone_m"], R.ARRIVE_ZONE_MIN_M))
# 우리 씬은 한계 사이에 편안히 들어와야 한다
_base = SFL.measure_one(copy.deepcopy(HEAD), {k: np.array(v, copy=True) for k, v in A.items()},
                        SCENE, TH)
if not (R.ARRIVE_ZONE_MIN_M < _base["arrive"]["zone_m"] < R.ARRIVE_ZONE_MAX_M):
    FAIL.append("우리 씬의 구역이 %.2f m 로 한계에 붙어 있다 (%.2f ~ %.2f)"
                % (_base["arrive"]["zone_m"], R.ARRIVE_ZONE_MIN_M, R.ARRIVE_ZONE_MAX_M))


# ── 씬을 아무도 안 보고 있었다 (2026-09-09) ────────────────────────────────────────────
#
# 도착 7 점이 통째로 **씬의 책상 좌표** 위에 서 있다 -- 구역의 중심이 책상이고 반지름이
# |목표 − 책상| 이기 때문이다.  그런데 위생 검사는 로그만 보고 씬은 그냥 믿고 있었다
# (그 함수의 주석이 "`scene` 은 지금 쓰지 않지만 자리를 남겨 둔다" 였다).
#
# 이것은 참가자 공격이 아니다 -- 시뮬 환경을 우리가 내주므로 참가자는 씬을 못 건드린다.
# **우리 실수**를 잡는 검사다.  두 좌표는 `destinations.json` 에서 오고 그것은 매장 USD 를
# 다시 구울 때마다 다시 뽑아야 하는 파생 파일이다.  잘못 뽑히면 구역이 조용히 옮겨가고
# 오류도 경고도 안 난다.
def want_refused(label, scene=None, a=None):
    _a = {k: np.array(v, copy=True) for k, v in (a if a is not None else A).items()}
    probs = LC.problems(_a, copy.deepcopy(HEAD), scene if scene is not None else SCENE)
    if not probs:
        FAIL.append("%s: 채점을 거부해야 하는데 통과시켰다" % label)


def want_accepted(label, scene=None, a=None):
    _a = {k: np.array(v, copy=True) for k, v in (a if a is not None else A).items()}
    probs = LC.problems(_a, copy.deepcopy(HEAD), scene if scene is not None else SCENE)
    if probs:
        FAIL.append("%s: 멀쩡한데 거부했다 -- %s" % (label, probs[0][:70]))


want_accepted("진짜 씬은 통과한다")

# 열쇠가 없다.  **앞 판은 여기서 KeyError 로 죽었다** -- 채점 거부가 아니라 프로그램이
# 멈춘다.  여러 판을 이어 채점하는 중이면 거기서 전부 멈추고, 앞 결과가 저장 전이면 잃는다.
for _k in ("desk", "goal"):
    _gone = copy.deepcopy(SCENE); _gone.pop(_k)
    want_refused("씬에 '%s' 가 없다" % _k, scene=_gone)
_empty = copy.deepcopy(SCENE); _empty["desk"] = {}
want_refused("씬의 desk 에 좌표가 없다", scene=_empty)

# NaN.  이것이 앞 판에서 **도착 3 점 + 들고 4 점을 무조건 주던** 입력이다 (1,409 프레임
# 전부가 구역 안으로 잡혔다).  이제 두 겹으로 막힌다 -- 위생 검사가 거부하고, 뚫려도
# `zone_gap_mm` 이 inf 를 낸다.
_nan = copy.deepcopy(SCENE); _nan["desk"]["pos"] = [float("nan")] * 3
want_refused("씬의 책상 좌표가 NaN", scene=_nan)
_nang = copy.deepcopy(SCENE); _nang["goal"]["xy"] = [float("nan")] * 2
want_refused("씬의 목표 좌표가 NaN", scene=_nang)
# 뚫렸다 치고 채점기 자신도 닫히는가 (두 겹의 두 번째)
_m3 = SFL.measure_one(copy.deepcopy(HEAD), {k: np.array(v, copy=True) for k, v in A.items()},
                      _nan, TH)
if _m3["arrive"]["reached"] or _m3["arrive"]["held"]:
    FAIL.append("씬이 NaN 인데 도착/들고가 참이다 -- zone_gap_mm 이 아직 새고 있다")

# 붙박이 자리에서 벗어난 책상·목표.  **이것이 진짜 잡고 싶은 것**이다 -- NaN 은 눈에 띄기라도
# 하지만, 「정상처럼 보이는 틀린 숫자」는 오류도 경고도 없이 구역만 조용히 옮긴다.
for _d in (0.05, 0.40, 3.00):
    _off = copy.deepcopy(SCENE)
    _off["desk"]["pos"] = [SCENE["desk"]["pos"][0], SCENE["desk"]["pos"][1] + _d,
                           SCENE["desk"]["pos"][2]]
    want_refused("책상이 붙박이 자리에서 %.2f m 어긋났다" % _d, scene=_off)
_offg = copy.deepcopy(SCENE)
_offg["goal"]["xy"] = [SCENE["goal"]["xy"][0], SCENE["goal"]["xy"][1] + 0.40]
want_refused("목표가 붙박이 자리에서 0.40 m 어긋났다", scene=_offg)

# 문턱 바로 아래는 통과해야 한다 -- 좌표를 소수 5 자리로 반올림해 싣는 것 때문에 멀쩡한
# 판이 거부되면 안 된다.  허용치는 `DESK_OK_MM` 을 그대로 쓴다 (같은 물음, 같은 문턱).
_ok = copy.deepcopy(SCENE)
_ok["desk"]["pos"] = [SCENE["desk"]["pos"][0], SCENE["desk"]["pos"][1] + 0.019,
                      SCENE["desk"]["pos"][2]]
want_accepted("책상이 19 mm 어긋난 것은 봐준다", scene=_ok)

# 씬과 로그가 서로 다른 판의 것이다.
_mis = {k: np.array(v, copy=True) for k, v in A.items()}
_mis["desk_pos"][:, 1] += 0.50
want_refused("씬의 책상과 로그의 책상이 0.50 m 어긋난다", a=_mis)


# ── 매장 이탈이 실제 로그에서 잡히나 (2026-09-10) ──────────────────────────────────────
#
# 벽은 단단하다 (`taskA_colliders._SOLID_TYPES` 에 "Cube" 가 있고 벽은 Cube 다) -- 그래서
# 그냥 밀고 나갈 수는 없다.  그래도 규칙을 두는 이유는 **넘어지는 방향** 때문이다: 앞 판은
# 나가면 벌칙이 없거나(매장 밖 2 m 까지) 「채점 거부」였고, 둘 다 "로봇이 못했다" 가 아니다.
#
# **이탈은 주행 중에 일으켜야 한다.**  판 전체를 평행이동하면 바구니가 책상에서 벗어나
# `dropped` 가 먼저 걸려서, 무엇을 시험하는지 흐려진다 (첫 판이 그래서 틀렸다).
# 쥐고 있는 구간(프레임 55~1827)의 한가운데에서 남쪽으로 밀어낸다 -- 그 동안은 로봇이
# 바구니를 쥐고 있으므로 낙하가 성립하지 않는다.
if not (A["base_pos"][:, 1].min() > R.STORE_Y[0] + 0.503):
    FAIL.append("합성 정답 로그가 이미 남쪽 벽에 붙어 있다 -- 시험의 전제가 깨졌다")

_out = {k: np.array(v, copy=True) for k, v in A.items()}
_n = len(_out["t"])
_a, _b = int(_n * 0.45), int(_n * 0.55)
_ramp = np.zeros(_n)
_ramp[_a:_b] = np.linspace(0.0, -3.0, _b - _a)      # 남쪽으로 3 m, 서서히 (순간이동 검사 회피)
_ramp[_b:] = -3.0
for _k in ("base_pos", "crate_pos"):
    _out[_k][:, 1] += _ramp
_out["grip_pos"][:, :, 1] += _ramp[:, None]

_p = SFL.measure_one(copy.deepcopy(HEAD), _out, SCENE, TH)
if _p.get("stopped_why") != "out_of_store":
    FAIL.append("매장 밖으로 나갔는데 판이 %r 로 끝났다 -- out_of_store 여야 한다"
                % _p.get("stopped_why"))
if not (_p.get("store") or {}).get("left"):
    FAIL.append("매장 밖으로 나갔는데 store.left 가 참이 아니다")
if LC.problems(_out, copy.deepcopy(HEAD), SCENE):
    FAIL.append("이탈 로그가 위생 검사에 걸렸다 -- 채점 거부가 아니라 판 종료여야 한다")
_s = R.score(SFL.merge([_p]))
if _s["items"]["placed"]["points"] or _s["items"]["stayed"]["points"]:
    FAIL.append("매장 밖으로 나갔는데 놓기 점수가 남아 있다")
if _s["possible"] != 21.0:
    FAIL.append("이탈 판의 분모가 %s 다 -- 21 이어야 한다" % _s["possible"])
if _s["ended"] != "out_of_store":
    FAIL.append("이탈 판의 ended 가 %r 다" % _s["ended"])

# **안 나간 판은 건드리지 않는다.**  이 규칙이 멀쩡한 주행을 자르면 그게 더 나쁘다.
_pi = SFL.measure_one(copy.deepcopy(HEAD),
                      {k: np.array(v, copy=True) for k, v in A.items()}, SCENE, TH)
if (_pi.get("store") or {}).get("left"):
    FAIL.append("멀쩡한 주행이 이탈로 찍혔다")
if _pi.get("stopped_why") == "out_of_store":
    FAIL.append("멀쩡한 주행이 이탈로 잘렸다")

# 이탈이 충돌보다 **먼저** 일어나면 이탈이 이긴다 (가장 이른 사유가 이긴다)
_both = {k: np.array(v, copy=True) for k, v in _out.items()}
_both["hit_now"] = np.array(_both["hit_now"], copy=True)
_both["hit_now"][-1] = 1.0                       # 맨 마지막에 충돌을 심는다
_pb = SFL.measure_one(copy.deepcopy(HEAD), _both, SCENE, TH)
if _pb.get("stopped_why") != "out_of_store":
    FAIL.append("이탈이 충돌보다 먼저인데 %r 로 끝났다" % _pb.get("stopped_why"))

# 거꾸로: 충돌이 먼저면 충돌이 이긴다
_hit1 = {k: np.array(v, copy=True) for k, v in _out.items()}
_hit1["hit_now"] = np.array(_hit1["hit_now"], copy=True)
_hit1["hit_now"][int(_n * 0.20)] = 1.0
_ph = SFL.measure_one(copy.deepcopy(HEAD), _hit1, SCENE, TH)
if _ph.get("stopped_why") != "hit":
    FAIL.append("충돌이 이탈보다 먼저인데 %r 로 끝났다" % _ph.get("stopped_why"))


# ── 「떨어진 것」과 「파고든 것」을 가르는 것은 **속도**다 (2026-09-10, 이슈 #3) ─────────
#
# 얹힘 판정에 아래쪽 여유를 준 이상, 그 여유가 «통과 중인 프레임»까지 삼키면 안 된다.
# 가르는 것은 띠의 너비가 아니라 **받쳐져 멈춰 있나**이다:
#
#     얹힌 바구니      속도 0
#     떨어지는 바구니   낙하 속도 그대로
#     오버슛 프레임     낙하 속도 그대로 (실측: seat -5.344 mm 인 프레임의 vz 가 -2.779 m/s.
#                                      한 적분 스텝 8.3 ms 에 23 mm 를 지나간 위치다)
def _place_frame(a, scene):
    """상판에 처음 앉는 프레임 번호."""
    topz = float(scene["desk"]["pos"][2]) + float(scene["desk"]["size"][2])
    seat = (a["crate_pos"][:, 2].astype(np.float64) - topz) * 1000.0
    idx = np.flatnonzero((seat >= -2.0) & (seat <= 3.0))
    return int(idx[0]) if idx.size else None


def _physics(a, i0):
    """놓기 전에는 로봇이 쥐고, 놓은 뒤에는 책상이 받치는 힘을 채운다 (참가자 판의 모양)."""
    a["crate_robot_force"][:i0] = 5.0
    a["crate_robot_force"][i0:] = 0.0
    a["crate_nonrobot_force"][:i0] = 0.0
    a["crate_nonrobot_force"][i0:] = 12.0
    return a


_HD = copy.deepcopy(HEAD)
_HD["kinematic"] = False
_i0 = _place_frame(A, SCENE)
_dt = float(np.median(np.diff(A["t"])))

# ① 정상 안착: 실측 겹침만큼 파고든 채 **멈춰 있다** -> 얹힘이다
_ok = _physics({k: np.array(v, copy=True) for k, v in A.items()}, _i0)
_top = float(SCENE["desk"]["pos"][2]) + float(SCENE["desk"]["size"][2])
_ok["crate_pos"][_i0:, 2] = _top - 0.000804
_r = R.score(SFL.merge([SFL.measure_one(copy.deepcopy(_HD), _ok, SCENE, TH)]))
if _r["items"]["placed"]["points"] == 0 or _r["items"]["stayed"]["points"] == 0:
    FAIL.append("정상 안착(-0.804 mm, 멈춤)이 얹힘으로 안 잡힌다 -- 이슈 #3 이 되돌아왔다")
if _r["ended"] != "ok":
    FAIL.append("정상 안착인데 판이 %r 로 끝났다" % _r["ended"])

# ② **적분 오버슛**: 떨어져 내려오다 한 프레임만 상판 아래에 찍히고 다음 프레임에 앉는다.
#
#    실측 그대로의 모양이다 (배포 이미지, 낙하 400 mm, 120 Hz, 3 회 재현):
#        스텝 31  seat +17.819 mm  vz -2.698 m/s
#        스텝 32  seat  -5.344 mm  vz -2.779 m/s   <- 아직 낙하 속도다.  눌린 것이 아니다
#        스텝 33  seat  -1.075 mm  vz -0.031 m/s
#
#    **낙하로 찍히면 안 되고**(그 프레임은 통과 중이다), 그 뒤 앉은 프레임들로 얹힘은 받아야 한다.
#    앞 판은 이 한 프레임 때문에 판이 끝났다.
_ov = _physics({k: np.array(v, copy=True) for k, v in A.items()}, _i0)
_ov["crate_pos"][_i0 - 2, 2] = _top + 0.0400          # 내려오는 중
_ov["crate_pos"][_i0 - 1, 2] = _top + 0.0178
_ov["crate_pos"][_i0, 2] = _top - 0.005344            # 한 프레임만 상판 아래를 지나간다
_ov["crate_pos"][_i0 + 1:, 2] = _top - 0.000804       # 그 다음부터 앉아서 안 움직인다
_p = SFL.measure_one(copy.deepcopy(_HD), _ov, SCENE, TH)
if _p.get("stopped_why") == "dropped":
    FAIL.append("오버슛 한 프레임이 낙하로 찍혔다 -- on_top 의 자가 너무 좁다")
_rov = R.score(SFL.merge([_p]))
if _rov["items"]["placed"]["points"] == 0:
    FAIL.append("오버슛 뒤에 제대로 앉았는데 얹힘을 못 받았다")
# 그리고 **그 통과 프레임 자체는 얹힘이 아니어야 한다** -- 멈춤 조건이 하는 일이 이것이다
_seat_ov = (_ov["crate_pos"][_i0, 2] - _top) * 1000.0
if -TH["SEAT_SINK_MAX_MM"] <= _seat_ov <= TH["SEAT_ON_MAX_MM"]:
    FAIL.append("시험이 틀렸다: 오버슛 프레임(%.3f mm)이 띠 안에 있어 멈춤 조건을 시험 못 한다"
                % _seat_ov)

# ②-b **띠 안에 있는데 움직이는 프레임**은 얹힘이 아니어야 한다.
#
#    ② 의 오버슛(-5.3 mm)은 띠 밖이라 띠만으로도 걸러진다.  멈춤 조건이 진짜로 일하는지
#    보려면 **띠 안(-1 mm)인데 낙하 속도인** 프레임을 넣어야 한다.  그 조건이 없으면
#    아래쪽 여유를 넓힌 것이 곧 「통과 중인 프레임도 얹힘」이 된다.
#
#    자유낙하 식으로는 이 프레임을 못 만든다 -- 10 Hz 로 표본하는데 상판을 지날 때 속도가
#    2 m/s 대라 한 프레임에 200 mm 넘게 움직이고, 폭 8 mm 인 띠를 통째로 건너뛴다.
#    (그 자체가 안심할 근거이기도 하다: 그냥 떨어지는 바구니는 띠에 거의 안 찍힌다.)
#    그래서 그 한 프레임을 **손으로 놓는다.**
_thr = {k: np.array(v, copy=True) for k, v in A.items()}
_k = _i0 + 4
_thr["crate_pos"][:, 2] = _top + 0.300              # 위에 떠 있다가
_thr["crate_pos"][_k - 1, 2] = _top + 0.230
_thr["crate_pos"][_k, 2] = _top - 0.001             # <- 띠 안(-1 mm)인데
_thr["crate_pos"][_k + 1:, 2] = _top - 0.230        #    앞뒤로 230 mm 씩 움직인다 (2.3 m/s)
_thr["crate_robot_force"][:] = 0.0
_thr["crate_robot_force"][:_i0] = 5.0               # 그 전에는 쥐고 있었다
_thr["crate_nonrobot_force"][:] = 0.0               # 아무것도 안 받친다
_sthr = (_thr["crate_pos"][:, 2].astype(np.float64) - _top) * 1000.0
_inband = int(((_sthr >= -TH["SEAT_SINK_MAX_MM"]) & (_sthr <= TH["SEAT_ON_MAX_MM"])).sum())
_pthr = SFL.measure_one(copy.deepcopy(_HD), _thr, SCENE, TH)
_rthr = R.score(SFL.merge([_pthr]))
if _inband == 0:
    FAIL.append("시험이 틀렸다: 띠 안 프레임을 못 만들어 멈춤 조건을 시험 못 한다")
elif _rthr["items"]["placed"]["points"]:
    FAIL.append("받쳐지지도 멈추지도 않고 띠를 지나가기만 했는데 얹힘을 줬다 "
                "(띠 안 프레임 %d 개) -- 멈춤 조건이 일하지 않는다" % _inband)

# ②-c **6 초 창은 위아래를 둘 다 본다.**
#
#    정상 안착은 이제 -0.8 mm 쯤으로 읽힌다.  앞 판은 「0 아래가 하나라도 있으면 최솟값만」
#    이라 그 뒤 위로 들썩인 순간을 한 번도 안 봤다 -- 5.9 초 잘 있다가 0.1 초 +5.1 mm 로
#    들린 판이 4 점을 받았다.  아래로 3 mm 넘게 파고든 순간도 같이 걸려야 한다.
for _lbl, _bump, _want in (("0.1 초 +5.1 mm 들썩", +0.0051, 0.0),
                           ("0.1 초 -3.1 mm 파고듦", -0.0031, 0.0),
                           ("0.1 초 +4.9 mm (띠 안)", +0.0049, 4.0)):
    _bw = _physics({k: np.array(v, copy=True) for k, v in A.items()}, _i0)
    _bw["crate_pos"][_i0:, 2] = _top - 0.000804
    _bw["crate_pos"][_i0 + 30, 2] = _top + _bump        # 놓고 3 초 뒤 한 프레임
    _rb = R.score(SFL.merge([SFL.measure_one(copy.deepcopy(_HD), _bw, SCENE, TH)]))
    if _rb["items"]["stayed"]["points"] != _want:
        FAIL.append("-0.8 mm 로 앉았다가 %s 인데 6초 항목이 %g 점이다 (%g 점이어야 한다)"
                    % (_lbl, _rb["items"]["stayed"]["points"], _want))

# ③ 한 번도 안 받쳐지고 바닥까지 떨어진다 -> 얹힘이 아니고 낙하로 끝나야 한다
_fall = {k: np.array(v, copy=True) for k, v in A.items()}
_n = len(_fall["t"]) - _i0
_t = np.arange(_n) * _dt
_z = np.maximum(0.003 - 0.5 * 9.81 * _t ** 2, -0.725)
_fall["crate_pos"][_i0:, 2] = _top + _z
_fall["crate_robot_force"][:_i0] = 5.0
_fall["crate_robot_force"][_i0:] = 0.0
_fall["crate_nonrobot_force"][:_i0] = 0.0
_fall["crate_nonrobot_force"][_i0:] = np.where(_z <= -0.7249, 12.0, 0.0)
_rf = R.score(SFL.merge([SFL.measure_one(copy.deepcopy(_HD), _fall, SCENE, TH)]))
if _rf["items"]["placed"]["points"] or _rf["items"]["stayed"]["points"]:
    FAIL.append("한 번도 안 얹히고 바닥까지 떨어졌는데 놓기 점수가 남았다")
if _rf["ended"] != "dropped":
    FAIL.append("바닥까지 떨어졌는데 판이 %r 로 끝났다 -- dropped 여야 한다" % _rf["ended"])

# ④ 기준면이 책상을 따라간다: 책상 높이만 바꿔도 같은 놓기는 같은 점수여야 한다
#    (이슈 #3 의 핵심.  앞 판은 여기서 18/21 대 11/21 로 갈렸다)
_scores = {}
for _dz in (0.000, 0.002, 0.010):
    _sc = copy.deepcopy(SCENE)
    _sc["desk"]["pos"] = [_sc["desk"]["pos"][0], _sc["desk"]["pos"][1], _dz]
    _aa = _physics({k: np.array(v, copy=True) for k, v in A.items()}, _i0)
    _aa["desk_pos"][:, 2] = _dz
    _aa["crate_pos"][_i0:, 2] = (_dz + float(SCENE["desk"]["size"][2])) - 0.000804
    _scores[_dz] = R.score(SFL.merge([SFL.measure_one(copy.deepcopy(_HD), _aa, _sc, TH)]))["total"]
if len(set(_scores.values())) != 1:
    FAIL.append("책상 높이만 바꿨는데 점수가 갈린다 %r -- 기준면이 책상을 안 따라간다" % _scores)


if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print("공격 전부 막혔다 (정답 주행 3판은 그대로 21/21)")
