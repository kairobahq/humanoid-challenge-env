# Copyright 2025.
#
# 과제 B 궤적 채점기 -- `평가표.xlsx` 의 Task-B 시트를 그대로 코드로 옮긴 것.
#
# 상품 하나에 15항목 TOTAL 점이다 (2026-09-07 시트: B12 4점 · B16 4점으로 올라 34점). 판정은 시트가 정한 두 가지뿐이다:
#
#   [한 번이라도]  판이 도는 내내 보고, 한 번이라도 참이면 점수. 뒤에 무슨 일이 생겨도 뺏지 않는다.
#   [그 시점에]    채점 종료의 한 순간에 한 번만 보고 판정한다.
#
# [그 시점에] 인 것 중 **B12~B18 과 B20** 은 상품을 선반에 내려놓았을 때만 점수가 된다 (사용자
# 2026-09-09). 든 채 끝났거나 바닥에 떨어뜨렸으면 0이다 -- 진열을 마치지 못한 판이라 볼 것이 없다.
# **B19(파란 상자)만 예외로 그대로 둔다** -- 상자는 진열을 마쳤든 아니든 탁자 위에 있어야 하고,
# 사용자가 09-09 에 바꾸라고 한 것은 B12 와 B20 둘이다.
#
# 감점 항목은 없다. 문턱값과 무엇을 재는지는 시트의 H열("simulation 평가 로직 구현 관련")에서
# 왔고, 아래 THRESHOLD 에 한 곳으로 모았다. 시트가 「아직 안 잰 값」이라 표시한 다섯
# (30 mm · 300 mm · 15° · 45° · 45°) 은 2026-09-03 에 잰 결과를 그 옆에 적었다.
#
# 채점 로직(ProductScorer)은 Isaac 을 모른다 -- numpy 와 기하 상수만 쓴다. 그래서 입구가 둘이다:
#
#   score_npz(path)      state npz(task_b_episode.py 가 쓰는 것, humanoid-challenge-env 의
#                        taskB/demos/demo_*.npz 도 같은 형식)를 읽어 프레임을 먹인다. 접촉력은 없지만
#                        B6 는 상품이 상자 안에서 움직였는가(또는 들렸는가)로 재서 TOTAL 점 만점이다.
#   ProductScorer 직접   판이 도는 중에 프레임마다 .update() 를 부르고, 놓은 뒤 3초에 .finish().
#                        접촉 센서 값(contact_N)을 주면 B6 는 그것으로도 참이 된다.
#
# 채점 종료는 시트대로 둘뿐이다. 둘 다 채점기가 스스로 찾는다:
#   놓은 뒤 3초   잡고 있던 손의 gripper 가 열리는 프레임 + 3초 (score_npz 가 관절 기록에서 찾는다)
#   떨어짐        상자 밖으로 나온 뒤 어느 판에도 안 놓인 채 바닥에 밑면이 닿은 그 순간. 그 뒤는 안 본다
#
# 그리고 시트 [심사 유의사항]의 조합 중단 하나 -- 그 순간까지의 점수가 최종 점수다:
#   상자가 탁자에서 떨어짐   상자 중심이 탁자 윗면 아래로 내려간 프레임 (crate_off_table)
#   ~~탁자가 10 cm 넘게 움직임~~ 은 채점 기준에서 뺐다 (사용자 2026-09-07)
#
# 시트와 다르게 둔 것 셋 -- 전부 사용자 결정 2026-09-03, THRESHOLD 옆에 적혀 있다:
#   B15 뒷줄 상품과 위아래가 같은가   진열 자세 15° 가 아니라 뒷줄 같은 상품의 z 축과 같은 쪽
#                 (< 45°, ~~90°~~ 사용자 2026-09-07). 항목 이름은 ~~서 있는가~~ 였다 -- 그 이름은
#                 **거꾸로 선 것**(위아래만 뒤집혀 그대로 서 있는 상자, 실측 538판)이 0점인 것을
#                 안 담아서, 사진을 보고 채점이 틀린 줄 알게 된다 (사용자 2026-09-08)
#   B16 방향        45° 가 아니라 뒷줄 같은 상품 기준 ±90° (~~180°~~ 사용자 2026-09-08)
#   B9~B11 사다리   상자 밖으로 꺼낸(B8) 뒤부터 센다 (3층 목표에서 상자 속 상품이 프레임 0에 B10 을 넘던 구멍)
#
# 이 파일은 저장소의 다른 코드를 부르지 않는다. taskB_shelf / taskB_restock / taskB_table 세 모듈은
# 패키지 __init__ 을 타지 않고 파일 경로로 읽는다 -- 패키지가 isaaclab 과 toml 을 끌어오기 때문이고,
# humanoid-challenge-env/scripts/task_b_replay.py 가 같은 이유로 같은 방법을 쓴다.
#
#   python3 scripts/tools/taskb_score.py <state.npz> [...]         판마다 TOTAL 점 표
#   python3 scripts/tools/taskb_score.py --glob '<dir>/*.npz' --json out.json

import argparse
import glob
import importlib.util
import json
import math
import os
import sys

import numpy as np

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _object_dir():
    """세 모듈이 있는 폴더. 이 저장소 안이면 그 자리, 배포 이미지(humanoid-challenge-env)면 $CYCLOLAB_PATH."""
    for cand in (os.environ.get("CYCLO_OBJECT_DIR"),
                 f"{_REPO}/source/cyclo_lab/cyclo_lab/assets/object",
                 f"{os.environ.get('CYCLOLAB_PATH', '/workspace/cyclo_lab')}/source/cyclo_lab/cyclo_lab/assets/object"):
        if cand and os.path.isfile(f"{cand}/taskB_restock.py"):
            return cand
    raise SystemExit("taskB_restock.py 를 찾지 못했다 -- CYCLO_OBJECT_DIR 또는 CYCLOLAB_PATH 를 확인하라")


_OBJ = _object_dir()


def _by_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


taskB_shelf = _by_path("taskB_shelf", f"{_OBJ}/taskB_shelf.py")
taskB_table = _by_path("taskB_table", f"{_OBJ}/taskB_table.py")
taskB_restock = _by_path("taskB_restock", f"{_OBJ}/taskB_restock.py")

# ---- 기하 -- 전부 코드에서 읽는다. 여기 적은 숫자는 주석이다 ---------------------------------
FRONT_X = 0.47                                   # 선반 앞면 x (pick_stance.py:94 FRONT_X)
BOARD_TOPS = tuple(float(v) for v in taskB_shelf.BOARD_TOPS)   # (0.100, 0.4022, 0.7461, 1.1555, 1.600)
SHELF_W, SHELF_D = float(taskB_shelf.SIZE[0]), float(taskB_shelf.SIZE[1])   # 0.900 · 0.3566
CRATE_H = float(taskB_table.CRATE_SIZE[2])       # 0.140 -- 상자 origin 은 바닥이라 테두리 = z + 0.140
TABLE_TOP = float(taskB_table.TABLE_TOP)         # 0.725
COLS = int(taskB_restock.COLS)                   # 3
CELL_HALF = float(taskB_restock.COL_PITCH) / 2.0  # 0.140 -- 칸 구역: 칸 중심 좌우 140 mm
FRONT_ROW_X = FRONT_X + taskB_restock.FRONT_MARGIN + taskB_restock.ROW_PITCH / 2.0   # 0.640 -- 앞줄/뒷줄의 금

