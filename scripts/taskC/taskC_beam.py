# Copyright 2026.
#
# 스캐너 빔의 **자국**. 빔은 공중의 경로가 아니라 물체에 닿는 면으로 그린다.
#
# 수집 파이프라인(v5, `qr_sweep_replay.py`)의 V4-70 / V4-318 / V4-337 / v5-3c 를 옮긴 것이다.
# 기록판 로그(`gt_final/<시드>/<시드>_chain.log`)가 쓴 값이 기본값이며, v5 소스의 기본값과
# 다른 것들이 있다 -- 그 줄을 그대로 남겨 둔다:
#
#     [RPL] V4-337 시트 재질 = OmniSurface 투명 1.00 발광 12000
#     [RPL] V4-318 각뿔대 빔: 개구 11.5x2.4mm · 반각 11.94/0.881도 · 사거리 30cm
#     [RPL] V4-70 빔 자국 준비: samyang_buldak_cup 삼각형 26198개 -> /World/envs/env_0/P_0/BeamHit
#     [RPL] v5-3c 빔 시트 빨강 [0.44, 0.03, 0.03] 점멸(주기 6 듀티 0.50 방식 collapse)
#
# 기록판에는 **점군(V4-323)도 막대(V4-302)도 BeamViz 도 없다.** 그 셋은 경로를 보여주는
# 디버그 표시라 기록 때 꺼져 있었다. 그래서 여기에도 넣지 않는다 -- 상품 표면에 붙는 면 하나뿐이다.

import json
import math
import os
import pathlib

import numpy as np

from . import taskC_products as P

__all__ = ["load_tiles", "BeamSheet", "BandLight"]

TILES_JSON = pathlib.Path(__file__).resolve().parent / "_qr_tiles.json"


def _noop(*_a, **_k):
    pass


def load_tiles():
    """품목별 QR 타일의 상품 로컬 위치·법선. 판독기가 이걸로 QR 까지의 거리를 잰다."""
    with open(TILES_JSON, encoding="utf-8") as f:
        return json.load(f)


def _cast(origins, dirs, A, B, C, chunk=16, max_t=None):
    """광선마다 제 원점을 갖는 레이캐스트 (V4-318 각뿔대용).

    각뿔대는 출구창에 크기가 있어 광선마다 원점이 다르다. 원점 하나를 공유할 때 쓰는
    최적화(tvec 를 한 번만 계산)를 쓸 수 없어 묶음을 절반으로 줄여 메모리를 맞춘다.
    `max_t` 를 주면 그보다 먼 명중은 버린다 -- 빔 사거리.
    """
    n = len(dirs)
    best_t = np.full(n, np.inf)
    best_i = np.full(n, -1, dtype=int)
    # 삼각형이 없으면 전부 빗나감이 정답이다 (V4-329). 그냥 두면 argmin 이 빈 축에서 터진다.
    if len(A) == 0:
        return best_t, best_i
    e1, e2 = B - A, C - A
    for s0 in range(0, n, chunk):
        d = dirs[s0:s0 + chunk]
        o = origins[s0:s0 + chunk]
        tv3 = o[:, None, :] - A[None, :, :]
        q = np.cross(tv3, e1[None, :, :])
        eq = np.einsum("tj,rtj->rt", e2, q)
        pv = np.cross(d[:, None, :], e2[None, :, :])
        det = np.einsum("tj,rtj->rt", e1, pv)
        ok = np.abs(det) > 1e-12
        inv = np.zeros_like(det)
        inv[ok] = 1.0 / det[ok]
        u = np.einsum("rtj,rtj->rt", tv3, pv) * inv
        v = np.einsum("rj,rtj->rt", d, q) * inv
        t = eq * inv
        hit = ok & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6) & (t > 1e-6)
        if max_t is not None:
            hit = hit & (t <= max_t)
        tt = np.where(hit, t, np.inf)
        j = np.argmin(tt, axis=1)
        tvv = tt[np.arange(len(d)), j]
        sel = np.isfinite(tvv)
        best_t[s0:s0 + len(d)][sel] = tvv[sel]
        best_i[s0:s0 + len(d)][sel] = j[sel]
    return best_t, best_i


