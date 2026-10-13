# Copyright 2025.
#
# 태스크 D 의 시작 장면 하나를 띄워서 보여준다.
#
# 태스크 D 는 **과제 B 의 모의판**이다. 과제 B 를 그대로 두고 목표 선반만 바꿨다 --
# 받은 `Shelf.zip` 으로 만든 3 단 프레임인데 **판은 맨 위 한 장뿐**이고 아래 두 단은
# 지지대만 남는다. 로봇은 빈손으로 서고, 채워 넣을 상품은 옆 검정 책상 위 **파란 크레이트**
# 안에 하나 들어 있다. 맨 위 판 3 열 중 **한 열의 앞자리가 비어 있고, 크레이트에 든 것이
# 바로 그 자리의 상품이다.** 주변은 매장 기물로 씨앗에 따라 다르게 어질러진다.
#
# 한 장면을 정하는 것은 `--seed` 하나뿐이다. 규칙은 `taskD/taskD_scene_seed.py` 에 전부 있다.
#
# 실행:
#     ${ISAACLAB_PATH}/_isaac_sim/python.sh -u scripts/task_d_demo.py --seed 1000
#     ${ISAACLAB_PATH}/_isaac_sim/python.sh -u scripts/task_d_demo.py --seed 7 --seconds 20
#     ${ISAACLAB_PATH}/_isaac_sim/python.sh -u scripts/task_d_demo.py --seed 7 --headless \
#         --shot /tmp/d7.png --scene-json /tmp/d7.json
#
#     # 장면 규칙과 에셋만 확인하고 끝낸다 (Isaac Sim 을 띄우지 않는다 -- 1 초):
#     ${ISAACLAB_PATH}/_isaac_sim/python.sh -u scripts/task_d_demo.py --check --seed 1000
#
# `--check` 도 **아이작 인터프리터로** 돈다 -- 이 파일이 `isaaclab.app.AppLauncher` 를 모듈
# 스코프에서 import 하기 때문이다(과제 A·B·C 와 같다). 띄우지 않는 것은 `SimulationApp`
# 이고, 그것이 60 초다. 인터프리터조차 없는 데서 규칙만 보려면 아이작을 아예 안 쓰는
# `scripts/taskD/selftest_taskD.py` 와 각 모듈의 `main()` 이 있다.
#
# **코드는 레포에, 에셋은 이미지에.** 이 파일은 마운트되는 쪽이라 에셋을 패키지 상대경로로
# 찾을 수 없다. `taskD/taskD_layout.py` 가 `CYCLOLAB_PATH` 우선으로 푼다.

import argparse
import json
import os
import sys

from isaaclab.app import AppLauncher

_HERE = os.path.dirname(os.path.abspath(__file__))
_TASKD = os.path.join(_HERE, "taskD")

parser = argparse.ArgumentParser(description="태스크 D 의 시작 장면 하나를 띄운다.")
parser.add_argument("--seed", type=int, default=1000,
                    help="장면 하나를 정하는 수. 같은 값이면 같은 장면이다.")
parser.add_argument("--seconds", type=float, default=0.0,
                    help="장면을 몇 초 동안 유지할지. 0 이면 창을 닫을 때까지 (headless 면 "
                         "정착과 보고를 마치고 끝낸다).")
parser.add_argument("--settle", type=float, default=2.0,
                    help="보고 전에 물리를 몇 초 돌릴지. 상품은 닿는 높이로 놓으므로 "
                         "기다리는 것이 아니라 확인이다.")
parser.add_argument("--shot", default=None, metavar="FILE.png",
                    help="로봇 머리 카메라가 보는 그림을 한 장 저장한다.")
parser.add_argument("--scene-json", default=None, metavar="FILE.json",
                    help="장면 내용을 JSON 으로 저장한다.")
parser.add_argument("--no-clutter", action="store_true",
                    help="배경 기물과 매장 바닥을 빼고 맨 장면만 세운다.")
parser.add_argument("--check", action="store_true",
                    help="장면 규칙과 에셋만 검사하고 끝낸다. SimulationApp 을 띄우지 않으므로 "
                         "1 초면 된다 (아이작 인터프리터는 필요하다).")
AppLauncher.add_app_launcher_args(parser)
# 환경이 하나뿐이라 GPU 파이프라인은 손해다. 과제 A·B·C 와 같은 선택.
parser.set_defaults(device="cpu")
args_cli = parser.parse_args()
# 로봇이 카메라를 달고 있어 이 깃발 없이는 스폰이 막힌다 ("A camera was spawned without
# the --enable_cameras flag"). GUI 든 headless 든 켠다.
args_cli.enable_cameras = True

