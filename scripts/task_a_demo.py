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

"""과제 A 의 시작 장면 하나를 띄워서 보여준다.

과제 A 는 "시식 탁상에서 바구니를 집어, 장애물을 피해 목적지 진열대 옆 책상에 옮겨 놓는"
과제이고, 이 스크립트는 그 **에피소드가 시작되는 순간의 장면**을 만든다. 여기서 멈춘다 --
집지도, 몰지도, 놓지도 않는다. 참가자가 보아야 하는 것은 자기 정책이 첫 관측으로 받게 될
바로 그 그림이기 때문이다.

한 장면은 seed 하나로 완전히 정해진다. 같은 seed 는 어디서 돌려도 같은 장면이다.

  * **매장**    편의점 전체가 들어온다. 통로 세 줄, 곤돌라, 냉장고, 냉동고, 와인 진열대,
    계산대, 그리고 시식 코너. 과제 B 가 진열대 하나 앞에서 벌어지는 것과 달리 과제 A 는
    매장을 가로지른다 -- 좌석에 따라 목적지까지 9.3 ~ 11.2 m 다.
  * **좌석**    원형 시식 탁상 3 개 x 4 등분 = **12 개 고정 좌석** 중 하나. 임의 지점에서
    출발하던 옛 정의는 폐기됐다. 다양성은 좌석과 목적지에서 나온다.
  * **바구니**  로봇 앞 탁상 위에 놓인 파란 상자. 이것을 집어서 가져가야 한다.
  * **책상**    목적지 진열대 옆. 바구니는 여기에 놓여야 한다. 장면에 책상은 **하나뿐**이다.
  * **로봇**    좌석에서 300 mm 앞으로 나와, 몸통을 이미 작업 높이까지 내리고 고개를 숙인
    채로 선다. 바퀴가 바닥에 닿아 있다 -- 공중에서 떨어지지 않는다(아래 settle_on_ground).

실행:

    cd /workspace/cyclo_lab
    ${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
        /workspace/challenge_scripts/task_a_demo.py --seed 1000

    # 화면 없이, 장면 내용만 파일로:
    ${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
        /workspace/challenge_scripts/task_a_demo.py --seed 1000 --headless \
        --seconds 2 --scene-json /workspace/user/scene_a_1000.json

    # 좌석 기하만 확인하고 끝낸다 (Isaac Sim 을 띄우지 않는다 -- 1 초):
    ${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
        /workspace/challenge_scripts/task_a_demo.py --check
"""

import argparse
import os
import threading as _threading

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="과제 A 의 시작 장면 하나를 띄운다.")
parser.add_argument("--seed", type=int, default=1000,
                    help="장면 하나를 정하는 수. 같은 값이면 같은 장면이다.")
parser.add_argument("--seat", type=int, default=None, choices=range(12), metavar="{0..11}",
                    help="어느 좌석에서 시작할지. 기본값은 seed 가 정한다. 좌석은 시식 탁상 "
                         "3 개를 4 등분한 12 곳이고, 탁상 순서로 번호가 붙는다.")
parser.add_argument("--seconds", type=float, default=0.0,
                    help="장면을 몇 초 동안 유지할지. 0 이면 창을 닫을 때까지 (--headless "
                         "일 때는 1 초).")
parser.add_argument("--shot", default=None, metavar="FILE.png",
                    help="로봇 머리 카메라가 보는 그림을 한 장 저장한다. 화면 없이 돌릴 때 "
                         "장면을 눈으로 확인하는 길이고, 정책이 받게 될 관측 그대로다.")
parser.add_argument("--scene-json", default=None, metavar="FILE.json",
                    help="장면 내용을 JSON 으로 저장한다. 좌석과 로봇 자세, 바구니 좌표, "
                         "목적지와 책상 좌표, 스툴 자리가 들어 있다.")
parser.add_argument("--check", action="store_true",
                    help="12 좌석의 기하와 매장 USD 만 검사하고 끝낸다. Isaac Sim 을 띄우지 "
                         "않으므로 1 초면 된다 -- 좌석이 벽 안에 있거나 스툴이 회전을 막거나 "
                         "매장 USD 가 없는 것은 시뮬레이터 기동 60 초를 치르기 전에 알 수 "
                         "있는 종류의 문제다.")
AppLauncher.add_app_launcher_args(parser)
parser.set_defaults(device="cpu")     # 환경 하나뿐이라 GPU 파이프라인은 손해다 (1.83 ms vs 38.11)
args_cli = parser.parse_args()
args_cli.enable_cameras = True        # 로봇이 카메라를 달고 있어 이 깃발 없이는 스폰이 막힌다

import importlib.util as _ilu   # noqa: E402
import json                     # noqa: E402
import math                     # noqa: E402

CYCLOLAB = os.environ.get("CYCLOLAB_PATH", "/workspace/cyclo_lab")
_SRC = f"{CYCLOLAB}/source/cyclo_lab/cyclo_lab"
if not os.path.isdir(_SRC):
    raise SystemExit(f"환경 코드를 찾지 못했다: {_SRC}\n"
                     f"CYCLOLAB_PATH 를 확인하라 (현재 {CYCLOLAB!r}).")

# 과제 A 의 장면 정의 모듈은 **이 저장소 안**, 이 파일 옆의 `taskA/` 에 있다.
#
# 이미지 안이 아니라 여기 두는 이유 셋:
#   * `scripts/` 는 마운트라 `git pull` 만으로 갱신된다. 이미지를 다시 굽지 않아도 된다.
#   * 참가자가 장면이 어떻게 서는지 GitHub 에서 바로 읽을 수 있다. 35 GB 컨테이너에
#     들어가야만 보이는 코드는 없는 것과 비슷하다.
#   * 이 저장소만 받으면 데모가 도는 데 필요한 코드가 전부 있다. 다른 저장소의 커밋 여부에
#     기대지 않는다.
#
# 이미지에서 오는 것은 **에셋뿐**이다 -- 매장 USD 184 MB, 로봇, 집기. 저장소에 둘 크기가
# 아니고, 매장 USD 는 참조 94 개를 상대경로로 물고 있어 통째로 옮겨야 한다.
_TASKA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "taskA")
if not os.path.isdir(_TASKA):
    raise SystemExit(f"과제 A 모듈을 찾지 못했다: {_TASKA}")


