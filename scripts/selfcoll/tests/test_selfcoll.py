"""자기 충돌 사전 검사기 시험 — 직접 만든 청크로.
    cd scripts/selfcoll && AIW_DESCRIPTION_DIR=<ai_worker 클론> python -m pytest -q tests
pinocchio·coal·scipy 와 FFW-SG2 URDF(ROBOTIS-GIT/ai_worker 의 ffw_description)가 없으면 건너뛴다."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pytest.importorskip("pinocchio")
pytest.importorskip("coal")
pytest.importorskip("scipy")

from aiw_selfcoll import POSE_KEYS, SelfCollision, chunk_path, close_pairs, urdf_limits  # noqa: E402
from aiw_selfcoll.robot import default_urdf  # noqa: E402

if not default_urdf().exists():
    pytest.skip(f"URDF 없음: {default_urdf()} (AIW_DESCRIPTION_DIR 로 ai_worker 클론을 가리킨다)", allow_module_level=True)

#: 기준 자세 예시 (팔을 몸 옆으로 조금 벌리고 목을 숙인 자세). 액션은 이 자세에 대한 상대값이다.
HOME = dict.fromkeys(POSE_KEYS, 0.0) | {"arm_r_joint2": -0.349, "arm_l_joint2": 0.349, "head_joint1": 0.489,
                                        "lift_joint": -0.22}
PERIOD = 0.05


@pytest.fixture(scope="module")
def c():
    return SelfCollision()


@pytest.fixture(scope="module")
def lim():
    return urdf_limits()


def q_home():
    return np.array([HOME[k] for k in POSE_KEYS])


def ramp(joint, target, n=20, q0=None):
    """joint 를 지금(q0, 기본 HOME)에서 target(rad)까지 n 틱에 고르게 움직이는 청크 (액션 = (목표 − HOME) / 0.5)."""
    i = POSE_KEYS.index(joint)
    start = HOME[joint] if q0 is None else q0[i]
    A = np.zeros((n, 22))
    A[:, i] = (np.linspace(start, target, n + 1)[1:] - HOME[joint]) / 0.5
    return A


def test_pairs_and_paddings(c):
    close = close_pairs(c.pairs)
    pad = dict(zip(c.pairs, c._pad))
    assert len(c.pairs) > 500 and c.kin_excluded
    assert all(pad[p] == pytest.approx(0.02) for p in close)
    assert sum(v == pytest.approx(0.03) for v in pad.values()) == len(c.pairs) - len(close)
    assert ("arm_r_link2", "arm_r_link5") in close or ("arm_r_link5", "arm_r_link2") in close      # 같은 팔 접기
    assert not any(("arm_l" in a and "arm_r" in b) or ("arm_r" in a and "arm_l" in b) for a, b in close)   # 양팔 사이는 기본
    assert not any(any(x in (a, b) for x in ("arm_base_link", "base_link")) and "gripper" in a + b for a, b in close)


def test_still_chunk_passes(c, lim):
    g = c.gate_chunk(q_home(), np.zeros((10, 22)), PERIOD, HOME, lim)
    assert g["verdict"] == "pass" and g["n_exec"] == 10 and g["full"]["min_dist_m"] > 0.02


def test_mild_motion_passes(c, lim):
    g = c.gate_chunk(q_home(), ramp("arm_r_joint4", -1.0), PERIOD, HOME, lim)
    assert g["verdict"] == "pass" and g["full"]["bad_pair"] is None


def test_deep_elbow_fold_is_cut(c, lim):
    """팔꿈치를 한계까지 접으면 손목 카메라가 위팔에 다가간다 → 걸리기 전에 도착하는 점까지만."""
    g = c.gate_chunk(q_home(), ramp("arm_r_joint4", -2.9), PERIOD, HOME, lim)
    assert g["verdict"] in ("truncate", "reject") and g["n_exec"] < 20
    bad = g["full"]["bad_pair"]
    assert bad and all(x.startswith(("arm_r", "camera_right", "gripper_r")) for x in bad["pair"])
    assert bad["dist_m"] < bad["limit_m"]
    if g["verdict"] == "truncate":                                           # 잘린 청크는 다시 검사해 통과한 것
        assert g["final"]["ok"] and len(g["chunk"]) == g["n_exec"]


def test_reject_when_nothing_safe_and_no_shared_state(c, lim):
    """이미 기준에 걸린 자세에서 더 접으면 거부. 판정은 반환값에만 있고 객체에 남지 않는다."""
    g = c.gate_chunk(q_home(), ramp("arm_r_joint4", -2.9), PERIOD, HOME, lim)
    q = q_home()
    i = POSE_KEYS.index("arm_r_joint4")
    q[i] = HOME["arm_r_joint4"] + 0.5 * g["chunk"][-1][i] if g["n_exec"] else q[i]
    g2 = c.gate_chunk(q, ramp("arm_r_joint4", lim["arm_r_joint4"][0], n=5, q0=q), PERIOD, HOME, lim)
    assert g2["verdict"] in ("truncate", "reject")
    assert not hasattr(c, "bad_pair")


def test_fast_motion_needs_more_room(c, lim):
    """같은 경로라도 빠르면 속도 여유만큼 하한이 커져 더 일찍 자른다 (또는 같다)."""
    A = ramp("arm_r_joint4", -2.9)
    slow = c.gate_chunk(q_home(), A, PERIOD * 4, HOME, lim)
    fast = c.gate_chunk(q_home(), A, PERIOD / 2, HOME, lim)
    assert fast["n_exec"] <= slow["n_exec"]


def brute(c, Q, times):
    """모든 샘플·모든 쌍을 원래 메시 거리로 — check_path 의 건너뛰기·거르기 없이. 하한을 깬 첫 (샘플, 쌍) | None."""
    d0 = c.distances(Q[0], exact=True)
    thr0 = np.minimum(c._pad, np.maximum(d0, c.HARD_FLOOR))
    thr = thr0 + c.SPEED_K * (thr0 >= c._pad) * c.pair_speeds(Q, times)
    for i in range(len(Q)):
        v = thr[i] - c.distances(Q[i], exact=True, limit=thr[i])   # 하한 근처는 원래 메시로 (껍질 거리는 실제보다 작다)
        if (v > 0).any():
            return i, c.pairs[int(v.argmax())]
    return None


def test_passed_paths_hold_under_brute_force(c, lim):
    """통과(또는 잘라서 통과)한 경로를 전수 계산해도 하한을 깨지 않는다 — 무작위 팔 동작 12개."""
    rng = np.random.default_rng(0)
    arm = [i for i, k in enumerate(POSE_KEYS) if k.startswith("arm_")]
    n_cut = 0
    for _ in range(12):
        A = np.zeros((10, 22))
        A[:, arm] = np.linspace(0, 1, 11)[1:, None] * rng.uniform(-3.0, 3.0, len(arm))
        g = c.gate_chunk(q_home(), A, PERIOD, HOME, lim, budget_s=60.0)
        n_cut += g["verdict"] != "pass"
        if g["n_exec"]:
            t, Q, _ = chunk_path(q_home(), g["chunk"], PERIOD, HOME, lim)
            assert brute(c, Q, t) is None
    assert n_cut > 0          # 시험이 실제로 걸리는 동작도 포함했는지


def test_worker_process_matches(c, lim):
    from aiw_selfcoll.worker import SelfCollProc

    A = ramp("arm_r_joint4", -2.9)
    want = c.gate_chunk(q_home(), A, PERIOD, HOME, lim)
    p = SelfCollProc()
    p.start()
    try:
        p.configure(c.padding, c.close_padding, c.SPEED_K, c.BUDGET_S)
        got = p.gate(q_home(), A, PERIOD, HOME, lim, None, wait_s=30.0)
    finally:
        p.close()
    assert (got["verdict"], got["n_exec"]) == (want["verdict"], want["n_exec"])