# ---- 문턱값 -- 시트 H열. ※ 는 시트가 「아직 안 잰 값」이라 표시한 것과 그 실측 ------------------
THRESHOLD = {
    "touch_N": 0.5,          # B6  상품에 붙은 접촉 센서가 팔꿈치 아래 로봇 바디와 이보다 세게 닿은 순간.
                             #     **이것 하나로만 판정한다** (사용자 2026-09-21: "상품이 접촉센서에 닿아야한다는
                             #     말이야"). 2026-09-03 의 "부딪히거나 하면 점수" 를 상품이 상자 안에서 2 mm 움직였거나
                             #     30 mm 들렸으면 닿은 것으로 읽었던 것이 틀렸다 -- 상자를 밀거나 로봇이 지나가며 낸
                             #     진동으로도 상품은 움직이고, 그러면 그리퍼가 상품에 한 번도 안 닿은 판이 점수를 받는다.
                             #     실제로 평가 서버에서 그렇게 받은 판이 있었다 (제출 #39, A1_touch 1점, 접촉 0.0 N).
                             #     0.5 N 은 평가 환경의 판정기 `taskb_restock_judge.py` 의 `touch_N` 과 같은 값이다
    "grip_contact_min_n": 0.5,
                             # B7·B8 「쥐고 있다」를 정하는 값 (사용자 결정 2026-09-22: 부하가 아니라 **접촉**으로).
                             #     상품에 붙은 접촉 센서가 그리퍼 마디와 이보다 세게 닿은 프레임을 「닿음」으로 보고,
                             #     그것이 grip_hold_s 이상 이어진 구간을 「쥐고 있다」로 본다. 0.5 N 은 touch_N 과 같은 값.
                             #     실측 2026-09-22 (step 22000, episode 33개 전부 계측): 96 초에 손에 있던 2 개는 접촉이
                             #     81.80 s · 72.85 s 이어졌고 든 동안에도 61.37 N · 52.43 N 이 걸려 있었다. 한 번 들었다
                             #     놓친 1 개(92016)는 75.20 s · 201.53 N. 반대로 손을 편 채 B7 2 점을 받은 92024 는
                             #     접촉이 6.12 N 으로 0.05 초(프레임 2 개)뿐이고 든 동안은 0.00 N 이었다.
                             #     그 전 규칙(그리퍼 관절 각도/부하)은 **빈손도 통과시킨다** -- step 16000 의 92004 는
                             #     접촉이 프레임 600 개 전부 0.00 N 인데 B7 2 점을 받았다 (MISTAKES §206).
    "grip_hold_s": 0.3,      # B7·B8 위 접촉이 이만큼 이어져야 쥔 것으로 본다. 평가 환경 판정기
                             #     `taskb_restock_judge.py` 의 `grip_hold_s` 와 같은 값이다.
    "grip_closed_rad": 0.3,  # B7·B8 **접촉 칸이 없는 옛 기록에서만** 쓰는 대체값. 그 프레임에 잡은 손의
                             #     `gripper_{l|r}_joint1` 이 이 값 이상이면 쥐고 있다고 본다.
                             #     쥐지 않은 채 오른 상품은 점수가 아니다 (사용자 결정 2026-09-22:
                             #     *"A1_lift 와 A1_out은 로봇이 상품을 박스에서 잘 들어올렸냐를 평가하는거야"*).
                             #     실측 2026-09-22: 시연 7판이 쥔 프레임 0.68~0.93 rad, 평가 33판이 쥔 프레임
                             #     0.63~1.01 rad, 손을 편 채 상품이 오른 프레임은 전부 0.013 rad 이하.
                             #     0.3 은 그 사이의 빈 구간이다 (덩어리 한가운데에 두지 않는다, MISTAKES §82).
                             #     열림은 어느 기록에서나 0.000~0.001 rad 라 절대값으로 잰다.
    "lift_mm": 30.0,         # B7  ※ 실측 2026-09-03: 성공한 pick 2,284판의 들어올림 최소 101.8 mm, 30 미만 0판.
                             #     실패한 pick 은 로컬 표본에 없어 「끌린 것」쪽 분포는 못 쟀다
    "near_shelf_mm": 300.0,  # B9  ※ 실측: passed 3,133판 x 최대 최소 0.513, refused 164판 중 160판도 넘음.
                             #     사다리의 첫 칸이라 후한 것이 맞다
    "upright_deg": 45.0,     # B15 뒷줄 같은 상품의 z 축과 같은 쪽을 보는가 -- 각도 < 45° (사용자 2026-09-07).
                             #     각도는 0~180° 라 **누운 것(90° 언저리)과 거꾸로 선 것(180° 언저리)이 둘 다**
                             #     탈락한다. 거꾸로 선 것도 0점인 것은 사용자 결정이다 (2026-09-08).
                             #     ※ 실측 passed 3,116판의 분포는 세 덩어리다: 0~10° 531 · 70~100° 2,051(누움) · 170~180° 524(거꾸로),
                             #     40~70° 사이는 3판. 09-03 의 90° 선은 누운 덩어리 한가운데라 80~90° 의 1,123판이 「서 있음」이 됐다
                             #     시트 "눕혀서 진열하는 상품은 누워 있는 것이 통과" (oreo_strawberry, taskb_orientation.json
                             #     upright: false) 는 따로 안 둔다 -- 진열 자세에서 하늘을 보던 축을 견주므로 누운
                             #     진열 자세가 곧 기준이다 (`up_angle_deg`).
                             #     ~~실측: oreo 의 진열 자세 대비 tilt 0.0°~~ 이 근거는 틀렸다 -- `tilt_deg` 로 잰 값인데
                             #     B15 가 쓰는 것은 `up_angle_deg` 였고, 그때의 `up_angle_deg` 는 **몸통 z 축**을 봤다.
                             #     oreo 는 진열 자세에서 몸통 z 가 옆을 봐서(90°) 제 자세로 누워 있어도 58~179° 가 나왔다.
                             #     2026-09-09 에 `up_angle_deg` 를 「진열에서 하늘 보던 축」으로 고쳐서 막았다 (MISTAKES §88)
    "facing_deg": 90.0,      # B16 뒷줄 같은 상품 기준 ±90° (사용자 2026-09-08, ~~180°~~ ~~45°~~).
                             #     B15(위아래)를 통과한 판만 본다. 제자리에서 돌아간 각도이고 0~180° 로 나온다.
                             #     ±180° 이던 동안에는 서 있기만 하면 방향 4점이 무조건 붙어 거르는 것이 없었다.
                             #     실측 B15 통과 563판: 0~30° 118 · 30~60° 56 · 60~90° 96 · 90~120° 101 ·
                             #     120~150° 72 · 150~180° 120 -- 이 선에서 293판이 방향 4점을 잃는다.
                             #     분포가 고르게 퍼져 있어 선 둘레에 골짜기가 없다. 사용자가 정한 값이다
    "still_mm_s": 10.0,      # B18
    "watch_s": 3.0,          # 시트: 놓은 뒤 3초에 판정한다
    "crate_tilt_deg": 45.0,  # B19 ※ 실측: passed 3,133판 중 45° 안 3,127
    "crate_moved_mm": 20.0,  # B19 파란 상자가 첫 자리에서 xy 로 이만큼 넘게 밀렸으면 0점 (시트·발표 대본 "2 cm 이상 움직이지
                             #     않았다면", 사용자 2026-09-07). 실측: passed 3,133판 최대 4.9 mm, pick 2,284판 중 넘는 판 9
    "neighbour_deg": 15.0,   # B20 시트 B15 의 옛 자(진열 자세 대비 15°)를 그대로 쓴다
    "neighbour_moved_mm": 5.0,  # B20 이웃이 판 안에 이만큼 넘게 밀렸으면 「건드려 움직였다」 (사용자 2026-09-07: "로봇에 의해
                             #     상품이 움직이면 가점은 없다"). 실측 passed 3,133판: 손 안 댄 이웃의 흔들림 상위 1 % 가 0.1 mm,
                             #     5 mm 넘게 밀린 판 5(5.1~15.2 mm). 2 mm 로 두면 로봇이 1 m 떨어져 있을 때 물리가 한 번 튄
                             #     2.0~2.3 mm 짜리(demo_05 의 3층 말차 송이 등 셋)까지 걸려서 5 mm 다 (사용자 2026-09-07)
}