def _by_path(name, path):
    """모듈을 경로로 읽는다.

    패키지(`import cyclo_lab`)를 거치면 isaaclab 이 딸려 들어오고, isaaclab 이
    SimulationApp 보다 먼저 import 되면 Isaac Sim 이 아예 뜨지 않는다. 아래 두 모듈은
    isaaclab 을 쓰지 않는 순수 파이썬이라 이렇게 먼저 읽을 수 있다. 나머지 셋
    (taskA_colliders / taskA_stools / taskA_robot_pose)은 pxr 과 isaaclab 을 쓰므로
    AppLauncher 뒤에서 읽는다.
    """
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


taskA_seats = _by_path("taskA_seats", f"{_TASKA}/taskA_seats.py")
taskA_layout = _by_path("taskA_layout", f"{_TASKA}/taskA_layout.py")
# 진열 셋. 셋 다 isaaclab 을 안 쓰므로 여기서 읽어도 된다 -- `taskA_shelf_stock.attach()` 와
# `taskA_store_dress.dress()` 만 각자 안에서 isaaclab/pxr 을 부른다.
taskA_scene_seed = _by_path("taskA_scene_seed", f"{_TASKA}/taskA_scene_seed.py")
taskA_shelf_stock = _by_path("taskA_shelf_stock", f"{_TASKA}/taskA_shelf_stock.py")
taskA_store_dress = _by_path("taskA_store_dress", f"{_TASKA}/taskA_store_dress.py")
# 카메라 값. 위 모듈들과 같이 **이 저장소**에서 온다 (윗 주석의 세 가지 이유 그대로).
# 2026-09-13: 이미지(2026-09-07 판)에 이 파일이 없어 데모 셋이 전부 FileNotFoundError 로
# 죽었다 (humanoid-challenge-env#4). 그때 이 줄은 AppLauncher **뒤**에 있어서, 트레이스백이
# 찍히고도 종료 코드가 0 으로 나왔다 -- 자동화가 성공으로 읽는다. 그래서 여기로 옮겼다.
# 이 모듈은 부를 때만 isaaclab 을 import 하므로 AppLauncher 앞에서 읽어도 된다.
REALCAM = _by_path("FFW_SG2_REAL_cameras", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "FFW_SG2_REAL_cameras.py"))
head_camera_cfg, wrist_camera_cfg = REALCAM.head_camera_cfg, REALCAM.wrist_camera_cfg

# 물리 한 걸음. 과제 B 와 같은 값이다.
#
# Task-A 쪽 수집 코드는 오랫동안 1/60 을 썼는데, 1/120 으로 올리자 바구니를 든 주행이
# 성공했다(2026-08-17). 이 데모는 아무것도 몰지 않으므로 어느 쪽이든 장면은 같지만,
# 두 데모가 같은 값을 쓰는 편이 읽는 사람에게 낫다.
PHYSICS_DT = 1.0 / 120.0
WHEEL_RADIUS = 0.0864       # 구동 바퀴 반지름 = 바퀴가 바닥에 닿았을 때의 바퀴 중심 높이

# 물리 몇 걸음마다 한 번 그릴지. **과제 B 데모에는 없는 값이고, 여기 필요한 이유가 있다.**
#
# 과제 B 의 장면은 진열대 하나와 상품 마흔 개 남짓이라 매 걸음 그려도 값이 싸다. 과제 A 는
# 편의점 전체 -- 집기 20 종, 상품 1,756 개, 레이어 94 개 -- 라 한 장이 훨씬 비싸다.
# 물리 120 Hz 에 맞춰 매 걸음 그리면 장면 하나 세우는 데 화면 없이도 몇 분이 걸린다
# (2026-08-25 실측). 물리와 그림은 같은 주기를 쓸 이유가 없다.
#
# 4 는 30 Hz 다. 눈으로 보기에 충분하고, 이 스크립트는 어차피 아무것도 움직이지 않는다.
# 평가 서버가 쓰는 값(물리 100 Hz, 렌더 50 Hz)과 같은 종류의 선택이다.
RENDER_EVERY = 4

# `--shot` 을 찍기 전에 몇 장을 그려 두고 찍을지. 렌더러가 프레임을 시간적으로 누적해서
# 잡티를 지우므로, 몇 장 안 그리고 찍으면 지글거리는 그림이 나온다.
SHOT_WARMUP = 16


def _yaw_quat(yaw):
    """Z 축 회전의 (w, x, y, z). **집기(prop)에만 쓴다.**

    로봇에는 절대 쓰지 않는다 -- FFW-SG2 의 루트 링크는 항등 자세에서 서 있지 않아서, 순수
    yaw 를 씌우면 로봇이 90 도 옆으로 눕는다(taskA_robot_pose.py 의 기록 참조). 로봇은
    robot_pose.place() 로만 세운다.
    """
    return (math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0))


