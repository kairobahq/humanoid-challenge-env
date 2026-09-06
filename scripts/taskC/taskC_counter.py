# Copyright 2026.
#
# 계산대 위의 장면 손질 -- Isaac 이 뜬 뒤에만 쓸 수 있는 것들.
#
#   draw_band                 상품이 놓이는 빨간 띠를 상판에 테이프 한 줄로 그린다. 시각 전용
#                             (콜라이더 없음). 수집 파이프라인의 `taskC/tape.py::draw_rect` 와
#                             같은 방식·같은 두께 -- 학습 데이터에 찍힌 띠와 참가자가 보는 띠가
#                             같아야 한다.
#   deactivate_duplicates     구워진 매장 USD 에 놓여 있는 정적 스캐너 소품과 계산대 옆 바구니를
#                             끈다. 과제 C 는 스캐너를 로봇이 드는 강체로 따로 스폰하므로, 끄지 않으면
#                             장면에 스캐너가 둘이 된다. 바구니는 수집 파이프라인이 끄고 찍었으므로
#                             (V4-235) 여기서도 끈다. USD 를 고치지 않고 스테이지에서만 비활성화한다.
#   remove_low_shelf          계산대 직원 쪽 맨 아래 선반판(바닥 위 0.104~0.138 m)을 메시에서
#                             잘라낸다. 로봇이 계산대 앞에 바짝 설 때 섀시가 이 판에 올라타
#                             기울어지므로, 수집 파이프라인(taskC/counter_edit.py)과 같은 방식으로
#                             면 단위로 지운다. InteractiveScene 이 prim 을 만든 뒤, sim.reset()
#                             이 콜라이더를 굽기 **전에** 불러야 한다.
#
# 이 파일은 pxr 과 isaaclab 을 쓴다. 데모가 AppLauncher **뒤에서** 읽는다.

import isaaclab.sim as sim_utils

from . import taskC_layout as L


def _strips(x0, x1, y0, y1, w):
    """사각형 테두리를 테이프 폭 w 의 막대 넷으로. (cx, cy, lx, ly) 세계 좌표."""
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    lx, ly = (x1 - x0), (y1 - y0)
    return [
        (cx, y0 + w / 2.0, lx, w),          # 아래
        (cx, y1 - w / 2.0, lx, w),          # 위
        (x0 + w / 2.0, cy, w, ly),          # 왼쪽
        (x1 - w / 2.0, cy, w, ly),          # 오른쪽
    ]


def band_world_rect():
    """로봇 좌표의 띠 [x0,x1]x[y0,y1] 를 세계 좌표 축정렬 사각형 (x0, x1, y0, y1) 으로."""
    a = L.robot_to_world((L.BAND["x0"], L.BAND["y0"]))
    b = L.robot_to_world((L.BAND["x1"], L.BAND["y1"]))
    return (min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1]))


def draw_band(env_prim="/World/envs/env_0", name="band", z_lift=0.0006, log=print):
    """빨간 띠를 상판 위에 그린다. sim.reset() 뒤에 부른다 (장면 장식이지 물리 물체가 아니다)."""
    x0, x1, y0, y1 = band_world_rect()
    for k, (cx, cy, lx, ly) in enumerate(_strips(x0, x1, y0, y1, L.TAPE_W)):
        cfg = sim_utils.CuboidCfg(
            size=(float(lx), float(ly), float(L.TAPE_T)),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=L.TAPE_COLOR, roughness=0.9))
        cfg.func(f"{env_prim}/Tape_{name}_{k}", cfg,
                 translation=(float(cx), float(cy), float(L.COUNTER_TOP_Z + L.TAPE_T / 2.0 + z_lift)))
    log(f"[TAPE] {name}  세계 x[{x0:.3f},{x1:.3f}]  y[{y0:.3f},{y1:.3f}]  "
        f"{(x1 - x0) * 100:.0f}(x) x {(y1 - y0) * 100:.0f}(y) cm, 테이프 {L.TAPE_W * 1000:.0f} mm")


def deactivate_duplicates(stage, store_prim="/World/envs/env_0/Store", log=print):
    """매장 USD 안의 정적 스캐너와 바구니 prim 을 끈다. 끈 prim 수를 돌려준다. sim.reset() 앞에서 부른다.

    계산대(cash_table)는 끄지 않는다 -- 이 데모는 매장에 구워진 계산대를 그대로 쓴다.
    """
    root = stage.GetPrimAtPath(store_prim)
    if not root or not root.IsValid():
        log(f"[STORE] {store_prim} 가 없다 -- 중복 집기 비활성화 건너뜀")
        return 0
    n = 0
    from pxr import Usd
    for prim in Usd.PrimRange(root):
        if not prim.IsActive():
            continue
        nm = prim.GetName().lower()
        if prim.GetParent().GetName() != root.GetName():
            continue                     # 매장 바로 아래 집기만 본다 (안쪽 링크 이름은 건드리지 않는다)
        if "scanner" in nm or "big_basket" in nm or nm.endswith("basket"):
            prim.SetActive(False)
            n += 1
            log(f"[STORE] 비활성화: {prim.GetPath()}")
    return n


BOARD_Z = (0.09, 0.15)          # 실측 0.104..0.138 m 판, 양쪽으로 조금 여유
COUNTER_MESHES = ("MainTable_link/visuals/MainTable",
                  "MainTable_link/collisions/MainTable_link_col_0")


def remove_low_shelf(stage, counter_prim="/World/envs/env_0/Store/Fix_cash_table",
                     z_band=BOARD_Z, log=print):
    """계산대 맨 아래 선반판의 면을 지운다. 메시별로 지운 면 수를 돌려준다.

    선반은 MainTable 메시 안의 기하이지 prim 이 아니라서 끌 수 없고 잘라내야 한다. 면 전체가
    z 띠 안에 있을 때만 판으로 본다 -- 띠를 가로지르는 면은 옆 판이라 지우면 구멍이 난다.
    """
    import numpy as np
    from pxr import Usd, UsdGeom

    out = {}
    for rel in COUNTER_MESHES:
        prim = stage.GetPrimAtPath(f"{counter_prim}/{rel}")
        if not prim or not prim.IsValid():
            log(f"[EDIT] {rel}: 없음 -- 건너뜀")
            continue
        mesh = UsdGeom.Mesh(prim)
        pts = np.asarray(mesh.GetPointsAttr().Get(), dtype=np.float64)
        idx = np.asarray(mesh.GetFaceVertexIndicesAttr().Get())
        cnt = np.asarray(mesh.GetFaceVertexCountsAttr().Get())
        M = np.array(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
        world = pts @ M[:3, :3] + M[3, :3]          # USD 는 행벡터: p @ M
        keep_idx, keep_cnt, dropped, k = [], [], 0, 0
        for c in cnt:
            face = idx[k:k + c]
            k += c
            z = world[face, 2]
            if z.min() >= z_band[0] and z.max() <= z_band[1]:
                dropped += 1
                continue
            keep_idx.extend(int(v) for v in face)
            keep_cnt.append(int(c))
        mesh.GetFaceVertexIndicesAttr().Set(keep_idx)
        mesh.GetFaceVertexCountsAttr().Set(keep_cnt)
        out[rel] = dropped
        log(f"[EDIT] {rel}: {len(cnt)} 면 중 {dropped} 면 제거 (z {z_band[0]:.2f}..{z_band[1]:.2f})")
    return out
