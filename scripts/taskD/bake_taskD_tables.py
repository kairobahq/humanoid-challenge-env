# Copyright 2025.
#
# 태스크 D 가 쓰는 치수 표를 `cyclo_lab` 에서 **구워서** 이 폴더에 JSON 으로 내린다.
#
# 왜 굽나 -- 장면 규칙 모듈은 순수 파이썬이어야 한다.  `from cyclo_lab...` 는 패키지
# `__init__` 이 `isaaclab_tasks` 를 끌고 오므로 아이작 밖에서는 실패하고, 그러면
# `task_d_demo.py --check` 가 Isaac Sim 없이 1 초에 돌 수 없다.  `scripts/taskA/
# taskA_shelf_stock.py` 가 같은 문제를 `store_fixtures.json` 으로 풀었고 그 방식을 따른다.
#
# **손으로 옮기지 않는다.**  이 레포에서 옮겨 적은 숫자가 틀린 적이 여러 번 있다.
# `--verify` 는 이미 구운 JSON 이 원본과 같은지만 대조하고 아무것도 쓰지 않는다.
#
#   python3 bake_taskD_tables.py            # 굽는다
#   python3 bake_taskD_tables.py --verify    # 대조만 한다 (다르면 종료코드 1)
#
# **USD 경로는 굽지 않는다.**  배포 이미지의 에셋 트리는 이름이 다르다
# (`fixtures/table/table.usd` 대 개발 체크아웃의 `Table/Table.usd`, 상품은 슬러그 폴더).
# 상품과 기물의 스폰은 `convstore_store.product_cfg()` / `fixture_cfg()` 가 **자기 매니페스트로**
# 풀게 맡긴다 -- 과제 A 의 `taskA_shelf_stock.attach()` 가 그렇게 한다.  여기서 굽는 것은
# 치수와 자세뿐이고, 그것은 두 트리에서 같다.  직접 푸는 것은 `taskD_layout.py` 가 세 개
# (선반·책상·크레이트) 뿐이다.
#
# 원본:
#   source/cyclo_lab/data/props/convstore/manifest.json          기물 20종, 상품 35종
#   source/cyclo_lab/cyclo_lab/assets/object/taskB_products.py    UPRIGHT / FLIP / 표시 각도
#   source/cyclo_lab/cyclo_lab/assets/object/taskB_restock.py     칸 간격·잔떨림·두 주력 상품

import argparse
import importlib.util as ilu
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

FIXTURES_JSON = os.path.join(HERE, "store_fixtures.json")
PRODUCTS_JSON = os.path.join(HERE, "taskD_products.json")
RULES_JSON = os.path.join(HERE, "taskD_stock_rules.json")


def repo_root():
    """cstore-challenge 뿌리. 이 파일은 <뿌리>/Task-D/challenge/scripts/taskD/ 에 있다."""
    env = os.environ.get("CYCLO_REPO")
    if env:
        return env
    return os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))


