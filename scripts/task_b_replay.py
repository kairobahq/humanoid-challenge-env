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

"""과제 B 한 판을 처음부터 끝까지 틀어서 보여준다.

`task_b_demo.py` 는 **시작 장면**을 세우고 멈춘다. 이 스크립트는 그 다음을 보여준다 --
로봇이 상자에서 상품을 꺼내고, 몸을 돌려 진열대로 가서, 빈 칸에 놓는 한 판 전부다.

    cd /workspace/cyclo_lab
    ${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
        /workspace/challenge_scripts/task_b_replay.py --seed 1

`--seed` 로 판을 고른다. 0 부터 6 까지 일곱 판이 들어 있다.

**이것은 재생이지 시뮬레이션이 아니다.** 프레임마다 로봇의 관절 31 개와 로봇의 위치,
그리고 상품 스물 몇 개의 위치를 기록에서 그대로 **써 넣는다**. 그래서

  * 로봇이 어디 있었고 상품이 어디 있었는지는 **기록 그대로 정확하다.**
  * 접촉은 보여줄 수 없다. 손가락이 상품을 눌러서 딸려 오는 것이 아니라, 상품도
    프레임마다 제 자리에 놓인다. "이 파지가 미끄러지지 않고 버티는가" 는 이 화면이
    답할 수 있는 질문이 아니다 -- 그건 이 판을 실제로 돌려서 이미 답한 것이고,
    일곱 판 모두 놓기에 성공한 판이다.

기록은 10 Hz 다. 그대로 그리면 눈에 뚝뚝 끊겨 보여서, 자세와 자세 사이를
`--substeps` 배로 채워 그린다(기본 4 배 = 40 Hz). 채우는 값은 양 끝을 잇는 것일 뿐
지어내는 것이 아니고, 끝점은 언제나 기록이다.

**배경은 편의점 매장이다.** 이 기록은 매장 안에서 모았고, 재생도 같은 매장 위에서 한다.

    --seed 1              어느 판 (0..6)
    --substeps 4          자세 사이를 몇 배로 채우나. 1 이면 안 채운다
    --hz 40               초당 몇 장까지 그리나. substeps 와 곱이 10 이면 실제 속도
    --list                무슨 판이 들어 있는지 찍고 끝낸다
"""

import argparse
import glob
import os
import threading as _threading

from isaaclab.app import AppLauncher

DEMO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "taskB", "demos")

parser = argparse.ArgumentParser(description="과제 B 한 판을 처음부터 끝까지 튼다.")
parser.add_argument("--seed", type=int, default=0,
                    help="어느 판을 틀지. 0 부터, --list 로 목록을 본다.")
parser.add_argument("--substeps", type=int, default=4,
                    help="기록된 자세 사이를 몇 배로 채우나. 기록이 10 Hz 라 4 면 40 Hz.")
parser.add_argument("--hz", type=float, default=40.0,
                    help="초당 그리는 장 수의 상한. substeps 와 곱이 10 이면 실제 속도.")
parser.add_argument("--list", action="store_true", help="들어 있는 판을 찍고 끝낸다.")
AppLauncher.add_app_launcher_args(parser)
parser.set_defaults(device="cpu")     # 환경 하나뿐이라 GPU 파이프라인은 손해다
args_cli = parser.parse_args()
args_cli.enable_cameras = True        # 로봇이 카메라를 달고 있어 이 깃발 없이는 스폰이 막힌다

import importlib.util as _ilu   # noqa: E402
import json                     # noqa: E402
import time                     # noqa: E402

CYCLOLAB = os.environ.get("CYCLOLAB_PATH", "/workspace/cyclo_lab")
_SRC = f"{CYCLOLAB}/source/cyclo_lab/cyclo_lab"
_HERE = os.path.dirname(os.path.abspath(__file__))
if not os.path.isdir(_SRC):
    raise SystemExit(f"환경 코드를 찾지 못했다: {_SRC}\n"
                     f"CYCLOLAB_PATH 를 확인하라 (현재 {CYCLOLAB!r}).")


