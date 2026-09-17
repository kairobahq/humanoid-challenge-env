# Copyright 2025.
#
# 태스크 A 평가표를 코드로 옮긴 것.  **측정값이 들어가고 점수가 나온다.**
#
# 어느 시트를 옮긴 것인가
#   `Task-A/docs/태스크A_평가표_내가만듬.xlsx` (2026-09-02 사용자가 준 판).  그 전 판
#   (8항목 30점, `태스크A_평가표.xlsx`)은 **폐기됐다** -- 배점도 판정도 다르다.  옛 구현은
#   `_rubric_taskA_30pt_old.py.bak` 에 남겨 두었다.
#
# WHY THIS FILE IMPORTS NOTHING
#   채점 코어가 아무것도 import 하지 않으면 단위 시험이 몇 초에 돌고, 이의가 제기됐을 때
#   판정 로그만으로 다시 채점할 수 있다.  재는 일(`score_from_log.py`)과 점수 매기는
#   일(여기)을 나누는 것이 요점이다.
#
# 항목과 배점 -- **6항목 21점, 시도 3회 합산 63점**
#
#   ALL 1#  매장 가구와 부딪히지 않았는가        [판 내내]      4   부딪히면 판 종료
#   Sub 1#  파란 바구니를 띄웠고 그때 그리퍼가 물었는가 [한 번이라도] 3   두 조건 동시
#   Sub 2#  목적지에 도착해 멈췄는가             [한 번이라도]  3
#   Sub 2#  그 시점에 로봇이 들고 있었는가       [그 시점에]    4   떨어뜨리면 판 종료
#   Sub 3#  책상 상판에 얹었는가                 [한 번이라도]  3   책상 20 mm 미만일 때만
#   Sub 3#  손 뗀 뒤 6초, 네 조건이 다 맞는가    [6초 창]       4
#
#   시트의 「총 합 17」은 오타다 -- Sub 1+2+3 만 더한 값이고 ALL 1# 의 4점이 빠져 있다.
#   **사용자 확인 2026-09-02: 점수다.  21 × 3 = 63.**
#
# 앞 판에서 바뀐 것만 (다시 읽지 않아도 되도록)
#   * 집기 두 항목이 **하나로** 합쳐졌다 (4+4=8 -> 3, 둘 다 참이어야 통과)
#   * 「들고 있었는가」가 **그리퍼 -> 로봇 전체**.  나르는 방식은 채점하지 않는다
#   * 도착에 숫자가 없어졌다 ("조금이라도 안에 들어가").  **로봇 발자국이 목표 구역에
#     걸치면 통과** (사용자 결정 2026-09-02)
#   * 책상 밀림이 5 -> **20 mm** 이고, 별도 항목이 아니라 `placed` 의 조건이 되었다
#   * 제한 시간 **20분**과 **시도 3회 합산**이 정해졌다 (앞 판은 둘 다 UNDECIDED)

# ---------------------------------------------------------------------------------------------
# 문턱.  출처를 셋으로 갈라 적는다 -- 이 구분이 이의 제기에 답하는 방식이다.
#
#   치수   물체나 로봇의 크기에서 나온 값.  다투려면 물체를 다시 재야 한다
#   선언   대회가 정하는 값.  시트에 적힌 것은 시트를 인용한다
#   우리것 우리 실행 분포에서 고른 값.  **하나도 없어야 한다** -- 있으면 참가자에게
#          우리 궤적을 따라오라고 요구하는 것이 된다
# ---------------------------------------------------------------------------------------------

# 선언 (시트 Sub 1#).  "바구니가 탁자에서 30 mm 넘게 떠오른 순간이 한 번이라도 있으면"
LIFT_OK_MM = 30.0

# 선언 (사용자 결정 2026-09-02).  시트는 "목표 지점에 **조금이라도 안에 들어가** 멈춰 선 적이
# 있으면 통과" 라고만 적고 반경을 안 준다.  구역은 목표점을 중심으로 한 반경 0.10 m 원으로
# 두고 -- 씬 파일이 `goal.tol_m` 로 이미 그 값을 싣고 온다 -- **로봇 발자국이 그 원에
# 걸치기만 하면** 통과로 한다.  중심이 원 안에 들어와야 한다는 뜻이 아니다.
# **더 이상 채점에 쓰이지 않는다** (사용자 결정 2026-09-09).
#
# 옛 규칙의 값이다 -- 우리가 정한 목표점 둘레 반경 0.10 m 원.  그러면 로봇 중심이 목표에서
# 0.325 m 안에 있어야 했고, 책상은 목표에서 0.900 m 떨어져 있어 **책상에 팔이 닿으면서
# 구역 밖인 자리가 있었다.**  거기 서서 바구니를 잘 놓아도 7 점을 못 받았다.
#
# 지금은 **책상 중심**을 원의 중심으로 쓰고 반지름을 씬에서 계산한다 (`|목표 − 책상|`,
# 우리 씬 0.900 m).  `score_from_log.py` 의 도착 블록이 그 자리다.
#
# 지우지 않는 이유: 정답지(`expected/score_*.json`)의 `thresholds` 에 이 열쇠가 들어 있어
# 지우면 대조가 깨지고, 왜 없어졌는지도 안 남는다.
ARRIVE_ZONE_M = 0.10

# 도착 구역 반지름의 한계 (m).  반지름은 씬에서 `|목표 − 책상|` 로 계산하는데, 씬이 책상을
# 목표에서 멀리 두면 그만큼 커진다 -- 시험 삼아 책상을 4 m 옮겼더니 구역이 4.35 m 가 됐고,
# 그러면 매장 절반이 「도착」이 된다.
#
# 위(1.5 m)는 **로봇이 서서 책상에 손이 닿을 수 있는 최대 거리**에서 왔다: 팔 도달 0.79 m
# 에 발자국 절반(앞 0.225 / 뒤 0.403)을 더하면 1.2 m 남짓이고, 1.5 는 거기에 여유를 둔 것.
# 아래(0.5 m)는 책상과 목표가 겹친 씬에서 구역이 0 이 되지 않게 하는 바닥이다.
#
# 우리 씬은 0.900 m 라 둘 사이에 편안히 들어온다.
ARRIVE_ZONE_MIN_M = 0.50
ARRIVE_ZONE_MAX_M = 1.50

