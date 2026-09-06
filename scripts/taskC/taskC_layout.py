# Copyright 2026.
#
# 과제 C 장면의 고정 기하. 계산대가 어디 있고, 로봇이 어디 서며, 상품이 놓이는 빨간 띠가
# 어디이고, 스캐너와 카메라가 어떻게 달리는지.
#
# 값의 출처는 옆 주석에 적었다. 대회 환경 저장소의 `taskC/kit_config.py`(계산대·로봇·띠·
# 스캐너)와 `fixture_kit/make_store.py`(구워진 매장 안 계산대 자리), 그리고 과제 A/B 데모의
# 카메라 정의다. 숫자를 여기 옮겨 적는 이유는 과제 A 와 같다 -- `scripts/` 는 마운트라
# `git pull` 만으로 갱신되고, 참가자가 장면이 어떻게 정해지는지 GitHub 에서 바로 읽을 수 있다.
#
# 두 좌표계가 나온다.
#   세계(store)  구워진 매장 USD 의 좌표. 바닥이 z = 0, 과제 A 와 같다.
#   로봇(robot)  로봇 베이스가 원점이고 +x 가 로봇 앞(계산대 쪽), +y 가 로봇 왼쪽이다.
#                띠와 배치 규칙은 이 좌표로 적혀 있다 -- 수집 파이프라인이 그렇게 쓴다.
#
# isaaclab 을 쓰지 않는 순수 파이썬이다.

import math as _math

# --------------------------------------------------------------------------- 계산대
#
# 구워진 매장(`store/scene/fixture_kit/out/store_scene.usd`) 안의 계산대. make_store.py 가
# `("cash_table", (-4.00, -4.22), FACE_PLUS_Y)` 로 놓는다. 수집 파이프라인의 kit_config 는
# convstore_store 판 계산대 (-4.00, -3.50) 를 기준으로 하고, 구워진 매장을 쓸 때는 매장을
# +Y 0.72 m 옮겨 두 계산대를 겹쳤다(V4-235). 여기서는 반대로 매장을 그대로 두고 로봇과
# 띠를 -0.72 m 옮긴다 -- 매장 좌표가 과제 A 와 같아지도록.
COUNTER_CENTRE_WORLD = (-4.00, -4.22)
COUNTER_TOP_Z = 0.9035                    # kit_config.COUNTER_TOP_Z (= convstore_store)
COUNTER_SIZE_XY = (3.2329, 1.80)          # store manifest, cash_table.size
COUNTER_FACE = "+x"                       # 로봇 좌표에서 계산대는 로봇 앞(+x)에 있다

# 매장에는 계산대 위에 정적 스캐너 소품이 하나 놓여 있다(make_store.py `("scanner",
# (-3.40, -3.92), ...)`). 과제 C 는 스캐너를 로봇이 드는 강체로 따로 스폰하므로 그 소품은
# 데모가 비활성화한다 -- 둘이면 장면에 스캐너가 두 개가 된다.
STORE_STATIC_SCANNER_XY = (-3.40, -3.92)

# --------------------------------------------------------------------------- 로봇
#
# kit_config: ROBOT_BASE_WORLD = (-3.50 + BASE_RIGHT 0.05, -3.70 + BASE_FORWARD 0.15) 를
# convstore 계산대 기준으로 적은 값. 위의 0.72 m 만큼 -Y 로 옮긴다.
_SHIFT_Y = COUNTER_CENTRE_WORLD[1] - (-3.50)          # = -0.72
ROBOT_BASE_WORLD = (-3.45, -3.55 + _SHIFT_Y, 0.0)
ROBOT_YAW = _math.pi / 2.0                # 세계 +Y 를 본다 = 계산대 위로
LIFT_JOINT_POS = 0.0                      # kit_config.LIFT_JOINT_POS
HEAD_PITCH = 0.6951                       # V4-139: 60 도를 요청하지만 관절 한계 0.6951 rad(39.8 도)
HEAD_YAW = 0.0
# kit_config.STOW_ARM_POS -- 오른팔 값. 왼팔은 joint2·joint3 의 부호를 뒤집는다
# (kit_config.stow_joint_pos 실측: 두 팔의 그 두 관절 가동범위가 거울상이다).
STOW_ARM_R = (1.2000, -0.4500, -0.0632, -2.5870, 0.0, 0.0, 0.0)
STOW_ARM_L = (1.2000, 0.4500, 0.0632, -2.5870, 0.0, 0.0, 0.0)
WHEEL_RADIUS = 0.0864                     # 과제 A/B 데모와 같은 값

# --------------------------------------------------------------------------- 빨간 띠
#
# 상품이 놓이는 사각형 (로봇 좌표). `.urdf_export/reach_band_final.json` 의 x0/x1/y0/y1.
# 테이프 폭 20 mm 는 띠 안쪽에서 뺀다 -- 상품이 테이프에 닿아서도 안 된다.
BAND = {"x0": 0.1101, "x1": 0.4999, "y0": -0.01, "y1": 0.57}
TAPE_W = 0.02
TAPE_T = 0.005                            # kit_config.TAPE_T -- 테이프 두께 5 mm
TAPE_COLOR = (0.80, 0.03, 0.03)           # qr_scene 이 그리는 빨간 띠 색