def _by_path(name, path):
    """모듈을 경로로 읽는다 (task_b_demo.py 와 같은 이유 -- isaaclab 을 먼저 끌어오지 않기)."""
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 카메라 값은 **이미지가 아니라 이 저장소**에서 온다 (task_b_demo.py 와 같다, #4).
REALCAM = _by_path("FFW_SG2_REAL_cameras", f"{_HERE}/FFW_SG2_REAL_cameras.py")
head_camera_cfg, wrist_camera_cfg = REALCAM.head_camera_cfg, REALCAM.wrist_camera_cfg
taskB_shelf = _by_path("taskB_shelf", f"{_SRC}/assets/object/taskB_shelf.py")
taskB_table = _by_path("taskB_table", f"{_SRC}/assets/object/taskB_table.py")
# 매장 씬 -- 과제 A 가 쓰는 그 파일이다. 과제 B 수집도 이 씬 안에서 돌았으므로
# (`meta.store_scene`, 2026-08-21~) 재생 화면도 같은 배경이어야 기록과 같은 그림이 된다.
taskA_layout = _by_path("taskA_layout", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "taskA", "taskA_layout.py"))

FRONT_X = 0.47
PHYSICS_DT = 1.0 / 120.0

# ---- 기록을 Isaac 보다 먼저 읽는다 (씬을 무엇으로 지을지가 여기서 정해진다) -------------------
import numpy as _np   # noqa: E402


def _demos():
    return sorted(glob.glob(os.path.join(DEMO_DIR, "demo_*.npz")))