def draw_scene(seed, seat_id):
    """이 seed 의 장면. Isaac 없이 정해지는 것 전부.

    돌려주는 것:
      seat      좌석 하나 -- 탁상 번호, 좌석 번호, 각도, 탁상 중심, 스툴 자리
      robot     로봇의 시작 (x, y, yaw). 좌석에서 SPAWN_FORWARD 만큼 앞으로 나온 자리다
      basket    탁상 위 바구니의 (x, y, z) 와 yaw
      goal      로봇이 도착해서 서야 하는 (x, y, yaw)
      desk      바구니를 내려놓는 책상의 (x, y, z)
    """
    # `stool_seed` 를 넘긴다. 넘기지 않으면 기본값 0 이 쓰이고, 그러면 **로봇이 앉지 않는
    # 나머지 두 탁상의 스툴 여덟 개가 seed 와 무관하게 늘 같은 자리에 선다.** taskA_seats 의
    # `_idle_places()` 는 `STOOL_SEED + table*131 + seed*7919` 로 뽑는데 그 seed 항이 0 이
    # 되기 때문이다. 원본 수집기도 이것을 안 넘겨서 같은 구멍을 갖고 있다(Task-A/CLAUDE.md
    # §4758 "재현에는 문제없지만 45 절이 정한 랜덤화가 아직 안 들어갔다").
    #
    # 로봇이 앉는 탁상의 스툴 넷은 여전히 좌석만의 함수다 -- `_stool_places()` 에는 시드
    # 인자가 없다. 그것이 §45 의 설계다: 그 넷은 "좌석 반대편으로 치운다" 는 규칙이 정하고,
    # 규칙이 정하는 것에 난수를 섞으면 로봇이 설 자리가 막힌다.
    all_seats = taskA_seats.seats(stool_seed=seed)
    # 좌석 사상은 `taskA_scene_seed.py` 한 곳에만 적혀 있다. 예전에는 그 식이 여기
    # `(seed * 7919) % len(all_seats)` 로도 적혀 있었는데, 같은 식을 두 번째로 적어 두는
    # 것은 두 값이 갈라질 두 번째 기회다 -- 그리고 이 식이 갈라지면 주최 측 정답 주행과
    # 참가자 장면이 **조용히** 다른 좌석이 된다.
    if len(all_seats) != taskA_scene_seed.N_SEATS:
        raise SystemExit(f"좌석 수가 안 맞는다: 실제 {len(all_seats)}, "
                         f"taskA_scene_seed.N_SEATS {taskA_scene_seed.N_SEATS}")
    n = taskA_scene_seed.seat_of(seed) if seat_id is None else seat_id
    seat = all_seats[n]
    seeds = taskA_scene_seed.spec(seed)

    rx, ry, ryaw = taskA_layout.spawn_robot_pose(seat)
    gx, gy, gyaw = taskA_layout.goal_pose()
    dx, dy, dz = taskA_layout.desk_pos()
    # 바구니는 좌석이 정한 자리에서 seed 가 정한 만큼 옮긴다 (반경 20 mm 안, 방향은 그대로).
    # 규칙과 20 mm 의 근거는 `taskA_scene_seed.CRATE_SHIFT_M` 에 있다. **여기 한 곳만 바꾸면
    # 스폰·가라앉힌 뒤 다시 적기(`rewrite_props`)·`--scene-json` 이 전부 따라온다** -- 셋 다
    # `SCENE["basket"]` 을 읽는다. 스폰만 옮기면 `rewrite_props` 가 기본 자리로 되돌려 놓는다.
    bx, by, bz = seat["basket_xyz"]
    cdx, cdy = seeds["crate_shift_m"]

    return {
        "seed": seed,
        "seat_id": int(n),
        # 진열 씨앗 둘. **자리는 안 바꾸고 물건만 바꾼다** -- 평가표가 "진열대 자체의 배치는
        # 달라지지 않음" 이라고 못 박고 있어서, 충돌 판정이 보는 발자국은 seed 를 타지 않는다.
        "store_seed": seeds["store_seed"],      # 곤돌라 12 개
        "shelf_seed": seeds["shelf_seed"],      # 목표 진열대
        "seat": seat,
        "robot": (float(rx), float(ry), float(ryaw)),
        # 바구니는 탁상 위에 놓이고, 긴 면이 로봇을 향하도록 좌석 각도만큼 돌아간다.
        "basket": {
            "pos": (float(bx + cdx), float(by + cdy), float(bz)),
            "yaw": math.radians(float(seat["seat_angle_deg"])),
            "shift": (float(cdx), float(cdy)),     # 기본 자리에서 옮긴 양 (m)
        },
        "goal": (float(gx), float(gy), float(gyaw)),
        "desk": (float(dx), float(dy), float(dz)),
        "drive_m": float(math.hypot(rx - gx, ry - gy)),
    }


def print_scene(scene):
    """장면을 사람이 읽을 수 있게 찍는다."""
    g = taskA_seats.geometry()
    s = scene["seat"]
    rx, ry, ryaw = scene["robot"]
    gx, gy, gyaw = scene["goal"]
    dx, dy, _dz = scene["desk"]
    bx, by, bz = scene["basket"]["pos"]
    tx, ty = s["table_xy"]

    print(f"\n[장면] seed {scene['seed']}, 좌석 {scene['seat_id']} "
          f"(탁상 {s['table_index']} 의 {s['seat_angle_deg']:.0f}도 자리)\n")

    print("  로봇 -- 좌석에서 앞으로 나와 탁상을 마주 본다")
    print(f"    자리      ({rx:+.3f}, {ry:+.3f})  yaw {math.degrees(ryaw):+.1f} 도")
    print(f"    탁상까지  중심에서 {math.hypot(rx - tx, ry - ty):.3f} m "
          f"(좌석은 {g['standoff']:.3f}, 여기서 {taskA_layout.SPAWN_FORWARD:.3f} 앞으로 나왔다)")
    print(f"    몸통      {taskA_layout.SPAWN_LIFT:+.4f}    "
          f"고개 {math.degrees(taskA_layout.SPAWN_HEAD_PITCH):.1f} 도 아래")

    print("\n  집을 것 -- 탁상 위 파란 바구니")
    print(f"    바구니    ({bx:+.3f}, {by:+.3f}, {bz:.3f})  "
          f"yaw {math.degrees(scene['basket']['yaw']):+.1f} 도")
    sx, sy = scene["basket"]["shift"]
    print(f"    옮김      좌석 기본 자리에서 ({sx * 1000:+.1f}, {sy * 1000:+.1f}) mm = "
          f"{math.hypot(sx, sy) * 1000:.1f} mm  (seed 가 정한다. 반경 "
          f"{taskA_scene_seed.CRATE_SHIFT_M * 1000:.0f} mm 안, 방향은 그대로)")
    print(f"    크기      {taskA_layout.BASKET_SIZE[0]:.3f} x "
          f"{taskA_layout.BASKET_SIZE[1]:.3f} x {taskA_layout.BASKET_SIZE[2]:.3f} m")
    print(f"    탁상      중심 ({tx:+.3f}, {ty:+.3f})  반지름 {g['table_radius']:.4f}  "
          f"상판 {g['table_top_z']:.4f}")

    print("\n  진열 -- 자리는 그대로고 물건만 이 seed 의 것으로 바뀐다")
    try:
        items = taskA_shelf_stock.stock(scene["shelf_seed"])
        gaps = taskA_shelf_stock.gaps(scene["shelf_seed"])
        print(f"    목표 진열대  씨앗 {scene['shelf_seed']}  상품 {len(items)}개, "
              f"빈 칸 {len(gaps)}곳 {gaps}")
    except SystemExit as exc:
        # 배포 이미지 밖에서 돌리면 과제 B 모듈이 없다. 장면의 나머지는 멀쩡하므로 멈추지
        # 않되, 조용히 넘어가지도 않는다.
        print(f"    목표 진열대  ! {exc}")
    d = taskA_store_dress.pick(scene["store_seed"])
    print(f"    기타 진열대  씨앗 {scene['store_seed']}  "
          + (f"곤돌라 12개 -> {os.path.basename(d)}" if d else
             "! 구워 둔 진열이 없다 (매장 USD 의 기본 진열로 간다)"))

    print("\n  가져갈 곳 -- 목적지 진열대와 그 옆 책상")
    print(f"    도착 자리 ({gx:+.3f}, {gy:+.3f})  yaw {math.degrees(gyaw):+.1f} 도")
    print(f"    책상      ({dx:+.3f}, {dy:+.3f})  상판 {taskA_layout.desk_top_z():.3f} m  "
          f"-- 도착 자리에서 {math.hypot(gx - dx, gy - dy):.3f} m")
    print(f"    직선거리  로봇에서 {scene['drive_m']:.3f} m "
          f"(실제 경로는 통로를 돌아가므로 이보다 길다)")

    print("\n  이 탁상의 스툴 -- 좌석 반대편으로 치워 둔다")
    for j, (sx, sy) in enumerate(s["stool_tidy_xy"]):
        print(f"    {j}: ({sx:+.3f}, {sy:+.3f})  로봇에서 {math.hypot(rx - sx, ry - sy):.3f} m")
    print(f"    회전 실측 기준 {taskA_seats.STOOL_MIN_ROBOT_DIST:.2f} m 이상 "
          f"-- 이보다 가까우면 베이스가 제자리 회전을 못 끝낸다\n")


