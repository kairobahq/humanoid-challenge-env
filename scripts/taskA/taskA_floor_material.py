# 배포용 정본 -- 대회 환경 저장소 `Task-A/sim/floor_material.py` 에서 옮겼다.
# 배포 이미지에는 `Task-A/` 도, 재질 값을 둔 `cyclo_lab/assets/ground.py` 도 없으므로 두 가지만 바꿨다:
# 재질 값(`GROUND_MATERIAL`)을 그 파일에서 그대로 옮겨 적었고, 매장 경로를 `taskA_colliders.STORE_PATH` 와
# 같은 값으로 적었다. 나머지는 원본 그대로다.
#
# 이 파일이 없으면 안 되는 이유는 바닥이다: 원본 기록(집기·주행·놓기)은 전부 **매장 바닥 콜라이더에
# 컴플라이언트 재질을 붙인 바닥**에서 모았다. 로봇은 z = 0 의 지면판이 아니라 `taskA_colliders.harden()`
# 이 켠 매장 바닥(그보다 2 mm 위)을 탄다.
# ---------------------------------------------------------------------------------------------

# Copyright 2025.
#
# 로봇이 **실제로 타는 면**에 물리 재질을 붙인다.
#
# 동료분이 2026-08-25 에 주행용 바닥을 확정했다 -- 후보를 한 세션에 나란히 세워 굴려 보고
# (`floor_shake_bench.py`), 마찰·결합모드·콜라이더 오프셋·바퀴 근사가 전부 노이즈 안이며
# **컴플라이언트 접촉만 듣는다**는 결론이다 (롤/피치 RMS 0.0519 -> 0.0400, 바퀴 리플 0.675 -> 0.116).
#
# 우리 씬에서 로봇은 GroundPlane 을 타지 않는다:
#
#     z = +0.002000   매장 충돌 바닥     부딪힘 O   보임 X   <- 로봇이 실제로 타는 면
#     z = +0.000245   매장 보이는 바닥   부딪힘 X   보임 O
#     z =  0.000000   GroundPlane       부딪힘 O   보임 X
#
# 둘 다 있으면 **높은 쪽**을 탄다. 그러므로 GroundPlane 에만 재질을 붙이면 접촉이 그것을
# 한 번도 안 거친다.
#
# `harden()` 은 바닥 콜라이더를 켜고 근사만 정할 뿐 **재질은 안 붙인다**. 그래서 매장 바닥은
# PhysX 기본 재질이다. 이 파일은 `harden()` 뒤에 불러서 그 바닥 프림들에 재질을 바인딩한다.
from pxr import Usd, UsdPhysics

STORE_PATH = "/World/envs/env_0/Store"
_MAT_PATH = "/World/Materials/driveFloorMat"


def _ground_material():
    """`cyclo_lab/assets/ground.py` 의 `GROUND_MATERIAL` 과 같은 값."""
    from isaaclab.sim import RigidBodyMaterialCfg

    return RigidBodyMaterialCfg(
        static_friction=0.8,
        dynamic_friction=0.7,
        restitution=0.0,
        compliant_contact_stiffness=1e5,
        compliant_contact_damping=1e3,
    )


def bind_store_floor(stage, log=print, store_path: str = STORE_PATH) -> dict:
    """매장 바닥 콜라이더에 주행용 재질을 붙인다.

    돌려주는 값은 무엇을 실제로 했는지에 대한 것이고, **아무것도 못 찾으면 그것을 그대로
    말한다.**  조용히 0 을 돌려주면 호출자는 재질이 붙은 줄 알고 넘어간다.
    """
    from isaaclab.sim.utils import bind_physics_material

    material = _ground_material()
    material.func(_MAT_PATH, material)

    root = stage.GetPrimAtPath(store_path)
    if not root or not root.IsValid():
        log(f"[FLOORMAT] 매장 프림이 없다: {store_path} -- 아무것도 안 붙였다")
        return {"floor_prims": 0, "found_floor": False}

    bound = 0
    found = False
    for child in root.GetChildren():
        if child.GetName() != "Floor":
            continue
        found = True
        for p in Usd.PrimRange(child):
            if not p.HasAPI(UsdPhysics.CollisionAPI):
                continue
            bind_physics_material(str(p.GetPath()), _MAT_PATH)
            bound += 1

    if not found:
        log(f"[FLOORMAT] {store_path} 아래에 Floor 가 없다 -- 아무것도 안 붙였다")
    elif bound == 0:
        log("[FLOORMAT] 매장 바닥에 켜진 콜라이더가 없다 -- 로봇은 GroundPlane 을 탄다")
    else:
        log(f"[FLOORMAT] 매장 바닥 콜라이더 {bound}개에 주행용 재질을 붙였다 "
            f"(강성 {material.compliant_contact_stiffness:g} / 감쇠 {material.compliant_contact_damping:g})")
    return {"floor_prims": bound, "found_floor": found}
