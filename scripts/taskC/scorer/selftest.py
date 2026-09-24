"""채점기 자체 검증 — 시뮬 없이 돈다.

    python selftest.py

기하 계산과 판정 로직을 가짜 관측으로 확인한다. 실패하면 AssertionError 로 죽는다.
"""
from __future__ import annotations

import math

import numpy as np

from geometry import (aabb_from_obb, aabb_xy_overlaps_rect, closest_dist_box,
                      closest_dist_cylinder, obb_sample_points)
from taskc_scorer import ScoreConfig, TaskCScorer

OK = "  OK  "
_n = [0]


def check(name, cond):
    _n[0] += 1
    assert cond, f"FAIL: {name}"
    print(OK + name)


# ------------------------------------------------------------------ 1. 기하
def test_geometry():
    print("\n[1] 기하")
    # 원통: 반경 0.033, 반높이 0.0615 (355ml 캔), 축 +Z, 원점
    C, A, R, H = (0, 0, 0), (0, 0, 1), 0.033, 0.0615
    check("원통 옆면 — 0.133m 에서 표면까지 0.100m",
          abs(closest_dist_cylinder((0.133, 0, 0), C, A, R, H) - 0.100) < 1e-9)
    check("원통 캡 — 축 위 0.1615m 에서 0.100m",
          abs(closest_dist_cylinder((0, 0, 0.1615), C, A, R, H) - 0.100) < 1e-9)
    d = closest_dist_cylinder((0.033 + 0.03, 0, 0.0615 + 0.04), C, A, R, H)
    check("원통 테두리 — hypot(0.04,0.03)=0.05", abs(d - 0.05) < 1e-9)
    check("원통 내부 — 0.0", closest_dist_cylinder((0, 0, 0), C, A, R, H) == 0.0)

    # 박스: 반크기 (0.05,0.03,0.02), 무회전
    q0 = (1, 0, 0, 0)
    check("박스 면 — 0.15m 에서 0.10m",
          abs(closest_dist_box((0.15, 0, 0), (0, 0, 0), q0, (0.05, 0.03, 0.02)) - 0.10) < 1e-9)
    check("박스 꼭짓점 — 3-4-5 삼각형",
          abs(closest_dist_box((0.05 + 0.03, 0.03 + 0.04, 0.0), (0, 0, 0), q0,
                               (0.05, 0.03, 0.02)) - 0.05) < 1e-9)
    check("박스 내부 — 0.0",
          closest_dist_box((0, 0, 0), (0, 0, 0), q0, (0.05, 0.03, 0.02)) == 0.0)

    # AABB: Z축 45도 회전한 정사각 기둥 -> XY 가 sqrt(2) 배로 커진다
    s = math.sin(math.pi / 8); c = math.cos(math.pi / 8)
    amin, amax = aabb_from_obb((0, 0, 1.0), (c, 0, 0, s), (0.05, 0.05, 0.02))
    check("AABB — 45도 회전 시 XY 반폭 0.05*sqrt2",
          abs((amax[0] - amin[0]) / 2 - 0.05 * math.sqrt(2)) < 1e-6)
    check("AABB — Z 는 불변", abs(amin[2] - 0.98) < 1e-9 and abs(amax[2] - 1.02) < 1e-9)

    # 띠 교차: 걸침도 통과여야 한다
    band = (0.11, 0.50, -0.01, 0.57)
    check("띠 — 완전히 안", aabb_xy_overlaps_rect((0.2, 0.2, 1), (0.3, 0.3, 1.1), band))
    check("띠 — 걸침(일부만 겹침)", aabb_xy_overlaps_rect((0.48, 0.2, 1), (0.55, 0.3, 1.1), band))
    check("띠 — 완전히 밖", not aabb_xy_overlaps_rect((0.6, 0.2, 1), (0.7, 0.3, 1.1), band))

    pts = obb_sample_points((0, 0, 0), q0, (0.05, 0.03, 0.02), (1, 1, 1))
    check("샘플점 9개 (면 6 + 최근접 꼭짓점 3)", pts.shape == (9, 3))