def _quads(points, landed, nu, nv, lift, depth, max_jump=0.02):
    """격자 명중점 -> 사각형. 모서리 중 하나라도 빗나갔거나 깊이 차가 크면 건너뛴다."""
    verts = [p + lift[i] for i, p in enumerate(points)]
    counts, idx = [], []
    for j in range(nv - 1):
        for i in range(nu - 1):
            c = [j * nu + i, j * nu + i + 1, (j + 1) * nu + i + 1, (j + 1) * nu + i]
            if not all(landed[x] for x in c):
                continue
            d = [depth[x] for x in c]
            if max(d) - min(d) > max_jump:
                continue
            counts.append(4)
            idx.extend(c)
    return verts, counts, idx


def _mesh_triangles(slug):
    """상품 시각 메시의 삼각형 (상품 로컬 좌표). 첫 Mesh 하나만 읽는다 -- 원문 그대로."""
    from pxr import Usd, UsdGeom
    stage = Usd.Stage.Open(str(P.product_mesh_usd(slug)))
    tri = []
    for prim in stage.Traverse():
        mesh = UsdGeom.Mesh(prim)
        if not mesh:
            continue
        pts = np.asarray([[q[0], q[1], q[2]]
                          for q in (mesh.GetPointsAttr().Get() or [])], dtype=float)
        counts = list(mesh.GetFaceVertexCountsAttr().Get() or [])
        idx = list(mesh.GetFaceVertexIndicesAttr().Get() or [])
        c = 0
        for n in counts:
            for k in range(1, n - 1):
                tri.append([pts[idx[c]], pts[idx[c + k]], pts[idx[c + k + 1]]])
            c += n
        break
    return np.asarray(tri, dtype=float)


class BandLight:
    """계산대 테두리 테이프. 평소 회색, 인식하면 빨강 (v5-3c 뒷부분).

    `taskC_counter.bind_band_idle` 이 만든 셰이더를 받아 색만 바꾼다. 상태가 바뀔 때만 쓴다.
    """

    def __init__(self, shader, log=None):
        self._shader = shader
        self._log = log or _noop
        self._state = None
        self._idle = [float(v) for v in
                      os.environ.get("TASKC_BAND_IDLE_RGB", "0.3,0.3,0.3").split(",")]
        self._idle_i = float(os.environ.get("TASKC_BAND_IDLE_INT", "0"))
        self._hit = [float(v) for v in
                     os.environ.get("TASKC_BAND_HIT_RGB", "1.0,0.03,0.03").split(",")]
        self._hit_i = float(os.environ.get("TASKC_BAND_HIT_INT", "5000"))
        if shader is not None:
            self._log("v5-3c 테두리 점등 준비 (평소 %s 발광 %.0f / 인식 시 빨강 %s 발광 %.0f)"
                      % (self._idle, self._idle_i, self._hit, self._hit_i))

    def set_hit(self, hit, frame=-1):
        if self._shader is None:
            return
        want = "hit" if hit else "idle"
        if self._state == want:
            return
        self._state = want
        from pxr import Gf
        rgb = self._hit if hit else self._idle
        self._shader.GetInput("diffuse_color_constant").Set(Gf.Vec3f(*rgb))
        self._shader.GetInput("emissive_color").Set(Gf.Vec3f(*rgb))
        self._shader.GetInput("emissive_intensity").Set(self._hit_i if hit else self._idle_i)
        self._log("v5-3c 테두리 -> %s f%d" % (want, frame))