def _head(path):
    z = _np.load(path, allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    n = int(z["all_joint_pos"].shape[0])
    z.close()
    return meta, n


_files = _demos()
if not _files:
    raise SystemExit(f"판이 하나도 없다: {DEMO_DIR}/demo_*.npz")
if args_cli.list:
    print(f"{len(_files)} 판\n")
    for _i, _f in enumerate(_files):
        _m, _n = _head(_f)
        _d = _m.get("demo_from") or {}
        print(f"  --seed {_i}   {_n:5d} 프레임 ({_n / 10.0:5.1f} 초)   "
              f"{_m.get('pick_product', '?'):26s}  {os.path.basename(_f)}")
        print(f"              {_m.get('task', '')}")
    raise SystemExit(0)
if not 0 <= args_cli.seed < len(_files):
    raise SystemExit(f"--seed 는 0 부터 {len(_files) - 1} 까지다 (받은 값 {args_cli.seed}). "
                     f"--list 로 목록을 보라.")

DEMO = _files[args_cli.seed]
_z = _np.load(DEMO, allow_pickle=False)
META = json.loads(str(_z["meta"]))
TABLE = json.loads(META["scene"])
JOINT_NAMES = list(META["joint_names"])
JOINTS = _np.asarray(_z["all_joint_pos"], dtype=_np.float64)
ROOT = _np.asarray(_z["root_pose"], dtype=_np.float64)
# 기록 속 물체 이름 -> 프레임별 자세. `crate_tracker` 는 상자와 같은 prim 의 두 번째
# 손잡이라 여기서는 쓰지 않는다 (같은 것에 두 번 쓸 뿐이다).
OBJ = {k.split("/", 1)[1]: _np.asarray(_z[k], dtype=_np.float64)
       for k in _z.files if k.startswith("obj/") and k != "obj/crate_tracker"}
_z.close()
NFRAMES = JOINTS.shape[0]

# 칸 -> 상품, 상자 자리 -> 상품. 기록의 장부가 이름을 주고, 첫 프레임이 자리를 준다.
SLOT_OF = {f"l{e['layer']}_s{int(e['slot']):02d}": e for e in TABLE.get("shelf") or []}
HELD_OF = {f"held{int(e['region'])}": e for e in TABLE.get("crate") or []}
SHELF_ITEMS, CRATE_ITEMS = [], []      # (기록 속 이름, 상품, 첫 자세)
for _k in sorted(SLOT_OF):
    if _k in OBJ:
        SHELF_ITEMS.append((_k, SLOT_OF[_k]["product"], OBJ[_k][0]))
for _k in sorted(HELD_OF, key=lambda s: int(s[4:])):
    if _k in OBJ:
        CRATE_ITEMS.append((_k, HELD_OF[_k]["product"], OBJ[_k][0]))
_named = {n for n, _, _ in SHELF_ITEMS} | {n for n, _, _ in CRATE_ITEMS} | {"crate"}
_extra = sorted(set(OBJ) - _named)
if _extra:
    # 조용히 빼지 않는다: 기록에 있는데 장부가 이름을 안 준 물체는 화면에서 사라지고,
    # 그러면 "그 상품이 왜 없지" 를 화면만 보고는 알 길이 없다.
    raise SystemExit(f"기록에 있는 물체 {_extra} 가 장면 장부에 없다 -- 이 판은 틀 수 없다.")

# 책상은 씨앗이 정한다. 기록이 적어 둔 자리와 맞는지 여기서 본다 -- 다르면 다른 장면이다.
TABLE_POS, TABLE_ROT = taskB_table.table_pose(int(META["seed"]))
_want = TABLE.get("table_pos")
if _want is not None:
    _off = max(abs(float(a) - float(b)) for a, b in zip(TABLE_POS, _want))
    if _off > 0.005:
        raise SystemExit(f"책상 자리가 기록과 다르다: 지금 {tuple(round(v, 4) for v in TABLE_POS)}, "
                         f"기록 {tuple(_want)} (최대 {_off * 1000:.1f} mm). 다른 장면이다.")

print(f"[i] {os.path.basename(DEMO)} -- {NFRAMES} 프레임 ({NFRAMES / 10.0:.1f} 초)")
print(f"[i] {META.get('task', '')}")
_d = META.get("demo_from") or {}
print(f"[i] 집기 {_d.get('pick_frames')} 프레임 + 놓기 {_d.get('place_frames')} 프레임, "
      f"이어 붙인 자리의 벌어짐 {_d.get('seam_deg')} 도 / {_d.get('seam_root_mm')} mm")
print(f"[i] 진열대 상품 {len(SHELF_ITEMS)} 개 · 상자 상품 {len(CRATE_ITEMS)} 개 · "
      f"{args_cli.substeps} 배로 채워 {args_cli.hz:.0f} Hz 로 그린다\n", flush=True)

# ---- 채점 -- 평가표(Task-B 시트)대로. 재생하기 전에 이 기록을 통째로 채점해 두고, 재생 중 그 프레임이 오면
# 알린다. 채점기는 taskB/taskb_score.py 이고 기록(npz)만 읽으므로 화면과 무관하게 같은 점수가 나온다.
taskb_score = _by_path("taskb_score", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   "taskB", "taskb_score.py"))
SCORED = next((r for r in taskb_score.score_npz(DEMO) if "points" in r), None)
RECORD_HZ = float(META.get("record_hz", 10.0))
EVENTS = {}       # 프레임 -> [(항목 문구, 점수)] -- [한 번이라도] 항목이 처음 참이 된 프레임
if SCORED is not None:
    for _rid, _sub, _mx, _kind, _label in taskb_score.RUBRIC:
        _at = SCORED["ever_at"].get(_rid)
        if _kind == "ever" and _at is not None:
            EVENTS.setdefault(int(_at), []).append((_label, int(_mx)))
    _lay, _col = SCORED["target"]
    print(f"[점수] 채점 대상 {SCORED['product']} → 목표 칸 L{_lay} c{_col} · 평가표 15항목 {taskb_score.TOTAL}점")
    print(f"[점수] 채점 종료 프레임 {SCORED['end_frame']} "
          f"({SCORED['end_frame'] / RECORD_HZ:.1f}초, {taskb_score.END_WORDS[SCORED['measured']['end_reason']]}"
          + (f" -- gripper 열림 {SCORED['release_frame'] / RECORD_HZ:.1f}초 + 3초"
             if SCORED["measured"]["end_by"] == "released+3s" else "") + ")\n", flush=True)
else:
    print("[점수] 이 기록은 채점하지 못했다 (상자 속 상품의 빈 칸이 장부에 없다)\n", flush=True)

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import numpy as np                                                    # noqa: E402
import torch                                                          # noqa: E402
import isaaclab.sim as sim_utils                                      # noqa: E402
from isaaclab.assets import AssetBaseCfg, RigidObjectCfg              # noqa: E402
from isaaclab.scene import InteractiveScene, InteractiveSceneCfg      # noqa: E402
from isaaclab.sensors import CameraCfg                                # noqa: E402
from isaaclab.utils import configclass                                # noqa: E402

from cyclo_lab.assets.robots.FFW_SG2 import FFW_SG2_MOBILE_CFG        # noqa: E402
from cyclo_lab.simulation_tasks.manager_based.manipulation.pick_place import (  # noqa: E402
    convstore_store,
)