# 도착 구역의 중심(책상)과 반지름(|목표 − 책상|)은 **씬이 싣고 온다.**  그런데 그 씬이
# 맞는지는 아무도 안 봤다.  아래 두 값이 그 대조 기준이다.
#
# 대조할 수 있는 이유: 책상과 목적지는 매장 붙박이라 **seed 와 무관하게 언제나 같은
# 자리**다.  드리는 세 장면(0 / 2 / 6)에서 소수 넷째 자리까지 같은 것을 확인했다.
# 반지름을 씬마다 계산하는 것도, 위의 한계 [0.50, 1.50] 도 실제로는 한 번도 안 물린다
# -- 둘 다 방어용이다.
#
# **왜 대조해야 하나.**  이 두 값은 `scripts/taskA/destinations.json` 에서 오고, 그것은
# 매장 USD 를 다시 구울 때마다 다시 뽑아야 하는 **파생 파일**이다.  잘못 뽑히면 구역이
# 조용히 옮겨간다 -- 오류도 경고도 안 나고 점수는 그럴듯하게 나온다.  채점을 다 끝내고
# 나서야 드러나고, 그때는 되돌릴 수 없다.  이 레포는 지도를 다시 뽑았다가 엉뚱한 건물이
# 나온 적이 이미 있다.
#
# 값은 `taskA_layout.DESK_POS` / `GOAL_POSE` 와 같아야 한다.  **두 곳에 적은 숫자는
# 언젠가 갈라지므로**, `test_rubric_taskA.py` 가 배포 이미지 안에서 둘을 대조한다.
FIXTURE_DESK_XY = (0.1616, 1.6975)
FIXTURE_GOAL_XY = (-0.1003, 2.5588)

# 허용 오차.  **`DESK_OK_MM` 을 그대로 쓴다** -- "책상이 있어야 할 자리에 있나" 라는 같은
# 물음이고, 같은 물음에 문턱을 두 개 두면 언젠가 갈라진다.  씬은 좌표를 소수 5 자리로
# 반올림해 싣고(1e-5 m) 로그의 책상은 float32(약 6e-8 m)이므로, 20 mm 는 잡음의 2,000 배다.

# 치수.  `FFW_SG2.usd` 의 base_mobile_assy.  앞뒤 -0.403~+0.225 m, 좌우 ±0.301 m 이고
# 뒤 모서리가 중심에서 sqrt(0.403^2 + 0.301^2) = 0.503 m 뻗는다.
# 로봇 기준 좌표계에서 +x 가 앞이다.
ROBOT_FOOTPRINT = {"back": -0.403, "front": 0.225, "half_width": 0.301}

# 매장 안쪽 면 (m).  `taskA_layout.py` 의 STORE_X / STORE_Y 와 같은 값이고, 여기 다시 적는
# 이유는 채점기가 배포 이미지 없이도 돌아야 하기 때문이다 (그쪽은 매장 USD 경로를 잡느라
# 이미지를 본다).  `log_check` 는 이 값을 그대로 가져다 쓴다 -- 두 곳에 적지 않는다.
#
# **이것은 위생 검사의 값이 아니라 채점 규칙의 값이다** (사용자 결정 2026-09-10).
# 앞 판은 매장 이탈을 위생 검사로만 봤고, 그래서 두 가지가 어긋나 있었다:
#
#     매장 밖 0 ~ 2 m     아무 일도 없었다.  점수 그대로
#     매장 밖 2 m 초과     「채점 거부」 -- 그리고 그 출력이 "로그가 깨진 것과 로봇이 못한
#                        것은 다른 일" 이라고 말한다.  **나간 것은 로봇이 못한 것이다.**
#
# 이제 발자국이 이 선을 넘으면 그 프레임에서 판이 끝난다 (`ended = "out_of_store"`).
STORE_X = (-11.1, 1.3)
STORE_Y = (-5.12, 7.25)

# 선언 (시트 Sub 3# ④).  "멈췄다" 의 뜻.
STOP_MM_S = 10.0

# 선언.  접촉을 접촉으로 치는 최소 힘.  시트는 "힘의 크기는 보지 않는다" 고 적으므로 이것은
# **잡음 바닥을 넘는가**를 가르는 값이지 세기를 재는 값이 아니다.  태스크 B 가 같은 질문에
# 같은 값을 쓴다 (`scripts/tools/task_b_episode.py:2401`).
CONTACT_N = 0.5

# 선언 (시트 Sub 3# ①).  "바구니 밑면이 상판에서 0 이상 5 mm 이하"
SEAT_ON_MAX_MM = 5.0

# 얹힘 판정의 **아래쪽** 여유 (mm).  「0 이상」이 아니라 「-3 mm 이상」인 이유:
#
# **이 시뮬레이터에서는 얹힌 물체가 언제나 받침면을 조금 파고든 채로 앉는다.**  PhysX 가
# 접촉을 풀고 남기는 잔여 겹침이고, 크레이트 탓이 아니다 -- 같은 바깥치수·같은 질량의
# **속이 찬 단순 박스**를 같은 자리에 놓아도 -0.617 mm 로 앉는다 (크레이트는 -0.673).
#
# 실측 (배포 이미지, 2026-09-10):
#
#     정착 겹침      0.29 ~ 1.03 mm    책상 상판 충돌면이 x 로 0.19 도 기울어져 있어
#                                     자리를 탄다 (서쪽 -0.291, 동쪽 -1.033, 완전히 선형)
#     받쳐진 최악    1.370 mm          놓일 수 있는 자리 전체 x 기울기 0~30 도 x 낙하 50~600 mm,
#                                     |vz| < 0.05 m/s 인 프레임만 세어 23 회 중 최악
#     3.0           그 2.2 배.  채점 서버의 물리가 이 기계와 다를 여지를 남긴 값이다
#                   (`Task-A/CLAUDE.md` 68 절: 기계가 바뀌면 갈린다, 다른 양에서 1.9 배)
#     52 mm         수집 1,451 편에서 관측된 **가장 얕은 진짜 실패**.  그 위는 통째로 비어 있다
#
# 즉 -5.3 ~ -2 mm 구간이 실데이터에서 완전히 비어 있어, 이 안의 어떤 값도 기존 편의 판정을
# 바꾸지 않는다.  **채점 서버가 정해지면 거기서 겹침을 다시 재고 확인할 것** -- 한 줄이다.
#
# **이 여유가 안전한 것은 `seated` 가 「멈춰 있을 것」을 함께 요구하기 때문이다.**  그 조건이
# 없으면 여유를 넓히는 것이 곧 통과 중인 프레임을 얹힘으로 세는 것이 된다.
SEAT_SINK_MAX_MM = 3.0

