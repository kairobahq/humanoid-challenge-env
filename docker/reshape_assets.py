"""원본 저장소의 에셋 트리를 배포용으로 다시 깐다.

대회 환경 저장소는 여러 해 쌓인 이름을 그대로 들고 있다 -- `props/convstore/taskB_products`,
`our_scan_data`, `Table`, `taskb_orientation.json`. 참가자에게 주는 트리는 그러면 안 되고,
무엇보다 **같은 상품이 두 곳에 200 MB씩 들어 있으면 안 된다.**

## 중복이 왜 있었나 (2026-08-25 측정)

`our_scan_data/<이름>/` 과 `props/convstore/taskB_products/<이름>/` 은 36 개 상품이 md5
단위로 **동일**했다. 둘 다 필요했던 이유는 하나뿐이다: 상품의 skin USD 가 색 텍스처를
**절대경로**로 물고 있었다.

    inputs:diffuse_texture =
      '/workspace/cyclo_lab/source/cyclo_lab/data/our_scan_data/<이름>/textures/material_0.png'

바로 옆에 같은 그림이 있는데도 그쪽을 안 본다. 그래서 `our_scan_data` 를 통째로 같이
넣어야만 상품에 색이 입었다. (이 함정은 `scripts/tools/eval_ckpt_fleet.py:85` 에 이미
기록돼 있다 -- 텍스처가 빠진 채 평가 두 판을 돌리고 나서야 발견됐다.)

이 스크립트는 그 경로를 **상대경로**로 다시 써넣는다. 그러면 사본 한 벌만 남는다.

## 만들어지는 트리

    data/
      robot/ffw_sg2.usd
      fixtures/
        shelf/shelf.usd + 재질 맵 4 장
        table/table.usd
        crate/crate.usd
        scanner/scanner_taskC.usd   과제 C 의 바코드 스캐너
      products/                과제 B 가 쓰는 상품 36 개
        manifest.json      크기·무게·콜라이더·usd 상대경로
        orientation.json   어느 면이 위인가
        display_yaw.json   진열될 때 몇 도 돌아가는가
        shapes.json        상자냐 원통이냐 -- 상자 안에서 어떻게 눕는지를 정한다
        <이름>/
          <이름>.usd        스폰되는 것. ./<이름>_skin.usd 를 상대참조한다
          <이름>_skin.usd   보이는 메시와 재질
          textures/albedo.png
      products_c/              과제 C 가 쓰는 상품 8 개 -- QR 타일이 붙은 별도 파일
        products.json          이름·가격·QR 타일 위치
        _qr_tiles.json         타일 법선과 크기
        taskC_products.json    크기·콜라이더
        taskC_barcodes.json    QR 면의 꼭짓점
        <이름>/
          <이름>_phys.usd      스폰되는 것. ./<이름>.usdc 와 텍스처를 상대참조한다
          <이름>.usdc, 텍스처 1 장, info.json
      store/                   매장. 앞의 둘은 매장을 '말로' 적은 것이고,
        manifest.json            진열대·냉장고 20 종과 거기 놓이는 상품 35 종의 목록.
        layout.json              매장 배치. 위 products 와는 이름이 하나도 겹치지 않는
                                 별개의 집합이다. 과제 B 는 쓰지 않지만 환경 코드가
                                 import 할 때 읽으므로 들어간다(48 KB).
        scene/                   매장 **자체** (191 MB). 과제 A 는 편의점을 가로지르므로
                                 그림이 있어야 한다. 이 아래만은 원본의 상대 배치를 그대로
                                 지킨다 -- 이유는 copy_scene 의 주석에 있다.

버려지는 것: `our_scan_data/`(중복), FFW-SH5 와 OMY 로봇 USD(아무 과제도 안 쓴다),
Table 의 CAD 원본(`.3MF`/`.step`/`_mesh.json`/`.glb`), 변환 부산물(`config.yaml`,
`.asset_hash`), 그리고 매장 씬이 실제로 물고 있지 않은 fixture_kit 의 나머지 전부
(stage 로 옮긴 347 MB 중 191 MB 만 도달한다).

pxr 은 Isaac Sim 을 띄우지 않고도 쓸 수 있다 -- extscache 의 omni.usd.libs 를
PYTHONPATH/LD_LIBRARY_PATH 에 얹으면 import 된다. build_image.sh 가 그렇게 부른다.
"""

