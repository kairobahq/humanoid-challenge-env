# Copyright 2025 ROBOTIS CO., LTD.
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

"""과제 A 의 정답 주행 한 판을 처음부터 끝까지 틀어 준다.

`task_a_demo.py` 가 **에피소드가 시작되는 순간**만 세워 보여 준다면, 이 스크립트는 로봇이
실제로 바구니를 집어 매장을 가로질러 책상에 내려놓는 **전 과정**을 보여 준다. 저장소에
주최 측이 미리 수집한 정답 주행 세 판이 들어 있고, 셋 다 평가표 만점(21/21)이다.

    seed 0   좌석  0   147 초   21/21
    seed 2   좌석 10   135 초   21/21
    seed 6   좌석  6   189 초   21/21

한 판은 세 토막이 이어진 것이다 -- **1 집기 · 2 주행 · 3 놓기**. 화면 왼쪽 위에 지금이 어느
토막인지 찍힌다.

실행:

    cd /workspace/cyclo_lab
    ${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
        /workspace/challenge_scripts/task_a_replay.py --seed 6

    # 어떤 판이 있는지만 (Isaac Sim 을 안 띄운다):
    ${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
        /workspace/challenge_scripts/task_a_replay.py --list

기록해 둔 궤적을 말 그대로 재생한다 -- 관절 각도와 베이스 자세, 바구니 자세를 프레임마다
기록에서 그대로 읽어 써 넣는다. 물리가 결과를 정하지 않는다. 과제 B 의 `task_b_replay.py`
와 같은 방식이고, 같은 방식인 것이 중요하다:

  **기구학 재생이라 수집 환경과 재생 환경의 차이를 타지 않는다.** 이 기록은 GPU 물리와
  컴플라이언트 바닥 위에서, 초당 10 프레임으로 찍혔다. 이 저장소의 데모는 CPU 물리에
  기본 바닥이다. 그 차이는 **물리가 결과를 만들 때만** 문제가 된다 -- 실측으로, 같은 계획을
  GPU 물리에서 돌리면 바구니를 끝까지 들고 갔고 CPU 물리에서는 목적지 2.5 m 앞에서
  떨어뜨렸다. 여기서는 매 프레임의 자세를 **써 넣으므로** 그 갈림길이 없다.

  대신 지켜야 하는 것이 셋이고, 셋 다 아래 코드에 있다:
    * 관절은 **이름으로** 맞춘다 (순서로 맞추면 어긋나도 그럴듯해 보인다)
    * 집게의 2~4 번 마디를 **매 프레임 1 번 마디로 채운다** (안 하면 턱이 벌어진 채로 간다)
    * 루트 쿼터니언을 **새로 만들지 않는다** (만들면 로봇이 옆으로 눕는다)

재생하면서 평가표대로 채점한 결과가 같이 찍힌다. 과제 B 의 재생기와 같다. 다만 점수를
**재생 중에 계산하지 않는다** -- 앱을 띄우기 전에 기록을 통째로 채점해 두고, 토막이 끝날
때마다 그 토막에 걸린 항목을 알린다. 그렇게 하는 이유가 있다: 항목마다 "몇 번째 프레임에
달성했는가" 를 재생기가 다시 계산하면 채점기와 다른 답을 낼 여지가 생기고, 그러면 화면에
찍힌 점수와 `taska_score.py` 가 내는 점수가 조용히 갈린다. 계산은 한 곳에서만 한다.
"""

import argparse
import glob
import importlib.util as _ilu
import json
import math
import os
import sys
import threading as _threading
import time

from isaaclab.app import AppLauncher

_HERE = os.path.dirname(os.path.abspath(__file__))
_TASKA = os.path.join(_HERE, "taskA")
DEMO_DIR = os.path.join(_TASKA, "demos")

parser = argparse.ArgumentParser(description="과제 A 의 정답 주행 한 판을 틀어 준다.")
parser.add_argument("--seed", type=int, default=6,
                    help="어느 판을 틀지. --list 로 있는 판을 본다.")