# 「책상에 있나, 바닥에 있나」의 자 (mm).  **얹힘 판정과 다른 물음이다.**
#
# 낙하 판정과 감시창 열기에만 쓴다.  바닥은 상판보다 725 mm 아래이므로 이 물음은 밀리미터
# 정밀도가 필요 없다.  앞 판은 얹힘과 같은 식(0~5 mm)을 써서, 잔여 겹침이나 적분 오버슛
# 한 프레임이 곧바로 「낙하」가 됐다 (이슈 #3).
#
# 50 mm 는 실측된 최악 오버슛(5.3 mm)의 9 배이고, 관측된 가장 얕은 진짜 실패(52 mm)보다는
# 아래다 -- 둘 사이가 비어 있어 그 안이면 답이 같다.
SEAT_NEAR_MM = 50.0

# **재기만 하고 채점에 쓰지 않는다** (사용자 결정 2026-09-02):
#
#   "지금 책상에 나란히 바구니를 놓지 않아도 돼.  그냥 놓고 6초동안 떨어지지 않으면 돼."
#
# 시트(`태스크A_평가표_내가만듬.xlsx`) Sub 3# ② 는 "걸침 30 mm 이내" 라고 적고 있고, 그
# 문장은 이 결정으로 **무효가 됐다.**  시트도 같이 고쳐야 한다.
#
# 왜 뺐는가 -- 30 mm 는 사실상 "상판과 나란히 놓아라" 였다.  상판 600 x 600 에 바구니가
# 380 x 590 이라 긴 변 여유가 10 mm 뿐이고, 45 도로 놓으면 대각이 0.70 m 라 반드시 넘는다.
# 실측된 우리 놓기는 72.1 / 84.0 / 96.0 / 113.7 / 200.3 mm 로 전부 30 을 넘었다.
#
# **그래도 값을 지우지는 않는다.**  `score_from_log.py` 가 걸침을 계속 재서 출력에 남기고,
# 판정 문장에도 숫자가 들어간다.  나중에 다시 채점에 쓰기로 하면 로그를 다시 만들 필요가
# 없어야 한다 -- 재는 일과 점수 매기는 일을 나눈 이유가 그것이다.
#
# 「떨어지지 않았다」는 남은 세 조건이 이미 묻는다: 밑면이 상판에 얹혀 있고(①), 안 넘어졌고
# (③), 창 끝에 멈춰 있다(④).  상판에서 굴러떨어졌으면 ①이 잡는다 -- 상판보다 725 mm 아래다.
OVERHANG_OK_MM = 30.0
OVERHANG_SCORED = False

# 선언 (시트 Sub 3# ③).  "기울기 15도 이내".  어디에 둬도 답이 같다 -- 정상 편이 중앙
# 0.22 도 / 최악 1.23 도, 넘어진 편이 106.7 과 113.1 도로 두 집단 사이가 통째로 비어 있다.
TILT_OK_DEG = 15.0

# 선언 (시트 Sub 3#).  "손을 뗀 뒤 6초 동안".
WATCH_S = 6.0

# 선언 (시트 Sub 3# ④).  "창 마지막 0.5초 동안 바구니 속도가 초당 10 mm 미만".
WATCH_TAIL_S = 0.5

# 선언 (시트 Sub 3#).  "책상이 2cm 이상 움직였을 시, 가점을 부여하지 않는다".
# 앞 판은 5 mm 였다.  바닥값은 실측했다 -- 로봇이 책상 근처에도 안 간 편에서 책상은
# 0.0005~0.0006 mm 를 오가고, 주행 1,180편 중 1,175편이 0.01 mm 미만이다.
DESK_OK_MM = 20.0

# 선언 (시트 머리 "제한 시간: 20min").
TIME_LIMIT_S = 600.0

# 선언 (시트의 「시도 1 / 2 / 3」 열과 「최종 점수 51」).  세 판을 **더한다**.
ATTEMPTS = 3

# ---------------------------------------------------------------------------------------------
# **떨림은 채점 항목이 아니다.  넣지 말 것.** (사용자 지시 2026-09-02: "평가 함수에 떨림을
# 둬서는 안 돼.")
#
# 시트가 이미 같은 말을 한다 -- Sub 2# 의 자유도 문단: "중앙 통로로 가든 북쪽 통로로 돌든,
# 길이·꺾임 수·속도·후진 여부를 전부 보지 않는다.  **오로지 목적지 도착 여부만 본다.**"
# 떨림은 어떻게 갔는가이지 무엇을 했는가가 아니므로 그 문장에 걸린다.
#
# 왜 이 주석이 필요한가: 2026-09-02 에 우리 GT 한 편이 떨림 12.9%(최장 24.1초, 조향 왕복
# 403배)로 드러났고, 그것을 **채점에서 거르고 싶은 유혹**이 바로 생긴다.  거르는 자리는
# 여기가 아니라 **넘길 편을 고르는 단계**다 (`automation/tremor_index.py`).  참가자의 주행이
# 덜덜거려도 도착하면 만점이고, 그것이 맞다 -- 우리 궤적의 매끄러움을 합격선으로 만들면
# 참가자에게 우리처럼 몰라고 요구하는 것이 된다.
# ---------------------------------------------------------------------------------------------

ITEMS = ("no_hit", "picked", "arrived", "held", "placed", "stayed")

GROUP = {"no_hit": "전체",
         "picked": "집기",
         "arrived": "이동", "held": "이동",
         "placed": "놓기", "stayed": "놓기"}

POINTS = {"no_hit": 4.0, "picked": 3.0, "arrived": 3.0,
          "held": 4.0, "placed": 3.0, "stayed": 4.0}

WHEN = {"no_hit": "판 내내", "picked": "한 번이라도", "arrived": "한 번이라도",
        "held": "그 시점에", "placed": "한 번이라도", "stayed": "손 뗀 뒤 6초"}