import json
import os
import shutil
import sys

from pxr import Sdf

RAW = sys.argv[1]      # 원본에서 그대로 추린 트리
OUT = sys.argv[2]      # 여기에 깨끗한 트리를 만든다

DATA = f"{RAW}/source/cyclo_lab/data"
PROPS = f"{DATA}/props/convstore"
SRC_PRODUCTS = f"{PROPS}/taskB_products"


def copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def texture_specs(layer):
    """이 레이어가 물고 있는 그림 파일 속성 전부. [(AttributeSpec, 원래 경로)].

    합성된 Stage 가 아니라 **레이어 자체**를 연다. 고쳐야 하는 것은 파일에 적힌 값이고,
    Stage 로 열면 참조가 합성돼 어느 파일에 쓸지가 흐려진다.
    """
    out = []

    def walk(spec):
        for attr in spec.properties:
            if not isinstance(attr, Sdf.AttributeSpec):
                continue
            if attr.typeName != Sdf.ValueTypeNames.Asset:
                continue
            value = attr.default
            if value is None or not value.path:
                continue
            # MDL 자체(`OmniPBR.mdl`)는 Isaac 이 자기 경로에서 찾는다. 건드리면 재질이 죽는다.
            if value.path.endswith(".mdl"):
                continue
            out.append((attr, value.path))
        for child in spec.nameChildren:
            walk(child)

    walk(layer.pseudoRoot)
    return out


def retexture(src_dir, skin_usd):
    """상품 하나의 그림들을 옆에 두고, USD 가 그 자리를 상대경로로 보게 만든다.

    파일 **하나하나를 대응시킨다.** 예전에는 눈에 띈 속성을 전부 albedo 로 덮었는데,
    그건 상품이 색 말고 다른 맵을 갖게 되는 순간 그 맵을 조용히 잃는 방식이다.
    실제로 pringles_original_large 는 diffuse 와 opacity 를 둘 다 갖고 있다(둘 다 같은
    파일을 가리키므로 결과는 같았지만, 같으리라는 보장은 어디에도 없었다).

    돌려주는 것: [(속성 경로, 원래 경로, 새 경로)].
    """
    layer = Sdf.Layer.FindOrOpen(skin_usd)
    if layer is None:
        raise RuntimeError(f"열 수 없다: {skin_usd}")

    # 원본 그림 하나 = 배포 그림 하나. 색 지도는 albedo.png 라는 이름을 갖고,
    # 그 밖의 맵이 있으면 원래 파일 이름을 그대로 쓴다.
    renamed = {}
    for _attr, raw in texture_specs(layer):
        if raw in renamed:
            continue
        base = os.path.basename(raw)
        renamed[raw] = "albedo.png" if base == "material_0.png" else base

    changed = []
    for attr, raw in texture_specs(layer):
        new_name = renamed[raw]
        source = os.path.join(src_dir, "textures", os.path.basename(raw))
        if not os.path.isfile(source):
            raise RuntimeError(
                f"{skin_usd} 가 {raw} 를 물고 있는데 그 그림이 상품 폴더에 없다: {source}")
        copy(source, os.path.join(os.path.dirname(skin_usd), "textures", new_name))
        attr.default = Sdf.AssetPath(f"./textures/{new_name}")
        changed.append((str(attr.path), raw, new_name))

    if not changed:
        raise RuntimeError(f"{skin_usd} 에 고칠 텍스처 경로가 없다 -- "
                           f"에셋 구조가 바뀌었다면 이 스크립트를 다시 재야 한다.")
    layer.Save()
    return changed


STORE_SCENE = f"{RAW}/fixture_kit/out/store_scene.usd"


