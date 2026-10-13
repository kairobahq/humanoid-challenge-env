# Copyright 2025.
#
# 태스크 D 의 **자리**와 **에셋 경로**. seed 와 무관한 것은 전부 여기 있다.
#
# seed 가 바꾸는 것은 선반 위에 선 물건, 크레이트에 든 물건, 주변 기물뿐이다
# (`taskD_scene_seed.py`). 로봇·책상·크레이트·선반이 **어디 서는지는 seed 와 무관하고**,
# 그래서 충돌 판정이 보는 발자국도 seed 와 무관하다. 그 숫자가 이 파일이다.
#
# 숫자마다 근거는 `taskD_measured.json` 의 `note` 에 있다. 여기서는 그 JSON 을 읽어
# 상수로 꺼내 놓기만 한다 -- 같은 숫자를 코드와 JSON 두 곳에 적으면 갈라진다.
#
# isaaclab 도 numpy 도 pxr 도 안 쓴다. `task_d_demo.py --check` 가 Isaac Sim 없이 1 초에
# 도는 것은 이 파일과 `taskD_scene_seed.py` 가 순수 파이썬이기 때문이다.
#
# 혼자 돌려 볼 수 있다:
#     python3 scripts/taskD/taskD_layout.py

import json as _json
import os as _os

_HERE = _os.path.dirname(_os.path.abspath(__file__))

with open(_os.path.join(_HERE, "taskD_measured.json"), encoding="utf-8") as _f:
    MEASURED = _json.load(_f)


# ---------------------------------------------------------------- 에셋 경로
#
# **배포 이미지와 개발 체크아웃의 에셋 트리가 다르다.**
#
#     배포 이미지   $CYCLOLAB_PATH/source/cyclo_lab/data -> /workspace/assets 심볼릭 링크
#                  fixtures/table/table.usd,  fixtures/crate/crate.usd
#     개발 체크아웃  <cstore-challenge>/source/cyclo_lab/data
#                  Table/Table.usd,  Crate/blue_box.usd
#
# 그래서 경로를 한 줄로 적을 수 없다. 우선순위는 과제 C 의 `taskC_products.assets_root()` 와
# 같다: **환경변수 > 배포 이미지 > 개발 체크아웃**, 그리고 **하나도 없으면 첫 후보를
# 그대로 돌려준다** -- 여기서 터뜨리는 대신 스폰 시점에 경로가 찍힌 오류로 드러나게 한다.
# `--check` 는 이 세 경로의 존재를 따로 확인한다.
#
# 마운트되는 레포라 패키지 상대경로(`dirname(__file__)/../..`)는 쓸 수 없다. 이 파일이
# 배포 꾸러미 안으로 들어가면 그 상대경로는 레포 뿌리가 아니라 `scripts/` 를 가리킨다.
_CYCLOLAB = _os.environ.get("CYCLOLAB_PATH", "/workspace/cyclo_lab")
_IMAGE_DATA = _os.path.join(_CYCLOLAB, "source", "cyclo_lab", "data")

# 개발 체크아웃(cstore-challenge)의 에셋 자리.
#
# **깊이를 고정으로 가정하지 않고 위로 올라가며 찾는다.** 이 파일이 cstore 안에서는
# `<뿌리>/Task-D/challenge/scripts/taskD/`(네 단 위), 배포 꾸러미에서는
# `<뿌리>/scripts/taskD/`(두 단 위)에 있어서, 고정 단수를 적으면 한쪽에서 반드시 틀린다.
# 실제로 `..` 를 네 번 적어 두었다가 꾸러미 자리에서 `/home/source/cyclo_lab/data` 라는
# 엉뚱한 경로가 나왔다 (2026-10-13). 없으면 `None` 이고, 그때는 이미지 경로만 쓴다.
def _find_dev_data(start):
    d = start
    for _ in range(8):
        cand = _os.path.join(d, "source", "cyclo_lab", "data")
        if _os.path.isdir(cand):
            return cand
        parent = _os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


_DEV_DATA = _find_dev_data(_HERE)