LABEL = {"no_hit": "매장 가구와 부딪히지 않았는가",
         "picked": "바구니를 띄웠고 그때 그리퍼가 물었는가",
         # 2026-09-09: 멈춤을 더 이상 안 보므로 이름에서 뺐다.  구역도 「우리가 정한
         # 목표점」에서 「책상 둘레」로 넓혔다.  열쇠(`arrived`)와 배점(3)은 그대로다 --
         # 열쇠를 바꾸면 정답지와 대조가 깨진다.
         "arrived": "목적지(책상 둘레)에 도착했는가",
         "held": "그 시점에 로봇이 들고 있었는가",
         "placed": "책상 상판에 얹었는가",
         "stayed": "손 뗀 뒤 6초 동안 잘 놓여 있었는가"}

# 판이 끝난 이유.  **반드시 출력에 남는다** (시트가 그렇게 요구한다) -- 없으면 낙하로 끝난
# 판과 시간이 다 되어 끝난 판이 점수만 봐서는 똑같아 보인다.
#
#   dropped     바구니를 떨어뜨렸다      (시트 Sub 2#)
#   hit         매장 가구에 부딪혔다     (시트 ALL 1#: "sim, real 모두 평가 종료")
#   time_limit  20분이 다 됐다
ENDED = ("ok", "dropped", "hit", "time_limit")


def _item(got, why):
    """`got` 은 True / False / None.

    **None 은 "잴 수 없었다" 이고 0 점이다.  분모는 그대로 배점이다.**

    앞 판은 None 이면 분모에서도 뺐다.  「안 했다」와 「못 쟀다」를 가르려는 뜻이었는데,
    가를 방법이 로그뿐이고 로그는 채점받는 쪽이 만든다 -- 실측 2026-09-08: 집기만 하고
    멈추면 7/7 = 100 %, 놓기 토막만 내면 18/18 = 100 % 가 나왔다.  **덜 할수록 비율이
    좋아졌다.**  사용자 결정으로 분모를 배점에 고정했다 (아래 `score` 의 주석).
    """
    return {"got": got, "why": why}


def zone_gap_mm(base_xy, base_yaw, goal_xy, zone_m=None, footprint=None):
    """로봇 발자국이 목표 구역에서 얼마나 떨어져 있나 (mm).  **0 이면 걸친 것이다.**

    시트가 "목표 지점에 조금이라도 안에 들어가" 라고만 적어서, 사용자 결정(2026-09-02)으로
    **반경 `zone_m` 원 vs 로봇 사각 발자국의 겹침**으로 읽는다.  중심이 원 안에 들어와야
    한다는 뜻이 아니다.

    재는 방법은 교과서 그대로다 -- 목표점을 로봇 좌표계로 옮기고, 발자국 사각형 안으로
    잘라 붙인 뒤(clamp), 그 점까지의 거리에서 반경을 뺀다.  음수면 겹쳤다는 뜻이라 0 으로
    자른다.

    **이 함수가 여기 있는 이유:** 이것은 재는 일이 아니라 **평가표가 정한 규칙**이다.
    문턱을 다투려면 이 함수를 봐야 하고, 그러려면 시뮬레이터 없이 시험할 수 있어야 한다.
    """
    import math
    zone_m = ARRIVE_ZONE_M if zone_m is None else zone_m
    fp = ROBOT_FOOTPRINT if footprint is None else footprint

    # **못 재면 「구역 밖」이다.  0 이 아니다.**
    #
    # 마지막 줄이 `max(0.0, d - zone_m)` 인데, `d` 가 NaN 이면 파이썬 `max` 가 **0.0 을
    # 고른다** -- `nan > 0.0` 이 거짓이라 처음 값이 남기 때문이다.  그리고 0.0 은
    # 「발자국이 구역에 딱 걸쳤다」= 합격이다.  실측 2026-09-09: 씬의 책상 좌표를 NaN 으로
    # 두면 1,409 프레임 전부가 구역 안으로 잡혀 **도착 3 점 + 들고 4 점을 무조건 받았다.**
    #
    # 지금 씬으로 NaN 이 들어올 경로는 없다(좌표는 파일에서 읽고 없으면 상수로 떨어진다).
    # 그래도 막는 이유는 **넘어지는 방향**이다 -- 못 잰 것이 합격이 되면 아무도 모른다.
    if not all(math.isfinite(float(v)) for v in
               (base_xy[0], base_xy[1], base_yaw, goal_xy[0], goal_xy[1], zone_m)):
        return float("inf")

    dx = float(goal_xy[0]) - float(base_xy[0])
    dy = float(goal_xy[1]) - float(base_xy[1])
    c, s = math.cos(-float(base_yaw)), math.sin(-float(base_yaw))
    lx = dx * c - dy * s          # 로봇 기준 앞뒤 (+x 가 앞)
    ly = dx * s + dy * c          # 로봇 기준 좌우
    qx = min(max(lx, fp["back"]), fp["front"])
    qy = min(max(ly, -fp["half_width"]), fp["half_width"])
    d = math.hypot(lx - qx, ly - qy)
    return max(0.0, d - zone_m) * 1000.0