def scene_files(root):
    """`root` USD 가 실제로 물고 있는 파일 전부. RAW 기준 상대경로로 돌려준다.

    참조(reference/payload/subLayer)를 재귀로 따라가고, 도달한 레이어마다 에셋 값 속성
    -- 텍스처가 그것이다 -- 도 함께 모은다.

    **손으로 적지 않는 이유.** 이 그래프는 레이어 94 개와 텍스처 180 장이다(2026-08-25).
    사람이 유지하는 목록은 반드시 원본과 어긋나고, 어긋난 쪽이 텍스처면 증상은 "색이
    없다" 가 아니라 "아무 일도 없다" 이다 -- 그렇게 텍스처가 빠진 채로 평가를 두 판
    돌린 적이 있다(scripts/tools/eval_ckpt_fleet.py:85). USD 에게 직접 묻는다.
    """
    seen, layers, files = set(), [], set()

    def refs(layer):
        out = set(str(s) for s in layer.subLayerPaths)

        def rec(spec):
            for name in ("referenceList", "payloadList"):
                lst = getattr(spec, name, None)
                if lst is None:
                    continue
                for it in (list(lst.prependedItems) + list(lst.appendedItems)
                           + list(lst.explicitItems) + list(lst.addedItems)):
                    if getattr(it, "assetPath", ""):
                        out.add(str(it.assetPath))
            for c in spec.nameChildren:
                rec(c)

        for p in layer.rootPrims:
            rec(p)
        return out

    def walk(path):
        path = os.path.normpath(path)
        if path in seen:
            return
        seen.add(path)
        if not os.path.isfile(path):
            raise RuntimeError(f"매장 씬이 없는 파일을 참조한다: {path}\n"
                               f"build_image.sh 의 KEEP 이 부족하다.")
        layers.append(path)
        files.add(path)
        layer = Sdf.Layer.FindOrOpen(path)
        if layer is None:
            return
        here = os.path.dirname(path)
        for r in sorted(refs(layer)):
            walk(r if r.startswith("/") else os.path.join(here, r))

    walk(root)

    for path in layers:
        layer = Sdf.Layer.FindOrOpen(path)
        if layer is None:
            continue
        here = os.path.dirname(path)

        def textures(spec):
            for name in spec.attributes.keys():
                a = spec.attributes[name]
                if a.typeName != Sdf.ValueTypeNames.Asset or a.default is None:
                    continue
                ap = str(a.default.path)
                # 빈 값은 "이 입력은 안 쓴다" 는 뜻이다. 집기 USD 들이 opacity 같은
                # 입력을 선언해 두고 비워 놓는다 -- 가리키는 그림이 없는 것이 정상이다.
                if not ap:
                    continue
                # 절대경로면 옮길 수 없다. 2026-08-25 측정에서는 하나도 없었고, 생겼다면
                # 그것은 에셋 쪽이 바뀐 것이므로 조용히 지나가서는 안 된다.
                if ap.startswith("/"):
                    raise RuntimeError(f"{path} 의 {name} 이 절대경로다: {ap}")
                t = os.path.normpath(os.path.join(here, ap))
                if os.path.isfile(t):
                    files.add(t)
                elif not ap.lower().endswith(".mdl"):
                    # `.mdl` 은 Isaac 이 자기 재질 라이브러리에서 찾는 셰이더라 여기 없는
                    # 것이 정상이다. 그 밖에 해소되지 않는 것은 **그림이 빠진 것**이고,
                    # 조용히 지나가면 참가자는 회색 집기를 받는다. 2026-08-25 에 KEEP 이
                    # `out/scenes` 만 담아 곤돌라 가격표 24 장이 이렇게 빠졌고, 아무도
                    # 아무 말도 하지 않았다. 그래서 여기서 멈춘다.
                    raise RuntimeError(
                        f"{os.path.relpath(path, RAW)} 의 {name} 이 가리키는 그림이 "
                        f"stage 에 없다: {ap}\n"
                        f"build_image.sh 의 KEEP 이 부족하다.")
            for c in spec.nameChildren:
                textures(c)

        for prim in layer.rootPrims:
            textures(prim)

    rel = sorted(os.path.relpath(f, RAW) for f in files)
    for r in rel:
        if r.startswith(".."):
            raise RuntimeError(f"stage 밖을 가리킨다: {r}")
    return rel, len(layers)


