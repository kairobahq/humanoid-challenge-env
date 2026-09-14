"""Task-C 채점기.

평가표(Task-C) 의 5개 항목을 **시뮬 루프 안에서 매 스텝 판정**한다.
채점기는 로봇을 조작하지 않는다. 관측만 한다.

설계 원칙
  - 임계값은 전부 `ScoreConfig` 로 뺐다. 코드에 숫자를 박지 않는다.
  - **상판 높이·띠 좌표는 상수로 받지 않고 씬을 세운 뒤 재서 넣는다**(평가안 규정).
  - 판정이 성립하면 **래치**된다. 뒤에 놓쳐도 점수는 남고, 다시 해도 가점되지 않는다.
  - 연속 조건은 **한 프레임이라도 깨지면 타이머를 0 으로 되돌린다**.
  - 배선되지 않은 관측은 0 점이 아니라 **UNAVAILABLE** 로 남긴다. 조용히 틀리지 않는다.

사용법은 README.md 참조.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from geometry import aabb_from_obb, aabb_xy_overlaps_rect, closest_dist

UNAVAILABLE = "UNAVAILABLE"


# --------------------------------------------------------------------------- 설정

@dataclass
class ScoreConfig:
    """평가표 Task-C 의 임계값. 원본에서 확인이 필요한 값은 주석에 표시했다."""

    # Sub 1-1 물품을 쥐었는가 (2점)
    # 접촉 센서를 쓰지 않는다. 그리퍼는 액추에이터가 **하나**(gripper_?_joint1)뿐이라
    # V홈에 물리든 팁에 물리든 그 모터의 부하 하나로 드러난다.
    #   부하 = clip(stiffness x (명령 - 실측), ±effort_limit)   [N·m]
    #   FFW_SG2 좌측: stiffness 300.0, effort_limit 30.0
    grip_load_min_nm: float = 5.0        # 이 이상이면 모터가 실제로 밀고 있다
    grip_stall_margin_rad: float = 0.02  # 자유 닫힘 위치보다 이만큼 못 닫혔으면 물린 것
    grip_hold_s: float = 0.3             # 0.3초 연속
    pts_grip: float = 2.0
    # 「들려 있다」의 정의 -- 상판에서 이만큼 떠 있어야 손에 들린 것으로 본다.
    # 그리퍼가 닫혀 있어도 물건이 상판에 얹혀 있으면 든 것이 아니다.
    # (조준·판독 조건은 모두 물체를 실제로 들고 있을 때만 성립한다 --
    #  다 왼손에서 물체를 들었을 경우에만 해당")
    held_clear_m: float = 0.005

    # Sub 1-2 상판에서 들어올렸는가 (2점)
    lift_clear_m: float = 0.020          # AABB 최저점이 상판보다 20 mm 위
    pts_lift: float = 2.0

    # Sub 2-1 스캐너가 물체를 향했는가 (3점)
    aim_dist_m: float = 0.15             # 빔 출발선 -> 표면 최근접점 0.15 m 이하
    aim_hold_s: float = 1.0              # 1초 연속
    # 원문은 「프레임에 상품 픽셀 1개 이상」이지만, 그러면 화면 구석에 점 하나만 걸쳐도
    # 통과한다. 기준: **프레임의 10% 이상**을 차지해야 한다.
    aim_coverage_min: float = 0.10       # 스캐너 카메라 프레임 대비 상품 픽셀 비율
    pts_aim: float = 3.0

    # Sub 2-2 QR 인식에 성공했는가 (7점)
    decode_dist_m: float = 0.15          # 같은 0.15 m. 최적화가 아니라 채점 조건이다.
    # 판독에도 같은 화면 점유 조건을 걸지 여부. 원문 3조건에는 없어 기본 꺼둔다.
    decode_require_coverage: bool = False
    pts_decode: float = 7.0

    # Sub 3 빨간 띠에 놓았는가 (3점) -- 상품 AABB 가 띠(테이프 바깥선)와 **일부라도 겹치면** 인정, 걸침 포함
    #   (geometry.aabb_xy_overlaps_rect; 중심 기준이 아니다)
    release_speed_max: float = 0.010     # 10 mm/s 미만이면 「멈췄다」
    pts_place: float = 3.0

    # 중지 조건
    fall_speed_max: float = 0.010        # 낙하 판정도 10 mm/s
    fall_clear_m: float = 0.020          # 상판보다 이만큼 아래로 내려가야 「떨어졌다」.
                                         # 0 으로 두면 상판에 얹힌 물체가 수치오차로 낙하 판정된다.
    time_limit_s: float = 1200.0         # 20분. 원본에 10분 표기도 있다 -> README §6-①

    @property
    def pts_total_per_product(self) -> float:
        return (self.pts_grip + self.pts_lift + self.pts_aim
                + self.pts_decode + self.pts_place)


# --------------------------------------------------------------------------- 래치

class _Latch:
    """한 번 성립하면 유지되는 판정. 연속 시간 조건을 함께 다룬다."""

    def __init__(self, hold_s: float = 0.0):
        self.hold_s = float(hold_s)
        self.passed = False
        self.acc = 0.0
        self.first_t: Optional[float] = None
        self.available = False   # 관측이 한 번이라도 들어왔는가

    def update(self, cond: Optional[bool], dt: float, t: float) -> bool:
        if cond is None:          # 관측 없음 -- 타이머를 건드리지 않는다
            return self.passed
        self.available = True
        if self.passed:
            return True
        if cond:
            self.acc += dt
            if self.acc >= self.hold_s:
                self.passed = True
                self.first_t = t
        else:
            self.acc = 0.0        # 한 프레임이라도 깨지면 0 으로
        return self.passed

    def state(self):
        if self.passed:
            return True
        return False if self.available else UNAVAILABLE


# --------------------------------------------------------------------------- 상품별

class ProductScore:
    def __init__(self, slug: str, cfg: ScoreConfig):
        self.slug = slug
        self.cfg = cfg
        self.grip = _Latch(cfg.grip_hold_s)
        self.lift = _Latch(0.0)
        self.aim = _Latch(cfg.aim_hold_s)
        self.decode = _Latch(0.0)
        self.place = _Latch(0.0)
        self.fallen = False
        self.fall_t = None
        self._was_grasped = False
        self._release_pending = False   # 손을 뗐고, 멈추기를 기다리는 중
        # 왜 그렇게 됐는지 설명하려면 숫자가 있어야 한다. 매 틱 갱신한다.
        self.ev = dict(max_load_nm=0.0, max_grip_run_s=0.0, max_lift_m=None,
                       min_dist_m=None, frames_near=0, frames_grasped=0,
                       max_coverage=None, frames_held=0,
                       released=False, release_t=None, release_in_band=None,
                       release_pos=None)
        self.notes: list[str] = []

    # -- Sub 3 은 「내려놓은 순간 한 번」만 본다
    def judge_release(self, in_band: bool, t: float):
        if self.place.passed:
            return
        if not self.decode.passed:
            # 인식보다 먼저 띠 안에 놓은 것은 인정하지 않는다.
            # 「판정을 못 했다(UNAVAILABLE)」가 아니라 「판정했고 못 얻었다(FAIL)」이다.
            self.place.available = True
            self.notes.append(f"t={t:.2f} 내려놓음 -- QR 인식 전이라 미인정")
            return
        self.place.available = True
        if in_band:
            self.place.passed = True
            self.place.first_t = t
        self.notes.append(f"t={t:.2f} 내려놓음 -- 띠 교차 {'O' if in_band else 'X'}")

    def points(self) -> float:
        c = self.cfg
        return (c.pts_grip * self.grip.passed + c.pts_lift * self.lift.passed
                + c.pts_aim * self.aim.passed + c.pts_decode * self.decode.passed
                + c.pts_place * self.place.passed)

    def all_five(self) -> bool:
        return all(x.passed for x in (self.grip, self.lift, self.aim,
                                      self.decode, self.place))

    def explain(self, cfg) -> dict:
        """왜 그렇게 됐는지 -- 실측 숫자로 설명한다. 추측하지 않는다."""
        e, out = self.ev, {}

        def say(key, latch, ok_msg, fail_msg, na_msg):
            st = latch.state()
            out[key] = ok_msg if st is True else (na_msg if st == UNAVAILABLE else fail_msg)

        say("sub1_1_grip", self.grip,
            f"모터 부하가 {cfg.grip_load_min_nm:.1f}N·m 이상으로 "
            f"{cfg.grip_hold_s:.1f}초 연속 유지됐다 (최대 {e['max_load_nm']:.1f}N·m)",
            (f"부하 최대 {e['max_load_nm']:.1f}N·m, 연속 유지 최대 {e['max_grip_run_s']:.2f}초 — "
             f"기준({cfg.grip_load_min_nm:.1f}N·m / {cfg.grip_hold_s:.1f}초)에 못 미쳤다. "
             + (f"쥐긴 했으나 {cfg.grip_hold_s:.1f}초를 못 채웠다."
                if e['max_load_nm'] >= cfg.grip_load_min_nm
                else "모터가 밀지 않았다 — 손가락 사이에 아무것도 없었다.")),
            "그리퍼 부하가 배선되지 않아 재지 못했다")

        _ml = e["max_lift_m"]
        say("sub1_2_lift", self.lift,
            f"상판보다 최대 {(_ml or 0)*1000:.0f}mm 높이 올렸다",
            (f"쥔 상태에서 상판 대비 최대 {(_ml or 0)*1000:.0f}mm — "
             f"기준 {cfg.lift_clear_m*1000:.0f}mm 에 못 미쳤다"
             if _ml is not None else "쥔 적이 없어 들어올릴 기회가 없었다"),
            "파지 상태가 배선되지 않아 재지 못했다")

        _md = e["min_dist_m"]
        say("sub2_1_aim", self.aim,
            f"빔까지 최소 {(_md or 0):.3f}m, 화면 점유 최대 "
            f"{(e['max_coverage'] or 0)*100:.1f}% 로 {cfg.aim_hold_s:.0f}초 연속 유지했다",
            (f"빔까지 최소 {_md:.3f}m — 기준 {cfg.aim_dist_m:.2f}m 밖이다"
             if _md is not None and _md > cfg.aim_dist_m
             else (f"거리는 들어왔으나({(_md or 0):.3f}m) 화면 점유 최대 "
                   f"{(e['max_coverage'] or 0)*100:.1f}% 로 기준 {cfg.aim_coverage_min*100:.0f}% 에 못 미쳤다"
                   if (e.get("max_coverage") or 0) < cfg.aim_coverage_min
                   else f"거리·점유는 만족했으나 {cfg.aim_hold_s:.0f}초 연속을 못 채웠다")),
            f"화면 점유율(프레임의 {cfg.aim_coverage_min*100:.0f}% 이상)이 배선되지 않아 재지 못했다")

        say("sub2_2_decode", self.decode,
            f"빔에서 {(_md or 0):.3f}m 안에서 기대 코드를 읽었다",
            (f"빔까지 최소 {_md:.3f}m — {cfg.decode_dist_m:.2f}m 밖이라 판독을 시도할 수 없다"
             if _md is not None and _md > cfg.decode_dist_m
             else (f"거리는 {(_md or 0):.3f}m 로 들어왔으나({e['frames_near']}프레임) "
                   f"기대 코드가 나오지 않았다 — QR 면이 안 보였거나 읽히지 않았다"
                   if e["frames_near"] else
                   ("들고 있는 동안 스캐너 앞에 온 적이 없다"
                    if e.get("frames_held") else "들어올린 적이 없어 제시 자체가 없었다"))),
            "디코더가 배선되지 않아 재지 못했다")

        if self.place.passed:
            out["sub3_place"] = f"t={e['release_t']} 에 내려놨고 AABB 가 띠와 겹쳤다"
        elif e["released"]:
            out["sub3_place"] = (f"t={e['release_t']} 에 내려놨으나 "
                                 + ("띠 밖이었다" if e["release_in_band"] is False
                                    else "QR 인식 전이라 인정되지 않는다")
                                 + f" (놓인 중심 {e['release_pos']})")
        else:
            out["sub3_place"] = "내려놓은 적이 없다 — 판정할 순간이 없었다"

        if self.fallen:
            out["_fallen"] = f"t={self.fall_t} 에 상판 아래로 떨어져 멈췄다"
        return out

    def report(self) -> dict:
        c = self.cfg
        return {
            "slug": self.slug,
            "items": {
                "sub1_1_grip":   {"pass": self.grip.state(),   "pts": c.pts_grip * self.grip.passed,   "t": self.grip.first_t},
                "sub1_2_lift":   {"pass": self.lift.state(),   "pts": c.pts_lift * self.lift.passed,   "t": self.lift.first_t},
                "sub2_1_aim":    {"pass": self.aim.state(),    "pts": c.pts_aim * self.aim.passed,     "t": self.aim.first_t},
                "sub2_2_decode": {"pass": self.decode.state(), "pts": c.pts_decode * self.decode.passed, "t": self.decode.first_t},
                "sub3_place":    {"pass": self.place.state(),  "pts": c.pts_place * self.place.passed, "t": self.place.first_t},
            },
            "points": self.points(),
            "max": c.pts_total_per_product,
            "fallen": self.fallen,
            "why": self.explain(c),
            "evidence": self.ev,
            "notes": self.notes,
        }


# --------------------------------------------------------------------------- 채점기

class TaskCScorer:
    """매 스텝 `tick()` 을 부르면 판정이 갱신된다.

    필요한 관측은 전부 **콜백**으로 받는다. 시뮬 구현에 묶이지 않게 하기 위함이다.
    배선하지 않은 콜백의 항목은 UNAVAILABLE 로 남는다.

    products: [{slug, shape, get_pose(), half_extents|radius/half_height, expected_code}, ...]
    """

    def __init__(self, products, cfg: ScoreConfig, *,
                 table_z: float, band_rect,
                 beam_origin_fn: Callable[[], np.ndarray],
                 grasp_fn: Callable[[str], Optional[bool]],
                 grip_closed_fn: Optional[Callable[[str], Optional[bool]]] = None,
                 gripper_load_fn: Optional[Callable[[str], Optional[float]]] = None,
                 gripper_pos_fn: Optional[Callable[[str], Optional[float]]] = None,
                 q_free_close: Optional[float] = None,
                 coverage_fn: Optional[Callable[[str], Optional[float]]] = None,
                 decode_fn: Optional[Callable[[str], Optional[str]]] = None):
        self.cfg = cfg
        self.table_z = float(table_z)      # 씬을 세운 뒤 **재서** 넣는다
        self.band_rect = tuple(float(v) for v in band_rect)   # 마찬가지
        self.products = {p["slug"]: p for p in products}
        self.scores = {p["slug"]: ProductScore(p["slug"], cfg) for p in products}
        self.beam_origin_fn = beam_origin_fn
        self.grasp_fn = grasp_fn
        # 놓기 엣지는 **닫힘 명령**으로 본다. 부하만 보면 조이는 도중의 일시적 하강이
        # 「놓았다」로 오탐된다(실측: 예감 t=25.20 헛엣지). 없으면 grasp_fn 으로 대체.
        self.grip_closed_fn = grip_closed_fn or grasp_fn
        self.gripper_load_fn = gripper_load_fn
        self.gripper_pos_fn = gripper_pos_fn
        # 자유 닫힘(빈손) 시 관절이 서는 위치. **씬에서 재서 넣는다** -- 상수로 박지 않는다.
        # None 이면 부하만으로 판정하고, 리포트에 그 사실을 남긴다.
        self.q_free_close = None if q_free_close is None else float(q_free_close)
        # 스캐너 카메라 프레임에서 그 상품이 차지하는 비율(0~1). None 이면 못 잼.
        self.coverage_fn = coverage_fn
        self.decode_fn = decode_fn
        self._t = 0.0
        self._last_t: Optional[float] = None
        self.stopped: Optional[str] = None
        # 「시도 소모」는 점수와 별개다. 점수는 깎이지 않지만 그 판은 거기서 끝난다.
        self.attempt_consumed = False
        self.attempt_reason: Optional[str] = None

    # ------------------------------------------------------------------ 내부
    def _obb(self, prod):
        pos, quat = prod["get_pose"]()
        if prod["shape"] == "cylinder":
            r, h = prod["radius"], prod["half_height"]
            he = (r, r, h)
        else:
            he = prod["half_extents"]
        return np.asarray(pos, dtype=float), quat, np.asarray(he, dtype=float)

    def _aabb(self, prod):
        """월드 AABB. `aabb_he`(놓인 자세의 월드 축정렬 반치수)가 있으면 그것을 쓴다.

        딜이 남기는 `he` 가 바로 그 값이다(`|R| @ (ext/2)`). 이것을 로컬 반치수로 보고
        회전을 한 번 더 먹이면 AABB 가 부풀어 상판에 얹힌 물체가 낙하로 잡힌다.
        """
        pos, quat, he = self._obb(prod)
        w = prod.get("aabb_he")
        if w is not None:
            w = np.asarray(w, dtype=float)
            return pos - w, pos + w
        return aabb_from_obb(pos, quat, he)

    def _prod_view(self, prod):
        pos, quat, he = self._obb(prod)
        v = dict(prod)
        v["pos"], v["quat"] = pos, quat
        if prod["shape"] == "box":
            v["half_extents"] = he
        return v

    # ------------------------------------------------------------------ 본체
    def tick(self, t: float):
        """t = 에피소드 경과 시간(초). 물리 스텝마다 부른다."""
        if self.stopped:
            return
        dt = 0.0 if self._last_t is None else max(0.0, t - self._last_t)
        self._last_t = t
        self._t = t

        b0 = np.asarray(self.beam_origin_fn(), dtype=float)
        n_fallen = 0

        for slug, prod in self.products.items():
            sc = self.scores[slug]
            amin, amax = self._aabb(prod)
            grasped = self.grasp_fn(slug)

            # --- Sub 1-1 그리퍼 모터 부하 0.3초 연속
            # 액추에이터가 하나라 V홈이든 팁이든 구분하지 않는다 -- 부하 하나로 본다.
            #   ① 모터가 실제로 밀고 있는가        (부하 >= grip_load_min_nm)
            #   ② 자유 닫힘보다 덜 닫혔는가        (물체가 사이에 있다는 증거)
            # ②는 q_free_close 를 측정해 넣었을 때만 본다. 빈손으로 한계까지 닫아도
            # 부하가 붙는 기구라면 ①만으로는 헛집기를 걸러내지 못한다.
            cond = None
            if self.gripper_load_fn is not None:
                ld = self.gripper_load_fn(slug)      # [N·m] 또는 None
                if ld is not None:
                    cond = abs(float(ld)) >= self.cfg.grip_load_min_nm
                    if cond and self.q_free_close is not None and self.gripper_pos_fn is not None:
                        qg = self.gripper_pos_fn(slug)
                        if qg is not None:
                            cond = (self.q_free_close - float(qg)) >= self.cfg.grip_stall_margin_rad
            if self.gripper_load_fn is not None:
                _ld = self.gripper_load_fn(slug)
                if _ld is not None:
                    sc.ev["max_load_nm"] = max(sc.ev["max_load_nm"], abs(float(_ld)))
            sc.grip.update(cond, dt, t)
            sc.ev["max_grip_run_s"] = max(sc.ev["max_grip_run_s"], sc.grip.acc)

            # --- Sub 1-2 상판보다 20mm 위 (쥔 상태에서)
            if grasped is None:
                sc.lift.update(None, dt, t)
            else:
                if grasped:
                    sc.ev["frames_grasped"] += 1
                    h = float(amin[2] - self.table_z)
                    sc.ev["max_lift_m"] = h if sc.ev["max_lift_m"] is None else max(sc.ev["max_lift_m"], h)
                sc.lift.update(bool(grasped)
                               and (amin[2] - self.table_z) > self.cfg.lift_clear_m, dt, t)

            # --- 「들려 있는가」 = 쥔 상태 + 상판에서 떠 있음.
            # 이송 중 떨어뜨리면 이 값이 즉시 False 가 되어 지향·판독이 성립하지 않는다.
            held = None if grasped is None else (
                bool(grasped) and (amin[2] - self.table_z) > self.cfg.held_clear_m)
            if held:
                sc.ev["frames_held"] = sc.ev.get("frames_held", 0) + 1

            # --- 거리 (Sub 2-1 / 2-2 공용 -- 한 번만 계산해 나눠 쓴다)
            d = closest_dist(b0, self._prod_view(prod))
            near = d <= self.cfg.aim_dist_m
            if grasped:
                sc.ev["min_dist_m"] = d if sc.ev["min_dist_m"] is None else min(sc.ev["min_dist_m"], d)
                if near:
                    sc.ev["frames_near"] += 1

            # --- Sub 2-1 지향 연속 유지 (cfg.aim_hold_s)
            cond = None
            cov = None
            if self.coverage_fn is not None:
                cov = self.coverage_fn(slug)
                if cov is not None:
                    sc.ev["max_coverage"] = max(sc.ev.get("max_coverage") or 0.0, float(cov))
            if held is not None and cov is not None:
                # 세 조건 동시: **들려 있음** / 화면 10% 이상 / 빔에서 0.15m 이내
                cond = (bool(held) and float(cov) >= self.cfg.aim_coverage_min and near)
            sc.aim.update(cond, dt, t)

            # --- Sub 2-2 판독 (같은 프레임 3조건, 1회면 통과)
            cond = None
            if held is not None and self.decode_fn is not None:
                _cov_ok = (not self.cfg.decode_require_coverage or
                           (cov is not None and float(cov) >= self.cfg.aim_coverage_min))
                if bool(held) and near and _cov_ok:
                    txt = self.decode_fn(slug)      # 기하 게이트 통과 시에만 렌더+디코드
                    if txt is not None:
                        cond = (txt == prod["expected_code"])
                else:
                    cond = False                    # 게이트 밖 -- 렌더하지 않는다
            sc.decode.update(cond, dt, t)

            # --- Sub 3 내려놓은 순간 한 번
            # 「내려놓았다」 = 쥔 상태가 풀리고 **그 뒤 처음으로** 속도가 10mm/s 미만이 된 시점.
            # 해제 프레임의 속도를 그대로 읽으면 아직 움직이는 중이라 한 프레임이면 끝난다.
            closed = self.grip_closed_fn(slug)
            if closed is not None:
                if sc._was_grasped and not closed:
                    sc._release_pending = True
                if sc._release_pending:
                    spd = float(np.linalg.norm(prod.get("get_lin_vel", lambda: (0, 0, 0))()))
                    if spd < self.cfg.release_speed_max:
                        sc._release_pending = False
                        _ib = aabb_xy_overlaps_rect(amin, amax, self.band_rect)
                        sc.ev.update(released=True, release_t=round(t, 2),
                                     release_in_band=bool(_ib),
                                     release_pos=[round(float(v), 4) for v in (amin + amax) / 2])
                        sc.judge_release(_ib, t)
                sc._was_grasped = bool(closed)

            # --- 낙하
            if not sc.fallen and amin[2] < (self.table_z - self.cfg.fall_clear_m):
                spd = float(np.linalg.norm(prod.get("get_lin_vel", lambda: (0, 0, 0))()))
                if spd < self.cfg.fall_speed_max:
                    sc.fallen = True
                    sc.fall_t = round(t, 2)
                    sc.notes.append(f"t={t:.2f} 낙하")
            if sc.fallen:
                n_fallen += 1

        # --- 중지 조건
        if n_fallen >= len(self.products) and len(self.products) > 0:
            self.stopped = "① 상품 전부 낙하"
            self.attempt_consumed = True
            self.attempt_reason = ("상품 3개가 모두 땅에 떨어졌다 -- 시도 1회 소모. "
                                   "점수는 깎이지 않고 그 시점으로 확정된다.")
        elif t >= self.cfg.time_limit_s:
            self.stopped = "② 제한 시간 경과"
            self.attempt_consumed = True
            self.attempt_reason = "제한 시간 경과 -- 시도 1회 소모."
        elif all(s.all_five() for s in self.scores.values()):
            self.stopped = "③ 전 항목 획득"

    # ------------------------------------------------------------------ 결과
    def total(self) -> float:
        return sum(s.points() for s in self.scores.values())

    def report(self) -> dict:
        return {
            "elapsed_s": round(self._t, 3),
            "stopped": self.stopped,
            "attempt_consumed": self.attempt_consumed,
            "attempt_reason": self.attempt_reason,
            "config": {
                "grip_load_min_nm": self.cfg.grip_load_min_nm,
                "grip_stall_margin_rad": self.cfg.grip_stall_margin_rad,
                "held_clear_m": self.cfg.held_clear_m,
                "grip_hold_s": self.cfg.grip_hold_s,
                "lift_clear_m": self.cfg.lift_clear_m,
                "aim_dist_m": self.cfg.aim_dist_m,
                "aim_hold_s": self.cfg.aim_hold_s,
                "aim_coverage_min": self.cfg.aim_coverage_min,
                "decode_dist_m": self.cfg.decode_dist_m,
                "fall_clear_m": self.cfg.fall_clear_m,
                "time_limit_s": self.cfg.time_limit_s,
            },
            "measured": {"table_z": self.table_z, "band_rect": list(self.band_rect),
                         "q_free_close": self.q_free_close},
            "warnings": ([] if self.q_free_close is not None else
                         ["q_free_close 미측정 -- Sub 1-1 을 모터 부하만으로 판정했다. "
                          "빈손으로 한계까지 닫아도 부하가 붙는 기구라면 헛집기가 통과할 수 있다."]),
            "products": [self.scores[s].report() for s in self.products],
            "total": self.total(),
            "max": self.cfg.pts_total_per_product * len(self.products),
        }

    def reset(self):
        """판을 갈아엎으면 그때까지의 점수는 전부 0 -- 평가안 규정."""
        self.scores = {s: ProductScore(s, self.cfg) for s in self.products}
        self._t = 0.0
        self._last_t = None
        self.stopped = None
        self.attempt_consumed = False
        self.attempt_reason = None
