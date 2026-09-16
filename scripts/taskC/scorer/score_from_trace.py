"""기록된 재생 트레이스로 Task-C 채점.

    python score_from_trace.py <trace.jsonl> <scene.json> <decode.json> [out.json]

트레이스는 `trace_patch.py` 로 만든 재생기 사본이 남긴다.
**상판 높이·띠 좌표는 상수로 받지 않고 씬에서 재서 쓴다**(평가안 규정).

한계는 정직하게 남긴다 — 트레이스에 없는 관측은 UNAVAILABLE 로 리포트된다.
"""
from __future__ import annotations

import json
import sys

import numpy as np

from taskc_scorer import ScoreConfig, TaskCScorer

STIFFNESS = 300.0     # FFW_SG2 gripper_master_l
EFFORT_LIMIT = 30.0


def load_trace(path):
    return [json.loads(ln) for ln in open(path, encoding="utf-8") if ln.strip()]


USD_ROOT = "taskC/out/qr_usd"


def expected_code(slug, root=USD_ROOT):
    """상품의 기대 바코드. 재생기와 같은 출처(`<slug>/info.json`)에서 읽는다."""
    import os
    for base in (root, os.path.join("/workspace/cyclo_lab", root),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "../../BREAD_V0", root)):
        f = os.path.join(base, slug, "info.json")
        if os.path.isfile(f):
            return json.load(open(f, encoding="utf-8")).get("code")
    return None


