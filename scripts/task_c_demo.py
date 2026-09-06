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

"""과제 C 의 시작 장면 하나를 띄워서 보여준다.

과제 C 는 "계산대의 상품을 하나씩 집으면서 무엇인지 알아보고(QR) 값을 더하는" 과제이고,
이 스크립트는 그 **에피소드가 시작되는 순간의 장면**을 만든다. 여기서 멈춘다 -- 집지도,
비추지도, 놓지도 않는다. 참가자가 보아야 하는 것은 자기 정책이 첫 관측으로 받게 될 바로 그
그림이기 때문이다.

한 장면은 seed 하나로 완전히 정해진다. 같은 seed 는 어디서 돌려도 같은 장면이다.

  * **매장**    편의점 전체가 들어온다(과제 A 와 같은 매장 USD). 장면은 그 매장의 **계산대**
    앞에서 벌어진다. 로봇은 주행하지 않는다.
  * **상품**    계산대 상판의 빨간 띠 안에 상품 세 개. 슬롯 0 이 집을 상품이고 나머지 둘은
    배경이다. 세 개 모두 QR 면이 로봇의 정 오른쪽(세계 -Y)을 보도록 놓인다. 원통은 서 있고
    (반은 뒤집어 세운다), 상자는 눕는다. 상품끼리는 10 cm 이상 떨어진다.
  * **스캐너**  로봇 왼손이 드는 자리에 떠 있다(중력 없음). 수집 파이프라인이 에피소드를
    시작하던 그 자세다.
  * **로봇**    계산대를 마주 보고 선다. 양팔은 스토우 자세, 고개는 39.8 도 숙임. 바퀴는
    바닥에 닿아 있다(아래 settle_on_ground).

실행:

    cd /workspace/cyclo_lab
    ${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
        /workspace/challenge_scripts/task_c_demo.py --seed 1000

    # 화면 없이, 장면 내용만 파일로:
    ${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
        /workspace/challenge_scripts/task_c_demo.py --seed 1000 --headless \
        --seconds 1 --scene-json /workspace/user/scene_c_1000.json

    # 에셋과 띠 기하만 확인하고 끝낸다 (Isaac Sim 을 띄우지 않는다 -- 1 초):
    ${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
        /workspace/challenge_scripts/task_c_demo.py --check
"""

import argparse
import os
import sys
import threading as _threading

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="과제 C 의 시작 장면 하나를 띄운다.")
parser.add_argument("--seed", type=int, default=1000,
                    help="장면 하나를 정하는 수. 같은 값이면 같은 장면이다.")
parser.add_argument("--products", default=None, metavar="a,b,c",
                    help="상품 세 개를 코드용 이름으로 직접 준다(쉼표). 첫 번째가 집을 상품이다. "
                         "기본값은 seed 가 8 종에서 고른다.")
parser.add_argument("--seconds", type=float, default=0.0,
                    help="장면을 몇 초 동안 유지할지. 0 이면 창을 닫을 때까지 (--headless "
                         "일 때는 1 초).")
parser.add_argument("--shot", default=None, metavar="FILE.png",
                    help="로봇 머리 카메라가 보는 그림을 한 장 저장한다. 화면 없이 돌릴 때 "
                         "장면을 눈으로 확인하는 길이고, 정책이 받게 될 관측 그대로다.")
parser.add_argument("--scene-json", default=None, metavar="FILE.json",
                    help="장면 내용을 JSON 으로 저장한다. 상품 세 개의 이름·좌표·자세, 띠, "
                         "로봇 자세, 스캐너 자리가 들어 있다.")
parser.add_argument("--check", action="store_true",
                    help="에셋(상품 8 종·타일·스캐너·매장 USD)과 띠 기하만 검사하고 끝낸다. "
                         "Isaac Sim 을 띄우지 않으므로 1 초면 된다.")
AppLauncher.add_app_launcher_args(parser)
parser.set_defaults(device="cpu")     # 환경 하나뿐이라 GPU 파이프라인은 손해다 (과제 A/B 와 같다)
args_cli = parser.parse_args()
args_cli.enable_cameras = True        # 로봇이 카메라를 달고 있어 이 깃발 없이는 스폰이 막힌다

import importlib.util as _ilu   # noqa: E402
import math                     # noqa: E402