@configclass
class World(InteractiveSceneCfg):
    """바닥, 조명, 로봇, 진열대, 책상, 상자, 그리고 이 기록에 나오는 상품 전부.

    카메라 둘은 `task_b_demo.py` 와 같은 값이다 -- 채점이 정책에게 보내는 관측과
    같은 화각이다 (head_cam 672x376, right_wrist_cam 424x240). 그 파일이 바뀌면
    여기도 같이 바꾼다.
    """

    ground = AssetBaseCfg(prim_path="/World/ground", spawn=sim_utils.GroundPlaneCfg())
    light = AssetBaseCfg(
        prim_path="/World/Light",
        spawn=sim_utils.DomeLightCfg(intensity=2500.0, color=(1.0, 1.0, 1.0)))
    robot = FFW_SG2_MOBILE_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")

    head_cam = head_camera_cfg(
        update_period=1.0e9,
        data_types=["rgb"],
        update_latest_camera_pose=True,
    )
    right_wrist_cam = wrist_camera_cfg("right", 
        update_period=1.0e9,
        data_types=["rgb"],
        update_latest_camera_pose=True,
    )

    def __post_init__(self):
        self.shelf = taskB_shelf.taskB_shelf_cfg(FRONT_X)
        # 매장이 우리에게 온다. 씬의 제 과제 B 진열대 자리(Fix_shelf_taskB: 앞면 x 0.9134 ·
        # 중심 y 2.60)가 우리 진열대(앞면 FRONT_X · 중심 y 0)에 겹치도록 옮긴다 --
        # 수집기(task_b_episode.py:1568)와 같은 값이다.
        self.store_bg = AssetBaseCfg(
            prim_path="{ENV_REGEX_NS}/StoreBg",
            spawn=sim_utils.UsdFileCfg(usd_path=taskA_layout.STORE_USD),
            init_state=AssetBaseCfg.InitialStateCfg(pos=(FRONT_X - 0.9134, -2.60, 0.0)))
        # 책상은 재생에서 kinematic 그대로다. 기록이 매 프레임 상자와 상품 자세를 덮어쓰는데
        # 책상은 기록에 없으므로, 몸으로 두면 상자가 얹히며 미끄러져 기록과 어긋난다.
        self.table = AssetBaseCfg(
            prim_path="{ENV_REGEX_NS}/Table",
            spawn=sim_utils.UsdFileCfg(
                usd_path=taskB_table.TABLE_USD,
                rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
                collision_props=sim_utils.CollisionPropertiesCfg()),
            init_state=AssetBaseCfg.InitialStateCfg(pos=TABLE_POS, rot=TABLE_ROT))
        # 상자와 상품은 첫 프레임의 자세로 세운다. 두 번째 프레임부터는 어차피 기록이
        # 덮어쓰지만, 첫 그림도 기록의 것이라야 한다.
        c0 = OBJ["crate"][0]
        self.crate = RigidObjectCfg(
            prim_path="{ENV_REGEX_NS}/Crate",
            spawn=sim_utils.UsdFileCfg(usd_path=taskB_table.CRATE_USD),
            init_state=RigidObjectCfg.InitialStateCfg(pos=tuple(c0[:3]), rot=tuple(c0[3:])))
        for i, (_k, name, p0) in enumerate(SHELF_ITEMS):
            setattr(self, f"shelf_item{i}", convstore_store.product_cfg(
                f"ShelfItem{i}", name, tuple(p0[:3]), tuple(p0[3:])))
        for i, (_k, name, p0) in enumerate(CRATE_ITEMS):
            setattr(self, f"crate_item{i}", convstore_store.product_cfg(
                f"CrateItem{i}", name, tuple(p0[:3]), tuple(p0[3:])))