def build_products(scene, decode_json):
    """씬 딜 결과에서 상품 근사 형상을 만든다."""
    out = []
    for i, p in enumerate(scene["products"]):
        he = [float(v) for v in p["he"]]
        if p.get("cyl"):
            spec = dict(shape="cylinder", radius=max(he[0], he[1]),
                        half_height=he[2], axis_local=(0, 0, 1))
        else:
            # `he` 는 딜 자세의 월드 반치수라, 최저점 계산용 로컬 반치수는 딜 회전을 되돌려 얻는다 (|R0^T| he).
            w, x, y, z = (float(v) for v in p.get("quat", (1.0, 0.0, 0.0, 0.0)))
            R0 = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                           [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                           [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
            spec = dict(shape="box", half_extents=tuple(he), local_he=tuple(float(v) for v in (np.abs(R0.T) @ np.asarray(he))))
        # `he` 는 놓인 자세의 **월드 축정렬** 반치수다 -- AABB 에 그대로 쓴다.
        spec.update(slug=p["slug"], aabb_he=tuple(he),
                    expected_code=expected_code(p["slug"]))
        out.append(spec)
    return out


def measure_scene(scene):
    """상판 높이·띠 좌표를 씬에서 잰다."""
    # 상품이 딜 직후 앉아 있는 면 = AABB 최저점. `he` 가 월드 반치수라 그대로 뺀다.
    tops = [float(p["pos"][2]) - float(p["he"][2]) for p in scene["products"]]
    table_z = float(np.median(tops))
    b = scene["band"]                          # 딜이 쓴 빨간 띠 (x0,x1,y0,y1)
    return table_z, (float(b[0]), float(b[1]), float(b[2]), float(b[3]))


def main(trace_path, scene_path, decode_path, out_path=None):
    tr = load_trace(trace_path)
    scene = json.load(open(scene_path, encoding="utf-8"))
    dec = json.load(open(decode_path, encoding="utf-8"))
    if not tr:
        raise SystemExit("트레이스가 비어 있다")

    specs = build_products(scene, dec)
    slugs = [p["slug"] for p in scene["products"]]

    # 지금 다루는 상품은 프레임마다 바뀐다 -- 트레이스가 슬롯을 함께 남긴다.
    # 슬롯이 없는 옛 트레이스는 종전대로 첫 상품만 대상으로 본다.
    def target_of(row):
        sl = row.get("slot")
        if sl is None:
            return slugs[0]
        sl = int(sl)
        return slugs[sl] if 0 <= sl < len(slugs) else None

    # 판독 성공은 **슬롯별로** 본다. 한 상품이 읽혔다고 다른 상품까지 읽힌 것이 아니다.
    decoded_slugs = set()
    decoded_text = {}      # 슬러그 -> 스캐너캠에서 실제로 읽힌 문자열
    decoded_by = {}        # 슬러그 -> "image" | "geometry"
    for d in dec.get("decode", []):
        if not d.get("ok"):
            continue
        if d.get("slug"):
            sg = d["slug"]
        elif d.get("slot") is not None and 0 <= int(d["slot"]) < len(slugs):
            sg = slugs[int(d["slot"])]
        else:
            sg = slugs[0]
        decoded_slugs.add(sg)
        decoded_by[sg] = d.get("by", "geometry")
        if d.get("text") is not None:
            decoded_text[sg] = str(d["text"])
    decoded_ok = bool(decoded_slugs)

    cfg = ScoreConfig()
    state = {"i": 0}

    def cur():
        return tr[state["i"]]

    def prod_row(slug):
        for pr in cur()["products"]:
            if pr["slug"] == slug:
                return pr
        return None

    for s in specs:
        s["get_pose"] = (lambda sl: (lambda: (prod_row(sl)["pos"], prod_row(sl)["quat"])))(s["slug"])
        s["get_lin_vel"] = (lambda sl: (lambda: prod_row(sl)["vel"]))(s["slug"])

    # 왼 그리퍼는 하나뿐이라 부하도 하나다. 그것을 슬러그로 안 가르면 손에 힘이 들어간
    # 순간 세 상품이 **동시에** 집기 통과한다. 지금 다루는 슬롯의 상품에만 준다.
    def load_nm(slug):
        row = cur()
        if slug != target_of(row) or row.get("grip_q") is None:
            return None
        return float(np.clip(STIFFNESS * (row["grip_cmd"] - row["grip_q"]),
                             -EFFORT_LIMIT, EFFORT_LIMIT))

    def grip_q(slug):
        return cur().get("grip_q") if slug == target_of(cur()) else None

    def grasped(slug):
        # 「쥔 상태」 = 닫힘 명령 + 모터가 실제로 밀고 있음. 대상 상품만.
        row = cur()
        if slug != target_of(row):
            return False
        if row.get("grip_q") is None:
            return None
        ld = load_nm(slug)
        return bool(row["grip_cmd"] > 0.1 and ld is not None
                    and abs(ld) >= cfg.grip_load_min_nm)

    def decode(slug):
        # 스캐너캠에서 읽힌 문자열을 그대로 돌려준다 -- 맞는 코드인지는 채점기가 견준다.
        # **거리·파지 조건은 채점기가 다시 판정한다**(평가안: 우리 조건으로 거른다).
        if slug != target_of(cur()) or slug not in decoded_slugs:
            return None
        if slug in decoded_text:
            return decoded_text[slug]
        # 그림 판독을 끄고 돌린 판(기하 판정만)이다. 읽힌 문자열이 없으니 대조할 것이
        # 없어 기대 코드를 그대로 준다. 요약의 `decoded_by` 에 그렇게 적힌다.
        return next((sp["expected_code"] for sp in specs if sp["slug"] == slug), None)


    def _obb_corners(pos, quat, he):
        """월드 OBB 8꼭짓점. quat 는 (w,x,y,z)."""
        w, x, y, z = quat
        R = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                      [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                      [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]], dtype=float)
        out = []
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    out.append(np.asarray(pos, dtype=float)
                               + R @ (np.array([sx, sy, sz], dtype=float) * np.asarray(he, dtype=float)))
        return np.asarray(out)

    def coverage(slug):
        """Sub 2-1 화면 점유율 — 스캐너캠에 투영한 대상 OBB 의 2D 넓이 비율.

        재생기와 **같은 카메라**를 해석적으로 재현한다:
          자세   eye = b0 + bd*0.03,  target = b0 + bd*0.30   (V4-250 과 동일)
          스펙   1600x1000, focal 31.43mm, horizontal_aperture 20.955mm  (CameraCfg 그대로)
        픽셀 세기가 아니라 **경계상자 투영 넓이**라 실제 점유율의 상한이다.
        가려짐·곡면은 반영하지 않는다 -- 리포트에 그대로 적는다.
        """
        row = cur()
        if slug != target_of(row):
            return None
        cam = row.get("cam")
        sz = row.get("tgt_size")
        bd = row.get("bd")
        if not cam or not sz or not bd:
            return None
        W, H, foc, ap, d_eye, d_tgt = cam
        b0 = np.asarray(row["beam"], dtype=float)
        bd = np.asarray(bd, dtype=float)
        eye = b0 + bd * float(d_eye)
        tgt = b0 + bd * float(d_tgt)
        fwd = tgt - eye
        n = float(np.linalg.norm(fwd))
        if n < 1e-9:
            return None
        fwd /= n
        up0 = np.array([0.0, 0.0, 1.0])
        if abs(float(fwd @ up0)) > 0.99:
            up0 = np.array([0.0, 1.0, 0.0])
        right = np.cross(fwd, up0); right /= max(float(np.linalg.norm(right)), 1e-9)
        up = np.cross(right, fwd)
        fx = float(foc) / float(ap) * float(W)
        fy = fx                       # 정사각 픽셀 (수직 개구 = 수평 x H/W)
        # 대상 상품의 현재 자세
        prod = next((q for q in row["products"] if q["slug"] == slug), None)
        if prod is None:
            return None
        he = [float(v) / 2.0 for v in sz]
        pts = _obb_corners(prod["pos"], prod["quat"], he)
        us, vs = [], []
        for P in pts:
            d = P - eye
            zc = float(d @ fwd)
            if zc <= 1e-4:            # 카메라 뒤 -- 한 점이라도 뒤면 상한을 못 믿는다
                return None
            us.append(fx * float(d @ right) / zc + W / 2.0)
            vs.append(fy * float(d @ up) / zc + H / 2.0)
        # 화면과 교차하는 부분만 센다 (프레임을 넘치면 넘친 만큼은 안 보인다)
        u0, u1 = max(0.0, min(us)), min(float(W), max(us))
        v0, v1 = max(0.0, min(vs)), min(float(H), max(vs))
        if u1 <= u0 or v1 <= v0:
            return 0.0
        return float((u1 - u0) * (v1 - v0) / (float(W) * float(H)))

    table_z, band = measure_scene(scene)
    sc = TaskCScorer(
        specs, cfg, table_z=table_z, band_rect=band,
        beam_origin_fn=lambda: np.asarray(cur()["beam"], dtype=float),
        grasp_fn=grasped,
        grip_closed_fn=lambda sl: (cur()["grip_cmd"] > 0.1) if sl == target_of(cur()) else False,
        gripper_load_fn=load_nm,
        gripper_pos_fn=grip_q,
        q_free_close=dec.get("q_free_close"),   # 재생기가 씬에서 잰 값
        coverage_fn=coverage,       # OBB 투영 넓이 비율
        decode_fn=decode,
    )

    for i in range(len(tr)):
        state["i"] = i
        sc.tick(float(tr[i]["t"]))
        if sc.stopped:
            break

    rep = sc.report()
    rep["source"] = {"trace": trace_path, "frames": len(tr),
                     "targets": slugs, "decoded": sorted(decoded_slugs),
                     "decoded_by": decoded_by, "decoded_text": decoded_text,
                     "replay_grade": dec.get("grade"),
                     "replay_decode_ok": decoded_ok}
    rep["warnings"].append(
        "화면 점유율은 OBB 투영 넓이 비율이다 -- 가려짐·곡면을 반영하지 않는 **상한**이고, "
        "이 스캐너캠(화각 약 37도)에서는 제시 거리에서 100% 로 포화해 사실상 변별하지 않는다.")
    if out_path:
        json.dump(rep, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return rep


def _fmt(rep):
    L = []
    L.append(f"대상 {', '.join(rep['source']['targets'])}  프레임 {rep['source']['frames']}  "
             f"재생기 등급 {rep['source']['replay_grade']}")
    L.append(f"상판 z={rep['measured']['table_z']:.4f}  "
             f"띠={[round(v,4) for v in rep['measured']['band_rect']]}")
    total = 0.0
    for p in rep["products"]:
        L.append(f"[{p['slug']}]")
        for k, v in p["items"].items():
            mark = {True: "PASS", False: "FAIL"}.get(v["pass"], v["pass"])
            t = f"  t={v['t']:.2f}" if v["t"] is not None else ""
            L.append(f"  {k:<16} {mark:<12} {v['pts']:>4.1f}점{t}")
            L.append(f"      └ {p['why'].get(k, '')}")
        L.append(f"  {'합계':<16} {p['points']:.1f} / {p['max']:.1f}")
        total += p["points"]
        if p["why"].get("_fallen"):
            L.append(f"  낙하: {p['why']['_fallen']}")
    L.append(f"총점 {total:.1f} / {sum(p['max'] for p in rep['products']):.1f}")
    if rep["stopped"]:
        L.append(f"  중지: {rep['stopped']}")
    if rep.get("attempt_consumed"):
        L.append(f"  ** 시도 1회 소모 ** {rep.get('attempt_reason', '')}")
    for w in rep["warnings"]:
        L.append(f"  ! {w}")
    return "\n".join(L)


if __name__ == "__main__":
    r = main(*sys.argv[1:])
    print(_fmt(r))
