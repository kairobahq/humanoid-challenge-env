"""AI Worker FFW-SG2 의 관절 순서·액션 변환·청크 궤적 — 검사기가 '실제로 보낼 궤적'을 똑같이 만들기 위한 부분.

평가 대시보드(실기 브리지)가 청크를 로봇에 보내는 계산과 같다. 검사 경로 = 실행 경로여야 판정이 의미가 있으므로,
대시보드 쪽 계산이 바뀌면 이 파일도 같이 바꾼다.
  · 액션 22개 → 관절 목표 (action_targets): 시뮬 UnifiedActionsCfg 와 같은 식
  · 청크 → 다점 궤적 (chunk_traj): 점마다 위치·속도·가속도, 컨트롤러(JTC)가 5차 스플라인으로 잇는다
"""
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

#: 22-dim 통합 액션의 슬롯 0–17 관절 (14·15 = 그리퍼 r·l, 16·17 = 목) + 리프트. 슬롯 19–21 은 베이스 속도라 검사와 무관.
JOINT_NAMES = ([f"arm_r_joint{i}" for i in range(1, 8)] + [f"arm_l_joint{i}" for i in range(1, 8)]
               + ["gripper_r_joint1", "gripper_l_joint1", "head_joint1", "head_joint2"])
POSE_KEYS = JOINT_NAMES + ["lift_joint"]   # 관절 벡터 19개의 순서 (이 패키지 전체)

#: 컨트롤러 → 관절 (ffw_sg2_follower_ai_hardware_controller.yaml). 팔 컨트롤러는 그리퍼를 함께 갖는다.
GROUPS = {
    "arm_l_controller": [f"arm_l_joint{i}" for i in range(1, 8)] + ["gripper_l_joint1"],
    "arm_r_controller": [f"arm_r_joint{i}" for i in range(1, 8)] + ["gripper_r_joint1"],
    "head_controller": ["head_joint1", "head_joint2"],
    "lift_controller": ["lift_joint"],
}
GRIPPERS = ("gripper_l_joint1", "gripper_r_joint1")
#: 팔 궤적 맨 앞 점의 시각(컨트롤러 1주기). 이 점에서 그리퍼는 직전 지령을 유지한다
#: (JTC 는 새 궤적을 실측에서 시작해, 물체를 쥔 그리퍼의 힘이 잠깐 0 으로 떨어지는 것을 막는다).
GRIP_KEEP_S = 0.01

JOINT_SCALE, GRIP_SCALE, GRIP_CLIP = 0.5, -1.0, (0.0, 1.0)   # 시뮬 UnifiedActionsCfg
GRIP_SLOTS = {14, 15}

URDF_REL = "urdf/ffw_sg2_rev1_follower/ffw_sg2_follower.urdf"


def description_dir() -> Path:
    """`ffw_description` 패키지의 **부모** 디렉토리 (URDF 의 package:// 메시 경로를 풀 때 쓴다).
    순서: 환경 변수 AIW_DESCRIPTION_DIR → ROS(ament) 설치본 → 현재 디렉토리의 ai_worker/ (ROBOTIS-GIT/ai_worker 클론)."""
    env = os.environ.get("AIW_DESCRIPTION_DIR")
    if env:
        return Path(env)
    try:
        from ament_index_python.packages import get_package_share_directory
        return Path(get_package_share_directory("ffw_description")).parent
    except Exception:  # noqa: BLE001 — ROS 없는 PC
        return Path.cwd() / "ai_worker"


def default_urdf() -> Path:
    return description_dir() / "ffw_description" / URDF_REL


def urdf_limits(urdf=None, overrides=None) -> dict:
    """{관절: [lower, upper]} (POSE_KEYS 만). overrides = {관절: (lower, upper)} 로 일부를 덮는다
    (예: 실기에서 모터 한계를 URDF 와 다르게 쓴 관절)."""
    urdf = Path(urdf or default_urdf())
    lim = {j.get("name"): [float(j.find("limit").get("lower")), float(j.find("limit").get("upper"))]
           for j in ET.parse(urdf).getroot().findall("joint") if j.get("name") in POSE_KEYS}
    for k, v in (overrides or {}).items():
        lim[k] = [float(v[0]), float(v[1])]
    return lim


def action_targets(a, home: dict, limits: dict) -> dict:
    """22 액션 → 관절 목표 {POSE_KEYS: 값}. 관절·목·리프트 = home + 0.5·a, 그리퍼 = clip(home − a, 0, 1),
    그 뒤 관절 한계로 clamp. home = 기준 자세 {POSE_KEYS: 값} (액션은 이 자세에 대한 상대값)."""
    out = {}
    for i, k in enumerate(POSE_KEYS):
        v = float(np.clip(home[k] + GRIP_SCALE * a[i], *GRIP_CLIP)) if i in GRIP_SLOTS else home[k] + JOINT_SCALE * float(a[i])
        lo, hi = limits.get(k, (-np.inf, np.inf))
        out[k] = min(max(v, lo), hi)
    return out


def chunk_traj(q0, Q, period: float):
    """청크 한 번에 보낼 다점 궤적. q0 = 지금 위치(정지로 가정), Q[N, J] = 틱별 목표.
    → (times[N], vel[N, J], acc[N, J], last_s). 위치 = 그 틱 목표 그대로, 속도 = (q_{i+1} − q_{i−1}) / 2p, 끝점 0.
    정지 → 출발 구간(N ≥ 2)과 정지 구간은 등가감속: 거리 d 를 속도 v 와 0 사이에서 등가속으로 가는 시간 2d/v 를
    [p, 3p] 로 자르고 관절 중 최대. 가운데 점 간격은 p. N = 1 은 정지 → 정지 한 구간 p."""
    Q = np.asarray(Q, float)
    n = len(Q)
    P = np.vstack([np.asarray(q0, float), Q])
    V = np.zeros_like(Q)
    V[:-1] = (P[2:] - P[:-2]) / (2 * period)

    def ramp(d, v):   # 등가감속 구간 시간
        mv = d > 1e-4
        return float(np.clip((2 * d[mv] / np.maximum(np.abs(v[mv]), 1e-9)).max(), period, 3 * period)) if mv.any() else period

    first = last = period
    if n > 1:
        first = ramp(np.abs(Q[0] - P[0]), V[0])
        last = ramp(np.abs(Q[-1] - P[-2]), V[-2])
    t = first + period * np.arange(n, dtype=float)
    if n > 1:
        t[-1] = t[-2] + last
    # 가속도 = 비균등 2차 차분, 끝점 0
    T = np.concatenate([[0.0], t])
    h1, h2 = np.diff(T)[:-1, None], np.diff(T)[1:, None]
    Acc = np.zeros_like(Q)
    Acc[:-1] = 2 * ((P[2:] - P[1:-1]) / h2 - (P[1:-1] - P[:-2]) / h1) / (h1 + h2)
    return t, V, Acc, last