def by_path(name, path):
    """모듈을 경로로 읽는다 -- 패키지 경로로 가면 isaaclab 이 딸려 온다."""
    spec = ilu.spec_from_file_location(name, path)
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def gather():
    """구울 표 셋을 만든다. {파일 경로: 내용}."""
    root = repo_root()
    obj = os.path.join(root, "source/cyclo_lab/cyclo_lab/assets/object")
    props = os.path.join(root, "source/cyclo_lab/data/props/convstore")
    manifest_path = os.path.join(props, "manifest.json")
    if not os.path.isfile(manifest_path):
        raise SystemExit("manifest.json 이 없다: %s" % manifest_path)

    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    sys.path.insert(0, obj)
    products_mod = by_path("taskB_products_for_bake", os.path.join(obj, "taskB_products.py"))
    restock_mod = by_path("taskB_restock_for_bake", os.path.join(obj, "taskB_restock.py"))

    # ---- 기물: 배경 흩뿌리기가 쓰는 것만.  size/center/base_offset/usd 넷뿐이다 ----
    fixtures = {}
    for name, e in manifest["fixtures"].items():
        fixtures[name] = {
            "size": [round(float(v), 6) for v in e["size"]],
            "center": [round(float(v), 6) for v in e["center"]],
            "base_offset": round(float(e["base_offset"]), 6),
        }

    # ---- 상품 ----
    #
    # 치수의 정본은 `taskB_restock._PRODUCTS` 다 -- `props/convstore/manifest.json` 의 상품에
    # 프링글스 한 항목과 `taskB_products.MANIFEST_ENTRIES`(스캔한 36종) 를 합친 것이고,
    # `taskB_restock.product(name)` 이 읽는 바로 그 사전이다.  convstore 매니페스트만 보면
    # 스캔 상품이 하나도 안 잡힌다 (처음에 그렇게 해서 0 항목이 나왔다).
    #
    # 진열 자세는 **`stock_orientation()` 이 돌려주는 쿼터니언을 그대로** 굽는다.
    # upright/flip/display_yaw 셋을 굽고 여기서 다시 합성하면, 합성 순서를 한 번 잘못
    # 적는 순간 선반 위 상품이 조용히 다른 면을 보게 된다 -- 그 함수의 주석이 바로 그
    # 순서(왼쪽 곱)를 경고하고 있다.
    #
    # 후보를 좁히지 않는다.  어느 상품이 뽑힐지는 씨앗이 정하므로, 좁혀 두면 씨앗을 바꿀
    # 때마다 이 표를 다시 구워야 한다.
    pool = set(products_mod.TEXTURED_NAMES or products_mod.NAMES)
    pool |= {restock_mod.PRINGLES, restock_mod.COLA}
    pool |= set(restock_mod._fillers())
    products = {}
    for name in sorted(pool):
        e = restock_mod._PRODUCTS.get(name)
        if e is None:
            continue
        up, quat = restock_mod.stock_orientation(name)
        products[name] = {
            "size": [round(float(v), 6) for v in e["size"]],
            "base_offset": round(float(e["base_offset"]), 6),
            # 선반용: 세우는가, 그리고 그 자세의 쿼터니언 (w, x, y, z)
            "shelf_upright": bool(up),
            "shelf_quat": [round(float(v), 9) for v in quat],
            # 크레이트용: place_in_crate 가 읽는 두 결정
            "crate_upright": bool(products_mod.UPRIGHT.get(name, True)),
            "crate_flip": bool(products_mod.FLIP.get(name, False)),
            "display_yaw_deg": round(float(restock_mod.DISPLAY_YAW.get(name, 0.0)), 6),
        }

    # ---- 진열 규칙: 과제 B 의 숫자를 그대로 ----
    rules = {
        "rows": int(restock_mod.ROWS),
        "cols": int(restock_mod.COLS),
        "front_margin": round(float(restock_mod.FRONT_MARGIN), 6),
        "row_pitch": round(float(restock_mod.ROW_PITCH), 6),
        "col_pitch": round(float(restock_mod.COL_PITCH), 6),
        "slot_jitter": round(float(restock_mod.SLOT_JITTER), 6),
        "pringles": restock_mod.PRINGLES,
        "cola": restock_mod.COLA,
        "fillers": list(restock_mod._fillers()),
        "crate": {
            "size": [round(float(v), 6) for v in (0.380, 0.590, 0.140)],
            "floor": 0.0107,
            "inside_x": [round(float(v), 6) for v in restock_mod.CRATE_INSIDE_X],
            "inside_y": [round(float(v), 6) for v in restock_mod.CRATE_INSIDE_Y],
            "wall_gap": round(float(restock_mod.WALL_GAP), 6),
        },
        "note": ("과제 B 의 cyclo_lab.assets.object.taskB_restock 에서 구운 값. "
                 "앞뒤 140 은 손가락이 들어갈 자리, 좌우 280 은 서로 다른 상품을 "
                 "떨어뜨려 놓으라는 2026-08-07 지시. 잔떨림은 축당 5 mm."),
    }
    return {FIXTURES_JSON: fixtures, PRODUCTS_JSON: products, RULES_JSON: rules}


def main():
    ap = argparse.ArgumentParser(description="태스크 D 치수 표를 굽는다.")
    ap.add_argument("--verify", action="store_true",
                    help="쓰지 않고, 이미 구운 것이 원본과 같은지만 대조한다")
    a = ap.parse_args()

    tables = gather()
    bad = 0
    for path, data in tables.items():
        blob = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True)
        name = os.path.basename(path)
        if a.verify:
            if not os.path.isfile(path):
                print("! %s 가 없다" % name)
                bad += 1
                continue
            with open(path, encoding="utf-8") as fh:
                have = fh.read()
            if have.strip() != blob.strip():
                print("! %s 가 원본과 다르다 -- 다시 구울 것" % name)
                bad += 1
            else:
                print("  %-24s 일치 (%d 항목)" % (name, len(data)))
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(blob + "\n")
            print("  %-24s %d 항목  %d 바이트" % (name, len(data), len(blob)))

    if a.verify:
        print("판정: %s" % ("문제 없음" if not bad else "%d 건" % bad))
        raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