CYCLOLAB = os.environ.get("CYCLOLAB_PATH", "/workspace/cyclo_lab")
_SRC = f"{CYCLOLAB}/source/cyclo_lab/cyclo_lab"
if not os.path.isdir(_SRC):
    raise SystemExit(f"환경 코드를 찾지 못했다: {_SRC}\n"
                     f"CYCLOLAB_PATH 를 확인하라 (현재 {CYCLOLAB!r}).")

# 과제 C 의 장면 정의 모듈은 **이 저장소 안**, 이 파일 옆의 `taskC/` 에 있다. 과제 A 와 같은
# 이유다 -- `scripts/` 는 마운트라 `git pull` 만으로 갱신되고, 참가자가 장면이 어떻게 서는지
# GitHub 에서 바로 읽을 수 있다. 이미지에서 오는 것은 에셋뿐이다: 매장 USD, 로봇, QR 타일이
# 붙은 상품 8 종, 스캐너.
_HERE = os.path.dirname(os.path.abspath(__file__))
_TASKC = os.path.join(_HERE, "taskC")
if not os.path.isdir(_TASKC):
    raise SystemExit(f"과제 C 모듈을 찾지 못했다: {_TASKC}")
sys.path.insert(0, _HERE)

# 아래 다섯은 isaaclab 을 쓰지 않는 순수 파이썬이라 AppLauncher 앞에서 읽는다.
from taskC import taskC_check as K        # noqa: E402
from taskC import taskC_deal as D         # noqa: E402
from taskC import taskC_layout as L       # noqa: E402
from taskC import taskC_products as P     # noqa: E402
from taskC import taskC_report as R       # noqa: E402

# 물리 한 걸음과 그리기 주기. 과제 A 데모와 같은 값이다 -- 매장 전체를 그리는 한 장이 비싸다.
PHYSICS_DT = 1.0 / 120.0
RENDER_EVERY = 4
SHOT_WARMUP = 16
SETTLE_SECONDS = 3.0        # 상품을 스폰한 뒤 물리로 가라앉히는 시간 (qr_scene --settle 기본값)
WHEEL_RADIUS = L.WHEEL_RADIUS

STORE_USD = str(P.assets_root() / "store" / "scene" / "fixture_kit" / "out" / "store_scene.usd")
SCANNER_USD = str(P.assets_root() / "fixtures" / "scanner" / "scanner_taskC.usd")


def _by_path(name, path):
    """모듈을 경로로 읽는다 (과제 A 데모와 같은 방식)."""
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def draw_deal(seed, products):
    """이 seed 의 딜. Isaac 없이 정해지는 것 -- 상품 셋과 스폰 자세·자리(로봇 좌표)."""
    slugs = D.pick_products(seed, products)
    return {"seed": seed, "slugs": slugs, "dealt": D.deal(seed, 0, slugs)}


def print_deal(deal):
    print(f"\n[딜] seed {deal['seed']}  집을 것 {P.LABELS[deal['slugs'][0]]} "
          f"[{deal['slugs'][0]}]  배경 {', '.join(deal['slugs'][1:])}")
    for k, d in enumerate(deal["dealt"]):
        x, y, z = d["pos"]
        print(f"    {k}: {d['slug']:<26s} 로봇 좌표 ({x:+.3f}, {y:+.3f}, {z:.3f})  "
              f"{'직립' if P.is_cylinder(d['slug']) else '눕힘'}")
    print("  (정착 뒤 실제 자리는 아래 [장면] 에 찍힌다)\n", flush=True)