parser.add_argument("--substeps", type=int, default=4,
                    help="기록 한 프레임을 몇 걸음으로 나눠 그릴지. 높이면 부드럽고 느려진다.")
parser.add_argument("--hz", type=float, default=40.0,
                    help="화면을 초당 몇 장 그릴지. 0 이면 최대 속도로.")
parser.add_argument("--from_seconds", type=float, default=0.0,
                    help="몇 초 지점부터 볼지. 놓기만 보고 싶을 때 쓴다.")
parser.add_argument("--list", action="store_true", help="들어 있는 판을 찍고 끝낸다.")
parser.add_argument("--as_recorded", action="store_true",
                    help="진열을 **기록이 찍힌 그대로** 짓는다. 기본값은 seed 규칙대로 짓는 것이라 "
                         "`task_a_demo.py --seed N` 과 같은 매장이 나온다. 차이는 화면에 적힌다.")
AppLauncher.add_app_launcher_args(parser)
parser.set_defaults(device="cpu")     # 환경 하나뿐이고 물리가 결과를 정하지도 않는다
args_cli = parser.parse_args()

import numpy as np   # noqa: E402


def _by_path(name, path):
    """모듈을 경로로 읽는다. `task_a_demo.py` 와 같은 이유로 -- 패키지를 거치면 isaaclab 이
    딸려 들어오고, isaaclab 이 SimulationApp 보다 먼저 import 되면 Isaac Sim 이 안 뜬다."""
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# **`--list` 가 이것들보다 먼저 온다.** `taskA_layout` 은 배포 이미지 안의 과제 B 모듈을
# 읽으므로 이미지 밖에서는 import 만으로 죽는다. 목록을 찍는 데는 기록 파일만 있으면 되고,
# 목록조차 못 찍는 도구는 "무엇이 들어 있나" 를 물어볼 방법이 없다는 뜻이다.
taskA_scene_seed = _by_path("taskA_scene_seed", f"{_TASKA}/taskA_scene_seed.py")
taskA_store_dress = _by_path("taskA_store_dress", f"{_TASKA}/taskA_store_dress.py")

PHYSICS_DT = 1.0 / 120.0
WHEEL_RADIUS = 0.0864


# ---- 기록을 Isaac 보다 먼저 읽는다 (씬을 무엇으로 지을지가 여기서 정해진다) ------------------

def _demos():
    return sorted(glob.glob(os.path.join(DEMO_DIR, "demo_*.npz")))


def _meta_of(path):
    z = np.load(path, allow_pickle=False)
    m = json.loads(str(z["meta"]))
    z.close()
    return m


_files = _demos()
if not _files:
    raise SystemExit(f"판이 하나도 없다: {DEMO_DIR}/demo_*.npz")
_by_seed = {}
for _f in _files:
    _m = _meta_of(_f)
    _by_seed[int(_m["seed"])] = (_f, _m)

if args_cli.list:
    print(f"\n정답 주행 {len(_by_seed)} 판 -- 셋 다 평가표 만점입니다\n")
    print("  --seed   좌석   프레임      길이    점수    토막(집기/주행/놓기)")
    for _s in sorted(_by_seed):
        _f, _m = _by_seed[_s]
        _sf = _m["segment_frames"]
        print(f"  {_s:6d}   {_m['seat']:4d}   {_m['frames']:6d}  {_m['frames'] / _m['fps']:6.1f}초  "
              f"{_m['score']:>6}    {_sf['pick']}/{_sf['carry']}/{_sf['place']}")
    print(f"\n  {DEMO_DIR}\n")
    raise SystemExit(0)

if args_cli.seed not in _by_seed:
    raise SystemExit(f"--seed {args_cli.seed} 인 판이 없다. 있는 것: "
                     f"{' '.join(str(s) for s in sorted(_by_seed))}. --list 로 보라.")