# ---------------------------------------------------------------- 장면 규칙 모듈
#
# **`AppLauncher` 보다 먼저 읽는다.** 아래 여섯은 isaaclab·numpy·pxr 을 모듈 스코프에서
# 쓰지 않는 순수 파이썬이라, `SimulationApp` 이 뜨기 전에 읽을 수 있다. 그래서 `--check` 가
# 앱을 띄우지 않고 1 초에 끝나고, 같은 모듈들을 `selftest_taskD.py` 가 아이작 없이 돌린다.
# 모듈 안에서 isaaclab 을 쓰는 곳(`SH.cfg()`, `*.attach()`)은 전부 함수 안에서 import 한다.
#
# 과제 A 는 같은 목적으로 `_by_path()` 를 쓰는데, 여기서는 `taskD/` 를 경로에 넣고 평범하게
# import 한다 -- 효과는 같고, 모듈마다 혼자 실행할 수 있는 성질(`python3 taskD/
# taskD_stock.py`)이 유지된다.
sys.path.insert(0, _TASKD)
if not os.path.isdir(_TASKD):
    raise SystemExit("[태스크 D] 장면 모듈 폴더가 없다: %s" % _TASKD)

import taskD_clutter as CL     # noqa: E402
import taskD_crate as CR       # noqa: E402
import taskD_layout as LAY     # noqa: E402
import taskD_scene_seed as SD  # noqa: E402
import taskD_shelf as SH       # noqa: E402
import taskD_stock as ST       # noqa: E402

# 로봇 카메라의 정본. 배포 꾸러미에서는 이 파일 옆에 있다. cstore 체크아웃에는 없어서
# `--shot` 만 못 쓰고 장면은 그대로 선다.
try:
    import FFW_SG2_REAL_cameras as CAM     # noqa: E402
except ImportError:
    CAM = None

VIEW_EYES = (                  # 배경 기물이 렌즈 안에 생기지 않게 막을 자리들
    (-2.05, -2.60, 2.10), (0.00, -2.90, 1.40), (-0.45, 2.60, 1.50),
    (-1.45, -1.45, 2.90), (-0.35, 1.55, 0.95), (-1.10, -1.95, 1.50),
)
PHYSICS_DT = 1.0 / 120.0


def draw_scene(seed):
    """이 seed 의 장면. Isaac 없이 정해지는 것 전부."""
    spec = SD.spec(seed)
    ss, cs, ls = spec["shelf_seed"], spec["crate_seed"], spec["clutter_seed"]
    columns, empty = ST.layout(ss)
    (gl, gs), = empty
    carried = ST.carried_item(ss)
    room = () if args_cli.no_clutter else CL.scatter(ls, VIEW_EYES)
    return {
        "seed": seed,
        "shelf_seed": ss, "crate_seed": cs, "clutter_seed": ls,
        "columns": [columns[(gl, i)] for i in range(ST.COLS)],
        "gap": {"layer": gl, "slot": gs, "product": carried},
        "shelf": ST.stock(ss),
        "crate": CR.poses(ss, cs),
        "clutter": list(room),
        "clutter_on": not args_cli.no_clutter,
        "robot": LAY.ROBOT_POS, "table": LAY.TABLE_POS, "crate_pos": LAY.CRATE_POS,
        "shelf_front_x": LAY.SHELF_FRONT_X, "board_top": SH.BOARD_TOPS[SH.LAYERS[0]],
        "shelf_gap_m": LAY.SHELF_GAP,
    }


def print_scene(sc):
    print()
    print("[장면] seed %d   선반씨앗 %d · 크레이트씨앗 %d · 배경씨앗 %d"
          % (sc["seed"], sc["shelf_seed"], sc["crate_seed"], sc["clutter_seed"]))
    print("[장면] 맨 위 판 %.3f m   열 %s" % (sc["board_top"], sc["columns"]))
    print("[장면] 빈 자리 %d 열 앞줄  ->  크레이트 %s" % (sc["gap"]["slot"], sc["gap"]["product"]))
    print("[장면] 선반 %d 개 + 크레이트 %d 개   배경 기물 %d 개%s"
          % (len(sc["shelf"]), len(sc["crate"]), len(sc["clutter"]),
             "" if sc["clutter_on"] else " (껐다)"))
    print("[장면] 로봇 %s   선반까지 %.0f mm   책상 %s"
          % (sc["robot"], sc["shelf_gap_m"] * 1000.0, sc["table"]))


