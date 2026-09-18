# Copyright 2026.
#
# 스캐너 카메라로 QR 을 실제로 읽는다. 평가표가 요구하는 판독 방식이다 --
# 「판독은 스캐너 카메라 이미지로 한다. 실물 스캐너가 보는 것과 같은 시점이어야 하므로
# 다른 카메라를 쓰지 않는다. 디코더가 그 시도 상품의 기대 코드 문자열을 반환해야 한다.」
#
# 매 프레임 읽지 않는다. 렌더가 비싸고, 실물 스캐너도 늘 읽고 있지 않다.
#
#     1  판독 시작     빨간 빔이 대상 상품에 닿아 있고 빔 출발선에서 QR 타일까지 18 cm 이내 (2026-09-18)
#     2  이미지 판독   그 프레임만 스캐너캠을 렌더해 디코드한다
#     3  인식 후       기대 코드가 읽히면 1 초만 더 읽고 끈다. 빔이 떨어졌다 다시 닿거나 대상이 바뀌면 다시 켠다
#
# 카메라 사양은 수집 파이프라인의 `ScanCam`(QR-136: 800x500, focal 31.43 mm, 조리개 20.955 / 13.097 mm,
# 방출점 15 cm 에서 가로 8 x 세로 5 cm)에서 왔고, 2026-09-18 에 조리개만 30% 넓혔다(아래 SCAN_CAM).
# 눈은 빔 출발선 앞 3 cm, 겨눔점은 30 cm 앞이다.

import os

__all__ = ["SCAN_CAM", "QrReader", "scan_cam_cfg"]

# (폭, 높이, 초점거리 mm, 가로조리개 mm, 세로조리개 mm, 눈 거리 m, 겨눔 거리 m)
# 2026-09-18: 화각을 30% 넓혔다 (조리개 20.955 x 13.097 -> 27.2415 x 17.0261 mm, 초점거리는 그대로).
# 방출점 15 cm 에서 가로 10.4 x 세로 6.5 cm 를 본다. 세로 시야가 좁아 빔보다 2~3 cm 높게 든 제시가 잘리던 것을 줄인다.
SCAN_CAM = (800, 500, 31.43, 27.2415, 17.0261, 0.03, 0.30)


def scan_cam_cfg():
    """`CameraCfg` 를 만든다. Isaac 이 있는 곳에서만 부른다."""
    import isaaclab.sim as sim_utils
    from isaaclab.sensors import CameraCfg
    w, h, foc, ha, va, _, _ = SCAN_CAM
    return CameraCfg(
        prim_path="{ENV_REGEX_NS}/ScanCam", update_period=0.0,
        height=h, width=w, data_types=["rgb"],
        spawn=sim_utils.PinholeCameraCfg(focal_length=foc, horizontal_aperture=ha,
                                         vertical_aperture=va, clipping_range=(0.02, 5.0)))