DEMO, META = _by_seed[args_cli.seed]
_z = np.load(DEMO, allow_pickle=False)
JOINT_NAMES = list(META["joint_names"])
BASE_JOINT_NAMES = list(META["base_joint_names"])
FOLLOWERS = META["gripper_followers"]
JOINTS = np.asarray(_z["joint_pos"], dtype=np.float64)          # (T, 19)
BASEJ = np.asarray(_z["base_joints"], dtype=np.float64)         # (T, 6)
BASE = np.asarray(_z["base"], dtype=np.float64)                 # (T, 3)  x, y, yaw
CRATE = np.asarray(_z["obj/crate"], dtype=np.float64)           # (T, 7)
SEG = np.asarray(_z["segment"], dtype=np.int64)                 # (T,)
_z.close()
NFRAMES = JOINTS.shape[0]
SEG_NAMES = list(META["segment_names"])
FPS = float(META["fps"])

# 진열. 기본은 seed 규칙대로 -- `task_a_demo.py --seed N` 과 같은 매장이 나온다.
_rule = taskA_scene_seed.spec(args_cli.seed)
_rec = META["recorded"]
if args_cli.as_recorded:
    STORE_SEED, SHELF_SEED = _rec["store_seed"], _rec["shelf_seed"]
else:
    STORE_SEED, SHELF_SEED = _rule["store_seed"], _rule["shelf_seed"]
# 스툴은 **기록이 찍힌 값**을 쓴다. 이것만은 seed 규칙을 따르지 않는다 -- 스툴은 콜라이더가
# 있는 정적 가구이고 로봇이 그 사이를 빠져나오므로, 기록과 다른 자리에 세우면 화면에서 로봇이
# 스툴을 통과하는 그림이 나온다.
STOOL_SEED = int(_rec.get("stool_seed", 0))

SEAT_ID = int(META["seat"])

print(f"\n[판] seed {args_cli.seed}, 좌석 {SEAT_ID}, {NFRAMES} 프레임 "
      f"({NFRAMES / FPS:.1f} 초), 점수 {META['score']}")
print(f"     {META['task']}")
print(f"     토막  {META['segment_frames']}")
print(f"     진열  매장씨앗 {STORE_SEED}  진열대씨앗 {SHELF_SEED}"
      f"{'  (기록 그대로)' if args_cli.as_recorded else '  (seed 규칙대로)'}")
if not args_cli.as_recorded and (_rec["store_seed"], _rec["shelf_seed"]) != (STORE_SEED, SHELF_SEED):
    print(f"     [알림] 이 기록이 찍힌 매장은 진열이 달랐습니다 "
          f"(매장씨앗 {_rec['store_seed']}, 진열대씨앗 {_rec['shelf_seed']}; -1 은 '재진열 안 함'). "
          f"궤적에는 영향이 없습니다 -- 자세를 프레임마다 써 넣는 기구학 재생이고, 바구니는 "
          f"목표 진열대에서 최소 0.45 m 떨어져 지나갑니다. 기록 그대로는 --as_recorded.")
print()

# 여기서부터는 배포 이미지가 필요하다 (`taskA_layout` 이 이미지 안의 과제 B 모듈을 읽는다).
taskA_seats = _by_path("taskA_seats", f"{_TASKA}/taskA_seats.py")
taskA_layout = _by_path("taskA_layout", f"{_TASKA}/taskA_layout.py")
taskA_shelf_stock = _by_path("taskA_shelf_stock", f"{_TASKA}/taskA_shelf_stock.py")

# ---- 채점 -- 앱을 띄우기 전에 기록을 통째로 채점해 둔다 --------------------------------------
#
# 여기서 하지 않고 재생 중에 하면 매 프레임 numpy 를 돌려야 하고, 무엇보다 **항목마다
# 달성 프레임을 재생기가 다시 판정하게 된다.** 판정은 `scorer/` 한 곳에서만 한다.
sys.path.insert(0, os.path.join(_TASKA, "scorer"))
SCORE = None
try:
    import taska_score as _TS   # noqa: E402
    import rubric_taskA as _R   # noqa: E402
    SCORE = _TS.score_one(DEMO, quiet=True)["score"]
except SystemExit as _exc:      # 채점용 데이터가 없는 판이면 재생만 한다
    print(f"[채점] 건너뜀 -- {_exc}\n")
