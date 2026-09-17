# Copyright 2026 ROBOTIS CO., LTD.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""과제 C 의 시작 장면을 세우고 멈춘다.

`task_c_replay.py` 를 그대로 쓰되 **기록을 틀지 않는다.** 장면·로봇·카메라·스캐너 용접·
빔 자국·LED·계산대 띠까지 재생기와 같은 것을 세우고, 로봇에게는 시작 자세만 계속 명령한다.
그래서 여기 보이는 화면이 재생 첫 프레임과 같고, 정책이 t=0 에 받게 될 관측과도 같다.

    cd /workspace/cyclo_lab
    ${ISAACLAB_PATH}/_isaac_sim/python.sh -u         /workspace/challenge_scripts/task_c_demo.py --seed 1234

상품은 시드가 정한다. 빨간 띠 안에 3 개를 놓고, QR 면이 정 오른쪽(월드 -Y)을 보도록
돌려 세운다. 규칙(띠 안 · 최소 간격 · 원통 직립 · QR 방향)을 지킬 때까지 다시 깐다.

    --seed N              상품 3 종과 배치를 정하는 수 (0·1·2 는 평가 표본)
    --products a,b,c      상품을 직접 고른다. 첫 번째가 로봇이 다룰 대상이다
    --scene-file FILE     이미 만든 장면 JSON 을 그대로 쓴다 (재생기 기록의 장면도 된다)
    --scene-json FILE     세운 장면을 JSON 으로 적는다
    --shot FILE.png       머리 카메라 그림을 한 장 적는다
    --seconds S           S 초 동안 세워 둔다 (0 이면 창을 닫을 때까지, --headless 면 바로 끝)