# --check 는 여기서 끝난다. Isaac Sim 을 띄우지 않는다.
if args_cli.check:
    print("\n[검사] 과제 C 장면 기하와 에셋 -- Isaac Sim 없이\n")
    print(f"  계산대    중심 ({L.COUNTER_CENTRE_WORLD[0]:+.3f}, {L.COUNTER_CENTRE_WORLD[1]:+.3f})  "
          f"상판 {L.COUNTER_TOP_Z:.4f}  크기 {L.COUNTER_SIZE_XY[0]:.3f} x {L.COUNTER_SIZE_XY[1]:.3f}")
    print(f"  로봇      ({L.ROBOT_BASE_WORLD[0]:+.3f}, {L.ROBOT_BASE_WORLD[1]:+.3f})  "
          f"yaw {math.degrees(L.ROBOT_YAW):+.1f} 도  몸통 {L.LIFT_JOINT_POS:+.3f}  "
          f"고개 {math.degrees(L.HEAD_PITCH):.1f} 도 아래")
    x0, x1, y0, y1 = L.band_inner()
    print(f"  빨간 띠   로봇 좌표 x {L.BAND['x0']:.4f}~{L.BAND['x1']:.4f}  y {L.BAND['y0']:.3f}~{L.BAND['y1']:.3f}"
          f"  (테이프 {L.TAPE_W * 1000:.0f} mm 안쪽 x {x0:.3f}~{x1:.3f}  y {y0:.3f}~{y1:.3f})")
    print(f"  상품 8 종  {P.products_dir()}")
    for s in P.PRODUCTS:
        w, d, h = P.size_mm(s) if P.product_usd(s).is_file() else (0, 0, 0)
        print(f"    {s:<26s} {P.LABELS[s]:<34s} {w:5.1f} x {d:5.1f} x {h:5.1f} mm  "
              f"{'원통' if P.is_cylinder(s) else '상자'}  {'O' if P.product_usd(s).is_file() else '! USD 없음'}")
    print(f"  스캐너 USD {SCANNER_USD}")
    problems = K.check_static(P.assets_root())
    if os.path.isfile(STORE_USD):
        print(f"  매장 USD  {STORE_USD}")
    else:
        print(f"  ! 매장 USD 가 없다: {STORE_USD}")
    print(f"\n  판정: {'문제 없음' if not problems else f'{len(problems)} 건'}")
    for p in problems:
        print(f"   ! {p}")
    print()
    raise SystemExit(1 if problems else 0)


try:
    DEAL = draw_deal(args_cli.seed, args_cli.products)
except ValueError as e:
    raise SystemExit(str(e))
print_deal(DEAL)

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import numpy as np                                                    # noqa: E402
import torch                                                          # noqa: E402
import omni.usd                                                       # noqa: E402
import isaaclab.sim as sim_utils                                      # noqa: E402
from isaaclab.assets import AssetBaseCfg, RigidObjectCfg              # noqa: E402
from isaaclab.scene import InteractiveScene, InteractiveSceneCfg      # noqa: E402
from isaaclab.sensors import CameraCfg                                # noqa: E402
from isaaclab.utils import configclass                                # noqa: E402

from cyclo_lab.assets.robots.FFW_SG2 import (                         # noqa: E402
    FFW_SG2_MOBILE_CFG, SG2_SWERVE_STEERING_JOINTS, SG2_SWERVE_WHEEL_JOINTS,
)

# pxr / isaaclab 을 쓰는 것들은 여기서 읽는다. 과제 A 의 두 모듈은 **그대로 빌려 쓴다** --
# 매장 콜라이더 켜기와 로봇 세우기는 과제가 달라도 같은 일이고, 같은 값을 두 번째로 적어 두는
# 것은 두 값이 갈라질 두 번째 기회다(taskA_layout.py 의 말). 이 파일은 그 모듈을 고치지 않는다.
_TASKA = os.path.join(_HERE, "taskA")
taskA_colliders = _by_path("taskA_colliders", f"{_TASKA}/taskA_colliders.py")
robot_pose = _by_path("taskA_robot_pose", f"{_TASKA}/taskA_robot_pose.py")
from taskC import taskC_counter as counter                            # noqa: E402

LEFT_JOINTS = [f"arm_l_joint{i + 1}" for i in range(7)]
RIGHT_JOINTS = [f"arm_r_joint{i + 1}" for i in range(7)]


def _cam(name):
    c = L.CAMERAS[name]
    return CameraCfg(
        prim_path="{ENV_REGEX_NS}/Robot/" + c["rel"],
        update_period=1.0e9, height=c["h"], width=c["w"], data_types=["rgb"],
        update_latest_camera_pose=True,
        spawn=sim_utils.PinholeCameraCfg(focal_length=c["focal"], focus_distance=c["focus"],
                                         horizontal_aperture=c["aperture"],
                                         clipping_range=c["clip"]),
        offset=CameraCfg.OffsetCfg(pos=c["offset_pos"], rot=c["offset_rot"], convention="isaac"))