def _store_scene_fixups():
    """매장 씬을 깔았으니 셋을 손본다. 수집기(task_b_episode.py:1727)와 같은 순서다.

    ① 씬의 제 과제 B 진열대를 끈다 -- 그 자리는 우리 진열대가 선다.
    ② 씬의 전역 조명 둘(Dome·Key)을 끈다 -- 우리 돔과 겹치면 화면이 하얗게 뜬다.
    ③ 우리 격자 바닥판은 **가시성만** 끈다 -- 씬 바닥은 충돌체가 없어서 우리 판을 빼면
       로봇과 책상이 뚫고 떨어진다.
    """
    import omni.usd as _ou
    from pxr import UsdGeom as _UG
    stage = _ou.get_context().get_stage()
    fix = stage.GetPrimAtPath("/World/envs/env_0/StoreBg/Fix_shelf_taskB")
    if not (fix and fix.IsValid()):
        raise SystemExit(
            "[씬 단계에서 에러 발생] 사유: 매장 씬의 Fix_shelf_taskB 가 StoreBg 아래에 "
            f"없습니다. 씬이 참조하는 조각 파일이 안 열린 것입니다:\n  {taskA_layout.STORE_USD}")
    fix.SetActive(False)
    # 조명은 매장 씬이 들고 온 것을 그대로 쓴다 (2026-09-12). 씬의 Dome 850 · Key 1500 ·
    # 냉장고 RectLight 8개가 그대로 켜져 있고, 과제 A·C 도 그 조명으로 돈다. 학습 데이터도
    # 2026-09-12 부터 이 조명으로 다시 그린다. 돔이 둘이면 화면이 하얗게 뜨므로 끄는 쪽은
    # 우리 돔이다.
    ours = stage.GetPrimAtPath("/World/Light")
    if ours and ours.IsValid():
        ours.SetActive(False)
    g = stage.GetPrimAtPath("/World/ground")
    if g and g.IsValid():
        _UG.Imageable(g).MakeInvisible()
    print("[B] 매장   Fix_shelf_taskB·전역 조명을 껐고 격자 바닥판을 감췄다")