def out_of_store_mm(base_xy, base_yaw, footprint=None,
                    store_x=None, store_y=None):
    """로봇 **발자국**이 매장 안쪽 면을 얼마나 넘어갔나 (mm).  **0 이면 아직 안 넘었다.**

    사용자 결정 2026-09-10: 기준은 중심이 아니라 **발자국**이다.  다른 기물의 충돌 판정과
    같은 잣대이고(겹치면 끝, 문턱 없음), 벽만 다른 잣대를 쓰면 왜 다른지를 설명할 수 없다.

    **그 대가를 적어 둔다: 벽을 스치기만 해도 판이 끝난다.**  앞 판은 `Walls` 를 충돌
    목록에서 통째로 빼서 벽을 긁어도 공짜였다.  뺀 이유는 벽이 나쁘지 않아서가 아니라
    **벽의 축정렬 상자가 매장 전체**(12.64 x 12.61 m)라 그대로 넣으면 로봇이 매장 안에
    있는 한 매 프레임 겹쳤기 때문이다.  안쪽 면과의 거리로 재면 그 문제가 없다.

    정답 주행 세 판의 여유 (2026-09-10 실측): 발자국 기준 0.975 / 0.360 / 0.340 m.
    가장 붙은 판이 34 cm 남는다.

    `zone_gap_mm` 과 같은 이유로 **못 재면 넘은 것으로 본다** -- 못 잰 것이 합격이 되는
    방향으로 넘어지면 아무도 모른다.
    """
    import math
    fp = ROBOT_FOOTPRINT if footprint is None else footprint
    sx = STORE_X if store_x is None else store_x
    sy = STORE_Y if store_y is None else store_y
    if not all(math.isfinite(float(v)) for v in (base_xy[0], base_xy[1], base_yaw)):
        return float("inf")
    c, s_ = math.cos(float(base_yaw)), math.sin(float(base_yaw))
    worst = 0.0
    for lx, ly in ((fp["front"], fp["half_width"]), (fp["front"], -fp["half_width"]),
                   (fp["back"], fp["half_width"]), (fp["back"], -fp["half_width"])):
        wx = float(base_xy[0]) + lx * c - ly * s_
        wy = float(base_xy[1]) + lx * s_ + ly * c
        worst = max(worst, sx[0] - wx, wx - sx[1], sy[0] - wy, wy - sy[1])
    return max(0.0, worst) * 1000.0


def thresholds():
    """이 판이 쓰는 문턱 전부.  출력에 실어 보내 이의 제기에 답할 수 있게 한다."""
    return dict(LIFT_OK_MM=LIFT_OK_MM, ARRIVE_ZONE_M=ARRIVE_ZONE_M,
                ROBOT_FOOTPRINT=dict(ROBOT_FOOTPRINT), STOP_MM_S=STOP_MM_S,
                CONTACT_N=CONTACT_N, SEAT_ON_MAX_MM=SEAT_ON_MAX_MM,
                SEAT_SINK_MAX_MM=SEAT_SINK_MAX_MM, SEAT_NEAR_MM=SEAT_NEAR_MM,
                OVERHANG_OK_MM=OVERHANG_OK_MM, OVERHANG_SCORED=OVERHANG_SCORED,
                TILT_OK_DEG=TILT_OK_DEG,
                WATCH_S=WATCH_S, WATCH_TAIL_S=WATCH_TAIL_S, DESK_OK_MM=DESK_OK_MM,
                TIME_LIMIT_S=TIME_LIMIT_S, ATTEMPTS=ATTEMPTS)