def assets_root():
    """에셋 뿌리. 우선순위: TASKD_ASSETS > 배포 이미지 > 개발 체크아웃."""
    env = _os.environ.get("TASKD_ASSETS")
    if env:
        return env
    if _os.path.isdir(_IMAGE_DATA):
        return _IMAGE_DATA
    return _DEV_DATA or _IMAGE_DATA


def _pick(*rel):
    """후보 상대경로를 차례로 보고 **있는 것**을 돌려준다. 없으면 첫 후보."""
    root = assets_root()
    cands = [_os.path.join(root, r) for r in rel]
    for c in cands:
        if _os.path.isfile(c):
            return c
    return cands[0]


# 선반 USD 를 **이 폴더 옆에 같이 커밋해 두었다** (`scripts/taskD/shelf/`, 610 KB).
#
# 이 레포의 원칙은 「코드는 레포, 에셋은 이미지」이고 책상·크레이트·상품은 전부 릴리스
# 오버레이(`challenge-overlay.tar.gz`)로 간다. 태스크 D 의 선반만 아직 그 오버레이에 없어서,
# 넣어 줄 사람이 생길 때까지 **꾸러미가 스스로 돌 수 있게** 사본을 들고 있는다. 이 레포는
# 이미 640 KB `demo_01.npz` 같은 바이너리를 커밋해 두었으므로 전례도 있다.
#
# **후보 순서가 그 임시성을 처리한다.** 오버레이에 들어가는 날 아무것도 고칠 필요가 없다 --
# 1 번이 생기면 자동으로 그쪽을 쓰고, 2 번(이 사본)은 한 커밋으로 지우면 된다.
_REPO_SHELF = _os.path.join(_HERE, "shelf", "shelf_taskD.usd")


def shelf_usd():
    """태스크 D 의 3 단 선반. 후보 셋을 순서대로 본다.

        1) <에셋 뿌리>/fixtures/shelf_taskD/shelf_taskD.usd   오버레이에 들어가면 여기가 이긴다
        2) <이 모듈 옆>/shelf/shelf_taskD.usd                  지금 레포가 들고 있는 사본
        3) <개발 체크아웃>/Shelf_taskD/shelf_taskD.usd          cstore-challenge 쪽
    """
    image = _os.path.join(assets_root(), "fixtures", "shelf_taskD", "shelf_taskD.usd")
    dev = _os.path.join(assets_root(), "Shelf_taskD", "shelf_taskD.usd")
    for c in (image, _REPO_SHELF, dev):
        if _os.path.isfile(c):
            return c
    return image


def table_usd():
    """검정 접이식 책상. 과제 A·B 가 쓰는 것과 같은 자산."""
    return _pick(_os.path.join("fixtures", "table", "table.usd"),
                 _os.path.join("Table", "Table.usd"))


def crate_usd():
    """파란 크레이트. 과제 B 가 쓰는 것과 같은 자산."""
    return _pick(_os.path.join("fixtures", "crate", "crate.usd"),
                 _os.path.join("Crate", "blue_box.usd"))


def usds():
    """{이름: 경로} 셋. `--check` 가 존재를 확인하는 대상이 이 셋이다.

    선반만 후보가 셋이다 -- `shelf_usd()` 의 주석 참조.
    """
    return {"shelf": shelf_usd(), "table": table_usd(), "crate": crate_usd()}


# ---------------------------------------------------------------- 자리
#
# 전부 `taskD_measured.json` 에서 읽는다. 근거는 그 파일의 `note` 에 있다.
_R = MEASURED["robot"]
_T = MEASURED["table"]
_C = MEASURED["crate"]
_S = MEASURED["shelf"]

ROBOT_POS = tuple(_R["pos"])                 # (x, y, z). z 는 0 으로 둔다 -- 아래 note 참조
ROBOT_FOOT = tuple(_R["footprint"])          # 로봇 바닥 발자국 (x0, x1, y0, y1), 로봇 기준
CHASSIS_FRONT = float(_R["chassis_front"])   # 섀시 앞면이 기준점에서 얼마나 앞인가

TABLE_POS = tuple(_T["pos"])
TABLE_YAW_DEG = float(_T["yaw_deg"])
TABLE_SIZE = tuple(_T["size"])
TABLE_TOP = TABLE_POS[2] + TABLE_SIZE[2]