def scene_json(sc):
    """저장용. 튜플을 리스트로 펴고 긴 것은 그대로 싣는다."""
    return {
        "seed": sc["seed"],
        "shelf_seed": sc["shelf_seed"], "crate_seed": sc["crate_seed"],
        "clutter_seed": sc["clutter_seed"],
        "columns": sc["columns"],
        "gap": sc["gap"],
        "shelf": [{"product": n, "pos": list(p), "layer": l, "slot": s}
                  for n, p, l, s in sc["shelf"]],
        "crate": [{"product": n, "pos": list(p), "quat": list(q)} for n, p, q in sc["crate"]],
        "clutter": [{"fixture": n, "prim": pr, "xy": list(xy), "yaw_deg": y}
                    for n, pr, xy, y in sc["clutter"]],
        "layout": {"robot": list(sc["robot"]), "table": list(sc["table"]),
                   "crate": list(sc["crate_pos"]), "shelf_front_x": sc["shelf_front_x"],
                   "board_top": sc["board_top"], "shelf_gap_m": sc["shelf_gap_m"]},
    }


def check(sc):
    """장면 규칙과 에셋만 본다. 어긋난 것들의 목록."""
    bad = list(SH.problems())
    bad += ST.problems(sc["shelf_seed"])
    bad += CR.problems(sc["shelf_seed"], sc["crate_seed"])
    if sc["clutter_on"]:
        bad += CL.problems(sc["clutter_seed"], VIEW_EYES)
    # 에셋 셋. **판정 줄보다 먼저** 보게 둔다 -- 과제 A 가 이 순서를 틀려서 "문제 없음" 을
    # 찍은 뒤 오류가 따라오고 종료코드만 바뀐 적이 있다.
    for name, path in LAY.usds().items():
        if not os.path.isfile(path):
            bad.append("%s USD 가 없다: %s" % (name, path))
    return bad


SCENE = draw_scene(args_cli.seed)
print_scene(SCENE)
if args_cli.scene_json:
    with open(args_cli.scene_json, "w", encoding="utf-8") as fh:
        json.dump(scene_json(SCENE), fh, ensure_ascii=False, indent=1)
    print("[장면] JSON 저장 %s" % args_cli.scene_json)

if args_cli.check:
    # **AppLauncher 앞에서 끝낸다.** 뒤에서 죽으면 역추적이 찍혀도 종료코드가 0 이 되어,
    # 자동화가 실패를 성공으로 읽는다.
    problems = check(SCENE)
    print()
    for s in problems:
        print("  ! %s" % s)
    print("판정: %s" % ("문제 없음" if not problems else "%d 건" % len(problems)))
    raise SystemExit(1 if problems else 0)

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import isaaclab.sim as sim_utils          # noqa: E402
from isaaclab.assets import AssetBaseCfg  # noqa: E402
from isaaclab.scene import InteractiveScene, InteractiveSceneCfg  # noqa: E402
from isaaclab.utils import configclass    # noqa: E402

from cyclo_lab.assets.object import taskB_shelf  # noqa: E402  (토르소·팔 자세만 가져온다)
from cyclo_lab.assets.robots.FFW_SG2 import FFW_SG2_MOBILE_CFG  # noqa: E402


@configclass
class World(InteractiveSceneCfg):
    """로봇, 검정 책상 위의 파란 크레이트, 판 한 장 선반, 그리고 주변 매장."""

    # 물리적으로 서는 바닥. 매장 바닥 판을 깔아도 이것은 남는다 -- 그 판은 얇은 시각용
    # 타일이고, 로봇과 가구가 실제로 올라서는 것은 이쪽이다.
    plane = AssetBaseCfg(prim_path="/World/GroundPlane", spawn=sim_utils.GroundPlaneCfg())
    light = AssetBaseCfg(
        prim_path="/World/Light",
        spawn=sim_utils.DomeLightCfg(color=(0.75, 0.75, 0.75), intensity=3000.0))

    # 과제 B 의 토르소와 쉬는 팔을 그대로 쓴다. 리프트 -0.30 과 팔꿈치 -138 도는 둘 다
    # 과제 B 가 **바구니** 때문에 재어 고른 값인데, 태스크 D 는 바구니를 들지 않는다.
    # 그래도 여기서 새 값을 지어내지 않는다 -- 대조 없이 손잡이를 돌리는 일이 된다.
    robot = FFW_SG2_MOBILE_CFG.replace(
        prim_path="{ENV_REGEX_NS}/Robot",
        init_state=FFW_SG2_MOBILE_CFG.init_state.replace(
            pos=LAY.ROBOT_POS,
            joint_pos={**FFW_SG2_MOBILE_CFG.init_state.joint_pos,
                       "lift_joint": taskB_shelf.LIFT_JOINT_POS,
                       **taskB_shelf.home_joint_pos()}))

    shelf = SH.cfg()
    desk = CR.table_cfg()
    crate = CR.cfg()

    if CAM is not None:
        head_cam = CAM.head_camera_cfg(update_period=1.0e9, data_types=["rgb"],
                                       update_latest_camera_pose=True)

    def __post_init__(self):
        # `InteractiveScene` 은 `cfg.__dict__` 를 훑어 자산을 만들므로, 여기서 다는 것은
        # 필드로 선언하는 것과 같다. 개수가 씨앗에 따라 달라지는 자산은 이렇게 단다.
        n_shelf = ST.attach(self, SCENE["shelf_seed"],
                            log=lambda s: print("[장면] %s" % s))
        n_crate = CR.attach(self, SCENE["shelf_seed"], SCENE["crate_seed"],
                            log=lambda s: print("[장면] %s" % s))
        if n_shelf <= 0 or n_crate <= 0:
            raise SystemExit("[태스크 D] 선반 %d 개 · 크레이트 %d 개 -- 하나도 못 세운 것은 "
                             "조용히 넘기지 않는다." % (n_shelf, n_crate))
        if SCENE["clutter_on"]:
            CL.attach(self, SCENE["clutter_seed"], VIEW_EYES,
                      log=lambda s: print("[장면] %s" % s))
            self.store_floor = CL.store_floor_cfg()