@configclass
class World(InteractiveSceneCfg):
    """매장 전체, 바닥, 로봇, 스캐너, 그리고 계산대 위 상품 셋.

    카메라 셋은 채점이 정책에게 보내는 관측과 같은 값이다 -- 머리 672x376, 손목 424x240.
    """

    store = AssetBaseCfg(
        prim_path="{ENV_REGEX_NS}/Store",
        spawn=sim_utils.UsdFileCfg(usd_path=STORE_USD),
        init_state=AssetBaseCfg.InitialStateCfg(pos=(0.0, 0.0, 0.0)))
    ground = AssetBaseCfg(
        prim_path="/World/GroundPlane",
        spawn=sim_utils.GroundPlaneCfg(),
        init_state=AssetBaseCfg.InitialStateCfg(pos=(0.0, 0.0, 0.0)))
    # 조명은 매장 USD 의 것(돔 + 천장 램프)만 쓴다. 수집 파이프라인이 그렇게 찍었고, 돔을 더
    # 얹으면 계산대가 과노출돼 참가자가 보는 그림이 학습 데이터와 달라진다.
    robot = FFW_SG2_MOBILE_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")

    head_cam = _cam("head_cam")
    left_wrist_cam = _cam("left_wrist_cam")
    right_wrist_cam = _cam("right_wrist_cam")

    def __post_init__(self):
        # 스캐너: 왼손이 드는 자리에 떠 있다(중력 없음). 수집 재생기와 같은 스폰이다.
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
        # 상품 셋. 스폰 자세·자리는 로봇 좌표로 정해졌으므로 세계 좌표로 옮겨 놓는다.
        for k, d in enumerate(DEAL["dealt"]):
            setattr(self, f"p_{k}", RigidObjectCfg(
                prim_path=f"{{ENV_REGEX_NS}}/P_{k}",
                spawn=sim_utils.UsdFileCfg(
                    usd_path=str(P.product_usd(d["slug"])),
                    rigid_props=sim_utils.RigidBodyPropertiesCfg(
                        disable_gravity=False, linear_damping=1.0, angular_damping=2.0)),
                init_state=RigidObjectCfg.InitialStateCfg(
                    pos=tuple(float(v) for v in L.robot_to_world(d["pos"])),
                    rot=tuple(float(v) for v in L.quat_robot_to_world(d["quat"])))))


