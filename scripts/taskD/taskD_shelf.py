# Copyright 2025.
#
# 태스크 D 가 쓰는 3 단 선반의 기하와 스폰 설정.
#
# 받은 `Shelf.zip` 의 `shelf_v02.usd` 를 요구 치수로 다시 구운 것이다. 굽는 스크립트와
# 굽는 과정에서 밟은 함정은 `source/cyclo_lab/data/Shelf_taskD/build_taskD_shelf.py` 에 있다.
#
# **판은 맨 위 한 장뿐이다.** 1·2 단 판은 2026-10-12 에 사용자 요청으로 스테이지에서
# 지웠고, 그 두 단은 지지대만 남는다. 숨기지 않고 지운 이유: 숨긴 메시의 콜라이더는 살아
# 있어서 상품이 보이지 않는 판 위에 선다 -- 눈으로는 공중부양이고 로그로는 정상이다.
#
# 과제 B 선반과 달리 **앞막이 턱이 없다.** 판이 평평해서 손이 넘어야 할 것이 없고,
# `LIP_TOPS` 를 두면 거짓이 된다. 일부러 정의하지 않았다.
#
# 치수의 정본은 `taskD_measured.json` 이고 이 파일은 그것을 읽는다. 경로는
# `taskD_layout.shelf_usd()` 가 푼다 -- 배포 이미지와 개발 체크아웃의 에셋 트리가 다르다.
#
# isaaclab 은 **함수 안에서만** import 한다. 모듈 스코프에서 끌어오면 `SimulationApp` 보다
# 먼저 들어와 Isaac Sim 이 아예 뜨지 않고, `--check` 도 못 돈다.

import taskD_layout as _L

SIZE = _L.SHELF_SIZE                 # 가로, 깊이, 높이 (m)
FRONT_X = _L.SHELF_FRONT_X           # 앞면의 월드 x
BOARD_TOPS = _L.BOARD_TOPS           # 세 판의 윗면. **0 과 1 은 지워진 판이다**
APRON_BOTTOMS = tuple(_L.MEASURED["shelf"]["apron_bottoms"])
BOARD_THICKNESS = float(_L.MEASURED["shelf"]["board_thickness"])
CLEAR_HEIGHTS = tuple(_L.MEASURED["shelf"]["clear_heights"])

# 로봇이 채우는 단, 그리고 배경으로만 채우는 단. 판이 하나뿐이라 (2,) 와 () 다.
LAYERS = tuple(_L.MEASURED["shelf"]["layers"])
SCENERY_LAYERS = tuple(_L.MEASURED["shelf"]["scenery_layers"])

# 구운 스테이지는 자기 원점을 중심으로 한다: x 는 가로 +-0.450, y 는 깊이 +-0.200, z 는
# 바닥이 0. Z 축 +90 도는 로컬 +y 를 월드 -X 로 보내므로, 매장 선반들과 같은 방향이 된다.
FACE_MINUS_X = (0.70710678, 0.0, 0.0, 0.70710678)
FRONT_Y_LOCAL = SIZE[1] / 2.0        # 중심이 원점이므로 앞면은 깊이의 절반


def usd():
    """선반 USD 경로. 배포 이미지 > 개발 체크아웃 순으로 푼다."""
    return _L.shelf_usd()


def pos(front_x=None, y=0.0, z=0.0):
    """앞면을 `front_x` 에 두고 -X 를 보게 세울 때의 프림 위치."""
    fx = FRONT_X if front_x is None else front_x
    return (fx + FRONT_Y_LOCAL, y, z)


def cfg(front_x=None, y=0.0, prim_path="{ENV_REGEX_NS}/Shelf"):
    """선반 하나. 정적이고, 삼각메시 콜라이더는 스테이지에 구워져 있다.

    `AssetBaseCfg` 인 이유 둘: 선반은 정물이고, PhysX 는 삼각메시 콜라이더를 움직이는
    바디에 허용하지 않는다.
    """
    import isaaclab.sim as sim_utils
    from isaaclab.assets import AssetBaseCfg

    return AssetBaseCfg(
        prim_path=prim_path,
        init_state=AssetBaseCfg.InitialStateCfg(pos=pos(front_x, y), rot=FACE_MINUS_X),
        spawn=sim_utils.UsdFileCfg(
            usd_path=usd(),
            collision_props=sim_utils.CollisionPropertiesCfg(collision_enabled=True),
        ),
    )


def problems():
    """`--check` 가 보는 것. 어긋난 것들의 설명 목록 (비어 있으면 정상)."""
    out = []
    if len(BOARD_TOPS) != 3:
        out.append("판 윗면이 3 개가 아니다: %r" % (BOARD_TOPS,))
    if LAYERS != (2,):
        out.append("일감 단이 (2,) 가 아니다: %r -- 판이 맨 위 하나뿐이다" % (LAYERS,))
    if SCENERY_LAYERS:
        out.append("배경 단이 비어 있지 않다: %r -- 채울 판이 없다" % (SCENERY_LAYERS,))
    for i, (top, bot) in enumerate(zip(BOARD_TOPS, APRON_BOTTOMS)):
        if not bot < top:
            out.append("%d 단 지지대 아랫면 %.3f 가 판 윗면 %.3f 보다 높다" % (i, bot, top))
    # 사용자가 지정한 두 간격을 다시 센다. 1 단 판 윗면 -> 2 단 지지대 시작 = 300,
    # 2 단 판 윗면 -> 3 단 지지대 시작 = 247.
    for i, want in ((0, 0.300), (1, 0.247)):
        got = APRON_BOTTOMS[i + 1] - BOARD_TOPS[i]
        if abs(got - want) > 1e-6:
            out.append("%d 단 판 윗면에서 %d 단 지지대까지 %.1f mm, 지정은 %.0f mm"
                       % (i + 1, i + 2, got * 1000.0, want * 1000.0))
    return out


def main():
    print("선반 %s m   앞면 x %.3f   판 윗면 %s" % (SIZE, FRONT_X, BOARD_TOPS))
    print("지지대 아랫면 %s   판 두께 %.3f   유효 높이 %s"
          % (APRON_BOTTOMS, BOARD_THICKNESS, CLEAR_HEIGHTS))
    print("일감 단 %s   배경 단 %s" % (LAYERS, SCENERY_LAYERS))
    print("USD %s" % usd())
    p = problems()
    print("판정: %s" % ("문제 없음" if not p else "%d 건" % len(p)))
    for s in p:
        print("  ! %s" % s)


if __name__ == "__main__":
    main()