# 배치 규칙 상수 (qr_scene.deal)
STOW_GRIP_XY = (0.19, 0.30)               # QR-35: 스토우 자세의 왼손 그리퍼가 띠 위에 떠 있는 자리
STOW_GRIP_CLEAR = 0.14                    # 그 아래 반경 0.14 m 에는 상품을 놓지 않는다
MIN_GAP = 0.10                            # QR-11: 상품 표면-표면 >= 10 cm
QR_TARGET_YAW_DEG = -90.0                 # kit_config.BARCODE_TARGET_YAW_DEG: QR 면이 세계 -Y(정 오른쪽)
QR_AZ_TOL_DEG = 3.0                       # QR-62: 정착 후 허용 오차 +-3 도
MAX_REDEAL = 50

# --------------------------------------------------------------------------- 스캐너
#
# 에피소드 시작 순간 스캐너는 왼손이 드는 자리에 떠 있다(중력 없음). 수집 재생기가 같은
# 자세로 스폰한다: kit_config.SCANNER_HOLD_POS / SCANNER_HOLD_QUAT (로봇 좌표).
SCANNER_HOLD_POS = (0.330, -0.1578, 1.161)
SCANNER_HOLD_QUAT = (0.7071068, 0.7071068, 0.0, 0.0)
SCANNER_SIZE = (0.0674, 0.1607, 0.0872)

# --------------------------------------------------------------------------- 카메라
#
# 채점이 정책에게 보내는 관측 셋. 머리는 과제 A 데모의 값(zed/cam_head), 손목은 과제 B 데모의
# 값(424x240) 그대로다. prim 경로는 로봇 prim 아래 상대 경로.
CAMERAS = {
    "head_cam": dict(
        rel="ffw_sg2_follower/head_link2/zed/cam_head", w=672, h=376,
        focal=10.4, focus=200.0, aperture=20.955, clip=(0.1, 100.0),
        offset_pos=(0.0, 0.03, 0.0), offset_rot=(0.5, 0.5, -0.5, -0.5)),
    "left_wrist_cam": dict(
        rel="ffw_sg2_follower/arm_l_link7/camera_l_bottom_screw_frame/camera_l_link/left_wrist_cam",
        w=424, h=240, focal=18.0, focus=400.0, aperture=20.955, clip=(0.1, 2.0),
        offset_pos=(-0.08, 0.0, 0.0), offset_rot=(0.5, -0.5, -0.5, 0.5)),
    "right_wrist_cam": dict(
        rel="ffw_sg2_follower/arm_r_link7/camera_r_bottom_screw_frame/camera_r_link/right_wrist_cam",
        w=424, h=240, focal=18.0, focus=400.0, aperture=20.955, clip=(0.1, 2.0),
        offset_pos=(-0.08, 0.0, 0.0), offset_rot=(0.5, -0.5, -0.5, 0.5)),
}


def band_inner():
    """테이프 폭만큼 안쪽으로 들어온 (x0, x1, y0, y1) -- 상품이 있어도 되는 영역(로봇 좌표)."""
    return (BAND["x0"] + TAPE_W, BAND["x1"] - TAPE_W, BAND["y0"] + TAPE_W, BAND["y1"] - TAPE_W)


def stow_joint_pos() -> dict:
    """{관절 이름: rad}. kit_config.stow_joint_pos() 와 같은 값."""
    out = {}
    for i, (r, l) in enumerate(zip(STOW_ARM_R, STOW_ARM_L), 1):
        out[f"arm_r_joint{i}"] = float(r)
        out[f"arm_l_joint{i}"] = float(l)
    return out


def world_to_robot(p):
    """세계 (x, y[, z]) -> 로봇 좌표."""
    dx, dy = p[0] - ROBOT_BASE_WORLD[0], p[1] - ROBOT_BASE_WORLD[1]
    c, s = _math.cos(-ROBOT_YAW), _math.sin(-ROBOT_YAW)
    out = (c * dx - s * dy, s * dx + c * dy)
    return out + tuple(p[2:]) if len(p) > 2 else out


def robot_to_world(p):
    """로봇 (x, y[, z]) -> 세계 좌표."""
    c, s = _math.cos(ROBOT_YAW), _math.sin(ROBOT_YAW)
    out = (ROBOT_BASE_WORLD[0] + c * p[0] - s * p[1],
           ROBOT_BASE_WORLD[1] + s * p[0] + c * p[1])
    return out + tuple(p[2:]) if len(p) > 2 else out


def quat_mul(a, b):
    """(w, x, y, z) 곱."""
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return (w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2)


def robot_yaw_quat():
    """로봇 좌표 -> 세계 좌표 회전 (세계 Z 축 +90 도)."""
    return (_math.cos(ROBOT_YAW / 2.0), 0.0, 0.0, _math.sin(ROBOT_YAW / 2.0))


def quat_robot_to_world(q):
    """로봇 좌표에서 적힌 자세 쿼터니언을 세계 좌표로."""
    return quat_mul(robot_yaw_quat(), q)


def quat_world_to_robot(q):
    yq = robot_yaw_quat()
    return quat_mul((yq[0], -yq[1], -yq[2], -yq[3]), q)