# ---- 시트 -- id · Sub Task · 배점 · 판정 종류 · 평가 항목(B열 그대로) -------------------------
RUBRIC = (
    ("B6", "A-1", 1, "ever", "product 에 닿았는가"),
    ("B7", "A-1", 2, "ever", "product 를 들어올렸는가"),
    ("B8", "A-1", 3, "ever", "product 를 상자 밖으로 꺼냈는가"),
    ("B9", "A-2", 2, "ever", "product 를 선반 앞까지 가져갔는가"),
    ("B10", "A-2", 2, "ever", "product 를 목표 층 높이까지 올렸는가"),
    ("B11", "A-2", 2, "ever", "product 를 목표 칸 바로 앞까지 가져갔는가"),
    ("B12", "A-2", 4, "at", "product 를 끝까지 떨어뜨리지 않았는가"),   # 2026-09-07 시트: 3 → 4
    ("B13", "A-3", 2, "at", "목표 층에 올렸는가"),
    ("B14", "A-3", 4, "at", "어느 칸에 넣었는가"),
    ("B15", "A-3", 2, "at", "뒷줄 상품과 위아래가 같은가"),   # 2026-09-08 사용자: ~~서 있는가~~
    ("B16", "A-3", 4, "at", "방향이 맞는가"),                          # 2026-09-07 시트 C16: 1 → 4 (D16 은 1로 남아 있어 사용자 결정 09-07)
    ("B17", "A-3", 1, "at", "앞줄인가"),
    ("B18", "A-3", 1, "at", "멈췄는가"),
    ("B19", "A-4", 2, "at", "파란색 상자가 탁자 위에 그대로 있는가"),
    ("B20", "A-4", 2, "at", "선반 위 다른 상품들이 그대로 서 있는가"),
)
POINTS = {r[0]: r[2] for r in RUBRIC}
TOTAL = sum(POINTS.values())     # 34 (2026-09-07). 화면·문서는 이 이름을 쓴다 -- 30 을 박아 두면 시트가 바뀔 때 거짓이 된다
assert TOTAL == 34


# ---- 쿼터니언 (w, x, y, z) -- task_b_episode.py 의 것과 같다 ------------------------------
def qmul(a, b):
    aw, ax, ay, az = (float(v) for v in a)
    bw, bx, by, bz = (float(v) for v in b)
    return (aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw)


def qinv(q):
    return (float(q[0]), -float(q[1]), -float(q[2]), -float(q[3]))


def qrot(q, v):
    p = qmul(qmul(q, (0.0, float(v[0]), float(v[1]), float(v[2]))), qinv(q))
    return (p[1], p[2], p[3])


def tilt_deg(q, display_quat):
    """진열 자세에서 하늘을 보는 축이 지금 하늘에서 몇 도 기울었나 (task_b_episode.py:4085 held_tilt)."""
    up = qrot(qinv(display_quat), (0.0, 0.0, 1.0))
    return math.degrees(math.acos(max(-1.0, min(1.0, qrot(q, up)[2]))))


def up_angle_deg(q, display_q, q_ref, display_ref):
    """놓은 상품과 뒷줄 상품이 **같은 쪽을 보고 있는가** -- 각자 진열 자세에서 하늘을 보던 축이
    둘 사이에 몇 도 벌어졌나 (B15).

    몸통 z 축이 아니라 이 축을 쓴다. 세워 두는 상품은 진열 자세에서 몸통 z 가 곧 위라서 둘이
    같지만, 눕혀 두는 상품(`taskb_orientation.json` 의 upright: false -- 실측 2026-09-09 기준
    oreo_strawberry 하나)은 몸통 z 가 옆을 봐서, 제자리에 제 자세로 누워 있어도 좌우로 돌아간
    만큼 각도가 벌어진다.

    실측 2026-09-09, 로컬 전수 7,506판: 제 진열 자세로 놓인 oreo 9판 중 6판이 몸통 z 로는
    58~179° 가 나와 0점이었고, 이 축으로 재면 0.6~1.8° 다. 세워 두는 상품 4,306판은 판정이
    하나도 안 바뀐다 (두 축이 같아서다 -- 진열 자세에서 몸통 z 가 하늘과 이루는 각 0.0°).
    """
    up_a = qrot(qinv(display_q), (0.0, 0.0, 1.0))
    up_b = qrot(qinv(display_ref), (0.0, 0.0, 1.0))
    a, b = qrot(q, up_a), qrot(q_ref, up_b)
    return math.degrees(math.acos(max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]))))


def _pose_word(up_deg):
    """위아래 차이를 사람 말로. 숫자만 보면 178° 가 왜 0점인지 사진과 어긋나 보인다.

    실측 3,408판이 세 덩어리다: 0~15° 559 · 45~135° 2,307(누움) · 165~180° 536(거꾸로 섬).
    거꾸로 선 것은 상자라서 그대로 서 있고, 그래서 사진만 보면 잘 놓인 것처럼 보인다.
    그것이 0점인 것은 사용자 결정이다 (2026-09-08).
    """
    if up_deg < THRESHOLD["upright_deg"]:
        return "똑바로 섬"
    return "거꾸로 섬" if up_deg > 180.0 - THRESHOLD["upright_deg"] else "누움"


def yaw_between_deg(q, q_ref):
    """제자리에서 돌아간 각도 -- 두 자세의 차이 회전에서 수직축 성분만. 둘 다 서 있을 때 뜻이 있다."""
    w, x, y, z = qmul(q, qinv(q_ref))
    return abs(math.degrees(math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))))


def col_of(y):
    """좌우 위치가 세 칸 중 어느 칸 구역(칸 중심 ±CELL_HALF)에 드는가. 없으면 None."""
    for c in range(COLS):
        if abs(y - slot_y(c)) <= CELL_HALF:
            return c
    return None


def slot_y(col):
    return float(taskB_restock.slot_positions(BOARD_TOPS[0], FRONT_X)[col][1])


def underside_z(p, q, size):
    """상품의 밑면 높이 -- 바깥 상자(size)를 지금 자세로 돌려 아래로 얼마나 뻗는지 (task_b_episode.py:5816)."""
    ax, ay, az = qrot(q, (1.0, 0.0, 0.0)), qrot(q, (0.0, 1.0, 0.0)), qrot(q, (0.0, 0.0, 1.0))
    half = 0.5 * (abs(ax[2]) * float(size[0]) + abs(ay[2]) * float(size[1]) + abs(az[2]) * float(size[2]))
    return float(p[2]) - half


# 밑면이 판 윗면에서 이 안에 있으면 「판 위에 놓였다」. 위로 15 mm 는 놓인 상품의 잰 분포(통과한 3,150판의
# 중앙값 -1.0 mm), 아래로 60 mm 는 눕힌 상품의 바깥 상자가 실제 몸통보다 커서 파묻힌 것으로 읽히는 폭
# (5,155판에서 -15~-41 mm 에 몰림, -41~-100 은 한 판도 없음). 둘 다 task_b_episode.py:5827·5851 의 값이다.
# 이 자를 안 대면 허공에 든 채 칸 앞에 멈춘 상품이 「칸에 넣었다」로 찍힌다 -- 2026-09-03 대조에서 refused
# 24판 전부가 그렇게 8점을 받았다.
ON_BOARD_MM = (-60.0, 15.0)