def scene_json(scene):
    """`--scene-json` 으로 나가는 내용. 사람이 읽는 출력과 같은 값이다."""
    s = scene["seat"]
    rx, ry, ryaw = scene["robot"]
    gx, gy, gyaw = scene["goal"]
    return {
        "seed": scene["seed"],
        "seat_id": scene["seat_id"],
        "seat": {
            "table_index": s["table_index"],
            "seat_index": s["seat_index"],
            "seat_angle_deg": s["seat_angle_deg"],
            "table_xy": [round(v, 5) for v in s["table_xy"]],
            "stool_xy": [[round(a, 5), round(b, 5)] for a, b in s["stool_tidy_xy"]],
        },
        "robot": {"pos": [round(rx, 5), round(ry, 5)],
                  "yaw_deg": round(math.degrees(ryaw), 3),
                  "lift": taskA_layout.SPAWN_LIFT,
                  "head_pitch_deg": round(math.degrees(taskA_layout.SPAWN_HEAD_PITCH), 3)},
        "basket": {"pos": [round(v, 5) for v in scene["basket"]["pos"]],
                   "yaw_deg": round(math.degrees(scene["basket"]["yaw"]), 3),
                   # 좌석 기본 자리에서 옮긴 양. `pos` 에 이미 더해져 있다
                   "shift_mm": [round(v * 1000.0, 2) for v in scene["basket"]["shift"]],
                   "size": list(taskA_layout.BASKET_SIZE)},
        "goal": {"pos": [round(gx, 5), round(gy, 5)],
                 "yaw_deg": round(math.degrees(gyaw), 3)},
        "desk": {"pos": [round(v, 5) for v in scene["desk"]],
                 "top_z": taskA_layout.desk_top_z(),
                 "size": list(taskA_layout.DESK_SIZE)},
        "drive_straight_m": round(scene["drive_m"], 4),
        # 진열. **이 파일은 Isaac 을 띄우기 전에 쓰이므로 여기 적히는 것은 "세우라고 시킨
        # 자리" 이지 "내려앉은 뒤의 자리" 가 아니다.** 상품은 중력이 켜진 강체라 몇 mm
        # 내려앉는다. 채점은 상품을 보지 않으므로 문제가 되지 않지만, 적어 두지 않으면
        # 나중에 이 값을 실측과 비교하다가 틀린 결론을 낸다.
        "products": _products_json(scene),
    }


def _products_json(scene):
    """장면 JSON 의 진열 항목. 순수 산술 -- Isaac 없이 나온다."""
    out = {
        "note": "자리는 seed 를 타지 않는다. 바뀌는 것은 선반에 선 물건뿐이다",
        "target_shelf": {"seed": scene["shelf_seed"], "fixture": taskA_shelf_stock.SHELF_NAME},
        "other_shelves": {"seed": scene["store_seed"], "kind": "gondola"},
    }
    try:
        items = taskA_shelf_stock.stock(scene["shelf_seed"])
        out["target_shelf"]["count"] = len(items)
        out["target_shelf"]["gaps"] = [list(g) for g in taskA_shelf_stock.gaps(scene["shelf_seed"])]
        out["target_shelf"]["items"] = [
            {"prim": prim, "product": name, "pos": [round(v, 5) for v in pos]}
            for prim, name, pos, _q in items]
    except SystemExit as exc:
        out["target_shelf"]["error"] = str(exc)
    d = taskA_store_dress.pick(scene["store_seed"])
    out["other_shelves"]["variant"] = os.path.basename(d) if d else None
    out["other_shelves"]["variants_available"] = len(taskA_store_dress.variants())
    return out