# ------------------------------------------------------------------ 2. 시나리오
class FakeProduct:
    """대본대로 움직이는 가짜 상품."""

    def __init__(self, slug, code):
        self.slug = slug
        self.code = code
        self.pos = np.array([0.30, 0.10, 0.96 + 0.0615])   # 상판 위에 앉힌 초기 자세
        self.quat = (1.0, 0.0, 0.0, 0.0)
        self.vel = np.zeros(3)

    def spec(self):
        return dict(slug=self.slug, shape="cylinder", radius=0.033, half_height=0.0615,
                    axis_local=(0, 0, 1), expected_code=self.code,
                    get_pose=lambda: (self.pos, self.quat),
                    get_lin_vel=lambda: self.vel)


def build(cfg, prods, state):
    return TaskCScorer(
        [p.spec() for p in prods], cfg,
        table_z=0.96, band_rect=(0.11, 0.50, -0.01, 0.57),
        beam_origin_fn=lambda: state["beam"],
        grasp_fn=lambda s: state["grasp"].get(s),
        gripper_load_fn=lambda s: state["load"].get(s),
        gripper_pos_fn=lambda s: state["qgrip"].get(s),
        q_free_close=state.get("qfree"),
        coverage_fn=lambda s: state["vis"].get(s),
        decode_fn=lambda s: state["decode"].get(s))


def test_full_run():
    print("\n[2] 정상 시나리오 — 5항목 전부 획득")
    cfg = ScoreConfig()
    p = FakeProduct("cocacola_zero", "8804409121470")
    st = {"beam": np.array([5.0, 5.0, 5.0]), "grasp": {}, "load": {}, "qgrip": {}, "qfree": 1.10,
          "vis": {}, "decode": {}}
    sc = build(cfg, [p], st)
    dt, t = 1 / 120, 0.0

    # (a) 접촉 0.4초 -> Sub1-1
    st["grasp"]["cocacola_zero"] = True
    st["load"]["cocacola_zero"] = 30.0     # 실측: 파지 중 부하는 30 N·m 로 포화한다
    st["qgrip"]["cocacola_zero"] = 1.028  # 실측: 콜라 정체값
    for _ in range(int(0.4 / dt)):
        t += dt; sc.tick(t)
    check("Sub1-1 쥠 통과", sc.scores["cocacola_zero"].grip.passed)

    # (b) 상판 +0.03m 로 들어올림 -> Sub1-2
    p.pos = np.array([0.30, 0.10, 0.96 + 0.0615 + 0.03])
    t += dt; sc.tick(t)
    check("Sub1-2 들어올림 통과", sc.scores["cocacola_zero"].lift.passed)

    # (c) 빔을 0.10m 앞으로 + 프레임에 보임, 2.1초 -> Sub2-1
    st["beam"] = p.pos + np.array([0.033 + 0.10, 0.0, 0.0])
    st["vis"]["cocacola_zero"] = 0.35   # 화면 35% 점유
    for _ in range(int(2.1 / dt)):
        t += dt; sc.tick(t)
    check("Sub2-1 지향 통과", sc.scores["cocacola_zero"].aim.passed)

    # (d) 디코더가 기대 코드 반환 -> Sub2-2
    st["decode"]["cocacola_zero"] = "8804409121470"
    t += dt; sc.tick(t)
    check("Sub2-2 판독 통과", sc.scores["cocacola_zero"].decode.passed)

    # (e) 띠 안에 내려놓기 -> Sub3
    p.pos = np.array([0.30, 0.10, 0.96 + 0.0615]); p.vel = np.zeros(3)
    st["grasp"]["cocacola_zero"] = False
    t += dt; sc.tick(t)
    check("Sub3 띠 안 배치 통과", sc.scores["cocacola_zero"].place.passed)
    check("합계 17.0점", abs(sc.total() - 17.0) < 1e-9)
    check("중지 조건 ③ 성립", sc.stopped == "③ 전 항목 획득")