def board_under(p, q, size):
    """어느 층 판 위에 놓였나. (층, 밑면-판 mm) 를 돌려주고, 어느 판에도 안 놓였으면 (None, 가장 가까운 mm)."""
    if not (FRONT_X <= p[0] <= FRONT_X + SHELF_D and abs(p[1]) <= SHELF_W / 2.0):
        return None, None
    u = underside_z(p, q, size)
    best = None
    for k, top in enumerate(BOARD_TOPS[:-1]):
        d = (u - top) * 1000.0
        if ON_BOARD_MM[0] <= d <= ON_BOARD_MM[1]:
            return k, round(d, 1)
        if best is None or abs(d) < abs(best):
            best = d
    return None, round(best, 1)


class ProductScorer:
    """상품 하나(시트의 A)를 채점한다. 프레임마다 update(), 채점 종료에 finish().

    `target` 은 (층, 칸) 이고 `gaps` 는 그 판의 빈 칸 전부 [(층, 칸), ...] (목표 포함) -- 시트의
    「다른 빈 칸: 2점」을 가르는 데 쓴다. 층은 taskB_shelf.BOARD_TOPS 의 index(시트의 3층 = 2, 4층 = 3),
    칸은 열 번호 0..2 다.

    `neighbours` 는 {열쇠: (진열 자세 quat, size)} -- 원래 선반에 서 있던 나머지 상품. update 에 같은
    열쇠로 (pos, quat) 를 넘긴다. `back_key` 는 목표 칸 뒷줄의 같은 상품 열쇠(있으면) -- B16 이 견줄 상대.
    """

    def __init__(self, name, target, gaps, neighbours, back_key=None, hz=10.0):
        self.name = name
        self.done = False          # 채점 종료 뒤에는 update 가 아무것도 안 한다
        self.layer, self.col = int(target[0]), int(target[1])
        self.gaps = {(int(a), int(b)) for a, b in gaps}
        self.display_quat = tuple(float(v) for v in taskB_restock.stock_orientation(name)[1])
        self.size = tuple(float(v) for v in taskB_restock.product(name)["size"])
        self.neighbours = dict(neighbours)   # {열쇠: (진열 자세 quat, size)}
        self.neighbours0 = {}                # {열쇠: 첫 프레임 pos} -- B20 밀림은 여기서부터 잰다
        self.neighbour_moved_mm = {}         # {열쇠: 판 안 최대 xy 이동 mm}
        self.back_key = back_key
        self.ever = {r[0]: None for r in RUBRIC if r[3] == "ever"}   # 처음 참이 된 프레임 번호
        self.z0 = None
        self.rim = None
        self.in_crate0 = None
        self.crate0 = None
        self.crate_moved_max_mm = 0.0
        self.lift_max_mm = 0.0
        self.moved_max_mm = 0.0
        self.moved_at_touch_mm = None
        self.contact_at_touch_N = None
        self.open_lift_frames = 0     # 손을 편 채 상품이 30 mm 넘게 올라가 있던 프레임 수
        self.n = 0
        self.last = None
        self.result = None

    # ---- [한 번이라도] ----------------------------------------------------------------------
    def update(self, t, product_pos, product_quat, crate_pos, crate_quat, shelf, contact_N=None,
               speed_mm_s=None, held=None):
        """프레임 하나. shelf 는 {열쇠: (pos, quat)}. contact_N 은 상품에 단 센서가 읽은 힘(없으면 None).

        `held` 는 **그 프레임에 로봇이 그 상품을 쥐고 있었나**다 (없으면 None). B7·B8 은 쥔 프레임에서만
        점수가 된다 -- 쓸어 내거나 쳐서 올라간 것은 들어올린 것이 아니다. None 이면 잴 것이 없으므로
        예전처럼 위치만 본다.

        떨어짐을 스스로 감지한다: 상자 밖으로 나온 뒤(B8) 상품이 어느 판에도 안 놓인 채 바닥에 밑면을
        대는 그 프레임에 finish("dropped") 를 부르고 `done` 이 된다 -- 시트: "상품이 바닥에
        떨어지면 그 상품의 평가는 거기서 끝난다. 떨어진 상품을 다시 줍는 것은 허용하지 않는다".
        그 뒤의 update 는 무시된다.

        조합 중단도 여기서 본다 (시트 [심사 유의사항]): 상자가 탁자에서 떨어지면 finish("crate_off_table") --
        그 순간까지의 점수가 최종이다. ~~탁자가 10 cm 넘게 움직임~~ 은 09-07 에 채점 기준에서 뺐다 (사용자).
        """
        if self.done:
            return
        p = np.asarray(product_pos, dtype=float)
        # 상품을 상자 좌표계로 -- 상자를 통째로 밀어도 이 값은 안 변하고, 상품을 건드리면 변한다 (B6)
        in_crate = np.asarray(qrot(qinv(crate_quat), p - np.asarray(crate_pos, dtype=float)), dtype=float)
        if self.n == 0:
            self.z0 = float(p[2])
            self.in_crate0 = in_crate
            # 테두리 높이는 상수가 아니라 상자가 탁자에 자리 잡은 뒤의 z 에서 잰다 (시트 B8 ※).
            self.rim = float(crate_pos[2]) + CRATE_H
            self.crate0 = np.asarray(crate_pos, dtype=float)
            self.crate_moved_max_mm = 0.0
            self.neighbours0 = {k: np.asarray(shelf[k][0], dtype=float) for k in self.neighbours if k in shelf}
        # B19 -- 상자가 첫 자리에서 xy 로 얼마나 밀렸나, 판 안 최대
        self.crate_moved_max_mm = max(self.crate_moved_max_mm,
                                      float(np.linalg.norm(np.asarray(crate_pos, dtype=float)[:2] - self.crate0[:2])) * 1000.0)
        # B20 -- 이웃이 첫 자리에서 xy 로 얼마나 밀렸나, 판 안 최대 (넘어지지 않아도 건드려 움직였으면 0점)
        for k, p0 in self.neighbours0.items():
            if k in shelf:
                d = float(np.linalg.norm(np.asarray(shelf[k][0], dtype=float)[:2] - p0[:2])) * 1000.0
                if d > self.neighbour_moved_mm.get(k, 0.0):
                    self.neighbour_moved_mm[k] = d
        self.lift_max_mm = max(self.lift_max_mm, (float(p[2]) - self.z0) * 1000.0)
        moved_mm = float(np.linalg.norm(in_crate - self.in_crate0)) * 1000.0
        self.moved_max_mm = max(self.moved_max_mm, moved_mm)
        lifted = (float(p[2]) - self.z0) * 1000.0 > THRESHOLD["lift_mm"]
        hit = {
            # 닿았다 = 상품에 붙은 접촉 센서가 팔꿈치 아래 로봇 바디와 이만큼 세게 닿았다. 그것 하나뿐이다.
            # 상품이 움직였다는 것도, 들렸다는 것도 여기서는 안 본다 (위 THRESHOLD["touch_N"] 주석 참고).
            "B6": contact_N is not None and float(contact_N) > THRESHOLD["touch_N"],
            # **쥔 채로여야 점수다** (사용자 결정 2026-09-22). `held` 를 안 주면 예전처럼 위치만 본다.
            "B7": lifted and (held is not False),
            "B8": float(p[2]) > self.rim and (held is not False),
        }
        if lifted and held is False:
            self.open_lift_frames += 1
        # 사다리 순서: 선반 앞 · 목표 층 높이 · 목표 칸 앞은 **상자 밖으로 꺼낸 뒤부터** 센다 (사용자 2026-09-03).
        # 안 그러면 3층 목표에서는 상자 속에 그냥 놓인 상품(중심 0.755~0.790)이 판 윗면 0.7461 을 이미 넘어
        # 프레임 0에 B10 을 통과한다.
        out = self.ever["B8"] is not None or hit["B8"]
        hit["B9"] = out and float(p[0]) > FRONT_X - THRESHOLD["near_shelf_mm"] / 1000.0
        hit["B10"] = out and float(p[2]) > BOARD_TOPS[self.layer]
        # B11 은 앞의 둘이 **같은 프레임에서** 참이면서 좌우가 목표 칸 구역 안일 때다.
        hit["B11"] = hit["B9"] and hit["B10"] and abs(float(p[1]) - slot_y(self.col)) <= CELL_HALF
        for k, v in hit.items():
            if v and self.ever[k] is None:
                self.ever[k] = int(t)
                if k == "B6":
                    self.moved_at_touch_mm = moved_mm
                    self.contact_at_touch_N = float(contact_N)
        self.last = (int(t), p, tuple(float(v) for v in product_quat),
                     np.asarray(crate_pos, dtype=float), tuple(float(v) for v in crate_quat),
                     shelf, contact_N, speed_mm_s)
        self.n += 1
        # ---- 채점 종료 ①: 떨어짐 = 상자 밖으로 나온 뒤, 어느 판에도 안 놓인 채 **바닥에 밑면이 닿은**
        # 그 순간. 바닥은 바닥이다 -- 탁자 위나 상자 속은 여기서 보지 않는다 (사용자 2026-09-03). 기다리지도
        # 않는다: 바닥에 놓여 있으면 떨어뜨린 것이다.
        # "테두리 아래" 만으로 가르면 안 된다: 오른손이 상품을 낮게(z 0.67~0.75) 든 채 서 있는 판(demo_02·03)이
        # 떨어진 것으로 찍힌다 -- 든 상품은 공중에 있고 떨어진 상품은 바닥에 닿아 있다. 자는 판 위 판정과 같은
        # ON_BOARD_MM 이다.
        if self.ever["B8"] is not None:
            q = tuple(float(v) for v in product_quat)
            if board_under(p, q, self.size)[0] is None and self._on_floor(p, q):
                self.finish("dropped")
                return
        # ---- 조합 중단: 파란 상자가 탁자에서 떨어짐 = 상자 중심이 탁자 윗면 아래 (B19 와 같은 자)
        if float(crate_pos[2]) + CRATE_H / 2.0 < TABLE_TOP:
            self.finish("crate_off_table")
            return

    def _on_floor(self, p, q):
        """상품의 밑면이 바닥(z = 0)에 닿아 있나. 허용 폭은 판 위 판정과 같은 ON_BOARD_MM."""
        u = underside_z(p, q, self.size)
        return ON_BOARD_MM[0] / 1000.0 <= u <= ON_BOARD_MM[1] / 1000.0

    # ---- [그 시점에] ------------------------------------------------------------------------
    def finish(self, reason="last"):
        """채점 종료. 마지막으로 update 한 프레임을 그 시점으로 본다. `reason` 은 왜 여기서 끝났는지.

        두 번 불려도 처음 결과를 돌려준다 -- 떨어짐으로 스스로 끝난 뒤에 부르는 쪽이 또 finish 해도 점수가
        안 바뀐다.
        """
        if self.result is not None:
            return self.result
        self.done = True
        t, p, q, cp, cq, shelf, contact_N, speed = self.last
        m = {}   # 잰 값 -- 점수 옆에 같이 남긴다
        pts = {}

        for k in self.ever:
            pts[k] = POINTS[k] if self.ever[k] is not None else 0
        m["moved_in_crate_max_mm"] = round(self.moved_max_mm, 1)
        m["moved_at_touch_mm"] = None if self.moved_at_touch_mm is None else round(self.moved_at_touch_mm, 1)
        m["contact_at_touch_N"] = None if self.contact_at_touch_N is None else round(self.contact_at_touch_N, 2)
        m["lift_max_mm"] = round(self.lift_max_mm, 1)
        m["open_lift_frames"] = self.open_lift_frames
        m["rim_z"] = round(self.rim, 4)

        # B12 -- 시트: 떨어뜨려서 끝난 것이 아니면 통과. 「떨어뜨렸다」는 **편의점 바닥**에 떨어진 것뿐이다 (사용자
        # 2026-09-07: 상자 속으로 떨어졌다가 다시 집어 진열하면 허용). 그래서 바닥 감지(update 의 finish("dropped"))가
        # 울린 판만 떨어진 것이고, 끝 프레임에 밑면이 어느 선반 판에 닿아 있으면 놓은 것, 둘 다 아니면 든 채 끝난
        # 것(시간 초과 · refused · 상자 속)이다. ~~테두리보다 낮으면 떨어진 것~~ 은 09-07 에 뺐다 -- 상자 위치가 이상한
        # 판 6개에서 손에 든 상품(z 0.87~0.92)이 떨어진 것으로 찍혔다.
        lay, m["under_mm"] = board_under(p, q, self.size)
        placed = lay is not None
        dropped = reason == "dropped"
        m["end_reason"] = "placed" if placed else ("dropped" if dropped else "in_hand")
        m["end_by"] = reason
        # **선반에 내려놓았을 때만 점수다** (사용자 2026-09-09). 든 채 끝났으면(시간 초과 · refused ·
        # 상자 속에 둔 채) 「끝까지 떨어뜨리지 않았다」를 물을 자리가 아니다 -- 진열을 마치지 못한 것이다.
        # ~~떨어뜨려서 끝난 것이 아니면 통과~~ 는 이날 바뀌었다: 그때는 실패한 pick 2,593판이 4점을 받았다.
        pts["B12"] = POINTS["B12"] if placed else 0

        # ---- 아래 여섯(B13~B18)은 시트가 「놓은 뒤 3초」에 보는 것이다. 놓지 않았으면 볼 것이 없다: 든 채
        # 끝났거나 떨어뜨렸으면 전부 0. 이 관문이 없으면 칸 앞 허공에 든 상품이 8점을 받는다 (2026-09-03 대조).
        m["layer"], m["z"] = lay, round(float(p[2]), 4)
        m["x"] = round(float(p[0]), 4)
        col = col_of(float(p[1]))
        m["col"], m["off_y_mm"] = col, round((float(p[1]) - slot_y(self.col)) * 1000.0, 1)
        m["cell"] = (lay, col) if placed and col is not None else None
        m["tilt_deg"] = round(tilt_deg(q, self.display_quat), 1)
        m["speed_mm_s"] = None if speed is None else round(float(speed), 2)
        m["yaw_deg"], m["facing_ref"] = None, None
        m["up_deg"], m["up_ref"] = None, None
        for k in ("B13", "B14", "B15", "B16", "B17", "B18"):
            pts[k] = 0

        if placed:
            # B13 -- 목표 층 판 위인가 (밑면이 닿은 판이 곧 층이다)
            pts["B13"] = POINTS["B13"] if lay == self.layer else 0

            # B14 -- 좌우로 여섯 칸 중 어느 칸. 목표 4 · 비어 있던 다른 칸 2 · 그 밖 0
            if m["cell"] == (self.layer, self.col):
                pts["B14"] = 4
            elif m["cell"] in self.gaps:
                pts["B14"] = 2

            # B15 -- 뒷줄 같은 상품과 z 축이 같은 쪽인가 (사용자 2026-09-03: "진열된 상품이랑 동일한 방향으로 서
            # 있으면 돼. z방향이 같으면"). 뒷줄이 없으면 진열 자세(stock_orientation)의 z 축과 견준다.
            # 각도를 접지 않는다 -- 접으면 180° 가 0° 가 되어 거꾸로 선 것이 통과한다 (사용자 2026-09-08: 0점).
            if self.back_key and self.back_key in shelf:
                m["up_ref"] = self.back_key
                # 뒷줄 상품의 진열 자세는 그 상품 것을 쓴다 (거의 늘 같은 상품이지만 가정하지 않는다)
                back_disp = (self.neighbours[self.back_key][0]
                             if self.back_key in self.neighbours else self.display_quat)
                m["up_deg"] = round(up_angle_deg(q, self.display_quat,
                                                 shelf[self.back_key][1], back_disp), 1)
            else:
                m["up_ref"] = "display"
                m["up_deg"] = round(up_angle_deg(q, self.display_quat,
                                                 self.display_quat, self.display_quat), 1)
            upright = m["up_deg"] < THRESHOLD["upright_deg"]
            pts["B15"] = POINTS["B15"] if upright else 0

            # B16 -- 서 있을 때만. 뒷줄의 같은 상품과 견주고, 뒷줄이 없으면 진열 자세 자체와 견준다
            if upright:
                if self.back_key and self.back_key in shelf:
                    ref, m["facing_ref"] = shelf[self.back_key][1], self.back_key
                else:
                    ref, m["facing_ref"] = self.display_quat, "display"
                m["yaw_deg"] = round(yaw_between_deg(q, ref), 1)
                # 경계를 넣는다 (`<=`) -- 「±90° 안이면 통과」라는 말은 90.0° 도 통과라는 뜻이다.
                pts["B16"] = POINTS["B16"] if m["yaw_deg"] <= THRESHOLD["facing_deg"] else 0

            # B17 -- 앞줄 칸 중심과 뒷줄 칸 중심의 딱 가운데보다 앞에
            pts["B17"] = POINTS["B17"] if float(p[0]) < FRONT_ROW_X else 0

            # B18 -- 그 순간의 속도
            pts["B18"] = POINTS["B18"] if speed is not None and float(speed) < THRESHOLD["still_mm_s"] else 0

        # B19 -- 상자 중심이 탁자 윗면 위 ∧ 바닥면이 수직에서 45° 안 ∧ 첫 자리에서 crate_moved_mm 넘게 안 밀림.
        # origin 이 바닥이라 중심 = z + H/2
        crate_centre_z = float(cp[2]) + CRATE_H / 2.0
        m["crate_tilt_deg"] = round(math.degrees(math.acos(max(-1.0, min(1.0, qrot(cq, (0.0, 0.0, 1.0))[2])))), 1)
        m["crate_centre_z"] = round(crate_centre_z, 4)
        m["crate_moved_mm"] = round(self.crate_moved_max_mm, 1)
        pts["B19"] = POINTS["B19"] if (crate_centre_z > TABLE_TOP
                                       and m["crate_tilt_deg"] < THRESHOLD["crate_tilt_deg"]
                                       and self.crate_moved_max_mm <= THRESHOLD["crate_moved_mm"]) else 0

        # B20 -- 원래 진열돼 있던 나머지 상품이 하나도 빠짐없이 ① 선반 판 위 ② 15° 안으로 서 있음 ③ 판 안에
        # neighbour_moved_mm 넘게 밀리지 않음 (사용자 2026-09-07: 건드려 움직였으면 0점)
        fallen = []
        for key, (dq, nsize) in self.neighbours.items():
            if key not in shelf:
                fallen.append((key, "missing"))
                continue
            npos, nq = shelf[key]
            if board_under(np.asarray(npos, dtype=float), nq, nsize)[0] is None:
                fallen.append((key, "off_board"))
            elif tilt_deg(nq, dq) >= THRESHOLD["neighbour_deg"]:
                fallen.append((key, f"tilt {tilt_deg(nq, dq):.0f}"))
            elif self.neighbour_moved_mm.get(key, 0.0) > THRESHOLD["neighbour_moved_mm"]:
                fallen.append((key, f"moved {self.neighbour_moved_mm[key]:.1f} mm"))
        m["neighbours_fallen"] = fallen
        m["neighbour_moved_max_mm"] = round(max(self.neighbour_moved_mm.values()), 1) if self.neighbour_moved_mm else 0.0
        # B12 와 같다 -- **선반에 내려놓았을 때만** 본다 (사용자 2026-09-09). 상품을 든 채 끝난 판은
        # 다른 상품을 안 건드렸더라도 진열을 마치지 못한 것이라 이 2점을 받지 않는다.
        pts["B20"] = POINTS["B20"] if (placed and not fallen) else 0

        got = sum(v for v in pts.values() if v is not None)
        mx = sum(POINTS[k] for k, v in pts.items() if v is not None)
        self.result = {"product": self.name, "target": (self.layer, self.col), "end_frame": t,
                       "frames": self.n, "points": pts, "total": got, "total_max": mx,
                       "ever_at": dict(self.ever), "measured": m}
        return self.result