def score(m, th=None):
    """측정값 `m` 에 점수를 매긴다.

    `m` 의 모양은 `score_from_log.measure()` 가 만든다.  여기서는 문턱만 적용한다.
    빠진 열쇠는 None 으로 읽는다 -- 채점기가 KeyError 로 죽는 것보다 그 항목이 분모에서
    빠지고 `unscored` 에 이름이 남는 편이 훨씬 낫다.
    """
    t = thresholds()
    if th:
        t.update(th)

    lift = m.get("lift") or {}
    arrive = m.get("arrive") or {}
    furn = m.get("furniture") or {}
    place = m.get("place") or {}
    watch = m.get("watch") or {}
    desk = m.get("desk") or {}
    ended = m.get("ended")

    items = {}

    # ---- ALL 1#  가구와 부딪히지 않았는가 ----------------------------------------------------
    # [판 내내] 이므로 판이 일찍 끝났어도 **그때까지는 채점한다.**  부딪힌 적이 없으면 통과다
    # -- 짧게 끝난 판을 미검증으로 돌리면 일찍 떨어뜨리는 쪽이 이득을 본다.
    #
    # **문턱이 없다.**  로봇(또는 든 바구니)의 발자국이 기물의 상자와 겹쳤는가 하나뿐이고,
    # 겹침은 0 을 넘느냐 마느냐이지 정도의 문제가 아니다.  숫자를 지어낼 자리가 없다.
    hit = furn.get("hit")
    if hit is None:
        items["no_hit"] = _item(None, "충돌을 못 읽었다")
    elif hit:
        items["no_hit"] = _item(False,
                                f"{furn.get('what') or '매장 가구'} 를 "
                                f"{furn.get('worst_mm', 0.0):.1f} mm 파고들었다"
                                + (f" ({furn['part']})" if furn.get("part") else "")
                                + f", {furn.get('frames', 0)} 프레임")
    else:
        items["no_hit"] = _item(True, "어느 기물과도 겹치지 않았다 "
                                      f"(최악 침투 {furn.get('worst_mm', 0.0):.1f} mm)")

    # ---- Sub 1#  띄웠고, 그 시점에 그리퍼가 물었는가 ------------------------------------------
    # **한 항목이다.**  둘 다 참이어야 3점이고, 하나만 참이면 0점이다 (시트가 두 물음을 한 칸에
    # 넣고 배점을 하나만 줬다).  여기만은 「그리퍼」다 -- 이동(`held`)과 헷갈리지 말 것.
    peak = lift.get("peak_mm")
    gripped = lift.get("gripped")
    if peak is None:
        items["picked"] = _item(None, "바구니 높이를 못 읽었다")
    elif peak < t["LIFT_OK_MM"]:
        items["picked"] = _item(False, f"가장 높이 떠오른 순간이 {peak:.1f} mm "
                                       f"(문턱 {t['LIFT_OK_MM']:.0f})")
    elif gripped is None:
        items["picked"] = _item(None, f"{peak:.1f} mm 떠올랐으나 그 프레임의 접촉을 못 읽었다")
    elif gripped:
        items["picked"] = _item(True, f"바구니가 {peak:.1f} mm 떠올랐고 "
                                      f"(문턱 {t['LIFT_OK_MM']:.0f}) 그 프레임에 그리퍼 링크가 "
                                      f"닿아 있었으며 로봇 아닌 것에는 닿아 있지 않았다")
    else:
        items["picked"] = _item(False, f"{peak:.1f} mm 떠올랐으나 "
                                       + (lift.get("why_grip")
                                          or "그 프레임에 그리퍼가 바구니에 닿아 있지 않았다"))

    # ---- Sub 2#  도착해 멈췄는가 -------------------------------------------------------------
    # **"안 멈췄다" 와 "못 쟀다" 는 다르다.**  판 내내 굴러다니기만 한 로봇은 도착한 적이
    # 없는 것이지 측정이 안 된 것이 아니다 -- None 으로 두면 그 점수가 분모에서 빠져,
    # 멈추지 않는 쪽이 총점 비율에서 이득을 본다.
    reached = arrive.get("reached")
    # **멈춤은 더 이상 안 본다** (사용자 결정 2026-09-09).  구역에 발자국이 걸친 적이
    # 있으면 도착이다.  놓기 성공도 요구하지 않는다 -- 주행을 다 하고 놓기만 실패한 로봇도
    # 거기까지 간 것은 인정한다.
    edge = arrive.get("nearest_edge_mm")
    zone_m = arrive.get("zone_m")
    if reached is None:
        items["arrived"] = _item(None, "베이스 자세를 못 읽었다")
    elif reached:
        items["arrived"] = _item(
            True, "로봇 발자국이 책상 둘레 구역"
                  + (f"(반경 {zone_m:.2f} m)" if zone_m else "") + "에 걸쳤다"
                  + (f" -- 그 안에 있던 프레임 {arrive['in_zone_frames']}개"
                     if arrive.get("in_zone_frames") else ""))
    else:
        items["arrived"] = _item(False, arrive.get("why") or
                                 ("발자국이 책상 둘레 구역에 닿지 않았다"
                                  + (f" (가장 가까웠던 것이 {edge:.0f} mm)"
                                     if edge is not None else "")))

    # ---- Sub 2#  그 시점에 로봇이 들고 있었는가 -----------------------------------------------
    # **여기는 「그리퍼」가 아니라 「로봇」이다.**  시트가 명시적으로 갈라 놓았다 -- 바퀴
    # 나르는 방식은 채점하지 않는다.  집기(`picked`)와 하나로 합치지 말 것.
    # 「그 시점」은 **구역 안에 있던 동안**이다 (사용자 결정 2026-09-09).  놓는 프레임에
    # 걸면 안 된다 -- 실측으로 「가장 잘 얹힌 프레임」이 손을 뗀 뒤인 판이 있었다.
    # 뜻은 「가져갔는가」다: 바닥으로 밀거나 던져서 올린 로봇은 여기서 걸린다.
    held = arrive.get("held")
    if items["arrived"]["got"] is False:
        items["held"] = _item(False, "구역에 들어온 적이 없어 볼 시점이 없다")
    elif items["arrived"]["got"] is None or held is None:
        items["held"] = _item(None, "그 프레임의 접촉을 못 읽었다")
    elif held:
        items["held"] = _item(True, "구역 안에 있는 동안 로봇이 바구니를 들고 있었다"
                                    + (f" ({arrive['held_frames']}개 프레임)"
                                       if arrive.get("held_frames") else ""))
    else:
        items["held"] = _item(False, arrive.get("why_held") or
                              "도착 시점에 로봇이 바구니를 들고 있지 않았다")

    # ---- Sub 3#  책상 상판에 얹었는가 --------------------------------------------------------
    # 판이 낙하나 충돌로 끝났으면 Sub 3# 는 통째로 못 얻는다.  **None 이 아니라 False** 다 --
    # 못 잰 것이 아니라 못 한 것이다.
    #
    # 시트: "여기는 얹히기(책상 상판과 접촉)만 하면 됨."  **걸침을 여기서 보지 않는다** --
    # 다음 항목(6초 창)이 그것을 본다.  대신 **책상이 20 mm 이상 움직였으면 가점이 없다.**
    if ended in ("dropped", "hit", "out_of_store"):
        why = ("바구니를 떨어뜨려 판이 끝났다" if ended == "dropped"
               else "로봇이 매장 밖으로 나가 판이 끝났다" if ended == "out_of_store"
               else "매장 가구에 부딪혀 판이 끝났다")
        items["placed"] = _item(False, why)
        items["stayed"] = _item(False, why)
    else:
        seat = place.get("seat_mm")
        import math
        dm = desk.get("worst_mm")
        # **NaN 은 None 과 같이 다룬다.**  `nan > DESK_OK_MM` 은 거짓이라, 그냥 두면
        # 「책상이 얼마나 밀렸는지 모르는」 판이 밀림 검사를 통과해 버린다 -- 위
        # `zone_gap_mm` 과 같은 종류의 새는 구멍이고, 방향도 같다(유리한 쪽).
        if dm is not None and not math.isfinite(float(dm)):
            dm = None
        if place.get("reached_desk") is False:
            items["placed"] = _item(False, "바구니가 책상 근처에 온 적이 없다")
        elif seat is None:
            items["placed"] = _item(None, "바구니나 책상 자세를 못 읽었다")
        elif not (-t["SEAT_SINK_MAX_MM"] <= seat <= t["SEAT_ON_MAX_MM"]):
            items["placed"] = _item(False, f"상판 대비 높이 {seat:.1f} mm "
                                           f"(-{t['SEAT_SINK_MAX_MM']:.0f}~"
                                           f"{t['SEAT_ON_MAX_MM']:.0f} 이어야 한다)")
        elif place.get("upright_any") is False:
            # **뒤집혀 얹힌 것은 얹은 것이 아니다** (사용자 결정 2026-09-07).
            #
            # 높이만 보면 거꾸로 엎어 놓아도 통과한다 -- 상판에서 0~5 mm 는 그대로이기
            # 때문이다.  얹힘과 똑바름을 **같은 프레임에서** 둘 다 만족해야 하고, 그
            # 판정은 `score_from_log.py` 의 place 블록이 한다.
            #
            # 문턱은 6 초 창과 같은 `TILT_OK_DEG` 다.  같은 물음에 문턱을 둘 두지 않는다.
            pt = place.get("tilt_deg")
            items["placed"] = _item(False,
                                    "상판 높이는 맞았으나 똑바로 얹힌 순간이 없다 — 기울기 "
                                    + (f"{pt:.1f} 도" if pt is not None else "미상")
                                    + f" (문턱 {t['TILT_OK_DEG']:.0f})")
        elif place.get("released_any") is False:
            # **놓지 않은 것은 얹은 것이 아니다** (2026-09-16).
            #
            # 앞 판은 높이·멈춤·똑바름 셋만 봤다.  그래서 바구니를 쥔 채 상판 바로 위에 대고
            # 있으면 통과했다 -- 재현했다: 상판에 닿은 65 프레임 내내 턱을 문 사본이 3 점을
            # 받았다.  판정은 `score_from_log.py` 의 `placed_free` 가 한다.
            #
            # **`is False` 로 본다.**  이 필드가 아예 없는 옛 기록은 `None` 이라 여기 안 걸리고
            # 예전처럼 채점된다 -- 모르는 것과 아닌 것은 다르다.
            items["placed"] = _item(False, "상판 높이와 자세는 맞았으나 그 순간 로봇이 "
                                           "바구니를 쥐고 있었다 — 놓아야 얹은 것이다")
        elif dm is None:
            items["placed"] = _item(None, "책상이 얼마나 움직였는지 못 읽었다 "
                                          "(동적으로 스폰됐나)")
        elif dm > t["DESK_OK_MM"]:
            items["placed"] = _item(False, f"상판에 얹히기는 했으나 책상이 {dm:.1f} mm 밀렸다 "
                                           f"(문턱 {t['DESK_OK_MM']:.0f})")
        else:
            items["placed"] = _item(True, f"상판에서 {seat:.1f} mm 뜬 채 얹혔고 "
                                          f"책상은 {dm:.3f} mm 움직였다 "
                                          f"(문턱 {t['DESK_OK_MM']:.0f})")

        # ---- Sub 3#  손 뗀 뒤 6초 --------------------------------------------------------
        # 감시창이 안 열렸으면 0점이다.  손을 끝내 안 뗀 것이고, 놓는 것이 과제다.
        #
        # **"안 열렸다"(False) 와 "열렸는지 모른다"(None) 는 다르다.**  측정기가 `opened` 를
        # 아예 안 실어 보냈으면 접촉을 못 읽었다는 뜻이고, 그것을 0점으로 매기면 재지도 않고
        # 4점을 깎는 것이 된다.
        opened = watch.get("opened")
        if opened is None:
            items["stayed"] = _item(None, "손을 뗐는지 자체를 못 읽었다")
        elif not opened:
            items["stayed"] = _item(False, "손을 떼지 않아 감시창이 열리지 않았다")
        else:
            w_seat = watch.get("seat_mm")
            w_over = watch.get("overhang_mm")
            w_tilt = watch.get("tilt_deg")
            w_spd = watch.get("tail_speed_mm_s")
            w_win = watch.get("window_s")
            # **6 초를 못 채웠으면 0 점이다** (사용자 결정 2026-09-07).
            #
            # 못 채우는 경우는 하나뿐이다 -- 손을 너무 늦게 뗐다.  에피소드에는 시간
            # 예산이 넉넉해서(제한 1,200 초), 일찍 끝낸 로봇은 6 초가 언제나 남는다.
            #
            # 있는 만큼만 보고 채점하면 **놓자마자 기록이 끝나는 쪽이 유리해진다** --
            # 볼 시간이 없으면 나쁜 순간도 없기 때문이다.  그래서 창이 짧으면 통과가
            # 아니라 실패다.  「못 잰 것」이 아니라 「못 보인 것」이므로 None 이 아니다.
            #
            # 우리 정답 주행 세 판은 창을 꽉 채우고 0.4 초가 남는다 (2026-09-07 실측).
            if watch.get("hands_off") is False:
                # 창 안에서 다시 잡았다.  「손 뗀 뒤 6 초 동안 잘 **놓여** 있었는가」이므로
                # 손을 대고 있으면 놓여 있는 것이 아니다.  바로잡고 다시 놓은 판은 여기
                # 안 걸린다 -- 그 마지막 놓기부터 창을 새로 세기 때문이다.
                items["stayed"] = _item(
                    False, "6초 창 안에서 바구니를 다시 잡았다 — 손을 뗀 뒤 6초를 "
                           "보이지 못했다 (바로잡고 다시 놓았다면 그 시점부터 다시 센다)")
            elif w_win is not None and w_win < t["WATCH_S"] - 1e-6:
                items["stayed"] = _item(
                    False, f"손 뗀 뒤 {w_win:.1f}초밖에 기록이 없다 "
                           f"(요구 {t['WATCH_S']:.0f}초) — 6초 동안 버티는 것을 보이지 못했다")
            elif None in (w_seat, w_over, w_tilt, w_spd) or dm is None:
                # `dm`(책상 밀림)을 여기 같이 넣는 이유: 아래에서 그 값을 보기 때문이다.
                # 못 읽은 채로 통과시키면 `nan > 문턱` 이 거짓이라 **유리한 쪽으로 새는**
                # 바로 그 구멍이 된다 -- `placed` 가 같은 이유로 None 을 낸다.
                items["stayed"] = _item(
                    None, "감시창 안에서 못 읽은 값이 있다"
                          + (" (책상이 얼마나 움직였는지 포함)" if dm is None else ""))
            else:
                bad = []
                if not (-t["SEAT_SINK_MAX_MM"] <= w_seat <= t["SEAT_ON_MAX_MM"]):
                    bad.append(f"받침 {w_seat:.1f} mm "
                               f"(-{t['SEAT_SINK_MAX_MM']:.0f}~{t['SEAT_ON_MAX_MM']:.0f})")
                # **걸침은 재기만 한다** (사용자 결정 2026-09-02, 위 상수의 머리말 참조).
                # 켜고 싶으면 `OVERHANG_SCORED = True` 하나만 바꾸면 된다.
                if t.get("OVERHANG_SCORED") and w_over > t["OVERHANG_OK_MM"]:
                    bad.append(f"걸침 {w_over:.1f} mm (문턱 {t['OVERHANG_OK_MM']:.0f})")
                if w_tilt > t["TILT_OK_DEG"]:
                    bad.append(f"기울기 {w_tilt:.1f} 도 (문턱 {t['TILT_OK_DEG']:.0f})")
                if w_spd >= t["STOP_MM_S"]:
                    bad.append(f"창 마지막 {t['WATCH_TAIL_S']:.1f}초 속도 {w_spd:.1f} mm/s "
                               f"(문턱 {t['STOP_MM_S']:.0f})")
                # **책상 밀림은 이 항목에도 건다** (2026-09-16).
                #
                # 앞 판은 밀림 검사가 「얹음」 가지에만 있었다.  그래서 주행 중에 책상을
                # 0.5 m 밀어붙이고도 이 4 점이 그대로 나왔다 -- 재현했다(얹음 0 / 6 초 4).
                # 평가표의 "책상이 2 cm 이상 움직였을 시 가점을 부여하지 않는다" 는
                # **Sub 3# 전체**에 걸리는 문장이지 한 항목에만 걸리는 것이 아니다.
                #
                # `placed` 와 **같은 값**을 본다 (판 내내 최악값) -- 같은 물음에 문턱이나
                # 기준을 둘 두지 않는다.
                if dm > t["DESK_OK_MM"]:
                    bad.append(f"책상이 {dm:.1f} mm 밀렸다 (문턱 {t['DESK_OK_MM']:.0f})")
                head = f"{t['WATCH_S']:.0f}초 창 최악 — "
                # 걸침은 채점에 안 쓰지만 **두 문장 모두에 숫자를 남긴다** -- 나중에 다시
                # 채점에 쓰기로 해도 로그를 다시 만들 필요가 없어야 한다.
                tail = (f" (걸침 {w_over:.1f} mm 는 쟀으나 채점에 쓰지 않는다)"
                        if not t.get("OVERHANG_SCORED") else "")
                if bad:
                    items["stayed"] = _item(False, head + " / ".join(bad) + tail)
                else:
                    items["stayed"] = _item(True,
                                            head + f"받침 {w_seat:.1f} mm / 기울기 {w_tilt:.1f} 도 "
                                            f"/ 창 끝 {w_spd:.1f} mm/s" + tail)

    # ---- 합산 -------------------------------------------------------------------------------
    out = {}
    for k in ITEMS:
        it = items[k]
        got = it["got"]
        out[k] = {"got": got, "why": it["why"], "when": WHEN[k], "label": LABEL[k],
                  "points": POINTS[k] if got else 0.0,
                  # **분모는 언제나 배점이다** (사용자 결정 2026-09-08).
                  #
                  # 예전에는 `got is None` 이면 분모에서 뺐다.  「안 했다」와 「못 쟀다」를
                  # 가르려는 뜻이었는데, 그것을 가를 방법이 로그밖에 없고 로그는 채점받는
                  # 쪽이 만든다.  실측 2026-09-08: 집기만 하고 멈추면 7/7 = 100 %,
                  # 놓기 토막만 내면 18/18 = 100 % 가 나왔다 -- **덜 할수록 비율이 좋아졌다.**
                  #
                  # 이제 한 시도는 언제나 21 점 만점이다.  못 보였으면 0 점이다.  로그가
                  # 깨져서 못 본 경우는 `log_check` 가 채점 자체를 거부하므로 여기까지
                  # 오지 않는다.  `unscored` 에는 이름을 계속 남겨 **왜 못 봤는지**는
                  # 보고한다.
                  "possible": POINTS[k]}

    groups = {}
    for k in ITEMS:
        g = groups.setdefault(GROUP[k], {"points": 0.0, "possible": 0.0})
        g["points"] += out[k]["points"]
        g["possible"] += out[k]["possible"]

    return {"items": out, "groups": groups,
            "total": sum(out[k]["points"] for k in ITEMS),
            "possible": sum(out[k]["possible"] for k in ITEMS),
            "full": sum(POINTS[k] for k in ITEMS),
            "unscored": [k for k in ITEMS if out[k]["got"] is None],
            "ended": ended,
            "elapsed_s": m.get("elapsed_s"),
            "thresholds": t}