def test_rules():
    print("\n[3] 규정 준수")
    cfg = ScoreConfig()

    # 연속 조건: 중간에 한 프레임 깨지면 타이머가 0 으로
    p = FakeProduct("a", "X")
    st = {"beam": np.array([9., 9., 9.]), "grasp": {"a": True},
          "load": {"a": 30.0}, "qgrip": {"a": 0.90}, "qfree": 1.10, "vis": {}, "decode": {}}
    sc = build(cfg, [p], st)
    dt, t = 1 / 120, 0.0
    for _ in range(int(0.08 / dt)):
        t += dt; sc.tick(t)
    st["load"]["a"] = 0.5                  # 부하가 떨어짐 (놓침) -- 기준 1 N·m 아래
    t += dt; sc.tick(t)
    st["load"]["a"] = 30.0
    for _ in range(int(0.08 / dt)):
        t += dt; sc.tick(t)
    check("부하가 끊기면 타이머 초기화 (0.08+0.08 로는 통과 못 함)",
          not sc.scores["a"].grip.passed)
    for _ in range(int(0.03 / dt) + 2):
        t += dt; sc.tick(t)
    check("이어서 0.1초를 채우면 통과", sc.scores["a"].grip.passed)

    # 인식 전 배치는 미인정
    p2 = FakeProduct("b", "Y")
    st2 = {"beam": np.array([9., 9., 9.]), "grasp": {"b": True}, "load": {}, "qgrip": {}, "qfree": 1.10,
           "vis": {}, "decode": {}}
    sc2 = build(cfg, [p2], st2)
    sc2.tick(0.01)
    st2["grasp"]["b"] = False
    sc2.tick(0.02)
    check("QR 인식 전 내려놓기는 미인정", not sc2.scores["b"].place.passed)

    # 15cm 밖 판독은 불인정
    p3 = FakeProduct("c", "Z")
    st3 = {"beam": p3.pos + np.array([0.033 + 0.20, 0, 0]), "grasp": {"c": True},
           "load": {}, "qgrip": {}, "qfree": 1.10, "vis": {"c": 0.4}, "decode": {"c": "Z"}}
    sc3 = build(cfg, [p3], st3)
    for i in range(300):
        sc3.tick(i / 120)
    check("0.20m 에서 읽힌 것은 불인정", not sc3.scores["c"].decode.passed)
    check("0.20m 에서는 지향도 불인정", not sc3.scores["c"].aim.passed)

    # 배선 안 된 관측은 0 이 아니라 UNAVAILABLE
    p4 = FakeProduct("d", "W")
    s4 = TaskCScorer([p4.spec()], cfg, table_z=0.96, band_rect=(0, 1, 0, 1),
                     beam_origin_fn=lambda: np.array([9., 9., 9.]),
                     grasp_fn=lambda s: None)
    s4.tick(0.1)
    r = s4.report()["products"][0]["items"]
    check("부하 미배선 -> UNAVAILABLE", r["sub1_1_grip"]["pass"] == "UNAVAILABLE")
    check("판독 미배선 -> UNAVAILABLE", r["sub2_2_decode"]["pass"] == "UNAVAILABLE")

    # 헛집기: 부하는 있으나 자유 닫힘 위치까지 닫혔다 -> 물린 것이 없다
    p6 = FakeProduct("e", "V")
    st6 = {"beam": np.array([9., 9., 9.]), "grasp": {"e": True},
           "load": {"e": 30.0}, "qgrip": {"e": 1.10}, "qfree": 1.10,
           "vis": {}, "decode": {}}
    sc6 = build(cfg, [p6], st6)
    for i in range(120):
        sc6.tick(i / 120)
    check("헛집기(자유 닫힘까지 닫힘) 불인정", not sc6.scores["e"].grip.passed)

    # 실측 정체값 8종이 전부 통과해야 한다
    real = {"chilsung": 0.976, "cocacola": 1.028, "pringles_o": 0.790, "pringles_s": 0.831,
            "yegam": 1.019, "lotte": 1.047, "samyang": 0.946, "ottogi": 0.859}
    for nm, q in real.items():
        pz = FakeProduct(nm, "C")
        stz = {"beam": np.array([9., 9., 9.]), "grasp": {nm: True},
               "load": {nm: 30.0}, "qgrip": {nm: q}, "qfree": 1.10,
               "vis": {}, "decode": {}}
        scz = build(cfg, [pz], stz)
        for i in range(60):
            scz.tick(i / 120)
        assert scz.scores[nm].grip.passed, f"FAIL: 실측 정체값 {nm} q={q}"
    check("실측 정체값 8종 전부 통과 (0.790~1.047)", True)

    # 상판에 얹힌 채 스캐너 앞에 있어도 인정하지 않는다 (들려 있어야 한다)
    p7 = FakeProduct("f", "T")
    p7.pos = np.array([0.30, 0.10, 0.96 + 0.0615])      # 상판에 그대로 앉아 있음
    st7 = {"beam": p7.pos + np.array([0.033 + 0.05, 0, 0]),   # 빔에서 0.05m -- 거리는 충분
           "grasp": {"f": True}, "load": {"f": 30.0}, "qgrip": {"f": 0.90}, "qfree": 1.10,
           "vis": {"f": 0.5}, "decode": {"f": "T"}}
    sc7 = build(cfg, [p7], st7)
    for i in range(400):
        sc7.tick(i / 120)
    check("상판에 얹힌 채로는 지향 불인정", not sc7.scores["f"].aim.passed)
    check("상판에 얹힌 채로는 판독 불인정", not sc7.scores["f"].decode.passed)
    check("  (같은 조건에서 집기는 인정된다)", sc7.scores["f"].grip.passed)

    # 들고 있다가 놓치면 그 순간부터 성립하지 않는다
    p8 = FakeProduct("g", "U")
    p8.pos = np.array([0.30, 0.10, 0.96 + 0.0615 + 0.10])   # 들려 있음
    st8 = {"beam": p8.pos + np.array([0.033 + 0.05, 0, 0]),
           "grasp": {"g": True}, "load": {"g": 30.0}, "qgrip": {"g": 0.90}, "qfree": 1.10,
           "vis": {"g": 0.5}, "decode": {"g": None}}
    sc8 = build(cfg, [p8], st8)
    for i in range(60):
        sc8.tick(i / 120)          # 0.5초 -- 유지 기준(1초) 미달
    p8.pos = np.array([0.30, 0.10, 0.96 + 0.0615])          # 떨어뜨림
    st8["beam"] = p8.pos + np.array([0.033 + 0.05, 0, 0])
    for i in range(60, 400):
        sc8.tick(i / 120)
    check("이송 중 떨어뜨리면 지향 유지 시간을 못 채운다", not sc8.scores["g"].aim.passed)

    # 전부 낙하하면 중지
    ps = [FakeProduct(f"p{i}", str(i)) for i in range(3)]
    st5 = {"beam": np.array([9., 9., 9.]), "grasp": {}, "load": {}, "qgrip": {}, "qfree": 1.10, "vis": {}, "decode": {}}
    sc5 = build(cfg, ps, st5)
    for q in ps:
        q.pos = np.array([0.3, 0.1, 0.5]); q.vel = np.zeros(3)
    sc5.tick(0.1)
    check("3개 전부 낙하 -> 중지", sc5.stopped == "① 상품 전부 낙하")

    # 리셋하면 0
    sc.reset()
    check("판 리셋 -> 점수 0", sc.total() == 0.0 and sc.stopped is None)


if __name__ == "__main__":
    test_geometry()
    test_full_run()
    test_rules()
    print(f"\n전부 통과 — {_n[0]}개 검사")