# ---- 입구 ① state npz ----------------------------------------------------------------------
def load_npz(path):
    z = np.load(path, allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    scene = json.loads(meta["scene"]) if isinstance(meta.get("scene"), str) else meta.get("scene", {})
    return z, meta, scene


def held_by_contact(CT, hz: float):
    """프레임마다 「쥐고 있나」 -- 상품과 그리퍼 마디의 접촉으로 정한다 (사용자 결정 2026-09-22).

    `CT` 는 `state.npz` 의 `contact/grip{N}` 칸(그리퍼 마디와 닿은 힘, N)이다. `grip_contact_min_n` 이상인
    프레임이 `grip_hold_s` 이상 **끊기지 않고** 이어지면, 그 구간 전체를 쥔 것으로 본다.

    왜 이어진 시간을 보나: 한 프레임 스치는 것은 쥔 것이 아니다. 2026-09-22 의 step 22000 에서
    B7 2 점을 잘못 받은 92024 는 접촉이 6.12 N 으로 두 프레임(0.05 초)뿐이었고, 진짜로 쥔 셋은
    72.85~81.80 초였다.
    """
    on = np.asarray(CT, dtype=np.float32) >= THRESHOLD["grip_contact_min_n"]
    need = max(1, int(round(THRESHOLD["grip_hold_s"] * hz)))
    out = np.zeros(on.shape[0], dtype=bool)
    i = 0
    while i < on.shape[0]:
        if not on[i]:
            i += 1
            continue
        j = i
        while j < on.shape[0] and on[j]:
            j += 1
        if j - i >= need:
            out[i:j] = True
        i = j
    return out


def score_npz(path, products=None, end_frame=None):
    """State npz 한 판을 채점한다. 상자 속 상품마다 결과 하나. `products` 로 고르지 않으면
    meta.pick_product, 그것도 없으면 상자 속 전부.

    채점 종료는 `end_frame`(없으면 마지막 프레임)이다. task_b_episode.py 가 쓴 npz 는 놓은 뒤 3초를 지켜본
    바로 그 순간에 끝나므로 마지막 프레임이 곧 시트의 「놓은 뒤 3초」다 -- meta 의 tilt_deg 와 222판
    대조로 확인했다 (2026-09-03).
    """
    z, meta, scene = load_npz(path)
    hz = float(meta.get("record_hz", 10.0))
    crate = scene.get("crate", [])
    gaps = [(int(g["layer"]), int(g["col"])) for g in scene.get("gaps", [])]
    gap_of = {g["product"]: (int(g["layer"]), int(g["col"])) for g in scene.get("gaps", [])}
    shelf_keys = [k for k in z.files if k.startswith("obj/l")]
    # (층, 자리) -> 상품 이름 -- 진열 자세를 알려면 이름이 있어야 한다
    name_at = {(int(s["layer"]), int(s["slot"])): s["product"] for s in scene.get("shelf", [])}
    slot_of_key = {k: (int(k[5]), int(k[8:10])) for k in shelf_keys}   # 'obj/l2_s04' -> (2, 4)

    want = products or ([meta["pick_product"]] if meta.get("pick_product") else [c["product"] for c in crate])
    C = z["obj/crate_tracker"] if "obj/crate_tracker" in z.files else z["obj/crate"]
    S = {k: z[k] for k in shelf_keys}
    n_all = int(C.shape[0])
    watch = max(1, int(round(THRESHOLD["watch_s"] * hz)))
    J = z["all_joint_pos"] if "all_joint_pos" in z.files else None
    jnames = list(meta.get("joint_names") or [])
    # **쥐고 있는가** -- 잡은 손의 gripper 관절 하나로 잰다 (사용자 결정 2026-09-22). 어느 손인지는
    # meta.pick_hand, 없으면 판 안에서 더 많이 움직인 쪽(놓기만 있는 기록도 그 손이 열린다).
    # 관절 기록이 없으면 None 이 넘어가고 B7·B8 은 예전처럼 위치만 본다.
    _gi = {h: jnames.index(f"gripper_{h}_joint1") for h in "lr" if f"gripper_{h}_joint1" in jnames}
    HELD_JOINT = None
    if J is not None and _gi:
        _hand = meta.get("pick_hand")
        if _hand not in _gi:
            _hand = max(_gi, key=lambda h: float(np.ptp(J[:, _gi[h]])))
        HELD_JOINT = J[:, _gi[_hand]] >= THRESHOLD["grip_closed_rad"]
    out = []
    for region, item in enumerate(crate):
        name = item["product"]
        if name not in want:
            continue
        key = f"obj/held{region}"
        if key not in z.files:
            continue
        # 접촉 센서 값. 이 상품에 붙은 센서가 팔꿈치 아래 로봇 바디와 닿은 힘이고, 단위는 N,
        # 길이는 기록 프레임 수와 같다. 이 칸이 없는 기록(2026-09-21 이전에 모은 것)은 None 이
        # 넘어가고, 그러면 B6 는 0점이 된다 -- 닿았는지 아닌지를 잴 것이 없기 때문이다.
        CT = z[f"contact/held{region}"] if f"contact/held{region}" in z.files else None
        # **「쥐고 있나」는 그리퍼 마디와의 접촉으로 정한다** (사용자 결정 2026-09-22).
        # 위 `contact/held{region}` 은 팔꿈치 아래 **모든** 부위와 닿은 힘이라 B6(닿았는가)의 값이고,
        # 그것으로 쥠을 재면 팔뚝으로 밀어 올린 상품도 쥔 것이 된다. 쥠은 `contact/grip{region}`,
        # 곧 그리퍼 네 마디만 골라 잰 힘으로 본다 (판정기의 `grip_contact_N` 과 같은 값).
        # 그 칸이 없는 옛 기록에서만 그리퍼 관절 각도로 물러난다 -- 그 값은 빈손도 통과시키므로
        # 대체값일 뿐이고, `notes` 에 무엇으로 쟀는지 적는다.
        CTG = z[f"contact/grip{region}"] if f"contact/grip{region}" in z.files else None
        HELD = held_by_contact(CTG, hz) if CTG is not None else HELD_JOINT
        if name not in gap_of:
            out.append({"product": name, "error": "이 상품의 빈 칸이 scene.gaps 에 없다"})
            continue
        layer, col = gap_of[name]
        P = z[key]
        # ---- 채점 종료 ②: 놓은 뒤 3초. 놓은 순간은 **잡고 있던 손의 gripper 가 열리는 프레임**이다 --
        # 시작 값(열림)과 상자 밖으로 나온 프레임의 값(닫힘)의 가운데를 열림 쪽으로 넘는 첫 프레임. 어느 손인지는
        # meta.pick_hand, 없으면 두 gripper 중 그 사이에 더 많이 움직인 쪽. 일곱 시연 실측: 잡음 0.68~0.92 rad,
        # 놓음 0.00, 열림+3초는 기록 끝보다 23~80 프레임 앞(기록기가 팔을 빼는 시간).
        release = None
        b8 = int(np.argmax(P[:, 2] > float(C[0, 2]) + CRATE_H)) if (P[:, 2] > float(C[0, 2]) + CRATE_H).any() else None
        if end_frame is None and J is not None and b8 is not None:
            gi = {h: jnames.index(f"gripper_{h}_joint1") for h in "lr" if f"gripper_{h}_joint1" in jnames}
            hand = meta.get("pick_hand")
            if hand not in gi and gi:
                hand = max(gi, key=lambda h: abs(float(J[b8, gi[h]] - J[0, gi[h]])))
            if hand in gi:
                g = J[:, gi[hand]]
                # 열림 기준은 첫 프레임이 아니라 **잡은 뒤 가장 열린 값**이다. 놓기만 있는 기록(held_from)은 첫
                # 프레임부터 잡고 있어서 g[0] 이 닫힌 값이고, 그러면 열림을 못 찾는다 (575판 대조에서 0/575).
                # 끝까지 안 놓은 기록은 가장 열린 값이 닫힌 값과 같아 저절로 「열림 없음」이 된다.
                open_ref, closed_ref = float(g[b8:].min()), float(g[b8])
                if abs(closed_ref - open_ref) > 0.1:
                    after = np.arange(b8, n_all)
                    opened = np.abs(g[after] - open_ref) < np.abs(g[after] - closed_ref)
                    # 놓은 순간은 **마지막으로 닫혀 있던 프레임의 바로 다음**이다 -- 첫 열림이 아니다.
                    # 첫 열림을 쓰면 중간에 한 번 놓았다 다시 집는 판이 그 첫 열림에서 끝나 버린다:
                    # 사용자 2026-09-07 "상자 안으로 떨어뜨렸다가 다시 집어 진열 -- 이건 허용이야" 와 어긋나고,
                    # 그리퍼가 옮기는 중에 잠깐 열렸다 닫혀도 거기서 끝난다 (둘 다 2026-09-09 에 시험해 걸렸다:
                    # 제대로 진열한 판이 14/34 로 끝났다). `place_release_review.py:37` 이 3,824판에서 정한
                    # 「마지막으로 닫혀 있던 프레임」과 같은 규칙이다.
                    if (~opened).any():
                        last_closed = int(after[len(opened) - 1 - int(np.argmax(~opened[::-1]))])
                        if last_closed + 1 < n_all:
                            release = last_closed + 1
                    elif opened.any():
                        release = int(after[int(np.argmax(opened))])
        if end_frame is not None:
            n, why = min(n_all, int(end_frame) + 1), "end_frame"
        elif release is not None and release + watch < n_all:
            n, why = release + watch + 1, "released+3s"
        elif release is not None:
            n, why = n_all, "released, record ended early"
        else:
            n, why = n_all, "last"
        neighbours = {}
        for k, (la, sl) in slot_of_key.items():
            pname = name_at.get((la, sl))
            if pname:
                neighbours[k] = (tuple(float(v) for v in taskB_restock.stock_orientation(pname)[1]),
                                 tuple(float(v) for v in taskB_restock.product(pname)["size"]))
        back_key = f"obj/l{layer}_s{col + COLS:02d}"
        sc = ProductScorer(name, (layer, col), gaps, neighbours,
                           back_key if back_key in S else None, hz=hz)
        for t in range(n):
            speed = None if t == 0 else float(np.linalg.norm(P[t, :3] - P[t - 1, :3])) * 1000.0 * hz
            sc.update(t, P[t, :3], P[t, 3:7], C[t, :3], C[t, 3:7],
                      {k: (S[k][t, :3], tuple(float(v) for v in S[k][t, 3:7])) for k in S},
                      contact_N=(None if CT is None else float(CT[t])), speed_mm_s=speed,
                      held=(None if HELD is None else bool(HELD[t])))
            if sc.done:          # 떨어져서 스스로 끝났다 -- 그 뒤 프레임은 안 본다
                break
        r = sc.finish(why)
        r["file"] = path
        r["seed"] = meta.get("seed")
        r["release_frame"] = release
        r["frames_total"] = n_all
        r["recorded_outcome"] = meta.get("place_outcome")
        out.append(r)
    z.close()
    return out


# ---- 화면 -----------------------------------------------------------------------------------
END_WORDS = {"placed": "선반 위에 놓음", "dropped": "떨어뜨림", "in_hand": "든 채 끝남"}
ABORT_WORDS = {"crate_off_table": "상자가 탁자에서 떨어져 조합 중단"}

# 채점을 **왜 그 프레임에서** 했나 -- 사람 말로. `end_by` 를 그대로 보여 주면 읽는 쪽이
# 알 수 없다 (사용자 2026-09-09: "종료가 되었는데 왜 종료가 되었는지 알 수가 없어").
WHY_END = {
    "released+3s": "손을 편 뒤 3초 -- 시트가 정한 판정 시점",
    "released, record ended early": "손을 폈지만 3초를 못 채우고 기록이 끝남",
    "last": "기록의 마지막 프레임 -- 끝까지 손을 안 펴서 판정 시점을 못 찾음",
    "dropped": "상품 밑면이 편의점 바닥에 닿은 순간 -- 그 뒤는 안 봄",
    "crate_off_table": "파란 상자가 탁자에서 떨어진 순간 -- 조합 중단",
    "end_frame": "밖에서 채점 시점을 지정함",
}


def reasons(r):
    """항목마다 점수 옆에 붙일 근거 한 토막 -- 표(fmt_result)와 재생 로그(task_b_replay.py)가 같은 문구를 쓴다."""
    m = r["measured"]
    return {
        "B6": (f"닿은 순간 접촉 {m['contact_at_touch_N']:.2f} N" if m["contact_at_touch_N"] is not None
               else f"접촉 센서가 {THRESHOLD['touch_N']} N 을 넘은 프레임 없음"),
        "B7": (f"최고 {m['lift_max_mm']:+.0f} mm"
               + (f" · 손을 편 채 오른 프레임 {m['open_lift_frames']}" if m.get("open_lift_frames") else "")),
        "B8": f"테두리 {m['rim_z']:.3f}",
        "B9": "", "B10": "",
        "B11": "",
        "B12": END_WORDS[m["end_reason"]] + (f" ({ABORT_WORDS[m['end_by']]})" if m["end_by"] in ABORT_WORDS else ""),
        "B13": (f"층 {m['layer']} 밑면 {m['under_mm']:+.0f} mm" if m["layer"] is not None
                else f"판 위 아님 (밑면 {m['under_mm']} mm)" if m["under_mm"] is not None else "선반 밖"),
        "B14": f"칸 {m['cell']} 좌우 {m['off_y_mm']:+.0f} mm",
        "B15": (f"위아래 차 {m['up_deg']}° vs {m['up_ref']} ({_pose_word(m['up_deg'])})"
                if m["up_deg"] is not None else "안 놓음"),
        # B15 가 떨어지면 여기는 볼 것이 없다. 그때 왜 떨어졌는지를 그대로 옮겨 적는다 --
        # "안 서 있음" 이라고만 적으면 거꾸로 선 판에서 사진과 어긋나 보인다 (사용자 2026-09-08).
        "B16": (f"yaw {m['yaw_deg']}° vs {m['facing_ref']}" if m["yaw_deg"] is not None
                else f"위아래가 다름 ({_pose_word(m['up_deg'])})" if m["up_deg"] is not None
                else "안 놓음"),
        "B17": f"x {m['x']:.3f} (금 {FRONT_ROW_X:.3f})",
        "B18": f"{m['speed_mm_s']} mm/s" if m["speed_mm_s"] is not None else "속도 없음",
        "B19": f"tilt {m['crate_tilt_deg']}° 중심 z {m['crate_centre_z']:.3f} 밀림 {m['crate_moved_mm']:.1f} mm",
        "B20": ("전부 서 있음" if not m["neighbours_fallen"]
                else " ".join(f"{k}:{w}" for k, w in m["neighbours_fallen"])),
    }


def fmt_result(r):
    if "error" in r:
        return f"  {r['product']}: {r['error']}"
    p, m = r["points"], r["measured"]
    lines = [f"  {r['product']}  목표 L{r['target'][0]}c{r['target'][1]}  "
             f"{r['total']} / {r['total_max']}점  (프레임 {r['end_frame']}/{r.get('frames_total', r['frames'])} 에서 종료: "
             f"{m['end_reason']} · {m['end_by']}"
             + (f", gripper 열림 @{r['release_frame']}" if r.get("release_frame") is not None else "")
             + (f", 기록된 판정 {r['recorded_outcome']}" if r.get("recorded_outcome") else "") + ")"]
    why = reasons(r)
    for rid, sub, mx, kind, label in RUBRIC:
        v = p[rid]
        s = " - " if v is None else f"{v:2d}"
        at = r["ever_at"].get(rid)
        ev = f"  @{at}" if (kind == "ever" and at is not None) else ""
        lines.append(f"    {rid:>3} {sub} [{'ever' if kind == 'ever' else ' at '}] {s}/{mx}  {label:22s} {why[rid]}{ev}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="과제 B 궤적을 평가표대로 채점한다.")
    ap.add_argument("files", nargs="*", help="state npz")
    ap.add_argument("--glob", help="npz 를 무늬로 고른다 (예 '~/render_fleet/state/*.npz')")
    ap.add_argument("--product", action="append", help="채점할 상품 이름 (여러 번). 없으면 meta.pick_product")
    ap.add_argument("--end-frame", type=int, help="채점 종료 프레임 번호. 없으면 마지막 프레임")
    ap.add_argument("--json", help="결과 전부를 이 파일에 JSON 으로")
    ap.add_argument("--quiet", action="store_true", help="판마다 표를 안 찍고 합계만")
    args = ap.parse_args()

    files = list(args.files)
    if args.glob:
        files += sorted(glob.glob(os.path.expanduser(args.glob)))
    if not files:
        ap.error("채점할 npz 가 없다")

    results, bad = [], 0
    for f in files:
        try:
            rs = score_npz(f, args.product, args.end_frame)
        except Exception as e:   # noqa: BLE001  -- 한 판이 깨져도 나머지는 센다
            bad += 1
            if not args.quiet:
                print(f"{f}: 못 읽음 ({type(e).__name__}: {e})")
            continue
        results.extend(rs)
        if not args.quiet:
            print(os.path.basename(f))
            for r in rs:
                print(fmt_result(r))
    ok = [r for r in results if "error" not in r]
    if ok:
        tot = sum(r["total"] for r in ok)
        mx = sum(r["total_max"] for r in ok)
        print(f"\n{len(ok)}개 상품 · 합계 {tot} / {mx} · 평균 {tot / len(ok):.2f}점"
              + (f" · 못 읽은 파일 {bad}" if bad else ""))
        for rid, _s, mxp, _k, label in RUBRIC:
            vals = [r["points"][rid] for r in ok]
            n_meas = sum(1 for v in vals if v is not None)
            n_full = sum(1 for v in vals if v == mxp)
            print(f"  {rid:>3} {label:22s} 만점 {n_full:5d} / {n_meas:5d}"
                  + ("" if n_meas == len(vals) else f"  (못 잼 {len(vals) - n_meas})"))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=1, default=str)
        print(f"→ {args.json}")


if __name__ == "__main__":
    main()
