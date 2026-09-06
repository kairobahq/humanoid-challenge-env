# Copyright 2026.
#
# 장면을 사람에게 보여 주는 두 형식: 터미널 요약(과제 A 데모의 `[장면]` 형식)과
# `--scene-json` 파일. 같은 값을 두 번 계산하지 않도록 둘 다 `scene_dict()` 하나에서 나온다.
#
# isaaclab 을 쓰지 않는 순수 파이썬이다.

import json
import math

from . import taskC_layout as L
from . import taskC_products as P


def scene_dict(seed, slugs, entries, redeal, robot_xy_yaw=None):
    """장면 하나를 dict 로.

    entries 는 로봇 좌표의 상품 목록(check_settled 의 결과 형식). 세계 좌표는 여기서 만든다.
    robot_xy_yaw 는 (x, y, yaw_deg) 세계 좌표; 없으면 layout 의 시작 자세.
    """
    if robot_xy_yaw is None:
        robot_xy_yaw = (L.ROBOT_BASE_WORLD[0], L.ROBOT_BASE_WORLD[1], math.degrees(L.ROBOT_YAW))
    prods = []
    for k, e in enumerate(entries):
        pr = tuple(float(v) for v in e["pos"])
        pw = L.robot_to_world(pr)
        qw = L.quat_robot_to_world(tuple(float(v) for v in e["quat"]))
        prods.append({
            "slot": k, "product": e["slug"], "label": P.LABELS[e["slug"]],
            "pos": [round(float(v), 5) for v in pw],
            "pos_robot": [round(float(v), 5) for v in pr],
            "quat": [round(float(v), 6) for v in qw],
            "quat_robot": [round(float(v), 6) for v in e["quat"]],
            "cylinder": bool(e.get("cyl", P.is_cylinder(e["slug"]))),
            "upright": bool(e.get("upright", True)),
            "qr_az_err_deg": e.get("qr_az_err"),
            "gap_min_m": (round(float(e["gap_min"]), 4) if e.get("gap_min") is not None else None),
        })
    bx0, bx1, by0, by1 = L.BAND["x0"], L.BAND["x1"], L.BAND["y0"], L.BAND["y1"]
    corners = [L.robot_to_world((bx0, by0)), L.robot_to_world((bx1, by1))]
    return {
        "task": "C",
        "seed": seed,
        "target": {"product": slugs[0], "label": P.LABELS[slugs[0]]},
        "products": prods,
        "band": {"robot": {"x0": bx0, "x1": bx1, "y0": by0, "y1": by1},
                 "world_corners": [[round(float(v), 4) for v in c] for c in corners],
                 "tape_w": L.TAPE_W},
        "counter": {"centre": list(L.COUNTER_CENTRE_WORLD), "top_z": L.COUNTER_TOP_Z,
                    "size": list(L.COUNTER_SIZE_XY)},
        "robot": {"pos": [round(float(robot_xy_yaw[0]), 5), round(float(robot_xy_yaw[1]), 5)],
                  "yaw_deg": round(float(robot_xy_yaw[2]), 3),
                  "lift": L.LIFT_JOINT_POS,
                  "head_pitch_deg": round(math.degrees(L.HEAD_PITCH), 3),
                  "arm_l": list(L.STOW_ARM_L), "arm_r": list(L.STOW_ARM_R)},
        "scanner": {"pos": [round(float(v), 5) for v in L.robot_to_world(L.SCANNER_HOLD_POS)],
                    "pos_robot": list(L.SCANNER_HOLD_POS),
                    "quat": [round(float(v), 6) for v in L.quat_robot_to_world(L.SCANNER_HOLD_QUAT)],
                    "size": list(L.SCANNER_SIZE), "held": True},
        "cameras": {k: {"width": v["w"], "height": v["h"]} for k, v in L.CAMERAS.items()},
        "redeal": int(redeal),
    }


def print_summary(d):
    """과제 A 데모 형식의 터미널 요약. 문자열을 돌려주고 호출자가 찍는다."""
    t = d["target"]
    r = d["robot"]
    b = d["band"]["robot"]
    lines = [f"[장면] seed {d['seed']}, 집을 것 {t['label']} [{t['product']}]", ""]
    lines.append("  로봇 -- 계산대를 마주 보고 선다 (정지 과제: 주행하지 않는다)")
    lines.append(f"    자리      ({r['pos'][0]:+.3f}, {r['pos'][1]:+.3f})  yaw {r['yaw_deg']:+.1f} 도")
    lines.append(f"    몸통      {r['lift']:+.4f}    고개 {r['head_pitch_deg']:.1f} 도 아래    "
                 f"양팔 스토우 (오른팔 joint1 {r['arm_r'][0]:.3f})")
    lines.append(f"    계산대    중심 ({d['counter']['centre'][0]:+.3f}, {d['counter']['centre'][1]:+.3f})  "
                 f"상판 {d['counter']['top_z']:.4f} m")
    lines.append("")
    lines.append("  계산대 위 상품 -- 슬롯 0 이 집을 상품, QR 면은 정 오른쪽(-Y)을 본다")
    for p in d["products"]:
        x, y, z = p["pos"]
        extra = ""
        if p.get("qr_az_err_deg") is not None:
            extra += f"  QR 오차 {p['qr_az_err_deg']:.1f} 도"
        if p.get("gap_min_m") is not None:
            extra += f"  최근접 {p['gap_min_m'] * 100:.1f} cm"
        shape = "직립" if p["cylinder"] else "눕힘"
        lines.append(f"    {p['slot']}: {p['label']:<32s} ({x:+.3f}, {y:+.3f}, {z:.3f})  "
                     f"[{p['product']}] {shape}{extra}")
    lines.append("")
    lines.append(f"  빨간 띠(로봇 좌표)  x {b['x0']:.3f}~{b['x1']:.3f}  y {b['y0']:.3f}~{b['y1']:.3f}  "
                 f"테이프 {d['band']['tape_w'] * 1000:.0f} mm  -- 상품끼리 10 cm 이상")
    s = d["scanner"]
    lines.append(f"  스캐너    왼손이 드는 자리 ({s['pos'][0]:+.3f}, {s['pos'][1]:+.3f}, {s['pos'][2]:.3f})  "
                 f"크기 {s['size'][0]:.3f} x {s['size'][1]:.3f} x {s['size'][2]:.3f} m")
    lines.append("  카메라    " + ", ".join(f"{k} {v['width']}x{v['height']}" for k, v in d["cameras"].items()))
    lines.append(f"  재딜      {d['redeal']} 회")
    lines.append("")
    return "\n".join(lines)


def write_scene_json(d, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2)