# --check 는 여기서 끝난다. Isaac Sim 을 띄우지 않는다.
if args_cli.check:
    print("\n[검사] 12 좌석의 기하 -- Isaac Sim 없이\n")
    g = taskA_seats.geometry()
    for k, v in g.items():
        print(f"  {k:14s} {v:.4f}")
    print()
    gx, gy, _ = taskA_layout.goal_pose()
    for i, s in enumerate(taskA_seats.seats(stool_seed=args_cli.seed)):
        x, y, yaw = taskA_layout.spawn_robot_pose(s)
        print(f"  좌석 {i:2d}  탁상{s['table_index']} {s['seat_angle_deg']:5.1f}도  "
              f"로봇 ({x:7.3f}, {y:7.3f}) yaw {math.degrees(yaw):+7.1f}  "
              f"목적지까지 {math.hypot(x - gx, y - gy):6.3f} m")
    problems = taskA_seats.check(store_x=taskA_layout.STORE_X, store_y=taskA_layout.STORE_Y)

    # 바구니 **네 모서리**가 탁상 안에 있는가 -- seed 가 어느 쪽으로 20 mm 를 밀어도.
    #
    # `taskA_seats.check()` 는 바구니 **중심**만 본다. 중심이 탁상 안이어도 모서리는 나갈 수
    # 있고, 바구니는 탁상 끝까지 여유가 35.2 mm 뿐이다. 누가 `CRATE_SHIFT_M` 을 늘리거나
    # 바구니를 바꾸면 여기서 먼저 걸려야 한다 -- 시뮬레이터에서는 바구니가 떨어지는 것으로만 보인다.
    _R = g["table_radius"]
    _U, _V = taskA_layout.BASKET_SIZE[0], taskA_layout.BASKET_SIZE[1]   # 좌석 방향, 가로
    _sh = taskA_scene_seed.CRATE_SHIFT_M
    _base, _worst = 1e9, (1e9, None)
    for i, s in enumerate(taskA_seats.seats(stool_seed=args_cli.seed)):
        tx, ty = s["table_xy"]
        bx, by, _ = s["basket_xyz"]
        c, sn = math.cos(math.radians(s["seat_angle_deg"])), math.sin(math.radians(s["seat_angle_deg"]))

        def _clear(cx, cy):
            far = max(math.hypot(cx + c * u - sn * v - tx, cy + sn * u + c * v - ty)
                      for u in (-_U / 2, _U / 2) for v in (-_V / 2, _V / 2))
            return (_R - far) * 1000.0

        _base = min(_base, _clear(bx, by))
        for k in range(360):
            a = math.radians(k)
            m = _clear(bx + _sh * math.cos(a), by + _sh * math.sin(a))
            if m < _worst[0]:
                _worst = (m, i)
    print(f"\n  바구니 모서리에서 탁상 끝까지 -- 기본 자리 {_base:.1f} mm, "
          f"{_sh * 1000:.0f} mm 옮겼을 때 최악 {_worst[0]:.1f} mm (좌석 {_worst[1]})")
    if _worst[0] < 0.0:
        problems = problems + [f"바구니를 {_sh * 1000:.0f} mm 옮기면 모서리가 탁상 밖으로 "
                               f"{-_worst[0]:.1f} mm 나간다 (좌석 {_worst[1]})"]

    # 진열도 여기서 본다. `stock()`/`gaps()`/`pick()` 은 순수 산술이라 Isaac 없이 돈다 --
    # 진열이 비는 것은 시뮬레이터 60 초를 치르기 전에 알 수 있는 종류의 문제다.
    sp = taskA_scene_seed.spec(args_cli.seed)
    print(f"\n  진열 -- seed {args_cli.seed}")
    try:
        items = taskA_shelf_stock.stock(sp["shelf_seed"])
        print(f"    목표 진열대  씨앗 {sp['shelf_seed']}  상품 {len(items)}개, "
              f"빈 칸 {taskA_shelf_stock.gaps(sp['shelf_seed'])}")
        if not items:
            problems = problems + ["목표 진열대에 세울 상품이 하나도 없다"]
    except SystemExit as exc:
        print(f"    목표 진열대  ! {exc}")
        problems = problems + ["목표 진열대 진열 코드가 과제 B 모듈을 못 찾는다"]
    vs = taskA_store_dress.variants()
    d = taskA_store_dress.pick(sp["store_seed"])
    if d:
        print(f"    기타 진열대  씨앗 {sp['store_seed']}  변주 {len(vs)}벌 중 "
              f"{os.path.basename(d)}")
    else:
        print("    기타 진열대  ! 구워 둔 진열이 없다 (scripts/taskA/stores/)")
        problems = problems + ["구워 둔 기타 진열대 진열이 없다"]

    # 매장 USD 확인은 **판정을 찍기 전에** 한다. 뒤에 두면 USD 가 없을 때 "판정: 문제 없음"
    # 을 찍고 나서 오류가 따라오고 종료 코드만 조용히 1 이 된다 -- 판정 한 줄만 보는 사람은
    # 통과한 줄 안다.
    if os.path.isfile(taskA_layout.STORE_USD):
        print(f"\n  매장 USD: {taskA_layout.STORE_USD}")
    else:
        print(f"\n  ! 매장 USD 가 없다: {taskA_layout.STORE_USD}")
        problems = problems + ["store usd 없음"]

    print(f"\n  판정: {'문제 없음' if not problems else f'{len(problems)} 건'}")
    for p in problems:
        print(f"   ! {p}")
    print()
    raise SystemExit(1 if problems else 0)


SCENE = draw_scene(args_cli.seed, args_cli.seat)
print_scene(SCENE)

if args_cli.scene_json:
    with open(args_cli.scene_json, "w", encoding="utf-8") as fh:
        json.dump(scene_json(SCENE), fh, ensure_ascii=False, indent=2)
    print(f"[i] 장면을 {args_cli.scene_json} 에 적었다\n")

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import numpy as np                                                    # noqa: E402
import torch                                                          # noqa: E402
import omni.usd                                                       # noqa: E402
import isaaclab.sim as sim_utils                                      # noqa: E402
from isaaclab.assets import AssetBaseCfg, RigidObjectCfg              # noqa: E402
from isaaclab.scene import InteractiveScene, InteractiveSceneCfg      # noqa: E402
from isaaclab.utils import configclass                                # noqa: E402

from cyclo_lab.assets.robots.FFW_SG2 import (                         # noqa: E402
    FFW_SG2_MOBILE_CFG, SG2_SWERVE_STEERING_JOINTS, SG2_SWERVE_WHEEL_JOINTS,
)