except Exception as _exc:       # noqa: BLE001  -- 채점이 안 된다고 재생까지 막지 않는다
    print(f"[채점] 건너뜀 -- {type(_exc).__name__}: {_exc}\n")

# 토막 이름 -> 평가표의 묶음 이름. `rubric_taskA.GROUP` 이 항목마다 묶음을 들고 있다.
SEG_GROUP = {"pick": "집기", "carry": "이동", "place": "놓기"}

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import omni.usd                                                       # noqa: E402
import torch                                                          # noqa: E402

import isaaclab.sim as sim_utils                                      # noqa: E402
from isaaclab.assets import AssetBaseCfg, RigidObjectCfg              # noqa: E402
from isaaclab.scene import InteractiveScene, InteractiveSceneCfg      # noqa: E402
from isaaclab.utils import configclass                                # noqa: E402

from cyclo_lab.assets.robots.FFW_SG2 import FFW_SG2_MOBILE_CFG        # noqa: E402

taskA_colliders = _by_path("taskA_colliders", f"{_TASKA}/taskA_colliders.py")
taskA_floor_material = _by_path("taskA_floor_material", f"{_TASKA}/taskA_floor_material.py")
taskA_stools = _by_path("taskA_stools", f"{_TASKA}/taskA_stools.py")
taskA_robot_pose = _by_path("taskA_robot_pose", f"{_TASKA}/taskA_robot_pose.py")

SEATS = taskA_seats.seats(stool_seed=STOOL_SEED)
SEAT = SEATS[SEAT_ID]


def _yaw_quat(yaw):
    """Z 축 회전의 (w, x, y, z). **집기(prop)에만 쓴다** -- 로봇에는 절대 쓰지 않는다."""
    return (math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0))


@configclass
class World(InteractiveSceneCfg):
    """`task_a_demo.py` 의 `World` 와 같은 장면에서 카메라만 뺀 것.

    **둘이 갈라지면 안 된다.** 카메라를 빼는 이유는 재생이 화면으로 보는 것이고 정책 관측을
    만드는 것이 아니어서다 -- 카메라 셋을 달면 한 판 재생이 몇 배 느려진다. 관측이 필요하면
    `task_a_demo.py --shot` 이 그 화각을 보여 준다.
    """

    store = AssetBaseCfg(
        prim_path="{ENV_REGEX_NS}/Store",
        spawn=sim_utils.UsdFileCfg(usd_path=taskA_layout.STORE_USD),
        init_state=AssetBaseCfg.InitialStateCfg(pos=(0.0, 0.0, 0.0)))

    ground = AssetBaseCfg(prim_path="/World/ground", spawn=sim_utils.GroundPlaneCfg())

    light = AssetBaseCfg(
        prim_path="/World/Light",
        spawn=sim_utils.DomeLightCfg(intensity=2500.0, color=(1.0, 1.0, 1.0)))

    robot = FFW_SG2_MOBILE_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")

    def __post_init__(self):
        self.basket = RigidObjectCfg(
            prim_path="{ENV_REGEX_NS}/Basket",
            spawn=sim_utils.UsdFileCfg(usd_path=taskA_layout.BASKET_USD,
                                       rigid_props=sim_utils.RigidBodyPropertiesCfg()),
            init_state=RigidObjectCfg.InitialStateCfg(
                pos=tuple(float(v) for v in SEAT["basket_xyz"]),
                rot=_yaw_quat(math.radians(float(SEAT["seat_angle_deg"])))))
        self.desk = AssetBaseCfg(
            prim_path="{ENV_REGEX_NS}/Desk",
            spawn=sim_utils.UsdFileCfg(
                usd_path=taskA_layout.DESK_USD,
                rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
                collision_props=sim_utils.CollisionPropertiesCfg()),
            init_state=AssetBaseCfg.InitialStateCfg(pos=taskA_layout.desk_pos(),
                                                    rot=(1.0, 0.0, 0.0, 0.0)))
        n = taskA_shelf_stock.attach(self, SHELF_SEED,
                                     log=lambda *a: print("[i]", *a, flush=True))
        if n <= 0:
            raise SystemExit("목표 진열대에 상품을 하나도 못 세웠다.")