class QrReader:
    """빨간 빔이 대상 상품에 닿아 있고 QR 까지 18 cm 이내인 프레임에서만 스캐너캠을 읽는다."""

    def __init__(self, cam, expect_by_slug, log=None, render_n=None):
        self.cam = cam
        self.expect = dict(expect_by_slug)
        self._log = log or (lambda m: None)
        # 판독 직전 RTX 를 수렴시키는 렌더 횟수. 적으면 얼룩진 그림을 읽는다.
        self.render_n = int(os.environ.get("TASKC_QR_RENDER_N", render_n or 8))
        # 판독 시작 기준: 빨간 빔이 대상 상품에 닿아 있고, 빔 출발선에서 QR 타일까지의 직선거리가 이 값 이내.
        self.gate_dmax = float(os.environ.get("TASKC_QR_GATE_DMAX_MM", "180"))
        # 기대 코드가 읽힌 뒤 이만큼만 더 읽고 끈다. 빔이 상품에서 떨어지거나 대상이 바뀌면 다시 켜진다.
        self.keep_s = float(os.environ.get("TASKC_QR_KEEP_S", "1.0"))
        self._armed, self._stop_at, self._slug = True, None, None
        self.events = []
        self._tries = 0
        # zxing 이 없으면 판독이 조용히 0점이 된다. 시작할 때 한 번 시험해 크게 알린다 (판독 동작은 그대로다).
        try:
            import zxingcpp  # noqa: F401
            self._zx_ok = True
        except Exception as e:
            self._zx_ok = False
            self._log("!! [QR] zxing-cpp 가 없어 QR 을 읽을 수 없다 (%r). 판독(Sub2-2)·배치(Sub3)가 전부 0점이 된다. "
                      "./run/setup.sh 로 이미지를 다시 빌드하거나, 컨테이너 안에서 "
                      "`${ISAACLAB_PATH}/_isaac_sim/python.sh -m pip install --no-deps zxing-cpp==3.1.1` 을 실행하라." % (e,))

    def in_range(self, b0, bd, tile_pos, n_quads):
        """지금 프레임에 판독을 시도하나. `(시도하나, 횡이탈mm, 축거리mm)`.

        조건은 둘이다 -- 빨간 빔이 대상 상품에 닿아 있고(자국 사각형 1개 이상), 빔 출발선에서 QR 타일까지의
        직선거리가 `gate_dmax`(18 cm) 이내. 읽히는지는 그림이 정한다. 횡이탈 · 축거리는 기록용으로만 돌려준다.
        """
        import numpy as np
        v = np.asarray(tile_pos, dtype=float) - np.asarray(b0, dtype=float)
        d = np.asarray(bd, dtype=float)
        al = float(v @ d)
        lat = float(np.linalg.norm(v - d * al)) * 1000.0
        ok = bool(n_quads) and float(np.linalg.norm(v)) * 1000.0 <= self.gate_dmax
        return ok, lat, al * 1000.0

    def _place(self, sim, b0, bd):
        import torch
        _, _, _, _, _, d_eye, d_tgt = SCAN_CAM
        eye = [float(b0[i] + bd[i] * d_eye) for i in range(3)]
        tgt = [float(b0[i] + bd[i] * d_tgt) for i in range(3)]
        dev = sim.device
        self.cam.set_world_poses_from_view(
            torch.tensor([eye], dtype=torch.float32, device=dev),
            torch.tensor([tgt], dtype=torch.float32, device=dev))

    def try_read(self, sim, b0, bd, slug, t, in_gate):
        """게이트 안이면 한 프레임 읽는다. 읽히면 `(코드, 맞았나)`, 아니면 None."""
        if self.cam is None or not self._zx_ok:
            return None
        if slug != self._slug or not in_gate:          # 대상이 바뀌었거나 빔이 떨어졌다 -> 다시 켠다
            self._slug, self._armed, self._stop_at = slug, True, None
        if not in_gate or not self._armed:
            return None
        if self._stop_at is not None and t > self._stop_at:
            self._armed = False                        # 인식 뒤 keep_s 가 지났다 -> 끈다
            return None
        try:
            import numpy as np
            import zxingcpp
            self._place(sim, b0, bd)
            for _ in range(self.render_n):
                sim.render()
            self.cam.update(0.0)
            img = np.asarray(self.cam.data.output["rgb"][0, ..., :3].cpu(), dtype=np.uint8)
            res = zxingcpp.read_barcodes(img)
            self._tries += 1
            if not res:
                return None
            text = res[0].text
            ok = bool(text and text == self.expect.get(slug))
            self.events.append(dict(ok=ok, slug=slug, t=round(float(t), 3), text=text))
            if ok and self._stop_at is None:
                self._stop_at = t + self.keep_s
                self._log("[QR] %s 판독 O (%s)  -- %.0f초 더 읽고 끈다" % (slug, text, self.keep_s))
            elif not ok:
                self._log("[QR] %s 다른 값 (%s)" % (slug, text))
            return (text, ok)
        except Exception as e:
            self._log("[QR] 판독 불가: %r" % (e,))
            return None

    def report(self):
        return {"decode": self.events, "tries": self._tries, "zxing": bool(self._zx_ok),
                "gate_dmax_mm": self.gate_dmax, "keep_s": self.keep_s}