CRATE_POS = tuple(_C["pos"])
CRATE_ROT_DEG = tuple(_C["rot_deg"])
CRATE_SIZE = tuple(_C["size"])
CRATE_FLOOR_Z = CRATE_POS[2] + float(_C["floor"])   # 크레이트 안쪽 바닥의 월드 높이
CRATE_RIM_Z = CRATE_POS[2] + CRATE_SIZE[2]

SHELF_FRONT_X = float(_S["front_x"])         # 선반 앞면의 월드 x
SHELF_Y = float(_S["y"])
SHELF_SIZE = tuple(_S["size"])
BOARD_TOPS = tuple(_S["board_tops"])

# 섀시 앞면에서 선반 앞면까지. 로봇을 뒤로 물릴수록 커진다.
SHELF_GAP = round(SHELF_FRONT_X - (ROBOT_POS[0] + CHASSIS_FRONT), 4)


def box(name):
    """작업물 하나의 평면 상자 (x0, x1, y0, y1). 배경 기물이 피해야 하는 것들."""
    if name == "robot":
        return (ROBOT_POS[0] + ROBOT_FOOT[0], ROBOT_POS[0] + ROBOT_FOOT[1],
                ROBOT_POS[1] + ROBOT_FOOT[2], ROBOT_POS[1] + ROBOT_FOOT[3])
    if name == "table":
        return (TABLE_POS[0] - TABLE_SIZE[0] / 2.0, TABLE_POS[0] + TABLE_SIZE[0] / 2.0,
                TABLE_POS[1] - TABLE_SIZE[1] / 2.0, TABLE_POS[1] + TABLE_SIZE[1] / 2.0)
    if name == "crate":
        # yaw 90 이면 긴 쪽(0.590)이 월드 x 로, 짧은 쪽(0.380)이 y 로 간다.
        w, d = (CRATE_SIZE[1], CRATE_SIZE[0]) if round(CRATE_ROT_DEG[2]) % 180 else \
               (CRATE_SIZE[0], CRATE_SIZE[1])
        return (CRATE_POS[0] - w / 2.0, CRATE_POS[0] + w / 2.0,
                CRATE_POS[1] - d / 2.0, CRATE_POS[1] + d / 2.0)
    if name == "shelf":
        return (SHELF_FRONT_X, SHELF_FRONT_X + SHELF_SIZE[1],
                SHELF_Y - SHELF_SIZE[0] / 2.0, SHELF_Y + SHELF_SIZE[0] / 2.0)
    raise KeyError(name)


WORK_OBJECTS = ("robot", "table", "crate", "shelf")


def work_boxes():
    """{이름: 상자}. 충돌 금지 검사가 쓰는 네 개 전부."""
    return {n: box(n) for n in WORK_OBJECTS}


def main():
    print("에셋 뿌리 %s" % assets_root())
    for name, path in usds().items():
        print("  %-6s %s  %s" % (name, "있음" if _os.path.isfile(path) else "없음 ", path))
    print()
    print("로봇  %s   섀시 앞면 %+.3f   선반까지 %.0f mm"
          % (ROBOT_POS, ROBOT_POS[0] + CHASSIS_FRONT, SHELF_GAP * 1000.0))
    print("책상  %s   yaw %+.0f   %s" % (TABLE_POS, TABLE_YAW_DEG, TABLE_SIZE))
    print("크레이트 %s  rot %s  안쪽 바닥 %.4f  림 %.4f"
          % (CRATE_POS, CRATE_ROT_DEG, CRATE_FLOOR_Z, CRATE_RIM_Z))
    print("선반  앞면 x %.3f   판 윗면 %s" % (SHELF_FRONT_X, BOARD_TOPS))
    print()
    print("작업물 상자 (배경 기물 금지 구역의 재료):")
    for n, b in work_boxes().items():
        print("  %-6s x %+.3f..%+.3f   y %+.3f..%+.3f" % (n, b[0], b[1], b[2], b[3]))


if __name__ == "__main__":
    main()