"""

import argparse
import glob
import json
import os
import sys
import threading as _threading

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="과제 C 의 시작 장면을 세우고 멈춘다.")
parser.add_argument("--seed", type=int, default=1000,
                    help="상품 3 종과 배치를 정하는 수 (0·1·2 는 평가 표본)")
parser.add_argument("--products", default=None, metavar="a,b,c",
                    help="상품을 직접 고른다. 첫 번째가 로봇이 다룰 대상이다.")
parser.add_argument("--scene-file", default=None, metavar="FILE.json",
                    help="이미 만든 장면 JSON 을 그대로 쓴다.")
parser.add_argument("--scene-json", default=None, metavar="FILE.json",
                    help="세운 장면을 JSON 으로 적는다.")
parser.add_argument("--shot", default=None, metavar="FILE.png",
                    help="머리 카메라 그림을 한 장 적는다.")
parser.add_argument("--seconds", type=float, default=0.0,
                    help="S 초 동안 세워 둔다 (0 이면 창을 닫을 때까지).")
AppLauncher.add_app_launcher_args(parser)
parser.set_defaults(device="cpu")
args_cli = parser.parse_args()
args_cli.enable_cameras = True

import importlib.util as _ilu   # noqa: E402
import math                     # noqa: E402

CYCLOLAB = os.environ.get("CYCLOLAB_PATH", "/workspace/cyclo_lab")
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from taskC import taskC_check as K        # noqa: E402
from taskC import taskC_layout as L       # noqa: E402
from taskC import taskC_products as P     # noqa: E402

DEMO_DIRS = {"gt": os.path.join(_HERE, "taskC", "demos_gt"),
             "single": os.path.join(_HERE, "taskC", "demos")}
PHYSICS_DT = 1.0 / 120.0
RENDER_EVERY = 4
WHEEL_RADIUS = L.WHEEL_RADIUS
STORE_USD = str(P.store_usd())
SCANNER_USD = str(P.scanner_usd())

# 기록의 22 열. kit_config.STATE_JOINTS 와 같다: 왼팔 7 · 왼 그리퍼 1 · 오른팔 7 · 오른 그리퍼 1 ·
# 머리 2 · 리프트 1 · 예비 3(베이스 속도 -- 정지 과제라 0).
REC_JOINTS = ([f"arm_l_joint{i}" for i in range(1, 8)] + ["gripper_l_joint1"]
              + [f"arm_r_joint{i}" for i in range(1, 8)] + ["gripper_r_joint1"]
              + ["head_joint1", "head_joint2", "lift_joint"])


def _demos(which):
    out = []
    for d in sorted(glob.glob(os.path.join(DEMO_DIRS[which], "*"))):
        if os.path.isfile(os.path.join(d, "actions.npy")) or os.path.isfile(os.path.join(d, "joints.npy")):
            out.append(d)
    return out


def _meta(d):
    f = os.path.join(d, "meta.json")
    return json.load(open(f, encoding="utf-8")) if os.path.isfile(f) else {}


# 장면은 기록에서 오지 않고 **여기서 깐다.** 시드가 상품 3 종과 자리를 정하고, 규칙을
# 지킬 때까지 다시 깐다. `--scene-file` 을 주면 그 JSON 을 그대로 쓴다 (재생기 기록의
# 장면 파일도 그대로 들어간다).
import numpy as np  # noqa: E402

if args_cli.scene_file:
    SCENE = json.load(open(args_cli.scene_file, encoding="utf-8"))
    print(f"[장면] {args_cli.scene_file} 을 그대로 쓴다", flush=True)
else:
    from taskC import taskC_deal as D          # noqa: E402
    _slugs = D.pick_products(args_cli.seed, args_cli.products)
    # 2026-09-12: 간격 10 cm 를 지킬 자리가 없으면 딜이 `Infeasible` 을 낸다. 규칙을
    # 어긴 장면을 만들지 않으려고, 다음 딜로 넘어가며 한도까지 찾는다.
    _d0, _a0 = None, 0
    while _a0 < L.MAX_REDEAL:
        try:
            _d0 = D.deal(args_cli.seed, _a0, _slugs)
            break
        except D.Infeasible:
            _a0 += 1
    if _d0 is None:
        raise SystemExit(f"! 시드 {args_cli.seed}: 상품 3 개를 간격 10 cm 로 놓을 자리가 "
                         f"없다 (딜 {L.MAX_REDEAL} 회). 다른 시드를 쓴다.")
    SCENE = {"seed": args_cli.seed,
             "products": [{"slug": d["slug"], "pos": list(d["pos"]), "quat": list(d["quat"])}
                          for d in _d0]}
    # 2026-09-12: 기타 진열대(곤돌라)의 진열도 씨앗이 정한다. 구워 둔 12 벌 중 하나를 골라
    # 장면에 적어 둔다 -- 재생기는 이 이름을 보고 같은 배경을 세운다. 계산대·상품·로봇은
    # 그대로다. 구워 둔 것이 없으면 적지 않고 매장 USD 의 기본 진열로 간다.
    try:
        from taskC import taskC_store_dress as _SD       # noqa: E402
        _svs = _SD.variants()
        if _svs:
            SCENE["store_variant"] = _svs[_SD.store_seed_for(args_cli.seed) % len(_svs)]
    except Exception as _esd:
        print(f"[장면] 진열 고르기 건너뜀: {_esd!r}", flush=True)

PRODUCTS = [{"slug": p["slug"], "pos": tuple(float(v) for v in p["pos"]),
             "quat": tuple(float(v) for v in p["quat"])} for p in SCENE["products"]]
for p in PRODUCTS:
    if p["slug"] not in P.PRODUCTS:
        raise SystemExit(f"장면의 상품이 8 종에 없다: {p['slug']}")

# 로봇에게는 **시작 자세 한 줄만** 계속 명령한다. 재생기의 명령 배열 자리에 그 한 줄을
# 채워 넣으면, 아래 재생 고리가 그대로 돌면서 아무것도 움직이지 않는다. 빔·LED·띠·
# 스캐너 용접은 그 고리 안에 있으므로 전부 살아 있다.
_sp0 = L.start_joint_pos()
_q_hold = np.array([_sp0[n] for n in REC_JOINTS], dtype=np.float64)
_SEC = args_cli.seconds if args_cli.seconds > 0 else (2.0 if args_cli.headless else 1e6)
N = max(1, int(round(_SEC * 30.0)))
CMD = np.tile(_q_hold, (N, 1))
ACTIONS = JOINTS = CMD
TS = None
META = {"chain_order": [PRODUCTS[0]["slug"]]}
# 재생기는 국면표를 기록에서 읽는다. 데모는 기록이 없으므로 0 프레임짜리 하나를 둔다.
# 이름에 슬롯 접두사(`s0_`)가 없으면 빔·인식이 슬롯 0 으로 붙는다 -- 재생기가
# 싱글 판(학습 데이터 형식)을 다루는 갈래와 같은 길이다. 이게 없으면 슬롯이 -1 로
# 남아 빔 각뿔대도 띠 인식도 아예 시작되지 않는다.
PHASES = [{"start_frame": 0, "name": "정지"}]
# 상품을 놓고 가라앉히는 시간. 수집 파이프라인 `qr_scene --settle` 의 기본값이다.
SETTLE_SECONDS = 3.0
INIT = None
REC_HZ = 30.0 if TS is None or len(TS) < 2 else 1.0 / float(np.median(np.diff(TS)))
order = META.get("chain_order") or [PRODUCTS[0]["slug"]]
print("")
print("[장면] 시드 %d  상품 %s" % (args_cli.seed,
                                     " · ".join(d["slug"] for d in PRODUCTS)), flush=True)

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import torch                                                          # noqa: E402
import omni.usd                                                       # noqa: E402
import isaaclab.sim as sim_utils                                      # noqa: E402
from isaaclab.assets import AssetBaseCfg, RigidObjectCfg              # noqa: E402
from isaaclab.scene import InteractiveScene, InteractiveSceneCfg      # noqa: E402
from isaaclab.sensors import CameraCfg                                # noqa: E402
from isaaclab.utils import configclass                                # noqa: E402
from isaaclab.utils import math as math_utils                          # noqa: E402

# 로봇은 과제 C 데이터 수집 판(taskC/taskC_ffw_sg2.py)을 쓴다. 공용 FFW_SG2.py 는 과제 A·B 값이라 다르다.
from taskC.taskC_ffw_sg2 import _SG2_GRIPPER_MATERIAL              # noqa: E402
from taskC.taskC_ffw_sg2 import (                                     # noqa: E402
    FFW_SG2_MOBILE_CFG, SG2_SWERVE_STEERING_JOINTS, SG2_SWERVE_WHEEL_JOINTS,
)


def _by_path(name, path):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_TASKA = os.path.join(_HERE, "taskA")
taskA_colliders = _by_path("taskA_colliders", f"{_TASKA}/taskA_colliders.py")
robot_pose = _by_path("taskA_robot_pose", f"{_TASKA}/taskA_robot_pose.py")
from taskC import taskC_counter as counter                            # noqa: E402
from taskC import taskC_scanner as scan_look                          # noqa: E402
from taskC import taskC_beam as beam                                  # noqa: E402


# QR 을 스캐너캠 그림으로 읽는다. 끄면 기하 판정만 남는다(v5-3c 와 같은 상태).
_QR_IMG = os.environ.get("TASKC_QR_IMG", "1") == "1"


def _cam(name):
    """수집 파이프라인과 같은 형태: 로봇 prim 밑에 붙이지 않고 독립 prim 으로 두고,
    매 스텝 링크 자세에서 계산한 월드 자세를 넣는다(`place_cameras`).

    `update_period=0.0` 이라야 `scene.update` 마다 그림이 갱신된다. 큰 값을 주면
    IsaacLab 이 센서를 낡음으로 표시하지 않아 `force_recompute` 를 줘도 그림이 첫
    프레임에서 얼어붙는다(실측: 1500 장이 전부 동일했다)."""
    c = L.CAMERAS[name]
    return CameraCfg(
        prim_path="{ENV_REGEX_NS}/" + c["prim"],
        update_period=0.0, height=c["h"], width=c["w"], data_types=["rgb"],
        spawn=sim_utils.PinholeCameraCfg(focal_length=c["focal"], focus_distance=c["focus"],
                                         horizontal_aperture=c["aperture"],
                                         clipping_range=c["clip"]))


# 리프트 강성 보정.
#
# 수집 파이프라인은 매 물리 걸음마다 로봇의 **루트를 다시 써 넣는다**(V4-30(1),
# qr_sweep_replay.py 의 `hold_step`). 이 로봇의 아티큘레이션 루트는 바퀴가 달린 섀시가
# 아니라 **리프트 위의 몸통(`arm_base_link`)** 이라, 그 재기입이 몸통을 공중에 못박아
# 리프트가 눌릴 수 없게 만든다. 그래서 GT 기록의 `lift_joint` 는 전 구간 0.000000 이다.
#
# 재생기는 그 재기입을 쓸 수 없다. 열린 고리라 매 걸음 순간이동이 팔 추종 오차로 쌓여
# 파지가 무너진다(실측: 슬롯0 들림 206.7 -> 28.4 mm, 왼팔 잔차 3.8 -> 27.1 mrad).
#
# 그대로 두면 리프트가 눌린다. 이건 설정대로의 정상 결과다 -- 리프트 위 질량이 약 26 kg
# 이라 258 N 이 걸리고, 강성 10000 N/m 에서 258/10000 = 25.8 mm 가 정확히 실측된다.
# 몸통이 그만큼 내려가면 머리캠도 같이 내려가, GT 대비 카메라가 30 mm 낮아진다
# (띠 네 모서리로 역산한 값: 높이 +30.1 mm, 전체 35.1 mm).
#
# 그래서 리프트만 뻣뻣하게 만들어 v5 와 같은 물리적 상태를 만든다. 개입 지점이 관절 하나
# 뿐이라 베이스도 팔도 건드리지 않는다. 10 배(100000)면 처짐이 2.6 mm 로 줄고 카메라
# 높이 오차가 30.1 -> 5.1 mm 가 된다. 더 올리면 오히려 목표를 지나친다(바퀴가 정착하며
# 4.6 mm 올라오는 몫이 남기 때문). 0 을 주면 보정이 꺼진다.
def _quat_mat(q):
    """쿼터니언 (w, x, y, z) -> 3x3 회전. 빔을 상품 로컬로 옮길 때 쓴다."""
    w, x, y, z = [float(v) for v in q]
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w),     2 * (x * z + y * w)],
        [2 * (x * y + z * w),     1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w),     2 * (y * z + x * w),     1 - 2 * (x * x + y * y)]])


LIFT_STIFFNESS = float(os.environ.get("TASKC_LIFT_K", "100000.0"))
LIFT_DAMPING = float(os.environ.get("TASKC_LIFT_D", "1000.0"))
if LIFT_STIFFNESS > 0:
    FFW_SG2_MOBILE_CFG.actuators["lift"].stiffness = LIFT_STIFFNESS
    FFW_SG2_MOBILE_CFG.actuators["lift"].damping = LIFT_DAMPING

# 팔도 같은 이유로 뻣뻣하게 만든다. 리프트와 달리 이쪽은 **기록의 성격** 때문이다.
#
# 밀(v5)은 목표 X 를 명령하고, 팔은 중력에 처져 X - d 에 도달하며, 기록에 남는 것은 그
# **도달값** X - d 이다. 재생기가 그 기록값을 다시 *목표* 로 넣으면 팔은 거기서 또 d 만큼
# 처져 X - 2d 에 선다. 처짐이 두 번 들어가는 것이다. 실측으로 오른손이 GT 보다 14.1 mm
# 아래(-9.0, +3.7, -10.2), `arm_r_joint1` 이 +25.36 mrad, 오른팔 rms 12.20 mrad 였고,
# 그리퍼가 스캐너 손잡이의 중간을 물었다(GT 는 손잡이 위쪽을 문다).
#
# 재생기가 할 일은 기록값을 *목표* 가 아니라 *도달값* 으로 만드는 것이다. 정상상태 오차는
# 토크/강성이므로 강성을 올리면 도달값이 목표에 붙는다. 세 무리(600/600/200)의 상대 조율은
# 밀에서 온 것이라 배율로만 올려 비율을 보존한다. 감쇠는 같은 감쇠비를 유지하도록 sqrt 배.
# 1 을 주면 보정이 꺼진다.
# 매장을 로봇에서 이만큼 멀리 민다 (로봇이 세계 +y 를 보므로 +y 가 멀어지는 쪽).
# 설정 클래스 안에 두면 IsaacLab 이 자산으로 오인한다(`Unknown asset config type`).
_STORE_FWD = float(os.environ.get("TASKC_STORE_FWD", "0.0"))

# 상품을 띠와 함께 `SCENE_FWD` 만큼 옮길 것인가.
#
# 0 (기본) 이면 상품은 기록된 로봇 좌표 그대로다. 팔 궤적이 그 자리를 전제로 계획됐으므로
# 옮기면 턱이 물체 중심을 못 물어 스쳐 지나가고, QR 타일도 빔 축에서 그만큼 벗어나 6 mm
# 판정을 통과하지 못한다. 실측(GT 시드 0, 같은 6 mm):
#
#     상품 = 기록 자리   f691 에 인식 발화 (횡이탈 3.3 mm)
#     상품 = +19.9 mm    f1412 까지 발화 없음
#
# 1 이면 띠와 한 덩어리로 움직인다 -- 띠와 상품의 상대 위치를 화면에서 맞춰 볼 때만 쓴다.
# 상품 쪽 접촉 솔버. **로봇과 같은 값으로 맞춘다.**
#
# 로봇 아티큘레이션은 `solver_position_iteration_count=32` · `max_depenetration_velocity=5.0`
# 으로 단단히 잡혀 있는데(taskC_ffw_sg2.py), 상품은 아무것도 주지 않아 USD 기본값(보통 4회)
# 이었다. 접촉의 한쪽만 32회면 겹침이 상품 쪽으로 밀려 들어간다 -- 그리퍼가 물체를 뚫고
# 지나가는 것처럼 보이는 것이 이것이다. 수집 파이프라인도 상품에 안 줬지만, 그쪽에는
# 기록을 되돌려 트는 재생기가 없어 이만큼 세게 미는 접촉 자체가 없었다.
_PROD_SOLVER_POS = int(os.environ.get("TASKC_PROD_SOLVER", "32"))
# 상품 접촉 오프셋(m). 접촉을 미리 만들어 깊이 파고들기 전에 잡는다 (권장 5~10 mm).
_PROD_CONTACT_OFF = float(os.environ.get("TASKC_PROD_CONTACT_OFFSET", "0.005"))
_PROD_FWD = os.environ.get("TASKC_PROD_FWD", "1") == "1"
_prod_to_world = (lambda q: L.scene_to_world(q)) if _PROD_FWD else (lambda q: L.robot_to_world(q))

# 턱 마찰. 0 이면 수집 판 값(정지 2.0 · 운동 1.8) 그대로 쓴다.
#
# `friction_combine_mode="max"` 라 턱과 상품 중 큰 쪽이 실효값이 된다. 상품 재질은 보통
# 0.5~1.0 이라 턱이 큰 쪽이므로, 이 값을 올리면 그대로 쥐는 마찰이 올라간다. 운동 마찰은
# 정지의 0.9 배로 같은 비율을 지킨다(2.0 : 1.8).
#
# **재생기 안에서만 걸린다** -- 평가 경로(task_c_demo.py)는 수집 판 값을 그대로 쓴다.
GRIP_MU = float(os.environ.get("TASKC_GRIP_FRICTION", "0"))
if GRIP_MU > 0:
    _SG2_GRIPPER_MATERIAL.static_friction = GRIP_MU
    _SG2_GRIPPER_MATERIAL.dynamic_friction = GRIP_MU * 0.9

ARM_K_MUL = float(os.environ.get("TASKC_ARM_K_MUL", "25.0"))
if ARM_K_MUL > 1.0:
    for _g in ("DY_80", "DY_70", "DP-42"):
        _a = FFW_SG2_MOBILE_CFG.actuators[_g]
        _a.stiffness = _a.stiffness * ARM_K_MUL
        _a.damping = _a.damping * (ARM_K_MUL ** 0.5)

# 잡기 직전 손이 GT 와 어긋나는 까닭은 팔이 아니라 **베이스가 굴러간 것**이다.
# 실측(슬롯0 접근, f105): 왼팔 관절 0.53 mrad · 그리퍼 0.21 mrad 로 GT 와 맞는데도
# 섀시(`world` 링크)가 계산대 쪽으로 2.25 mm 굴러가 있다. 몸통(`arm_base_link`)은
# 2.62 mm 인데 그 차 0.37 mm 만 구조 변형이고 z 는 0.09 mm 뿐이라 리프트 침하도 아니다.
# 그 2.25 mm 가 턱을 상품 중심에서 빗나가게 해 3.4 도 다른 자세로 물리고, QR 타일이
# 빔 축에서 벗어나 인식 횡이탈이 커진다.
#
# 바퀴 구동 감쇠를 1000 배까지 올려도 안 줄었다(2.62 -> 3.08 mm). 섀시를 미는 것은 팔의
# 반작용이고 그것을 버티는 것은 **바닥 마찰**이지 구동 관절이 아니다 -- 바퀴는 굴러가는 김에
# 따라 돈 것이라, 감쇠를 올리면 구르는 대신 미끄러질 뿐이다. 그래서 그 노브는 뺐다.


@configclass
class World(InteractiveSceneCfg):
    """task_c_demo.py 와 같은 장면. 상품은 기록의 장면 JSON 그대로."""

    store = AssetBaseCfg(
        prim_path="{ENV_REGEX_NS}/Store",
        spawn=sim_utils.UsdFileCfg(usd_path=STORE_USD),
        init_state=AssetBaseCfg.InitialStateCfg(pos=(0.0, _STORE_FWD, 0.0)))
    ground = AssetBaseCfg(
        prim_path="/World/GroundPlane",
        spawn=sim_utils.GroundPlaneCfg(),
        init_state=AssetBaseCfg.InitialStateCfg(pos=(0.0, 0.0, 0.0)))
    robot = FFW_SG2_MOBILE_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")
    head_cam = _cam("head_cam")
    left_wrist_cam = _cam("left_wrist_cam")
    right_wrist_cam = _cam("right_wrist_cam")

    def __post_init__(self):
        if _QR_IMG:
            # 판독용 스캐너캠. 켤 때만 만든다 -- 800x500 을 매 판 들고 다닐 까닭이 없다.
            from taskC.scorer.qr_decode import scan_cam_cfg
            self.scan_cam = scan_cam_cfg()
        spos = L.robot_to_world(L.SCANNER_HOLD_POS)
        self.scanner = RigidObjectCfg(
            prim_path="{ENV_REGEX_NS}/Scanner",
            spawn=sim_utils.UsdFileCfg(
                usd_path=SCANNER_USD,
                rigid_props=sim_utils.RigidBodyPropertiesCfg(
                    disable_gravity=True, linear_damping=5.0, angular_damping=5.0)),
            init_state=RigidObjectCfg.InitialStateCfg(
                pos=tuple(float(v) for v in spos),
                rot=tuple(float(v) for v in L.quat_robot_to_world(L.SCANNER_HOLD_QUAT))))
        for k, d in enumerate(PRODUCTS):
            setattr(self, f"p_{k}", RigidObjectCfg(
                prim_path=f"{{ENV_REGEX_NS}}/P_{k}",
                spawn=sim_utils.UsdFileCfg(
                    usd_path=str(P.product_usd(d["slug"])),
                    rigid_props=sim_utils.RigidBodyPropertiesCfg(
                        disable_gravity=False, linear_damping=1.0, angular_damping=2.0,
                        solver_position_iteration_count=_PROD_SOLVER_POS,
                        solver_velocity_iteration_count=1,
                        max_depenetration_velocity=5.0),
                    collision_props=sim_utils.CollisionPropertiesCfg(
                        contact_offset=_PROD_CONTACT_OFF, rest_offset=0.0)),
                init_state=RigidObjectCfg.InitialStateCfg(
                    pos=tuple(float(v) for v in _prod_to_world(d["pos"])),
                    rot=tuple(float(v) for v in L.quat_robot_to_world(d["quat"])))))


def main():
    sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=PHYSICS_DT, device=args_cli.device))
    scene = InteractiveScene(World(num_envs=1, env_spacing=8.0))
    stage = omni.usd.get_context().get_stage()
    taskA_colliders.harden(stage, log=lambda *a: None)
    _log = lambda m: print(f"[i] {m}", flush=True)  # noqa: E731
    counter.deactivate_duplicates(stage, log=_log)
    # 그리퍼 턱의 충돌 형상을 SDF 로 바꾸고 접촉 오프셋을 준다 -- 관통 대책.
    #
    # RH-P12-RN 의 턱은 안쪽이 오목한 갈고리다. USD 가 싣고 온 `convexHull` 은 그 오목한
    # 부분을 메워 버려 실제 윤곽과 다른 덩어리가 되고, 그 상태로 물체를 물면 옆면으로
    # 파고든다(IsaacLab #2651 · #3571 에 같은 증상과 처방이 있다). SDF 는 삼각형 메시를
    # 그대로 거리장으로 써서 윤곽을 지킨다.
    #
    # 접촉 오프셋은 접촉을 미리 만들어 깊이 파고들기 전에 잡는 값이다(권장 5~10 mm).
    # 재생기 안에서만 건다 -- 평가 경로(task_c_demo.py)는 건드리지 않는다.
    #
    # 2026-09-18: SDF 지정 한 줄만 기본 끔으로 바꿨다(TASKC_JAW_SDF_APPROX=1 로 되살린다). SDF 스키마
    # (PhysxSDFMeshCollisionAPI)가 빠져 있어 PhysX 가 "triangle mesh ... falling back to convexHull" 에러
    # 8 줄을 내며 USD 의 convexHull 로 되돌리고 있었다 -- 즉 SDF 는 한 번도 걸린 적이 없다. 접촉 오프셋은
    # 그대로 둔다. 실측(출하 3 판): 점수 · 베이스 이동 · 세 카메라 화면이 종전과 같고 에러만 사라진다.
    if os.environ.get("TASKC_JAW_SDF", "1") == "1":
        try:
            from pxr import Usd as _U9, UsdPhysics as _UP9, PhysxSchema as _PS9
            _co = float(os.environ.get("TASKC_JAW_CONTACT_OFFSET", "0.005"))
            from taskC.taskC_ffw_sg2 import _is_sg2_gripper_jaw_prim as _is_jaw9
            _root9 = stage.GetPrimAtPath("/World/envs/env_0/Robot")
            _n9 = 0
            for _pr9 in _U9.PrimRange(_root9):
                _path9 = str(_pr9.GetPath())
                if "/collisions/" not in _path9 or not _is_jaw9(_path9):
                    continue
                if os.environ.get("TASKC_JAW_SDF_APPROX", "0") == "1":
                    _UP9.MeshCollisionAPI.Apply(_pr9).CreateApproximationAttr().Set("sdf")
                _PS9.PhysxCollisionAPI.Apply(_pr9).CreateContactOffsetAttr().Set(_co)
                _PS9.PhysxCollisionAPI(_pr9).CreateRestOffsetAttr().Set(0.0)
                _n9 += 1
            _log("턱 충돌체 SDF %d개 · 접촉 오프셋 %.0f mm" % (_n9, _co * 1000))
        except Exception as _e9:
            _log("턱 SDF 불가: %r" % (_e9,))
    counter.remove_low_shelf(stage, log=_log)
    # 2026-09-12: 기타 진열대(곤돌라 12 개)에 이 판의 진열을 건다. 계산대·스캐너·빨간 띠·
    # 집는 상품은 건드리지 않는다 -- 배경만 바뀐다. 정책이 배경까지 외우는 것을 막는다.
    # 장면 파일에 `store_variant` 가 있으면 그 벌을 그대로 세운다(기록과 같은 배경이 선다).
    # 없으면 걸지 않는다 -- 그 판은 매장 USD 의 기본 진열로 수집된 것이기 때문이다.
    try:
        from taskC import taskC_store_dress as _dress
        _sv = SCENE.get("store_variant")
        if _sv:
            _vs = _dress.variants()
            if _sv in _vs:
                _dress.dress(stage, _vs.index(_sv), log=_log)
            else:
                _log("진열(기타): 장면이 가리키는 %s 이 없다 -- 기본 진열로 간다" % _sv)
        else:
            _log("진열(기타): 장면에 store_variant 가 없다 -- 기본 진열로 간다")
    except Exception as _edr:
        _log("진열(기타) 건너뜀: %r" % (_edr,))
    # V4-311: 스캐너와 로봇의 충돌을 **`sim.reset()` 전에** 끈다. 수집 파이프라인
    # (qr_sweep_replay.py 798~818)이 하는 그대로다. 리셋 뒤에 걸면 PhysX 가 이미 충돌 쌍을
    # 구성한 뒤라 먹지 않는다(그쪽 실측: `physics:filteredPairs not found` 경고).
    #
    # 이게 없으면 정착 동안 공중에 못박힌 스캐너와 닫힌 그리퍼가 서로 밀어낸다. 그 접촉이
    # 오른팔을 밀어 `arm_r_joint1` 이 +25 mrad 어긋나고, 파지 캡처가 214 mm 로 잡힌다
    # (정상 168 mm). 양방향으로 거는 것도 원문대로다 -- 한쪽만 걸면 파서가 놓치는 사례가 있다.
    try:
        from pxr import UsdPhysics as _UP11
        _sc11 = stage.GetPrimAtPath("/World/envs/env_0/Scanner")
        _rb11 = "/World/envs/env_0/Robot"
        if _sc11 and _sc11.IsValid():
            _UP11.FilteredPairsAPI.Apply(_sc11).CreateFilteredPairsRel().AddTarget(_rb11)
            _rp11 = stage.GetPrimAtPath(_rb11)
            if _rp11 and _rp11.IsValid():
                _UP11.FilteredPairsAPI.Apply(_rp11).CreateFilteredPairsRel().AddTarget(
                    "/World/envs/env_0/Scanner")
            _log("V4-311 스캐너-로봇 충돌 필터 (reset 전, 양방향)")
        else:
            _log("V4-311 스캐너 프림 없음 -- 건너뜀")
    except Exception as _e11:
        _log("V4-311 필터 불가: %r" % (_e11,))
    sim.reset()
    counter.draw_band(log=_log)
    band_shader = counter.bind_band_idle(stage, log=_log)

    # 스캐너 겉모습 (V4-305 광채 / V4-28 다크 도색 / V4-194 LED). 기록판이 켜 두었던
    # 것들이라 이게 없으면 초록 창이 어둡게 나와 관측이 기록과 달라진다. 도색은 메시마다
    # 걸어야 LED 서브셋을 안 덮는다 -- 그래서 순서도 도색 -> LED 다.
    scan_look.enable_glow(log=_log)
    scan_look.paint_dark(stage, log=_log)
    led = scan_look.bind_led(stage, log=_log)
    # V4-346: 사출점 왼쪽 레이저 개구의 빨간 점. 스캐너 자식이라 용접을 따라간다.
    # 리셋 전에 만들어야 한다 -- 리셋 뒤에 붙인 프림은 물리 뷰에 안 잡힌다.
    scan_look.add_window_dot(stage, L.SCANNER_EMIT_LOCAL, log=_log)
    # 판독 시각을 초 단위로 주면 그 때 깜빡인다 (기록판 로그의 `V4-194 LED 깜빡임 sim t=`).
    # dev 재생기에는 판독기가 없어 기본은 상시 점등이다.
    led_at = [float(v) for v in os.environ.get("TASKC_LED_BLINK_AT", "").replace(" ", "").split(",") if v]

    # 빔 자국 + 범위 인식 + 띠 점등 (V4-70 / V4-318 / V4-337 / v5-3c).
    # 자국은 슬롯마다 따로 만든다 -- 상품 메시가 다르고, 프림도 그 상품 밑에 붙는다.
    # 수집 파이프라인은 한 판에 슬롯 하나만 돌려 `--slot` 으로 받지만 여기서는 세 슬롯을
    # 한 판에 잇는다. 그래서 활성 슬롯을 국면 이름(`s0_...`/`s1_...`)에서 읽는다.
    band_light = beam.BandLight(band_shader, log=_log) if band_shader is not None else None
    sheets, recog, cur_slot = {}, None, -1
    if os.environ.get("TASKC_BEAM", "1") == "1":
        try:
            recog = beam.Recognizer(beam.load_tiles(), log=_log)
        except Exception as _eb:
            _log("빔 자국 준비 불가: %r" % (_eb,))
    qr = None
    if _QR_IMG and recog is not None:
        try:
            from taskC.scorer.qr_decode import QrReader
            _expect = {p["slug"]: P.qr_code(p["slug"]) for p in PRODUCTS}
            qr = QrReader(scene["scan_cam"], _expect, log=_log)
            _log("QR 이미지 판독 = 횡이탈<=%.0fmm 축거리 %.0f~%.0fmm 면각<=%.0f도"
                 " 화각<=%.0f도 안에서만 디코드, 읽히면 %.0f초 쉼"
                 % (qr.lat_max, qr.d_min, qr.d_max, qr.face_max, qr.cone_half,
                    qr.cooldown))
        except Exception as _eq:
            _log("QR 이미지 판독 준비 불가: %r" % (_eq,))

    def _beam_pose():
        """세계 좌표의 빔 원점·방향·오른쪽축. 용접된 스캐너 자세에서 나온다.

        수집 파이프라인 `_beam78` 과 같다 -- 원점은 스캐너 로컬 `SCANNER_EMIT_LOCAL`,
        방향은 스캐너 로컬 -Z, 넓은 축은 스캐너 로컬 +X 다.
        """
        fq = weld["fq"].unsqueeze(0)
        fp = weld["fp"]
        def _ap(v):
            return math_utils.quat_apply(fq, torch.tensor([list(v)], dtype=torch.float32,
                                                          device=dev))[0].cpu().numpy()
        o = (fp.cpu().numpy() + _ap(L.SCANNER_EMIT_LOCAL)).astype(float)
        d = np.asarray(_ap((0.0, 0.0, -1.0)), dtype=float)
        r = np.asarray(_ap((1.0, 0.0, 0.0)), dtype=float)
        return o - origin.cpu().numpy(), d / max(np.linalg.norm(d), 1e-12),             r / max(np.linalg.norm(r), 1e-12)

    robot = scene["robot"]
    names = list(robot.joint_names)
    rec_ids, _ = robot.find_joints(REC_JOINTS, preserve_order=True)
    slave_l, _ = robot.find_joints([f"gripper_l_joint{i}" for i in (2, 3, 4)], preserve_order=True)
    slave_r, _ = robot.find_joints([f"gripper_r_joint{i}" for i in (2, 3, 4)], preserve_order=True)
    steer_ids, _ = robot.find_joints(list(SG2_SWERVE_STEERING_JOINTS), preserve_order=True)
    wheel_ids, _ = robot.find_joints(list(SG2_SWERVE_WHEEL_JOINTS), preserve_order=True)
    wheel_bodies = [i for i, n in enumerate(robot.body_names) if "wheel_drive_link" in n]
    dev = sim.device
    zero_steer = torch.zeros((1, len(steer_ids)), device=dev)
    zero_wheel = torch.zeros((1, len(wheel_ids)), device=dev)
    render = not args_cli.headless
    step_count = [0]
    IL, IR = REC_JOINTS.index("gripper_l_joint1"), REC_JOINTS.index("gripper_r_joint1")

    # 스캐너를 오른손에 든 채로 유지한다. 수집 파이프라인 `hold_step`(V4-126 · V4-29 ·
    # V4-30(2)/V4-36)을 그대로 옮긴 것이다.
    #
    #   정착 동안 : 스캐너를 캘리브레이션 자세에 **절대 고정**한다("공중 그 상태 그대로").
    #               그 사이 로봇이 내려앉으며 그리퍼가 스캐너 사이로 들어간다.
    #   정착 뒤   : 그 순간의 (고정된 스캐너, 정착을 마친 손) 상대 자세를 **한 번** 재고,
    #               그 뒤로는 매 걸음 손 자세에서 다시 계산해 써 넣는다.
    #   저역 필터 : 팔의 미세 진동이 스캐너로 전사되는 것을 흡수한다. 정지 미진동
    #               (걸음당 1.5 mm 미만)만 강하게(0.85), 실제 이동 중엔 약하게(0.3).
    #
    # 이걸 안 하면 스캐너가 중력만 꺼진 자유 물체로 떠 있다가 그리퍼에 밀려 표류하고,
    # 그 반작용이 오른팔을 밀어낸다(실측: arm_r_joint1 이 +25 mrad, 오른손 14~16 mm).
    link7 = robot.body_names.index("arm_r_link7")
    weld = {}
    zero_vel6 = torch.zeros((1, 6), device=dev)

    def hold_scanner():
        scanner = scene["scanner"]
        if not weld.get("on"):
            if "pin" in weld:
                # 정착 동안 핀의 **높이만** 로봇을 따라 내린다.
                #
                # `SCANNER_HOLD_POS` 는 로봇 좌표지만 `robot_to_world` 는 x·y 만 옮기고 z 는
                # 그대로 통과시킨다 -- 스캐너 높이는 절대값이다. 수집 파이프라인은 루트를
                # 못박아(V4-30(1)) 로봇이 가라앉지 않으므로 절대 = 상대여서 문제가 없었다.
                # 재생기는 그 재기입을 쓸 수 없어 서스펜션·리프트가 눌리는데, 그때 손만
                # 내려가고 스캐너는 공중 그 높이에 남으면 그리퍼가 손잡이의 다른 자리를 문다.
                _p = weld["pin"].clone()
                _p[0, 2] += float(robot.data.root_pos_w[0, 2]) - _root_z0w
                scanner.write_root_pose_to_sim(_p)
                scanner.write_root_velocity_to_sim(zero_vel6)
            return
        hp = robot.data.body_pos_w[0:1, link7]
        hq = robot.data.body_quat_w[0:1, link7]
        if "rp" not in weld:
            sp0 = scanner.data.root_pos_w[0:1]
            sq0 = scanner.data.root_quat_w[0:1]
            hc = math_utils.quat_conjugate(hq)
            weld["rp"] = math_utils.quat_apply(hc, sp0 - hp)
            weld["rq"] = math_utils.quat_mul(hc, sq0)
            _log("[SCANNER] 파지 실측 (오른손 link7 기준): pos (%+.5f, %+.5f, %+.5f)"
                 % tuple(float(v) for v in weld["rp"][0]))
        sp = (hp + math_utils.quat_apply(hq, weld["rp"]))[0]
        sq = math_utils.quat_mul(hq, weld["rq"])[0]
        if "fp" in weld:
            a = 0.85 if float((sp - weld["fp"]).norm()) < 0.0015 else 0.3
            sp = a * weld["fp"] + (1.0 - a) * sp
            qd = sq if float(torch.dot(weld["fq"], sq)) >= 0.0 else -sq
            sq = a * weld["fq"] + (1.0 - a) * qd
            sq = sq / sq.norm()
        weld["fp"] = sp.clone()
        weld["fq"] = sq.clone()
        scanner.write_root_pose_to_sim(torch.cat([sp, sq]).unsqueeze(0))
        scanner.write_root_velocity_to_sim(zero_vel6)

    # 카메라 장착. 수집 파이프라인 `_cam_pose_urdf` 와 같은 식이다:
    #   wq = lq * rot,  wp = lp + lq*off0 + wq*off1
    # off1 만 회전된 프레임에서 더한다. 순서를 바꾸면 손목캠이 수 cm 어긋난다.
    cam_mounts = {}
    for _cn, _c in L.CAMERAS.items():
        cam_mounts[_cn] = (
            robot.body_names.index(_c["body"]),
            torch.tensor([_c["off0"]], dtype=torch.float32, device=dev),
            torch.tensor([_c["rot"]], dtype=torch.float32, device=dev),
            torch.tensor([_c["off1"]], dtype=torch.float32, device=dev))

    # 머리캠을 로봇 뒤쪽으로 이만큼 물린다 (로봇 좌표 -x, 계산대에서 멀어지는 쪽).
    #
    # 화면이 GT 보다 계산대 +6 px · 상품 +8 px 로 어긋나는데, 로봇을 물리면(BASE_BACK) 상품이
    # 따라와 계산대만 맞고, 상품까지 맞추려 상품을 되돌리면 팔↔상품이 어긋나 파지가 무너진다
    # (실측 들림 213 -> 40 mm). **카메라만** 물리면 셋이 다 맞고 팔은 안 건드린다.
    # 0 이면 종전대로다.
    _CAM_BACK = float(os.environ.get("TASKC_CAM_BACK", "0.0"))

    def place_cameras():
        for _cn, (_bi, _o0, _q0, _o1) in cam_mounts.items():
            lp = robot.data.body_pos_w[0:1, _bi]
            lq = robot.data.body_quat_w[0:1, _bi]
            wq = math_utils.quat_mul(lq, _q0)
            wp = lp + math_utils.quat_apply(lq, _o0) + math_utils.quat_apply(wq, _o1)
            if _CAM_BACK and _cn == "head_cam":
                # 로봇 좌표 -x = 세계 -y (로봇이 +y 를 본다). 머리캠에만 적용한다.
                wp = wp + torch.tensor([[0.0, -_CAM_BACK, 0.0]], dtype=wp.dtype, device=wp.device)
            scene[_cn].set_world_poses(wp, wq, convention="world")

    def command(q19):
        """22 열 기록 한 줄을 로봇 목표로. 그리퍼 종속 관절(2~4)은 마스터와 같은 값을 준다."""
        t = torch.as_tensor(np.asarray(q19[:len(REC_JOINTS)], dtype=np.float32), device=dev).unsqueeze(0)
        robot.set_joint_position_target(t, joint_ids=rec_ids)
        robot.set_joint_position_target(t[:, IL:IL + 1].repeat(1, 3), joint_ids=slave_l)
        robot.set_joint_position_target(t[:, IR:IR + 1].repeat(1, 3), joint_ids=slave_r)
        robot.set_joint_position_target(zero_steer, joint_ids=steer_ids)
        robot.set_joint_velocity_target(zero_wheel, joint_ids=wheel_ids)

    def step(q19, do_render=True):
        command(q19)
        hold_scanner()
        scene.write_data_to_sim()
        sim.step(render=do_render and render and step_count[0] % RENDER_EVERY == 0)
        scene.update(PHYSICS_DT)
        place_cameras()
        step_count[0] += 1

    # 시작 자세는 학습 데이터(HF taskC)의 첫 프레임과 같게 둔다 (L.start_joint_pos).
    # `initial_state.json` 의 `robot_joint_pose` 는 밀의 **실측**이라 명령값과 최대 4.5 mrad
    # 다르고, 정책이 t=0 에 본 것은 명령값 쪽이다. TASKC_START_FROM_LOG=1 이면 종전처럼
    # 기록의 실측 자세에서 출발한다.
    if os.environ.get("TASKC_START_FROM_LOG", "0") == "1":
        q0 = (np.array([INIT["robot_joint_pose"][n] for n in REC_JOINTS], dtype=np.float64)
              if INIT and all(n in INIT.get("robot_joint_pose", {}) for n in REC_JOINTS)
              else JOINTS[0][:len(REC_JOINTS)])
    else:
        _sp = L.start_joint_pos()
        q0 = np.array([_sp[n] for n in REC_JOINTS], dtype=np.float64)

    # ---- 로봇을 계산대 앞에 세운다 (데모와 같은 방식). 관절은 기록의 첫 프레임 자세로.
    scene.update(PHYSICS_DT)
    origin = scene.env_origins[0]
    spawn_quat, spawn_z = robot_pose.spawn_pose(robot, origin)
    want = robot.data.default_joint_pos[0].clone()
    for n, v in zip(REC_JOINTS, q0):
        want[names.index(n)] = float(v)
    for n in [f"gripper_l_joint{i}" for i in (2, 3, 4)]:
        want[names.index(n)] = float(q0[IL])
    for n in [f"gripper_r_joint{i}" for i in (2, 3, 4)]:
        want[names.index(n)] = float(q0[IR])
    robot.write_joint_state_to_sim(want.unsqueeze(0), torch.zeros_like(want).unsqueeze(0))
    scene.write_data_to_sim()
    rx, ry = L.ROBOT_BASE_WORLD[0], L.ROBOT_BASE_WORLD[1]
    z = spawn_z
    for _ in range(2):
        robot_pose.place(robot, origin, (rx, ry), L.ROBOT_YAW, spawn_quat, z)
        scene.write_data_to_sim()
        step(q0, do_render=False)
        low = min(float(robot.data.body_pos_w[0, i][2]) for i in wheel_bodies)
        z -= low - WHEEL_RADIUS
    # 바퀴 접지로 푼 높이에 오프셋을 더한다. 화면 정합을 위한 시험용 노브다 -- 양수면
    # 로봇이 그만큼 떠서 카메라가 올라간다. 리프트 강성으로는 침하 2.6 mm 만큼만 올릴 수
    # 있어 그보다 크게 움직여야 할 때 쓴다. 0 이면 종전대로 접지 높이 그대로다.
    z += float(os.environ.get("TASKC_BASE_UP", "0.0"))
    robot_pose.place(robot, origin, (rx, ry), L.ROBOT_YAW, spawn_quat, z)
    scene.write_data_to_sim()

    # 모바일 베이스 잠금 (선택). TASKC_BASE_LOCK = 0 끔(기본) · 1 x·y·요 · 2 6축 전부.
    #
    # 이 과제에서 베이스는 움직이지 않는다 -- 기록의 바퀴·조향 명령은 전부 0 이다. 수집 파이프라인은
    # 첫 걸음의 루트 자세를 매 걸음 다시 써 넣어 6축을 묶은 채 수집했다(qr_sweep_replay.py V4-30①).
    # 여기서는 베이스가 자유 물체라 바퀴 마찰로만 서 있고, 실측으로 한 판에 뒤로 6~15 mm 밀린다
    # (10 초에 약 0.5 mm 씩, 충격 때 3~8 mm 씩). 매 걸음 루트를 써 넣는 방식은 여기서 177 mm 어긋남을
    # 낸 적이 있어, 세계와 루트 링크 사이에 D6 조인트를 걸어 같은 효과를 낸다.
    #
    # 기본은 끔이다. 스캐너 쥐는 자리 등 보정값이 밀리는 베이스에서 맞춰져 있어, 잠그면 오른손목
    # 화면이 밀 기록에서 조금 멀어지고 GT1 점수가 달라진다(36 -> 24). 재보정 뒤에 기본값을 바꾼다.
    if os.environ.get("TASKC_BASE_LOCK", "0") in ("1", "2"):
        try:
            from pxr import Gf as _G12, Usd as _U12, UsdPhysics as _UP12
            _rn12 = robot.body_names[0]
            _rb12 = None
            for _pr12 in _U12.PrimRange(stage.GetPrimAtPath("/World/envs/env_0/Robot")):
                if _pr12.GetName() == _rn12 and _pr12.HasAPI(_UP12.RigidBodyAPI):
                    _rb12 = _pr12
                    break
            if _rb12 is None:
                raise RuntimeError("루트 링크 %s 프림을 못 찾았다" % _rn12)
            _q12 = robot_pose.quat_for_yaw(spawn_quat, L.ROBOT_YAW)[0].cpu().numpy().astype(float)
            _p12 = (origin.cpu().numpy().astype(float) + np.array([rx, ry, z], dtype=float))
            _j12 = _UP12.Joint.Define(stage, "/World/envs/env_0/BaseLock")
            _j12.CreateBody1Rel().SetTargets([_rb12.GetPath()])
            _j12.CreateExcludeFromArticulationAttr().Set(True)
            # 조인트 축을 세계 축에 맞춘다: 세계 쪽은 (자리, 항등), 링크 쪽은 (0, 링크 자세의 역).
            _j12.CreateLocalPos0Attr().Set(_G12.Vec3f(float(_p12[0]), float(_p12[1]), float(_p12[2])))
            _j12.CreateLocalRot0Attr().Set(_G12.Quatf(1.0, 0.0, 0.0, 0.0))
            _j12.CreateLocalPos1Attr().Set(_G12.Vec3f(0.0, 0.0, 0.0))
            _j12.CreateLocalRot1Attr().Set(_G12.Quatf(float(_q12[0]), -float(_q12[1]), -float(_q12[2]), -float(_q12[3])))
            _axes12 = (("transX", "transY", "rotZ") if os.environ.get("TASKC_BASE_LOCK") == "1"
                       else ("transX", "transY", "transZ", "rotX", "rotY", "rotZ"))
            for _ax12 in _axes12:      # 아래 > 위 = 잠금
                _l12 = _UP12.LimitAPI.Apply(_j12.GetPrim(), _ax12)
                _l12.CreateLowAttr().Set(1.0)
                _l12.CreateHighAttr().Set(-1.0)
            _log("베이스 잠금: %s 고정, 루트 링크 %s" % ("·".join(_axes12), _rn12))
        except Exception as _e12:
            _log("베이스 잠금 불가: %r" % (_e12,))

    def _set_root(obj, pos_w, quat_w):
        st = obj.data.root_state_w[0].clone()
        st[:3] = torch.as_tensor(np.asarray(pos_w, dtype=np.float32), device=st.device) \
            + torch.as_tensor(np.asarray(origin.cpu(), dtype=np.float32), device=st.device)
        st[3:7] = torch.as_tensor(np.asarray(quat_w, dtype=np.float32), device=st.device)
        st[7:] = 0.0
        obj.write_root_state_to_sim(st.unsqueeze(0))

    for k, d in enumerate(PRODUCTS):
        # 상품은 **기록의 로봇 좌표 그대로** 놓는다. 궤적이 그 자리를 전제로 계획된 것이라
        # 옮기면 턱이 중심을 못 물고 물체가 옆으로 튄다(실측: 19 mm 옮기니 y 로 24 mm 밀려
        # 나가고 쥐는 힘이 0.19 -> 0.047 로 무너져 들림 213 -> 40 mm). 수집 파이프라인도
        # `pos=tuple(p["pos"])` 로 로봇 좌표에 그대로 놓으며 보정 장치가 없다.
        _set_root(scene[f"p_{k}"], _prod_to_world(d["pos"]), L.quat_robot_to_world(d["quat"]))
    # 스캐너도 로봇 좌표 그대로다. 오른손이 이 자리로 와서 쥐므로 옮기면 손이 손잡이의
    # 다른 자리를 문다(실측: 19 mm 옮기니 파지가 y 17 mm · z 8 mm 어긋났다).
    _set_root(scene["scanner"], L.robot_to_world(L.SCANNER_HOLD_POS), L.quat_robot_to_world(L.SCANNER_HOLD_QUAT))
    scene.write_data_to_sim()

    # 배치가 규칙을 지킬 때까지 가라앉히고 다시 깐다. 재생기는 이미 정착된 장면을 받으므로
    # 이 고리가 없다. 데모는 장면을 여기서 만드니 여기서 확정한다.
    if not args_cli.scene_file:
        from taskC import taskC_check as K     # noqa: E402
        from taskC import taskC_deal as D      # noqa: E402
        _slugs_d = [d["slug"] for d in PRODUCTS]
        _try, _ok, _res = 0, False, []
        while not _ok and _try < L.MAX_REDEAL:
            for _ in range(int(SETTLE_SECONDS / PHYSICS_DT)):
                step(q0, do_render=False)
            _res = [dict(slug=d["slug"],
                         pos=L.world_to_robot(tuple(float(v) for v in
                                                    (scene[f"p_{k}"].data.root_pos_w[0] - origin).cpu().numpy())),
                         quat=L.quat_world_to_robot(scene[f"p_{k}"].data.root_quat_w[0].cpu().numpy()))
                    for k, d in enumerate(PRODUCTS)]
            _ok = K.check_settled(_res)
            if _ok:
                break
            _try += 1
            if _try >= L.MAX_REDEAL:
                break
            _log("재딜 %d: %s" % (_try, ", ".join(K.redeal_reason(_res)) or "방위/간격"))
            _dn = None
            while _try < L.MAX_REDEAL:
                try:
                    _dn = D.deal(args_cli.seed, _try, _slugs_d)
                    break
                except D.Infeasible:
                    _try += 1
            if _dn is None:
                break
            for k, d in enumerate(_dn):
                _set_root(scene[f"p_{k}"], _prod_to_world(d["pos"]),
                          L.quat_robot_to_world(d["quat"]))
            scene.write_data_to_sim()
        # 2026-09-12: 재딜을 다 써도 규칙을 못 지키면 **장면을 내놓지 않는다**. 종전에는
        # 경고만 찍고 그대로 진행해 간격 10 cm 위반 장면이 그대로 나갔다 (레포의 장면
        # 960 개 중 100 개가 그런 판이다). 둥근 어깨 형상의 기움 구제만 종전대로 둔다.
        if not _ok and not K.fail_open_ok(_res):
            raise SystemExit("! 시드 %d: 배치가 규칙을 못 지켰다 (재딜 %d 회) -- %s"
                             % (args_cli.seed, _try,
                                ", ".join(K.redeal_reason(_res)) or "방위/간격"))
        for k, r in enumerate(_res):
            SCENE["products"][k]["pos"] = list(r["pos"])
            SCENE["products"][k]["quat"] = list(r["quat"])
            PRODUCTS[k]["pos"] = tuple(r["pos"])
            PRODUCTS[k]["quat"] = tuple(r["quat"])

    weld["pin"] = scene["scanner"].data.root_state_w[0, :7].unsqueeze(0).clone()
    _root_z0w = float(robot.data.root_pos_w[0, 2])   # 핀을 잡은 순간의 몸통 높이
    scene.write_data_to_sim()
    for _ in range(int(1.0 / PHYSICS_DT)):
        step(q0)
    # V4-126: 정착 완료 -- 여기서부터 손에 용접한다. 상대 자세는 다음 걸음에 1 회 잰다.
    weld["on"] = True

    def prod_pos_r(k):
        pw = (scene[f"p_{k}"].data.root_pos_w[0] - origin).cpu().numpy()
        return L.world_to_robot(tuple(float(v) for v in pw))

    start_pos = [prod_pos_r(k) for k in range(len(PRODUCTS))]
    scan_r = np.asarray(L.SCANNER_HOLD_POS, dtype=float)
    stat = [{"slug": d["slug"], "max_lift_mm": 0.0, "min_scanner_mm": 1e9, "min_scanner_frame": -1,
             "moved_mm": 0.0} for d in PRODUCTS]
    ph_at = {int(p["start_frame"]): p["name"] for p in PHASES if p.get("name")}
    x0, x1, y0, y1 = L.band_inner()
    t_wall = None
    import time as _time
    t_wall = _time.time()
    trace = None
    print("[장면] 섰다. 여기서 과제 C 가 시작한다.")
    for k in range(N):
        if k in ph_at:
            print(f"[장면] 국면 {ph_at[k]} -- 빔·범위 인식 켬", flush=True)
        a = CMD[k]
        b = CMD[min(k + 1, N - 1)]
        # 프레임 안에서는 **목표를 고정한다.** 밀은 프레임마다 목표를 고정하고 물리 4 걸음을
        # 돌린 뒤 기록한다. 재생기가 프레임 안에서 다음 프레임 쪽으로 목표를 끌고 가면, 도달값을
        # 읽는 시점에 이미 `JOINTS[k]` 를 지나쳐 있다. 실측(f21 왼팔 rms, mrad):
        #
        #     보간 s      3.77      <- 종전 기본값. 관절 7개가 일관되게 0.61 프레임 앞섰다
        #     보간 s+1    5.19      <- 목표를 더 앞으로 보내니 더 나빠졌다
        #     고정        0.41      <- 관절 7개 전부 0.02~0.79 mrad
        #
        # 앞서던 것은 물리도 PD 지연도 아니라 명령 방식이 기록과 달랐던 것이다.
        # `--interp` 로 옛 동작을 되살릴 수 있다.
        for s in range(4):
            q = a
            step(q)
            if led is not None:
                # v5 는 `sim.step` 에 걸어 물리 걸음마다 틱한다. 프레임마다 틱하면
                # sim 시각이 4 배 느려져 점멸 시각이 어긋난다.
                while led_at and led.sim_time >= led_at[0]:
                    led_at.pop(0)
                    led.blink()
                led.tick(PHYSICS_DT)
        if recog is not None and weld.get("on") and "fq" in weld:
            _nm = ph_at.get(k)
            if _nm is not None:
                if _nm[:1] == "s" and _nm[1:2].isdigit():
                    cur_slot = int(_nm[1])
                elif cur_slot < 0:
                    # 싱글 판(학습 데이터 형식)의 국면 이름에는 슬롯 접두사가 없다
                    # (`approach` · `sweep_00` …). 계산대에 상품 셋이 놓여 있어도 로봇이
                    # 다루는 것은 슬롯 0 하나뿐이므로 그것으로 본다. 이 갈래가 없으면
                    # 슬롯이 -1 로 남아 빔도 인식도 아예 시작되지 않는다.
                    cur_slot = 0
            if cur_slot >= 0:
                if cur_slot not in sheets:
                    try:
                        sheets[cur_slot] = beam.BeamSheet(stage, cur_slot,
                                                          PRODUCTS[cur_slot]["slug"], log=_log)
                        recog.set_slot(cur_slot, PRODUCTS[cur_slot]["slug"])
                    except Exception as _es:
                        _log("슬롯 %d 빔 자국 실패: %r" % (cur_slot, _es))
                        sheets[cur_slot] = None
                sh = sheets.get(cur_slot)
                if sh is not None:
                    _b0, _bd, _br = _beam_pose()
                    _po = scene[f"p_{cur_slot}"]
                    _pp = (_po.data.root_pos_w[0] - origin).cpu().numpy().astype(float)
                    _R = _quat_mat(_po.data.root_quat_w[0].cpu().numpy())
                    # 자국 프림이 상품 밑에 있으므로 광선을 **상품 로컬**로 옮겨 쏜다.
                    _o, _dl, _rl = _R.T @ (_b0 - _pp), _R.T @ _bd, _R.T @ _br
                    _dl = _dl / max(np.linalg.norm(_dl), 1e-12)
                    _rl = _rl / max(np.linalg.norm(_rl), 1e-12)
                    _ul = np.cross(_dl, _rl)
                    _nq = sh.update(_o, _dl, _rl, _ul / max(np.linalg.norm(_ul), 1e-12), k)
                    _lit, _fired = recog.step(_b0, _bd, _pp, _R, _nq, k)
                    if qr is not None:
                        # 판독 창 -> 그 프레임만 그림 판독 -> 읽히면 냉각.
                        _tw9, _tn9 = recog.tile_world(_pp, _R)
                        _in, _glat, _gd = qr.in_window(_b0, _bd, _tw9, _tn9)
                        _hit = qr.try_read(sim, _b0, _bd, PRODUCTS[cur_slot]["slug"],
                                           k / REC_HZ, _in)
                        if _hit is not None and _hit[1]:
                            _fired = True
                            if trace is not None:
                                trace.note_decode(cur_slot, PRODUCTS[cur_slot]["slug"], k,
                                                  _glat, _gd, text=_hit[0])
                    elif _fired and trace is not None:
                        _tw = _pp + _R @ recog._tpos
                        _v = _tw - _b0
                        _al = float(_v @ _bd)
                        trace.note_decode(cur_slot, PRODUCTS[cur_slot]["slug"], k,
                                          float(np.linalg.norm(_v - _bd * _al)) * 1000.0,
                                          _al * 1000.0, by="geometry")
                    if _fired and led is not None:
                        led.blink()
                    if band_light is not None:
                        band_light.set_hit(_lit, k)
        if trace is not None:
            _po_all = [scene[f"p_{i}"] for i in range(len(PRODUCTS))]
            _o3 = origin.cpu().numpy()
            # 채점기는 장면 파일(로봇 좌표)에서 상판·띠를 재므로 **로봇 좌표로 넘긴다.**
            # 세계 좌표로 주면 띠 판정이 언제나 밖으로 떨어진다.
            _poses = [(L.world_to_robot(tuple(float(v) for v in
                                              (_x.data.root_pos_w[0].cpu().numpy() - _o3))),
                       L.quat_world_to_robot(tuple(float(v) for v in
                                                   _x.data.root_quat_w[0].cpu().numpy())))
                      for _x in _po_all]
            # 속도와 방향은 **벡터**라 회전만 걸려야 한다. `world_to_robot` 은 점 변환이라
            # 평행이동이 함께 걸리므로 원점의 상을 빼서 지운다.
            _z0r = np.asarray(L.world_to_robot((0.0, 0.0, 0.0)), dtype=float)

            def _vec_to_robot(v):
                return (np.asarray(L.world_to_robot(tuple(float(x) for x in v)),
                                   dtype=float) - _z0r)

            _vels = [_vec_to_robot(_x.data.root_lin_vel_w[0].cpu().numpy()) for _x in _po_all]
            _wb0, _wbd, _ = _beam_pose()
            _tb0 = L.world_to_robot(tuple(float(v) for v in _wb0))
            _tbd = _vec_to_robot(_wbd)
            _qnow = robot.data.joint_pos[0][rec_ids].cpu().numpy()
            trace.tick(k / REC_HZ, cur_slot, _poses, _vels, _tb0, _tbd,
                       float(CMD[k][IL]), float(_qnow[IL]))
        for i in range(len(PRODUCTS)):
            pr = prod_pos_r(i)
            lift = (pr[2] - start_pos[i][2]) * 1000.0
            dsc = float(np.linalg.norm(np.asarray(pr) - scan_r)) * 1000.0
            st = stat[i]
            st["max_lift_mm"] = max(st["max_lift_mm"], lift)
            if dsc < st["min_scanner_mm"]:
                st["min_scanner_mm"], st["min_scanner_frame"] = dsc, k
            st["moved_mm"] = max(st["moved_mm"], float(np.hypot(pr[0] - start_pos[i][0], pr[1] - start_pos[i][1])) * 1000.0)
        if k % int(REC_HZ * 10) == 0 and k > 0:
            el = _time.time() - t_wall
            print(f"[재생] {k / REC_HZ:6.1f}초 / {N / REC_HZ:.1f}초  (실시간 대비 x{(k / REC_HZ) / max(el, 1e-6):.2f})", flush=True)

    if trace is not None:
        if qr is not None:
            trace.qr = qr.report()
        trace.close(grade=META.get("grade"))
    print("", flush=True)
    for i, d in enumerate(PRODUCTS):
        pr = prod_pos_r(i)
        inside = (x0 <= pr[0] <= x1) and (y0 <= pr[1] <= y1)
        print("  %d: %-26s (%+.3f, %+.3f, %.3f)  %s"
              % (i, d["slug"], pr[0], pr[1], pr[2], "띠 안" if inside else "!! 띠 밖"), flush=True)
    _sp_w = scene["scanner"].data.root_pos_w[0]
    print("  스캐너 (%+.4f, %+.4f, %.4f) -- 오른손이 든 자리"
          % tuple(float(v) for v in _sp_w), flush=True)

    if args_cli.scene_json:
        with open(args_cli.scene_json, "w", encoding="utf-8") as fh:
            json.dump(SCENE, fh, ensure_ascii=False, indent=1)
        print("[장면] JSON 을 %s 에 적었다" % args_cli.scene_json, flush=True)

    if args_cli.shot:
        place_cameras()
        for _ in range(40):
            sim.render()
        from PIL import Image
        # 머리캠은 준 이름 그대로, 손목 둘은 이름 뒤에 붙여 적는다. 스캐너의 LED·창 점은
        # 7mm 라 머리캠 거리에서는 안 보인다 -- 우손목캠이 그것을 보는 눈이다.
        _stem = args_cli.shot[:-4] if args_cli.shot.lower().endswith(".png") else args_cli.shot
        for _cn, _sfx in (("head_cam", ""), ("left_wrist_cam", "_lw"), ("right_wrist_cam", "_rw")):
            try:
                _c = scene[_cn]
            except KeyError:
                continue
            _c._is_outdated[:] = True
            _c.update(0.0, force_recompute=True)
            _rgb = _c.data.output["rgb"][0][..., :3].cpu().numpy().astype(np.uint8)
            _dst = args_cli.shot if not _sfx else (_stem + _sfx + ".png")
            Image.fromarray(_rgb).save(_dst)
            print("[장면] %s 그림을 %s 에 적었다 (%dx%d)"
                  % (_cn, _dst, _rgb.shape[1], _rgb.shape[0]), flush=True)


main()
_exit_guard = _threading.Timer(10.0, os._exit, (0,))
_exit_guard.daemon = True
_exit_guard.start()
simulation_app.close()