class BeamSheet:
    """상품 표면에 붙는 빔 자국 하나. 슬롯 하나를 맡는다.

    빈 Mesh 를 상품 프림 **밑에** 만들어 두므로 상품이 움직여도 자국이 따라간다
    (부모가 상품이라 변환이 공짜다). 프레임마다 점만 갈아 끼운다.
    """

    def __init__(self, stage, slot, slug, log=None):
        self._log = log or _noop
        self._slot = int(slot)
        self._slug = slug
        self._nu = int(os.environ.get("TASKC_BEAM_NU", "25"))
        self._nv = int(os.environ.get("TASKC_BEAM_NV", "11"))
        self._range = float(os.environ.get("TASKC_BEAM_RANGE_MM", "300")) / 1000.0
        self._lift = float(os.environ.get("TASKC_BEAM_LIFT_MM", "1.5")) / 1000.0
        self._rgb = [float(v) for v in
                     os.environ.get("TASKC_BEAM_RGB", "0.44,0.03,0.03").split(",")]
        self._emit = float(os.environ.get("TASKC_SHEET_EMIT", "12000"))
        self._opac = float(os.environ.get("TASKC_BEAM_OPACITY", "1.0"))
        self._per = max(1, int(os.environ.get("TASKC_BAR_BLINK_N", "6")))
        self._duty = float(os.environ.get("TASKC_BAR_DUTY", "0.5"))
        self._said = False
        self._hit1 = False
        self._cull_n = 0

        self._tri = _mesh_triangles(slug)
        self._path = "/World/envs/env_0/P_%d/BeamHit" % self._slot
        self._mesh = self._make_mesh(stage)
        self._frustum()
        # V4-326: 빔 근처 삼각형만 쏘기 위한 사전 계산(슬롯당 1회). 메시는 상품 로컬에서
        # 고정이라 무게중심·반지름이 변하지 않는다.
        if len(self._tri):
            cen = self._tri.mean(axis=1)
            self._cen = cen
            self._rad = np.linalg.norm(self._tri - cen[:, None, :], axis=2).max(axis=1)
            nrm = np.cross(self._tri[:, 1] - self._tri[:, 0], self._tri[:, 2] - self._tri[:, 0])
            self._nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
        else:
            self._cen = self._rad = self._nrm = None
        self._log("V4-70 빔 자국 준비: %s 삼각형 %d개 -> %s"
                  % (slug, len(self._tri), self._path))

    # -------------------------------------------------------------- 준비
    def _make_mesh(self, stage):
        from pxr import UsdGeom, UsdShade, Sdf, Gf
        mesh = UsdGeom.Mesh.Define(stage, self._path)
        mesh.CreateDoubleSidedAttr(True)
        mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        # V4-337: 투명이 실제로 걸리는 경로는 OmniSurface + geometry_opacity 뿐이다.
        # UsdPreviewSurface + opacity 는 시험에서 자국이 아예 사라졌다(0px).
        mat = UsdShade.Material.Define(stage, self._path + "/MatSurf")
        shd = UsdShade.Shader.Define(stage, self._path + "/MatSurf/S")
        shd.CreateImplementationSourceAttr(UsdShade.Tokens.sourceAsset)
        shd.SetSourceAsset(Sdf.AssetPath("OmniSurface.mdl"), "mdl")
        shd.SetSourceAssetSubIdentifier("OmniSurface", "mdl")
        shd.CreateInput("diffuse_reflection_color", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*self._rgb))
        shd.CreateInput("emission_color", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*self._rgb))
        shd.CreateInput("emission_intensity", Sdf.ValueTypeNames.Float).Set(self._emit)
        shd.CreateInput("geometry_opacity", Sdf.ValueTypeNames.Float).Set(self._opac)
        mat.CreateSurfaceOutput("mdl").ConnectToSource(shd.ConnectableAPI(), "out")
        mat.CreateDisplacementOutput("mdl").ConnectToSource(shd.ConnectableAPI(), "out")
        mat.CreateVolumeOutput("mdl").ConnectToSource(shd.ConnectableAPI(), "out")
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(
            mat, UsdShade.Tokens.strongerThanDescendants)
        self._log("V4-337 시트 재질 = OmniSurface 투명 %.2f 발광 %.0f" % (self._opac, self._emit))
        return mesh

    def _frustum(self):
        """V4-318: 각뿔대. 출구창(개구면)에 크기가 있고 거기서 퍼진다.

        두 기준점(거리, 가로, 세로)에서 개구 크기와 발산을 유도한다. 개구면 위에 등간격으로
        원점을 깔아야 옆면이 평평한 면체가 된다 -- 한 점에서 쏘면 원뿔이라 자국 모서리가 휜다.
        """
        d1 = float(os.environ.get("TASKC_BEAM_D1_MM", "20")) / 1000.0
        w1 = float(os.environ.get("TASKC_BEAM_W1_MM", "20")) / 1000.0
        h1 = float(os.environ.get("TASKC_BEAM_H1_MM", "3")) / 1000.0
        d2 = float(os.environ.get("TASKC_BEAM_D2_MM", "150")) / 1000.0
        w2 = float(os.environ.get("TASKC_BEAM_W2_MM", "75")) / 1000.0
        h2 = float(os.environ.get("TASKC_BEAM_H2_MM", "7")) / 1000.0
        dd = max(d2 - d1, 1e-9)
        self._kw = (w2 - w1) / dd          # 거리당 가로 증가
        self._kh = (h2 - h1) / dd
        self._aw = max(w1 - self._kw * d1, 0.0)   # 개구 가로 (거리 0)
        self._ah = max(h1 - self._kh * d1, 0.0)
        self._log("V4-318 각뿔대 빔: 개구 %.1fx%.1fmm · 반각 %.2f/%.3f도 · %dcm 에서 %.1fx%.1fmm"
                  " · 사거리 %.0fcm"
                  % (self._aw * 1000, self._ah * 1000,
                     math.degrees(math.atan(self._kw * 0.5)),
                     math.degrees(math.atan(self._kh * 0.5)),
                     d2 * 100, (self._aw + self._kw * d2) * 1000,
                     (self._ah + self._kh * d2) * 1000, self._range * 100))

    # -------------------------------------------------------------- 갱신
    def _rays(self, o, d, right, up):
        dirs, ors = [], []
        for fv in np.linspace(1.0, -1.0, self._nv):
            for fu in np.linspace(-1.0, 1.0, self._nu):
                ors.append(o + right * (fu * self._aw * 0.5) + up * (fv * self._ah * 0.5))
                v = d + right * (fu * self._kw * 0.5) + up * (fv * self._kh * 0.5)
                dirs.append(v / np.linalg.norm(v))
        return np.asarray(ors), np.asarray(dirs)

    def _cull(self, o, d, right, up):
        """V4-326/327/328: 빔 포락선 밖 삼각형을 버린다.

        거르는 비용은 O(삼각형), 쏘는 비용은 O(광선x삼각형)이라 원통 품목(26k 삼각형)에서
        결정적이다. 넓은 축·좁은 축을 **따로** 걸어야 한다 -- 횡거리 하나로는 캔 전체가
        창 안에 들어와 못 거른다. 남는 게 없으면 원본으로 되돌리지 않고 비운다.
        """
        if self._cen is None or os.environ.get("TASKC_BEAM_CULL", "1") != "1":
            return self._tri
        pad = float(os.environ.get("TASKC_BEAM_CULL_PAD_MM", "10")) / 1000.0
        rel = self._cen - o
        al = rel @ d
        ac = np.clip(al, 0.0, None)
        hw = 0.5 * (self._aw + self._kw * ac)
        hh = 0.5 * (self._ah + self._kh * ac)
        keep = ((al >= -self._rad) & (al <= self._range + self._rad)
                & (np.abs(rel @ right) <= hw + self._rad + pad)
                & (np.abs(rel @ up) <= hh + self._rad + pad))
        if os.environ.get("TASKC_BEAM_CULL_BACK", "1") == "1":
            keep = keep & ((self._nrm @ d) < 0)   # 닫힌 메시에서 최근접 명중은 앞면뿐이다
        out = self._tri[keep]
        self._cull_n += 1
        every = int(os.environ.get("TASKC_BEAM_CULL_LOG", "200"))
        if every > 0 and self._cull_n % every == 1:
            self._log("V4-328 삼각형 거르기 %d -> %d개 (%.1f%%)"
                      % (len(self._tri), len(out), 100.0 * len(out) / max(len(self._tri), 1)))
        return out

    def update(self, o, d, right, up, frame):
        """빔 원점·방향(**상품 로컬 좌표**)을 받아 자국을 다시 그린다.

        반환값은 사각형 개수. 0 이면 자국이 없다 -- 빔이 상품에 닿지 않았다는 뜻이고, 판독기는 그때 읽지 않는다.
        """
        from pxr import Gf, UsdGeom
        ors, dirs = self._rays(o, d, right, up)
        tri = self._cull(o, d, right, up)
        t, i = _cast(ors, dirs, tri[:, 0], tri[:, 1], tri[:, 2], max_t=self._range) \
            if len(tri) else (np.full(len(dirs), np.inf), np.full(len(dirs), -1, dtype=int))
        land = np.isfinite(t)
        pts, lift = [], []
        for k in range(len(dirs)):
            if not land[k]:
                pts.append(ors[k] + dirs[k] * self._range)   # V4-318: 자리 채우기
                lift.append(np.zeros(3))
                continue
            tr = tri[i[k]]
            n = np.cross(tr[1] - tr[0], tr[2] - tr[0])
            n = n / max(float(np.linalg.norm(n)), 1e-12)
            if float(n @ (-dirs[k])) < 0:
                n = -n
            pts.append(ors[k] + dirs[k] * t[k])
            lift.append(n * self._lift)
        vt, ct, ix = _quads(pts, land, self._nu, self._nv, lift, t)

        # v5-3c 점멸: 방식 collapse -- 점을 한 자리로 무너뜨려 끈다. 가시성 토글은 폐기됐다.
        on = (self._duty >= 1.0) or ((int(frame) % self._per) < max(1, int(self._per * self._duty)))
        if (not on) and len(vt) > 0:
            vt = [[0.0, 0.0, -5.0]] * len(vt)

        self._mesh.GetPointsAttr().Set([Gf.Vec3f(*[float(q) for q in v]) for v in vt])
        self._mesh.GetFaceVertexCountsAttr().Set(ct)
        self._mesh.GetFaceVertexIndicesAttr().Set(ix)
        # extent 를 매번 채운다. extent 없는 메시는 렌더러가 빈 박스로 보고 컬링해
        # 아무것도 안 그린다 (실측).
        if vt:
            va = np.asarray([[float(q) for q in v] for v in vt])
            self._mesh.GetExtentAttr().Set([Gf.Vec3f(*[float(q) for q in va.min(0)]),
                                            Gf.Vec3f(*[float(q) for q in va.max(0)])])
        im = UsdGeom.Imageable(self._mesh.GetPrim())
        if len(ct) > 0:
            im.MakeVisible()
        else:
            im.MakeInvisible()

        if not self._said:
            self._said = True
            self._log("V4-70 자국 첫 갱신: 명중 %d/%d, 사각형 %d개"
                      % (int(land.sum()), len(dirs), len(ct)))
        if int(land.sum()) > 0 and not self._hit1:
            self._hit1 = True
            self._log("V4-70 자국 첫 명중: %d/%d, 사각형 %d개"
                      % (int(land.sum()), len(dirs), len(ct)))
        return len(ct)