def copy_scene():
    """매장 씬을 `store/scene/` 아래에 **원본의 상대 배치 그대로** 옮긴다.

    이 트리만 이름을 정리하지 않는 이유가 있다. 상품 쪽은 텍스처가 절대경로라 어차피 다시
    써야 했고, 그래서 겸사겸사 이름도 갈았다. 매장 쪽은 정반대다 -- 참조 94 개와 텍스처
    180 장이 **전부 상대경로**라(2026-08-25 측정: 절대경로 0), 서로의 위치 관계만 지키면
    한 글자도 고치지 않고 통째로 옮겨진다.

    이름을 정리하려면 그 274 개 경로를 전부 다시 써야 하고, 하나라도 놓치면 그 집기는
    조용히 회색으로 나온다. 고쳐서 얻는 것(보기 좋은 디렉토리 이름)보다 잃을 수 있는
    것(말없이 색이 빠진 매장)이 크다. 그래서 `store/scene/` 은 원본 저장소 루트 자리를
    대신하고, 그 아래는 원본 그대로다.
    """
    rel, n_layers = scene_files(STORE_SCENE)
    for r in rel:
        copy(f"{RAW}/{r}", f"{OUT}/store/scene/{r}")
    size = sum(os.path.getsize(f"{OUT}/store/scene/{r}") for r in rel)
    print(f"[scene]    매장 USD -- 레이어 {n_layers} 개, 파일 {len(rel)} 개, "
          f"{size / 1e6:.0f} MB")


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)

    # ---------------------------------------------------------------- 로봇
    copy(f"{DATA}/robots/FFW/FFW_SG2.usd", f"{OUT}/robot/ffw_sg2.usd")
    print("[robot]    ffw_sg2.usd")

    # ---------------------------------------------------------------- 픽스처
    # 진열대의 재질 맵 4 장은 USD 가 파일 이름으로 참조하므로 이름을 그대로 둔 채 옮긴다.
    shelf_src = f"{PROPS}/fixtures/shelf_taskB"
    for f in sorted(os.listdir(shelf_src)):
        dst = "shelf.usd" if f == "shelf_taskB.usd" else f
        copy(f"{shelf_src}/{f}", f"{OUT}/fixtures/shelf/{dst}")
    copy(f"{DATA}/Table/Table.usd", f"{OUT}/fixtures/table/table.usd")
    copy(f"{DATA}/Crate/blue_box.usd", f"{OUT}/fixtures/crate/crate.usd")
    print("[fixtures] shelf/ table/ crate/")

    # ---------------------------------------------------------------- 상품
    with open(f"{SRC_PRODUCTS}/manifest.json", encoding="utf-8") as fh:
        products = json.load(fh)["products"]
    names = sorted(products)
    total_rewritten = 0
    for name in names:
        src = f"{SRC_PRODUCTS}/{name}"
        dst = f"{OUT}/products/{name}"
        copy(f"{src}/{name}.usd", f"{dst}/{name}.usd")
        copy(f"{src}/{name}_skin.usd", f"{dst}/{name}_skin.usd")
        # 그림은 retexture 가 옮긴다 -- USD 가 실제로 물고 있는 것만 따라가야 하고,
        # 안 쓰이는 파일을 같이 넣지 않기 위해서다.
        changed = retexture(src, f"{dst}/{name}_skin.usd")
        total_rewritten += len(changed)
        # 매니페스트의 usd 경로도 새 자리로. convstore_store._usd() 가 PROPS + 이 값을 쓴다.
        products[name]["usd"] = f"{name}/{name}.usd"
        # GraspGen 파일 경로는 배포판에 없는 것을 가리키므로 지운다.
        products[name].pop("grasp_sim_yaml", None)

    with open(f"{OUT}/products/manifest.json", "w", encoding="utf-8") as fh:
        json.dump({"products": products}, fh, ensure_ascii=False, indent=1)
    copy(f"{SRC_PRODUCTS}/taskb_orientation.json", f"{OUT}/products/orientation.json")
    copy(f"{SRC_PRODUCTS}/taskb_display_yaw.json", f"{OUT}/products/display_yaw.json")
    # 이름이 grasp_filter 라서 GraspGen 잔재로 보이지만 아니다 -- 상품마다 "상자냐 원통이냐"
    # 를 담고 있고, 그 분류가 상자 안에서 상품이 어떻게 눕는지를 정한다. 한 번 빼 봤다가
    # taskB_restock._shape() 가 FileNotFoundError 로 죽었다(2026-08-25).
    copy(f"{SRC_PRODUCTS}/grasp_filter.json", f"{OUT}/products/shapes.json")

    # ---------------------------------------------------------------- 매장 정의
    # 상품 매니페스트와 **합치지 않는다.** 담는 것이 다르고(매장 픽스처 20 종 + 거기
    # 놓이는 상품 35 종 대 과제 B 상품 36 개), 이름이 하나도 겹치지 않는다. 합치면
    # 과제 B 의 진열대 추첨 판이 매장 상품까지 끌어들여 씬이 조용히 달라진다.
    # 과제 B 가 쓰지 않는데도 넣는 이유는 하나뿐이다: cyclo_lab 을 import 하면 매장 씬
    # 설정(convstore.py)이 함께 읽히고, 이 파일이 없으면 KeyError 로 죽는다(2026-08-25).
    copy(f"{PROPS}/manifest.json", f"{OUT}/store/manifest.json")
    copy(f"{PROPS}/layout.json", f"{OUT}/store/layout.json")
    print("[store]    manifest.json layout.json")

    # ---------------------------------------------------------------- 과제 C
    # 상품은 과제 B 의 36 개와 파일이 다르다 -- QR 타일이 메시에 붙박여 있다. `.usdc` 는 텍스처를
    # 상대경로로 물지만, `<이름>_phys.usd` 가 `.usdc` 를 무는 방식은 상품마다 달라 8 종 중 5 종은
    # 수집 저장소 자리인 `/workspace/cyclo_lab/taskC/out/qr_usd/…` **절대 경로**다(2026-09-14 실측;
    # 09-06 에 "상대경로" 로 본 것은 3 종만 맞았다). 크레이트(바이너리) 파일이라 여기서 고쳐 쓰지
    # 않고, Dockerfile 이 그 자리를 products_c 로 잇는 링크를 건다. 여기서는 어느 상품이 그 링크에
    # 기대는지 세어 찍는다 -- 링크가 빠지면 그 상품은 메시·QR 없이 스폰돼 판독이 안 된다.
    qr = f"{RAW}/taskC/out/qr_usd"
    names_c = sorted(d for d in os.listdir(qr) if os.path.isdir(f"{qr}/{d}"))
    abs_ref = []
    for name in names_c:
        for f in sorted(os.listdir(f"{qr}/{name}")):
            copy(f"{qr}/{name}/{f}", f"{OUT}/products_c/{name}/{f}")
        phys = f"{qr}/{name}/{name}_phys.usd"
        if os.path.isfile(phys):
            with open(phys, "rb") as fh:
                if b"/workspace/cyclo_lab/taskC/out/qr_usd" in fh.read():
                    abs_ref.append(name)
    if abs_ref:
        print(f"[taskC]    _phys.usd 가 /workspace/cyclo_lab/taskC/out/qr_usd 절대 경로를 무는 상품 "
              f"{len(abs_ref)} 종: {', '.join(abs_ref)} -- Dockerfile 의 taskC/out/qr_usd 링크가 필요하다")
    for f in ("products.json", "_qr_tiles.json"):
        copy(f"{qr}/{f}", f"{OUT}/products_c/{f}")
    for f in ("taskC_products.json", "taskC_barcodes.json"):
        copy(f"{PROPS}/{f}", f"{OUT}/products_c/{f}")
    copy(f"{PROPS}/fixtures/scanner_taskC/scanner_taskC.usd",
         f"{OUT}/fixtures/scanner/scanner_taskC.usd")
    print(f"[taskC]    products_c/ {len(names_c)} 개, fixtures/scanner/scanner_taskC.usd")

    # ---------------------------------------------------------------- 과제 A 의 매장
    # 위의 manifest/layout 은 매장을 **말로** 적은 것이고, 아래는 매장 **자체**다.
    # 과제 A 는 편의점을 가로지르므로 그림이 있어야 한다.
    copy_scene()
    print(f"[products] {len(names)} 개, 텍스처 경로 {total_rewritten} 곳을 "
          f"./textures/albedo.png 로 다시 썼다")

    size = sum(os.path.getsize(os.path.join(r, f))
               for r, _d, fs in os.walk(OUT) for f in fs)
    print(f"[done]     {size / 1e6:.0f} MB")


main()