# pxr / isaaclab 을 쓰는 셋은 여기서 읽는다 -- AppLauncher 앞에서 읽으면 Isaac Sim 이 뜨지 않는다.
taskA_colliders = _by_path("taskA_colliders", f"{_TASKA}/taskA_colliders.py")
taskA_stools = _by_path("taskA_stools", f"{_TASKA}/taskA_stools.py")
robot_pose = _by_path("taskA_robot_pose", f"{_TASKA}/taskA_robot_pose.py")

LEFT_JOINTS = [f"arm_l_joint{i + 1}" for i in range(7)]
RIGHT_JOINTS = [f"arm_r_joint{i + 1}" for i in range(7)]


@configclass
class World(InteractiveSceneCfg):
    """매장 전체, 바닥, 로봇, 탁상 위 바구니, 그리고 목적지 옆 책상.

    로봇에 달린 카메라 셋은 과제 B 데모와 같은 값이다 -- 정책이 받게 될 관측이 어떤
    화각인지 여기서 확인할 수 있다. 값은 이 저장소의 `scripts/FFW_SG2_REAL_cameras.py` 가
    유일한 출처다: head_cam 672x376 · 가로 85.0° (ZED Mini 왼눈), 손목 두 대 424x240 · 가로 87.0°
    (실기 ai_worker FFW-SG2 의 D405 그대로, camera_?_link 에 그대로 · 0.03~100 m, 2026-09-11).
    """

    # 매장 전체: 바닥, 벽, 집기 전부가 fixture_kit 이 조립해 둔 USD 하나에 들어 있다.
    # 물리가 적분할 것이 없으므로 AssetBaseCfg 다.
    store = AssetBaseCfg(
        prim_path="{ENV_REGEX_NS}/Store",
        spawn=sim_utils.UsdFileCfg(usd_path=taskA_layout.STORE_USD),
        init_state=AssetBaseCfg.InitialStateCfg(pos=(0.0, 0.0, 0.0)))

    # 로봇이 딛고 설 것.
    #
    # 매장 USD 도 바닥을 그리지만 그 콜라이더는 **꺼진 채로** 실려 온다 -- 손대지 않으면
    # 로봇은 z = -3.563 까지 떨어진다. 아래 harden() 이 그것을 켜는데, 바닥판의 윗면이
    # 정확히 z = 0 에 오도록 지어져 있으므로("its top surface sits 2 mm under its origin,
    # so lift it to meet z = 0" -- make_store.py) z = 0 의 평면은 그것과 싸우지 않고
    # 정확히 겹친다. 둘 다 두는 것은 벨트와 멜빵이다.
    ground = AssetBaseCfg(
        prim_path="/World/GroundPlane",
        spawn=sim_utils.GroundPlaneCfg(),
        init_state=AssetBaseCfg.InitialStateCfg(pos=(0.0, 0.0, 0.0)))

    light = AssetBaseCfg(
        prim_path="/World/Light",
        spawn=sim_utils.DomeLightCfg(intensity=2500.0, color=(1.0, 1.0, 1.0)))

    robot = FFW_SG2_MOBILE_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")

    head_cam = head_camera_cfg(
        update_period=1.0e9,
        data_types=["rgb"],
        update_latest_camera_pose=True,
    )
    cam_left_wrist = wrist_camera_cfg("left",
        update_period=1.0e9,
        data_types=["rgb"],
        update_latest_camera_pose=True,
    )
    cam_right_wrist = wrist_camera_cfg("right",
        update_period=1.0e9,
        data_types=["rgb"],
        update_latest_camera_pose=True,
    )

    def __post_init__(self):
        # 바구니. 집을 것이므로 강체다 -- 탁상 위에 놓이고, 상판 콜라이더가 받쳐 준다
        # (그 콜라이더도 harden() 이 켜는 것 중 하나다).
        self.basket = RigidObjectCfg(
            prim_path="{ENV_REGEX_NS}/Basket",
            spawn=sim_utils.UsdFileCfg(
                usd_path=taskA_layout.BASKET_USD,
                rigid_props=sim_utils.RigidBodyPropertiesCfg()),
            init_state=RigidObjectCfg.InitialStateCfg(
                pos=SCENE["basket"]["pos"], rot=_yaw_quat(SCENE["basket"]["yaw"])))
        # 책상은 kinematic -- 이 데모에서 로봇이 책상을 건드릴 일이 없고, 움직이면 장면
        # 기록과 어긋난다. 콜라이더는 살아 있어서 위에 물건을 놓을 수 있다.
        #
        # 장면에 책상은 **하나뿐**이다. 수집 때 쓰는 가짜 목적지 옆의 가짜 책상은 학습
        # 데이터를 만들기 위한 것이지 장면의 일부가 아니다.
        self.desk = AssetBaseCfg(
            prim_path="{ENV_REGEX_NS}/Desk",
            spawn=sim_utils.UsdFileCfg(
                usd_path=taskA_layout.DESK_USD,
                rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
                collision_props=sim_utils.CollisionPropertiesCfg()),
            init_state=AssetBaseCfg.InitialStateCfg(pos=SCENE["desk"], rot=(1.0, 0.0, 0.0, 0.0)))

        # 목표 진열대에 상품을 세운다. 상품마다 `RigidObjectCfg` 를 단다 -- `InteractiveScene`
        # 이 `cfg.__dict__` 를 훑으므로 `setattr` 은 필드로 선언한 것과 같고, 바구니·책상을
        # 바로 위에서 `self.` 로 다는 것과 같은 방식이다. 상품은 중력이 켜진 강체라 선반
        # 위에 내려앉는다.
        #
        # 이것이 없으면 목표 진열대가 **텅 빈 채로** 렌더된다. 매장 USD 는 곤돌라와 냉장고
        # 진열은 실어 오지만 그 진열대는 비워 두기 때문이다 -- 그 진열대는 과제 B 가 채우는
        # 대상이고, 과제 A 에서는 도착점의 표지다.
        n = taskA_shelf_stock.attach(self, SCENE["shelf_seed"],
                                     log=lambda *a: print("[i]", *a, flush=True))
        if n <= 0:
            raise SystemExit("목표 진열대에 상품을 하나도 못 세웠다 -- 진열이 비면 "
                             "USD 는 오류 없이 열리고 진열대만 텅 빈다. 조용히 넘기지 않는다.")