def report(scene):
    """물리가 한 번 본 뒤의 상태. 놓은 자리에서 얼마나 움직였는지로 잰다."""
    print()
    for i, (name, pos, _q) in enumerate(SCENE["crate"]):
        p = scene["crate%d" % i].data.root_state_w[0, :3].cpu()
        drop = (float(p[2]) - pos[2]) * 1000.0
        print("[정착] crate%d %-28s (%+.4f, %+.4f, %+.4f)  놓은 자리에서 %+.1f mm%s"
              % (i, name, p[0], p[1], p[2], drop, "  <-- 떨어졌다" if drop < -20 else ""))
    fallen = []
    for name, pos, layer, slot in SCENE["shelf"]:
        key = "l%d_s%02d" % (layer, slot)
        z = float(scene[key].data.root_state_w[0, 2].cpu())
        # **놓은 자리 기준**으로 잰다. 판 높이를 기준으로 재면, 바닥에 누운 상품도 밑동
        # 높이 때문에 판 위로 읽힌다 -- 그래서 15 개가 떨어진 것을 13 개라고 보고한 적이 있다.
        if z < pos[2] - 0.02:
            fallen.append((key, name, pos[2], z))
    if fallen:
        print("[경고] %d/%d 개가 놓은 자리보다 20 mm 넘게 내려갔다 -- 콜라이더를 의심할 것:"
              % (len(fallen), len(SCENE["shelf"])))
        for key, name, put, z in fallen:
            print("[경고]   %s %-28s 놓은 z %+.4f -> %+.4f (%+.0f mm)"
                  % (key, name, put, z, (z - put) * 1000.0))
    else:
        print("[정착] 선반 위 %d 개 전부 제자리" % len(SCENE["shelf"]))
    print()


def main():
    sim = sim_utils.SimulationContext(
        sim_utils.SimulationCfg(dt=PHYSICS_DT, device=args_cli.device))
    sim.set_camera_view(eye=(-2.05, -2.60, 2.10), target=(0.18, -0.32, 0.58))
    scene = InteractiveScene(World(num_envs=1, env_spacing=8.0))
    sim.reset()

    dt = sim.get_physics_dt()
    settle = int(args_cli.settle / dt)
    stop = int(args_cli.seconds / dt) if args_cli.seconds > 0 else None

    n = 0
    while simulation_app.is_running():
        scene.write_data_to_sim()
        sim.step()
        scene.update(dt)
        n += 1
        if n == settle:
            report(scene)
            if args_cli.shot:
                save_shot(scene)
            if args_cli.headless and stop is None:
                break
        if stop is not None and n >= stop:
            break
    simulation_app.close()


def save_shot(scene):
    """머리 카메라가 보는 그림 한 장."""
    if CAM is None:
        print("[사진] 카메라 정본 모듈(FFW_SG2_REAL_cameras.py)이 이 폴더에 없다 -- "
              "배포 꾸러미에 넣으면 쓸 수 있다. 저장을 건너뛴다.")
        return
    import numpy as np
    from PIL import Image
    rgb = scene["head_cam"].data.output["rgb"][0].cpu().numpy()
    Image.fromarray(np.asarray(rgb, dtype=np.uint8)[..., :3]).save(args_cli.shot)
    print("[사진] %s" % args_cli.shot)


if __name__ == "__main__":
    main()