def main():
    sim = sim_utils.SimulationContext(
        sim_utils.SimulationCfg(dt=PHYSICS_DT, device=args_cli.device))
    scene = InteractiveScene(World(num_envs=1, env_spacing=8.0))

    # ---------------------------------------------------------------- sim.reset() 앞에서만
    # 스테이지가 Fabric 으로 넘어가면 렌더러는 USD 에 적힌 변환을 더 이상 따르지 않는다.
    stage = omni.usd.get_context().get_stage()
    # 조명은 매장 씬이 들고 온 것을 그대로 쓴다 (2026-09-12). 씬의 Dome 850 · Key 1500 ·
    # 냉장고 RectLight 8개가 그대로 켜져 있고, 과제 B·C 도 그 조명으로 돈다. 돔이 둘이면
    # 화면이 하얗게 뜨므로 끄는 쪽은 우리 돔이다.
    ours = stage.GetPrimAtPath("/World/Light")
    if ours and ours.IsValid():
        ours.SetActive(False)
    # **`harden()` 앞이어야 한다** -- 진열을 걸면 곤돌라 프림의 참조가 통째로 갈리고,
    # harden 을 먼저 하면 콜라이더가 이미 없어진 프림에 붙는다.
    taskA_store_dress.dress(stage, STORE_SEED, log=lambda *a: print("[i]", *a, flush=True))
    taskA_colliders.harden(stage, log=lambda *a: None)
    # 원본 기록이 모인 바닥과 같게: 매장 바닥 콜라이더에 컴플라이언트 재질 (taskA_floor_material.py 머리말).
    taskA_floor_material.bind_store_floor(stage, log=lambda *a: print("[i]", *a, flush=True))
    stools = taskA_stools.Stools(stage, SEATS, log=lambda *a: None)
    stools.measure_home()
    stools.place(SEAT)
    stools.park_others(SEATS, SEAT_ID)

    sim.reset()
    scene.update(PHYSICS_DT)

    robot = scene["robot"]
    basket = scene["basket"]
    here = list(robot.joint_names)

    # ---- 관절을 **이름으로** 맞춘다 ------------------------------------------------------
    #
    # 순서로 맞추면 어긋나도 그럴듯해 보이는 동작이 나오고, 그것이 가장 나쁜 종류의 틀림이다.
    # 기록은 관절 19 개, 바퀴 6 개를 들고 있고 로봇은 31 개다. 남는 6 개는 집게의 2~4 번
    # 마디이고 1 번 마디를 따라간다.
    idx = {n: i for i, n in enumerate(here)}
    plan = []            # (로봇 관절 인덱스, 기록 배열, 기록 열)
    for j, n in enumerate(JOINT_NAMES):
        if n not in idx:
            raise SystemExit(f"기록의 관절 '{n}' 이 이 로봇에 없다. 같은 로봇이 아니면 "
                             f"이 기록은 틀 수 없다.")
        plan.append((idx[n], "j", j))
    for j, n in enumerate(BASE_JOINT_NAMES):
        if n not in idx:
            raise SystemExit(f"기록의 바퀴 관절 '{n}' 이 이 로봇에 없다.")
        plan.append((idx[n], "b", j))
    # 집게의 종속 마디. **이것을 빼면 턱이 벌어진 채로 재생된다** -- 실측 68.9~80.6 mm 대
    # 10.0 mm 이고, 그러면 화면에서 로봇이 아무것도 안 쥔 채로 바구니를 옮기는 그림이 된다.
    for lead, mates in FOLLOWERS.items():
        if lead not in JOINT_NAMES:
            raise SystemExit(f"집게의 기준 마디 '{lead}' 가 기록에 없다.")
        col = JOINT_NAMES.index(lead)
        for m in mates:
            if m not in idx:
                raise SystemExit(f"집게의 종속 마디 '{m}' 이 이 로봇에 없다.")
            plan.append((idx[m], "j", col))

    covered = sorted(i for i, _s, _c in plan)
    if len(covered) != len(set(covered)):
        raise SystemExit("같은 관절에 두 번 쓴다 -- 기록의 관절 목록이 겹친다.")
    missing = [n for i, n in enumerate(here) if i not in set(covered)]
    if missing:
        # 조용히 넘어가면 그 관절은 스폰값에 얼어붙은 채로 재생된다.
        raise SystemExit(f"기록이 채우지 못하는 관절 {len(missing)}개: {missing}. "
                         f"이 관절들은 스폰값에 얼어붙은 채로 재생된다 -- 멈춘다.")
    print(f"[i] 관절 {len(here)}개를 이름으로 맞췄다 "
          f"(기록 {len(JOINT_NAMES)} + 바퀴 {len(BASE_JOINT_NAMES)} + "
          f"집게 종속 {sum(len(v) for v in FOLLOWERS.values())})", flush=True)

    # ---- 루트 자세: 쿼터니언을 **새로 만들지 않는다** ---------------------------------------
    #
    # FFW-SG2 의 루트 링크는 항등 자세에서 서 있지 않다. yaw 쿼터니언을 만들어 씌우면
    # 로봇이 90 도 옆으로 눕는다 (`taskA_robot_pose.py` 머리말의 실측). 로봇이 실제로 서서
    # 생긴 쿼터니언을 읽어 두고, 그것을 세계의 수직축으로 돌린다.
    spawn_quat, spawn_z = taskA_robot_pose.spawn_pose(robot, scene.env_origins[0])
    z_ground = spawn_z
    for _ in range(2):
        taskA_robot_pose.place(robot, scene.env_origins[0], BASE[0, :2], float(BASE[0, 2]),
                               spawn_quat, z_ground)
        sim.step(render=False)
        scene.update(PHYSICS_DT)
        low = robot.data.body_pos_w[0, [i for i, n in enumerate(robot.body_names)
                                        if "wheel_drive_link" in n], 2].min().item()
        z_ground += WHEEL_RADIUS - (low - scene.env_origins[0][2].item())
    tilt, _up = taskA_robot_pose.tilt_degrees(robot)
    print(f"[i] 로봇 기울기 {tilt:.1f}도, 바퀴 높이 맞춤 z {z_ground:.4f}", flush=True)

    zero_qd = torch.zeros((1, len(here)), device=sim.device)
    zero_v6 = torch.zeros((1, 6), device=sim.device)
    q = torch.zeros((1, len(here)), dtype=torch.float32, device=sim.device)

    def put(i, t):
        """기록의 i 번째 프레임(다음 프레임과 t 만큼 섞은 것)을 씬에 써 넣는다."""
        k = min(i + 1, NFRAMES - 1)
        jj = JOINTS[i] if t == 0.0 else JOINTS[i] + (JOINTS[k] - JOINTS[i]) * t
        bb = BASEJ[i] if t == 0.0 else BASEJ[i] + (BASEJ[k] - BASEJ[i]) * t
        bp = BASE[i] if t == 0.0 else BASE[i] + (BASE[k] - BASE[i]) * t
        cp = CRATE[i] if t == 0.0 else CRATE[i] + (CRATE[k] - CRATE[i]) * t

        for slot, src, col in plan:
            q[0, slot] = float(jj[col] if src == "j" else bb[col])
        robot.write_joint_state_to_sim(q, zero_qd)
        taskA_robot_pose.place(robot, scene.env_origins[0], bp[:2], float(bp[2]),
                               spawn_quat, z_ground)
        # 바구니는 기록된 자세를 그대로. 쿼터니언은 선형으로 섞고 다시 정규화한다.
        pose = cp.copy()
        if t != 0.0:
            q0, q1 = CRATE[i, 3:7], CRATE[k, 3:7]
            if float(np.dot(q0, q1)) < 0.0:
                q1 = -q1
            mix = q0 + (q1 - q0) * t
            nrm = float(np.linalg.norm(mix))
            pose[3:7] = mix / nrm if nrm > 1e-12 else q0
        basket.write_root_pose_to_sim(
            torch.as_tensor(pose[None, :], dtype=torch.float32, device=sim.device))
        basket.write_root_velocity_to_sim(zero_v6)
        scene.write_data_to_sim()

    start = max(0, min(NFRAMES - 1, int(args_cli.from_seconds * FPS)))
    sub = max(1, args_cli.substeps)
    total = (NFRAMES - 1 - start) * sub + 1
    period = 0.0 if args_cli.hz <= 0 else 1.0 / args_cli.hz
    print(f"[i] 재생 시작 -- 기록 {NFRAMES - start} 프레임을 {total} 장으로\n", flush=True)

    got = [0.0]      # 지금까지 알린 점수 -- [점수] 줄마다 누적을 같이 찍는다

    def announce(group):
        """이 묶음에 걸린 평가표 항목을 알린다. 점수는 이미 계산돼 있다.

        묶음 이름을 그대로 받는다. 토막 이름을 받아 안에서 바꾸면 `announce(None)` 이
        「전체」를 뜻하는지 「아무것도 아님」을 뜻하는지가 부르는 쪽에서 안 보인다.
        """
        if SCORE is None or group is None:
            return
        for key, item in SCORE["items"].items():
            if _R.GROUP.get(key) != group:
                continue
            got[0] += float(item["points"])
            mark = "O" if item["got"] else ("X" if item["got"] is False else "?")
            print(f"[점수] {mark} {item['label']}  "
                  f"+{item['points']:g}/{item['possible']:g}  "
                  f"누적 {got[0]:g}/{SCORE['possible']:g}", flush=True)
            print(f"          {item['why']}", flush=True)

    t0 = time.time()
    shown = -1
    for n in range(total):
        i = start + n // sub
        t = (n % sub) / float(sub)
        if i >= NFRAMES - 1:
            i, t = NFRAMES - 1, 0.0
        if SEG[i] != shown:
            if shown >= 0:
                announce(SEG_GROUP.get(SEG_NAMES[shown]))
            shown = int(SEG[i])
            print(f"[토막] {shown + 1} {SEG_NAMES[shown]}   "
                  f"{(i - start) / FPS:6.1f} 초", flush=True)
        put(i, t)
        sim.step(render=True)
        scene.update(PHYSICS_DT)
        if period:
            late = t0 + n * period - time.time()
            if late > 0:
                time.sleep(late)
        if not simulation_app.is_running():
            print("[i] 창이 닫혔습니다.", flush=True)
            break

    if shown >= 0:
        announce(SEG_GROUP.get(SEG_NAMES[shown]))    # 마지막 토막
    announce("전체")                                  # 판 내내 보는 항목

    bx, by, _bz = BASE[-1]
    gx, gy, _gyaw = taskA_layout.goal_pose()
    print(f"\n[i] 끝. 로봇이 ({bx:+.3f}, {by:+.3f}) 에 섰고 도착 자리까지 "
          f"{math.hypot(bx - gx, by - gy):.3f} m 였습니다.\n", flush=True)
    if SCORE is not None:
        print(_R.render(SCORE), flush=True)
    else:
        print(f"[i] 이 판의 평가표 점수는 {META['score']} 입니다.\n", flush=True)


main()

# Kit 의 종료가 이 이미지에서는 돌아오지 않는다. `task_a_demo.py` 가 같은 이유로 같은 가드를
# 갖고 있다 (실측 2026-09-03: 할 일을 다 끝낸 뒤 `simulation_app.close()` 에서 34 분을
# 매달렸고 프로세스는 죽지도 않고 CPU 를 계속 썼다). 재생기는 한 판이 189 초까지 가므로
# 참가자가 "아직 도는 중" 과 "안 끝나는 중" 을 구별하기가 더 어렵다.
#
# 그래서 정상 종료를 먼저 시도하되, 10 초 안에 안 돌아오면 프로세스를 그대로 끝낸다.
# 이 시점에는 재생이 끝나고 마지막 줄까지 찍힌 뒤라 잃는 것이 없다.
_exit_guard = _threading.Timer(10.0, os._exit, (0,))
_exit_guard.daemon = True
_exit_guard.start()
simulation_app.close()