def main():
    sim = sim_utils.SimulationContext(
        sim_utils.SimulationCfg(dt=PHYSICS_DT, device=args_cli.device))
    scene = InteractiveScene(World(num_envs=1, env_spacing=8.0))

    # sim.reset() 앞에서만 되는 스테이지 손질: 매장 콜라이더 켜기, 정적 스캐너·바구니 끄기,
    # 계산대 맨 아래 선반판 잘라내기 (reset 이 콜라이더를 굽기 전에 해야 물리에 반영된다).
    stage = omni.usd.get_context().get_stage()
    taskA_colliders.harden(stage, log=lambda *a: None)
    _log = lambda m: print(f"[i] {m}", flush=True)  # noqa: E731
    counter.deactivate_duplicates(stage, log=_log)
    counter.remove_low_shelf(stage, log=_log)

    sim.reset()
    counter.draw_band(log=lambda m: print(f"[i] {m}", flush=True))

    robot = scene["robot"]
    names = list(robot.joint_names)
    left_ids, _ = robot.find_joints(LEFT_JOINTS, preserve_order=True)
    right_ids, _ = robot.find_joints(RIGHT_JOINTS, preserve_order=True)
    head_ids, _ = robot.find_joints(["head_joint1", "head_joint2"], preserve_order=True)
    lift_ids, _ = robot.find_joints(["lift_joint"], preserve_order=True)
    grip_ids, _ = robot.find_joints([f"gripper_{s}_joint{i + 1}"
                                     for s in ("l", "r") for i in range(4)],
                                    preserve_order=True)
    steer_ids, _ = robot.find_joints(list(SG2_SWERVE_STEERING_JOINTS), preserve_order=True)
    wheel_ids, _ = robot.find_joints(list(SG2_SWERVE_WHEEL_JOINTS), preserve_order=True)
    wheel_bodies = [i for i, n in enumerate(robot.body_names) if "wheel_drive_link" in n]

    left_hold = torch.tensor([list(L.STOW_ARM_L)], device=sim.device)
    right_hold = torch.tensor([list(L.STOW_ARM_R)], device=sim.device)
    head_hold = torch.tensor([[L.HEAD_PITCH, L.HEAD_YAW]], device=sim.device)
    lift_hold = torch.full((1, len(lift_ids)), L.LIFT_JOINT_POS, device=sim.device)
    zero_grip = torch.zeros((1, len(grip_ids)), device=sim.device)
    zero_steer = torch.zeros((1, len(steer_ids)), device=sim.device)
    zero_wheel = torch.zeros((1, len(wheel_ids)), device=sim.device)
    step_count = [0]

    def hold(n, render=True):
        """n 걸음 동안 자세를 유지한다. 바퀴 속도는 매 걸음 0. 그림은 RENDER_EVERY 걸음에 한 번."""
        for _ in range(n):
            robot.set_joint_position_target(left_hold, joint_ids=left_ids)
            robot.set_joint_position_target(right_hold, joint_ids=right_ids)
            robot.set_joint_position_target(head_hold, joint_ids=head_ids)
            robot.set_joint_position_target(lift_hold, joint_ids=lift_ids)
            robot.set_joint_position_target(zero_grip, joint_ids=grip_ids)
            robot.set_joint_position_target(zero_steer, joint_ids=steer_ids)
            robot.set_joint_velocity_target(zero_wheel, joint_ids=wheel_ids)
            scene.write_data_to_sim()
            sim.step(render=render and step_count[0] % RENDER_EVERY == 0)
            scene.update(PHYSICS_DT)
            step_count[0] += 1

    settle_render = not args_cli.headless
    scene.update(PHYSICS_DT)
    origin = scene.env_origins[0]
    spawn_quat, spawn_z = robot_pose.spawn_pose(robot, origin)

    def settle_on_ground():
        """로봇을 계산대 앞 제자리에, 바퀴를 바닥에 붙여 세운다 (과제 A 데모와 같은 방식)."""
        want = robot.data.default_joint_pos[0].clone()
        want[names.index("head_joint1")] = L.HEAD_PITCH
        want[names.index("head_joint2")] = L.HEAD_YAW
        want[names.index("lift_joint")] = L.LIFT_JOINT_POS
        for j, q in zip(LEFT_JOINTS, L.STOW_ARM_L):
            want[names.index(j)] = q
        for j, q in zip(RIGHT_JOINTS, L.STOW_ARM_R):
            want[names.index(j)] = q
        robot.write_joint_state_to_sim(want.unsqueeze(0), torch.zeros_like(want).unsqueeze(0))
        scene.write_data_to_sim()
        rx, ry = L.ROBOT_BASE_WORLD[0], L.ROBOT_BASE_WORLD[1]
        z = spawn_z
        for _ in range(2):
            robot_pose.place(robot, origin, (rx, ry), L.ROBOT_YAW, spawn_quat, z)
            scene.write_data_to_sim()
            hold(1, render=False)
            low = min(float(robot.data.body_pos_w[0, i][2]) for i in wheel_bodies)
            z -= low - WHEEL_RADIUS
        robot_pose.place(robot, origin, (rx, ry), L.ROBOT_YAW, spawn_quat, z)
        scene.write_data_to_sim()

    settle_on_ground()

    def _set_root(obj, pos_w, quat_w):
        st = obj.data.root_state_w[0].clone()
        st[:3] = torch.as_tensor(np.asarray(pos_w, dtype=np.float32), device=st.device) \
            + torch.as_tensor(np.asarray(origin.cpu(), dtype=np.float32), device=st.device)
        st[3:7] = torch.as_tensor(np.asarray(quat_w, dtype=np.float32), device=st.device)
        st[7:] = 0.0
        obj.write_root_state_to_sim(st.unsqueeze(0))

    def pin_scanner():
        _set_root(scene["scanner"], L.robot_to_world(L.SCANNER_HOLD_POS),
                  L.quat_robot_to_world(L.SCANNER_HOLD_QUAT))

    def settle_products(dealt):
        """상품을 스폰 자세로 다시 적고 SETTLE_SECONDS 동안 가라앉힌 뒤, 로봇 좌표로 읽어 검사한다."""
        for k, d in enumerate(dealt):
            _set_root(scene[f"p_{k}"], L.robot_to_world(d["pos"]), L.quat_robot_to_world(d["quat"]))
        pin_scanner()
        scene.write_data_to_sim()
        hold(int(SETTLE_SECONDS / PHYSICS_DT), render=settle_render)
        entries = []
        for k, d in enumerate(dealt):
            obj = scene[f"p_{k}"]
            pw = (obj.data.root_pos_w[0] - origin).cpu().numpy()
            qw = obj.data.root_quat_w[0].cpu().numpy()
            entries.append(dict(slug=d["slug"],
                                pos=L.world_to_robot(tuple(float(v) for v in pw)),
                                quat=L.quat_world_to_robot(tuple(float(v) for v in qw)),
                                sq=tuple(d["quat"])))
        return K.check_settled(entries)

    dealt = DEAL["dealt"]
    ok, res = settle_products(dealt)
    attempt = 0
    while not ok and attempt < L.MAX_REDEAL:
        attempt += 1
        print(f"[i] 재딜 {attempt}: {', '.join(K.redeal_reason(res)) or '방위/간격'} "
              f"-- 테이프 접촉/뚫림/넘어짐/QR 방위/간격", flush=True)
        dealt = D.deal(args_cli.seed, attempt, DEAL["slugs"])
        ok, res = settle_products(dealt)
    if not ok and K.fail_open_ok(res):
        print("[i] 재딜 소진 -- 위반이 비원통 기움뿐이라 수용 (둥근 형상 구제)", flush=True)
        ok = True
    if not ok:
        print(f"[!] seed {args_cli.seed}: 재딜 {attempt} 회 소진, 장면이 규칙을 만족하지 못했다", flush=True)

    pin_scanner()
    scene.write_data_to_sim()
    hold(int(0.5 / PHYSICS_DT), render=settle_render)

    x, y = float(robot.data.root_pos_w[0][0]), float(robot.data.root_pos_w[0][1])
    qw_, qx, qy, qz = (float(v) for v in robot.data.root_quat_w[0])
    yaw = math.degrees(math.atan2(2.0 * (qw_ * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz)))
    low = min(float(robot.data.body_pos_w[0, i][2]) for i in wheel_bodies)

    scene_d = R.scene_dict(args_cli.seed, DEAL["slugs"], res, redeal=attempt, robot_xy_yaw=(x, y, yaw))
    print(R.print_summary(scene_d), flush=True)
    if args_cli.scene_json:
        R.write_scene_json(scene_d, args_cli.scene_json)
        print(f"[i] 장면을 {args_cli.scene_json} 에 적었다\n", flush=True)

    print(f"[i] 로봇 시작 자세  x {x:+.4f}  y {y:+.4f}  yaw {yaw:+.2f} deg"
          f"  몸통 {float(robot.data.joint_pos[0, lift_ids[0]]):+.4f}", flush=True)
    gap_mm = (low - WHEEL_RADIUS) * 1000.0
    print(f"[i] 가장 낮은 바퀴 중심 {low:.4f} m, 반지름 {WHEEL_RADIUS:.4f} "
          f"-> 바닥과 {gap_mm:+.1f} mm. "
          f"{'닿아 있다' if abs(gap_mm) < 10.0 else '!! 떠 있거나 뚫었다 -- 장면이 잘못 섰다'}", flush=True)
    robot_pose.assert_upright(robot, log=lambda m: print(f"[i] {m}", flush=True))
    for k, r in enumerate(res):
        pw = L.robot_to_world(tuple(r["pos"]))
        print(f"[i] 상품 {k} {r['slug']}  ({pw[0]:+.4f}, {pw[1]:+.4f}, {pw[2]:.4f})  "
              f"{'상판 위' if not r['sunk'] else '!! 뚫림'}  "
              f"{'띠 안' if r['inside'] else '!! 띠 밖/간격/방위'}", flush=True)
    sp = scene["scanner"].data.root_pos_w[0]
    print(f"[i] 스캐너  ({float(sp[0]):+.4f}, {float(sp[1]):+.4f}, {float(sp[2]):.4f}) -- 왼손이 드는 자리", flush=True)
    print("[i] 장면이 섰다. 여기서 과제 C 가 시작한다.\n", flush=True)

    if args_cli.shot:
        cam = scene["head_cam"]
        for _ in range(SHOT_WARMUP):
            sim.render()
        cam._is_outdated[:] = True
        cam.update(PHYSICS_DT, force_recompute=True)
        rgb = cam.data.output["rgb"][0][..., :3].cpu().numpy().astype(np.uint8)
        from PIL import Image
        Image.fromarray(rgb).save(args_cli.shot)
        print(f"[i] 머리 카메라 그림을 {args_cli.shot} 에 적었다 "
              f"({rgb.shape[1]}x{rgb.shape[0]})\n", flush=True)

    secs = args_cli.seconds or (1.0 if args_cli.headless else 0.0)
    if secs > 0.0:
        hold(int(secs / PHYSICS_DT), render=settle_render)
    else:
        while simulation_app.is_running():
            hold(1)


main()
# Kit 의 종료가 이 이미지에서는 돌아오지 않는다 (과제 A/B 데모의 실측). 정상 종료를 먼저
# 시도하되, 10 초 안에 안 돌아오면 프로세스를 그대로 끝낸다. 장면 JSON 과 그림은 이미 쓰였다.
_exit_guard = _threading.Timer(10.0, os._exit, (0,))
_exit_guard.daemon = True
_exit_guard.start()
simulation_app.close()