def main():
    sim = sim_utils.SimulationContext(
        sim_utils.SimulationCfg(dt=PHYSICS_DT, device=args_cli.device))
    scene = InteractiveScene(World(num_envs=1, env_spacing=8.0))

    # ---------------------------------------------------------------- sim.reset() 앞에서만
    #
    # 스테이지가 Fabric 으로 넘어가는 순간 렌더러는 USD 에 적힌 변환을 더 이상 따르지
    # 않는다 -- 2026-08-12 실측: 스툴 열둘에 최대 1.10 m 이동을 써 넣었고 하나도 움직이지
    # 않았다. 그래서 콜라이더도 스툴도 여기서 끝낸다.
    stage = omni.usd.get_context().get_stage()
    # 조명은 매장 씬이 들고 온 것을 그대로 쓴다 (2026-09-12). 씬의 Dome 850 · Key 1500 ·
    # 냉장고 RectLight 8개가 그대로 켜져 있고, 과제 B·C 도 그 조명으로 돈다. 돔이 둘이면
    # 화면이 하얗게 뜨므로 끄는 쪽은 우리 돔이다.
    ours = stage.GetPrimAtPath("/World/Light")
    if ours and ours.IsValid():
        ours.SetActive(False)
    print("[A] 매장   씬의 조명을 그대로 쓴다 (Dome 850 · Key 1500 · 냉장고) -- 우리 돔은 껐다", flush=True)

    # **`harden()` 앞이어야 한다.** 진열을 걸면 곤돌라 프림의 참조가 통째로 갈린다. harden 을
    # 먼저 하면 콜라이더 설정이 **이미 없어진 프림**에 붙고, 그러면 로봇이 진열대를 뚫고
    # 지나가는데 발자국을 비교하는 충돌 판정은 그것을 알아채지 못한다.
    taskA_store_dress.dress(stage, SCENE["store_seed"],
                            log=lambda *a: print("  ", *a, flush=True))

    taskA_colliders.harden(stage, log=lambda *a: None)
    # draw_scene() 과 **같은 stool_seed** 여야 한다. 여기서 다른 값을 쓰면 stools.place() 가
    # 놓는 자리와 SCENE 이 기록한 자리가 어긋나고, --scene-json 이 거짓말을 하게 된다.
    seats_all = taskA_seats.seats(stool_seed=args_cli.seed)
    stools = taskA_stools.Stools(stage, seats_all, log=lambda *a: None)
    stools.measure_home()
    stools.place(SCENE["seat"])
    # 이 좌석의 탁상이 아닌 나머지 두 탁상의 스툴도 제자리로. keep 은 **방금 놓은 좌석**이어야
    # 한다 -- 다른 좌석을 대면 방금 쓴 배치를 조용히 덮어쓴다(2026-08-18 에 그렇게 해서
    # 로봇이 스툴 안에 스폰됐다).
    stools.park_others(seats_all, SCENE["seat_id"])

    sim.reset()

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

    left_hold = torch.tensor([list(taskA_layout.spawn_arm_pos("l"))], device=sim.device)
    right_hold = torch.tensor([list(taskA_layout.spawn_arm_pos("r"))], device=sim.device)
    head_hold = torch.tensor([[taskA_layout.SPAWN_HEAD_PITCH,
                               taskA_layout.SPAWN_HEAD_YAW]], device=sim.device)
    lift_hold = torch.full((1, len(lift_ids)), taskA_layout.SPAWN_LIFT, device=sim.device)
    zero_grip = torch.zeros((1, len(grip_ids)), device=sim.device)
    zero_steer = torch.zeros((1, len(steer_ids)), device=sim.device)
    zero_wheel = torch.zeros((1, len(wheel_ids)), device=sim.device)

    step_count = [0]

    def hold(n, render=True):
        """n 걸음 동안 자세를 유지한다.

        바퀴 속도를 매 걸음 0 으로 눌러 준다 -- 마지막 속도 목표를 그대로 들고 있는
        바퀴는 계속 굴러간다.

        그림은 RENDER_EVERY 걸음에 한 번만 그린다. `render=False` 면 아예 안 그린다 --
        자세를 가라앉히는 동안에는 볼 사람이 없다.
        """
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

    # 화면이 없으면 장면을 세우는 동안에는 한 장도 그리지 않는다. 사진은 --shot 이
    # 필요한 순간에만 따로 그린다(아래). 편의점 한 장이 비싸서, 이 한 줄이 headless
    # 실행 시간의 대부분을 결정한다.
    settle_render = not args_cli.headless

    scene.update(PHYSICS_DT)
    origin = scene.env_origins[0]
    # 로봇이 스폰과 함께 갖는 자세와 높이. 이 뒤의 모든 배치가 이것을 재사용한다.
    spawn_quat, spawn_z = robot_pose.spawn_pose(robot, origin)

    def settle_on_ground():
        """로봇을 좌석 앞 제자리에, 바퀴를 바닥에 붙여 세운다.

        두 가지를 바로잡는다.

        1. **높이.** 로봇 USD 의 정지 자세는 가장 낮은 구동 바퀴를 0.3045 m 에 놓는다
           (실측 2026-08-12). 손대지 않으면 로봇은 218 mm 를 낙하한다 -- "스폰할 때
           위에서 떨어진다"가 그것이다. 그래서 실제 바퀴 높이를 재고 그 차이만큼 루트를
           내린다. 설정값을 218 mm 낮추는 것으로는 안 된다: 이 관절 구조에는 몸체 변환이
           어긋난 FixedJoint 가 있어 오프셋이 1:1 로 전달되지 않고, 그러면 차체가 무언가와
           겹쳐 PhysX 가 로봇을 1.34 m 로 던진다.

        2. **자리와 방향.** 낙하는 로봇을 옆으로도 밀어 놓는다(실측: x 가 -22.6 mm).
           이 데모는 환경을 보여 주는 것이므로 좌석이 말하는 자리에 똑바로 세운다.

        방향은 `robot_pose` 를 거친다. 좌석마다 yaw 가 다른데, yaw 쿼터니언을 새로 만들어
        씌우면 로봇이 눕는다 -- FFW-SG2 의 루트 링크는 항등 자세에서 서 있지 않다.
        """
        want = robot.data.default_joint_pos[0].clone()
        want[names.index("head_joint1")] = taskA_layout.SPAWN_HEAD_PITCH
        want[names.index("head_joint2")] = taskA_layout.SPAWN_HEAD_YAW
        want[names.index("lift_joint")] = taskA_layout.SPAWN_LIFT
        for j, q in zip(LEFT_JOINTS, taskA_layout.spawn_arm_pos("l")):
            want[names.index(j)] = q
        for j, q in zip(RIGHT_JOINTS, taskA_layout.spawn_arm_pos("r")):
            want[names.index(j)] = q
        robot.write_joint_state_to_sim(want.unsqueeze(0), torch.zeros_like(want).unsqueeze(0))
        scene.write_data_to_sim()

        rx, ry, ryaw = SCENE["robot"]
        z = spawn_z
        for _ in range(2):
            robot_pose.place(robot, origin, (rx, ry), ryaw, spawn_quat, z)
            scene.write_data_to_sim()
            hold(1, render=False)
            low = min(float(robot.data.body_pos_w[0, i][2]) for i in wheel_bodies)
            z -= low - WHEEL_RADIUS
        robot_pose.place(robot, origin, (rx, ry), ryaw, spawn_quat, z)
        scene.write_data_to_sim()
        return min(float(robot.data.body_pos_w[0, i][2]) for i in wheel_bodies)

    settle_on_ground()

    def _set_root(obj, pos, quat):
        st = obj.data.root_state_w[0].clone()
        st[:3] = torch.as_tensor(np.asarray(pos, dtype=np.float32), device=st.device) \
            + torch.as_tensor(np.asarray(origin.cpu(), dtype=np.float32), device=st.device)
        st[3:7] = torch.as_tensor(np.asarray(quat, dtype=np.float32), device=st.device)
        st[7:] = 0.0
        obj.write_root_state_to_sim(st.unsqueeze(0))

    def rewrite_props():
        """바구니를 제 좌표에 다시 적는다. 속도는 0 으로.

        순간이동으로 놓인 물체는 접촉을 찾느라 1~2 mm 씩 기어간다. 가라앉은 뒤 한 번 더
        적어야 장면이 '기록된 좌표 근처'가 아니라 '기록된 좌표'가 된다. 책상은 kinematic
        이라 움직이지 않으므로 다시 적을 것이 없다.
        """
        _set_root(scene["basket"], SCENE["basket"]["pos"], _yaw_quat(SCENE["basket"]["yaw"]))
        scene.write_data_to_sim()

    hold(int(1.5 / PHYSICS_DT), render=settle_render)
    rewrite_props()
    hold(int(0.5 / PHYSICS_DT), render=settle_render)

    x, y = float(robot.data.root_pos_w[0][0]), float(robot.data.root_pos_w[0][1])
    q = robot.data.root_quat_w[0]
    w, qx, qy, qz = (float(v) for v in q)
    yaw = math.degrees(math.atan2(2.0 * (w * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz)))
    low = min(float(robot.data.body_pos_w[0, i][2]) for i in wheel_bodies)
    bpos = scene["basket"].data.root_pos_w[0]
    gx, gy, _gyaw = SCENE["goal"]

    print(f"[i] 좌석 {SCENE['seat_id']} -- 탁상 {SCENE['seat']['table_index']} 의 "
          f"{SCENE['seat']['seat_angle_deg']:.0f}도 자리", flush=True)
    print(f"[i] 로봇 시작 자세  x {x:+.4f}  y {y:+.4f}  yaw {yaw:+.2f} deg"
          f"  몸통 {float(robot.data.joint_pos[0, lift_ids[0]]):+.4f}", flush=True)
    gap_mm = (low - WHEEL_RADIUS) * 1000.0
    print(f"[i] 가장 낮은 바퀴 중심 {low:.4f} m, 반지름 {WHEEL_RADIUS:.4f} "
          f"-> 바닥과 {gap_mm:+.1f} mm. "
          f"{'닿아 있다' if abs(gap_mm) < 10.0 else '!! 떠 있거나 뚫었다 -- 장면이 잘못 섰다'}",
          flush=True)
    robot_pose.assert_upright(robot, log=lambda m: print(f"[i] {m}", flush=True))
    print(f"[i] 바구니  ({float(bpos[0]):+.4f}, {float(bpos[1]):+.4f}, {float(bpos[2]):.4f}) "
          f"-- 탁상 상판 {taskA_seats.geometry()['table_top_z']:.4f} 위에 놓여 있다", flush=True)
    print(f"[i] 목적지까지 직선 {math.hypot(x - gx, y - gy):.3f} m", flush=True)
    print("[i] 장면이 섰다. 여기서 과제 A 가 시작한다.\n", flush=True)

    if args_cli.shot:
        cam = scene["head_cam"]
        # 물리를 건드리지 않고 그림만 여러 장 그린다.
        #
        # 두 가지를 한꺼번에 해결한다. 하나는 headless 에서 settle_render 가 꺼져 있어
        # 렌더러가 프레임을 한 장도 만든 적이 없는 경우 -- 그러면 카메라가 가져올 것이
        # 없다. 다른 하나는 **거친 그림**이다: 이 렌더러는 프레임을 시간적으로 누적해서
        # 잡티를 지우므로, 두어 장만 그리고 찍으면 눈에 띄게 지글거린다(2026-08-25 실측,
        # 2 장과 16 장을 나란히 놓고 확인). 장면은 멈춰 있으니 누적이 흐려질 것도 없다.
        for _ in range(SHOT_WARMUP):
            sim.render()
        # 카메라는 update_period 가 커서 스스로 갱신하지 않는다. 한 장을 원하면 낡았다고
        # 표시하고 강제로 다시 그리게 한다.
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