def total(attempts):
    """시도 여러 판의 최종 점수.  **더한다** (시트: 최종 점수 = 배점 x 3).

    `attempts` 는 `score()` 결과의 목록.  세 판보다 적게 주면 **모자란 판은 0점으로 세지
    않고 만점에서도 뺀다** -- 아직 안 돌린 판과 0점 받은 판은 다르다.
    """
    got = [a for a in attempts if a]
    return {"attempts": len(got),
            "of": ATTEMPTS,
            "total": sum(a["total"] for a in got),
            "possible": sum(a["possible"] for a in got),
            "full": sum(POINTS[k] for k in ITEMS) * ATTEMPTS,
            "per_attempt": [a["total"] for a in got],
            "ended": [a.get("ended") for a in got]}


def _pad(text, width):
    """동아시아 글자를 두 칸으로 세어 폭을 맞춘다.

    `str.ljust` 는 글자 수를 세므로 한글 표가 들쭉날쭉해진다.
    """
    import unicodedata
    w = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)
    return text + " " * max(0, width - w)


def render(result, width=42):
    """사람이 읽는 채점표."""
    mark = {True: "O", False: "X", None: "-"}
    lines = []
    last = None
    for k in ITEMS:
        it = result["items"][k]
        g = GROUP[k]
        if g != last:
            gp = result["groups"][g]
            lines.append(f"[{g}]  {gp['points']:.0f} / {gp['possible']:.0f}")
            last = g
        lines.append(f"  {mark[it['got']]}  {_pad(it['label'], width)} "
                     f"{it['points']:>4.0f}/{it['possible']:.0f}  {it['why']}")
    lines.append("")
    lines.append(f"합계  {result['total']:.0f} / {result['possible']:.0f}"
                 + (f"   (만점 {result['full']:.0f}, "
                    f"못 잰 항목 {len(result['unscored'])}개는 분모에서 뺐다)"
                    if result["unscored"] else f"   (만점 {result['full']:.0f})"))
    el = result.get("elapsed_s")
    lines.append(f"판이 끝난 이유: {result['ended']}"
                 + (f"   ({el:.0f}초 / 제한 {TIME_LIMIT_S:.0f}초)" if el is not None else ""))
    return "\n".join(lines)


def render_total(tot):
    """시도 3회 합산."""
    per = " + ".join(f"{p:.0f}" for p in tot["per_attempt"]) or "-"
    return (f"시도 {tot['attempts']}/{tot['of']}판:  {per}  =  "
            f"{tot['total']:.0f} / {tot['possible']:.0f}   (만점 {tot['full']:.0f})\n"
            f"판이 끝난 이유: {', '.join(str(e) for e in tot['ended']) or '-'}")