class Recognizer:
    """지금 대상 상품의 QR 타일 자세와, 인식 표시(초록 LED · 빨간 테두리)를 켜 두는 시간을 들고 있다.

    인식 여부는 여기서 정하지 않는다 -- 스캐너 카메라가 기대 코드를 실제로 읽었을 때만 인식이다
    (`scorer/qr_decode.py`). 기하 조건으로 인식을 정하는 방식은 양산(수집) 파이프라인에만 있다.
    """

    def __init__(self, tiles, log=None):
        self._tiles = tiles
        self._log = log or _noop
        # 기록판은 물리 120 Hz 를 4 걸음마다 한 프레임으로 남긴다 -> 10 초 = 300 프레임.
        self._hold = int(round(float(os.environ.get("TASKC_SHEET_HIT_S", "10")) * 30.0))
        self._slot = None

    def set_slot(self, slot, slug):
        """슬롯(대상 물체)이 바뀌면 타일을 간다."""
        if self._slot == int(slot):
            return
        t = self._tiles[slug]
        self._tpos = np.asarray(t["pos"], dtype=float)
        self._tnrm = np.asarray(t["normal"], dtype=float)
        self._slot = int(slot)
        self._log("슬롯 %d(%s) 타일 갱신" % (int(slot), slug))

    def tile_world(self, prod_pos, prod_rot):
        """지금 대상 타일의 세계 좌표 (중심, 법선). 판독기가 거리를 재는 데 쓴다."""
        return prod_pos + prod_rot @ self._tpos, prod_rot @ self._tnrm