def main():
    sim = sim_utils.SimulationContext(
        sim_utils.SimulationCfg(dt=PHYSICS_DT, device=args_cli.device))
    scene = InteractiveScene(World(num_envs=1, env_spacing=8.0))
    _store_scene_fixups()
    sim.reset()

    robot = scene["robot"]
    # **관절은 순서가 아니라 이름으로 맞춘다.** 기록이 제 관절 이름 31 개를 들고 있으므로,
    # 이 환경의 관절 순서가 어떻든 같은 관절에 같은 값이 간다. 순서로 맞추면 어긋나도
    # 그럴듯해 보이는 동작이 나오고, 그것이 가장 나쁜 종류의 틀림이다.
    here = list(robot.joint_names)
    only_rec = [j for j in JOINT_NAMES if j not in here]
    only_env = [j for j in here if j not in JOINT_NAMES]
    if only_rec or only_env:
        raise SystemExit(f"관절이 서로 다르다 -- 기록에만 {only_rec}, 이 환경에만 {only_env}. "
                         f"같은 로봇이 아니면 이 기록은 틀 수 없다.")
    take = np.asarray([JOINT_NAMES.index(j) for j in here], dtype=np.int64)

    # 기록 속 물체 이름 -> 이 씬의 손잡이
    handles = {"crate": scene["crate"]}
    for i, (k, _n, _p) in enumerate(SHELF_ITEMS):
        handles[k] = scene[f"shelf_item{i}"]
    for i, (k, _n, _p) in enumerate(CRATE_ITEMS):
        handles[k] = scene[f"crate_item{i}"]

    zero_qd = torch.zeros((1, robot.data.joint_pos.shape[1]), device=sim.device)
    zero_v6 = torch.zeros((1, 6), device=sim.device)

    def put(q, root, poses):
        robot.write_joint_state_to_sim(
            torch.as_tensor(q[None, :], dtype=torch.float32, device=sim.device), zero_qd)
        robot.write_root_pose_to_sim(
            torch.as_tensor(root[None, :], dtype=torch.float32, device=sim.device))
        robot.write_root_velocity_to_sim(zero_v6)
        for k, o in handles.items():
            o.write_root_pose_to_sim(
                torch.as_tensor(poses[k][None, :], dtype=torch.float32, device=sim.device))
            o.write_root_velocity_to_sim(zero_v6)
        scene.write_data_to_sim()

    def blend(a, b, t, quat_at=None):
        out = a + (b - a) * t
        if quat_at is not None:
            q0, q1 = a[quat_at:quat_at + 4], b[quat_at:quat_at + 4]
            if float(np.dot(q0, q1)) < 0.0:
                q1 = -q1
            q = q0 + (q1 - q0) * t
            n = float(np.linalg.norm(q))
            out[quat_at:quat_at + 4] = q / n if n > 1e-12 else q0
        return out

    def frame(i, t):
        """기록의 i 번째와 그 다음 사이를 t 만큼 간 자세. t=0 이면 i 번째 그대로."""
        j = min(i + 1, NFRAMES - 1)
        q = JOINTS[i] if t == 0.0 else blend(JOINTS[i].copy(), JOINTS[j], t)
        r = ROOT[i] if t == 0.0 else blend(ROOT[i].copy(), ROOT[j], t, quat_at=3)
        p = {k: (v[i] if t == 0.0 else blend(v[i].copy(), v[j], t, quat_at=3))
             for k, v in OBJ.items() if k in handles}
        return q[take], r, p

    sub = max(1, args_cli.substeps)
    total = (NFRAMES - 1) * sub + 1
    print(f"[i] 재생 시작 -- {total} 장", flush=True)
    t0 = time.time()
    drawn = 0
    got = 0        # 지금까지 딴 점수 -- [점수] 줄마다 누적을 같이 찍는다

    def announce(i):
        """이 프레임에서 딴 점수를 알린다. 채점 종료 프레임이면 놓은 뒤 항목과 최종 점수까지."""
        nonlocal got
        if SCORED is None or i > SCORED["end_frame"]:
            return
        for label, pts in EVENTS.get(i, []):
            got += pts
            print(f"[점수] {i / RECORD_HZ:6.1f}초  {label:<26s} +{pts}   누적 {got:2d}/{taskb_score.TOTAL}", flush=True)
        if i != SCORED["end_frame"]:
            return
        m = SCORED["measured"]
        why = taskb_score.reasons(SCORED)
        head = ("── 놓은 뒤 3초 ──" if m["end_reason"] == "placed"
                else "── product 가 떨어졌다: 채점 종료 ──" if m["end_reason"] == "dropped"
                else "── 기록 끝 (product 를 든 채) ──")
        print(f"[점수] {i / RECORD_HZ:6.1f}초  {head}", flush=True)
        for rid, _sub, mx, kind, label in taskb_score.RUBRIC:
            if kind != "at":
                continue
            pts = SCORED["points"][rid]
            got += pts
            print(f"[점수]          {label:<26s} {'+' + str(pts) if pts else ' 0'}/{mx}   {why[rid]}", flush=True)
        print(f"[점수] ════ 최종 {got} / {taskb_score.TOTAL} 점 ════\n", flush=True)

    for i in range(NFRAMES):
        announce(i)
        for k in range(sub if i < NFRAMES - 1 else 1):
            q, r, p = frame(i, k / sub)
            # 두 번 쓰고 그 사이에 한 걸음. 걸음이 있어야 써 넣은 자세가 화면이 읽는
            # 변환까지 흘러가는데, 그 걸음 동안 팔이 제 무게로 조금 처진다. 걸음 뒤에
            # 한 번 더 쓰면 기록이 말하는 자리로 돌아온다.
            put(q, r, p)
            sim.step(render=False)
            put(q, r, p)
            scene.update(PHYSICS_DT)
            sim.render()
            drawn += 1
            if args_cli.hz > 0:
                due = t0 + drawn / args_cli.hz
                wait = due - time.time()
                if wait > 0:
                    time.sleep(wait)
            if not simulation_app.is_running():
                print("[i] 창이 닫혔다.", flush=True)
                return
        if i % 200 == 0:
            print(f"[i] {i}/{NFRAMES} 프레임 ({time.time() - t0:.0f} 초)", flush=True)
    print(f"[i] 끝 -- {drawn} 장을 {time.time() - t0:.0f} 초에 그렸다.", flush=True)
    if not args_cli.headless:
        print("[i] 마지막 자세로 20 초 세워 둔다 (Ctrl+C 로 바로 닫기)", flush=True)
        end = time.time() + 20.0
        while time.time() < end and simulation_app.is_running():
            sim.render()


main()
# Kit 의 종료가 이 이미지에서는 돌아오지 않는다. 실측 2026-09-03: 장면을 다 세우고 물리·렌더가
# 0.3 초에 끝난 뒤 `simulation_app.close()` 에서 34 분을 매달렸고, 프로세스는 죽지도 않고 CPU 를
# 계속 썼다. 그러면 --headless 로 돌린 참가자는 끝나지 않는 명령을 보게 된다.
#
# 그래서 정상 종료를 먼저 시도하되, 10 초 안에 안 돌아오면 프로세스를 그대로 끝낸다. 이 시점에는
# 장면 JSON 도 카메라 그림도 이미 파일에 쓰인 뒤라 잃는 것이 없다.
_exit_guard = _threading.Timer(10.0, os._exit, (0,))
_exit_guard.daemon = True
_exit_guard.start()
simulation_app.close()
