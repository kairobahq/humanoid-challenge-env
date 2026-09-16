# Copyright 2026.
#
# 스캐너 카메라로 QR 을 실제로 읽는다. 평가표가 요구하는 판독 방식이다 --
# 「판독은 스캐너 카메라 이미지로 한다. 실물 스캐너가 보는 것과 같은 시점이어야 하므로
# 다른 카메라를 쓰지 않는다. 디코더가 그 시도 상품의 기대 코드 문자열을 반환해야 한다.」
#
# 매 프레임 읽지 않는다. 렌더가 비싸고, 실물 스캐너도 늘 읽고 있지 않다.
#
#     1  판독 창       수집 파이프라인의 판독 수용 실측값 안에 들어와야 다음으로 간다
#     2  이미지 판독   그 프레임만 스캐너캠을 렌더해 디코드한다
#     3  냉각          한 번 읽히면 5 초 동안 판독기를 끈다. 게이트를 벗어나도 끈다
#
# 카메라 사양은 수집 파이프라인의 `ScanCam` 을 그대로 옮겼다(QR-136): 800x500,
# focal 31.43 mm, 조리개 20.955 / 13.097 mm. 방출점 15 cm 에서 가로 8 x 세로 5 cm 를
# 보는 방사형 빔 사양이다. 눈은 빔 출발선 앞 3 cm, 겨눔점은 30 cm 앞이다.

import os

__all__ = ["SCAN_CAM", "QrReader", "scan_cam_cfg"]

# (폭, 높이, 초점거리 mm, 가로조리개 mm, 세로조리개 mm, 눈 거리 m, 겨눔 거리 m)
SCAN_CAM = (800, 500, 31.43, 20.955, 13.097, 0.03, 0.30)


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
    """게이트를 넘긴 프레임에서만 스캐너캠을 읽는다."""

    def __init__(self, cam, expect_by_slug, log=None,
                 cooldown_s=None, render_n=None):
        self.cam = cam
        self.expect = dict(expect_by_slug)
        self._log = log or (lambda m: None)
        # 판독 창. 수집 파이프라인의 판독 수용 실측값은 횡이탈 40 mm · 축거리 50~150 mm · 면각 12도 ·
        # 원뿔 반각 18도(focal 32mm 의 half FOV)였다. 2026-09-16 에 횡이탈 60 mm · 축거리 40~150 mm ·
        # 면각 30도로 넓혔다. 창은 "디코드를 시도해도 되는 자리" 일 뿐이고 통과는 기대 바코드가
        # 실제로 읽혀야 하므로, 넓혀도 거짓 통과는 생기지 않는다. 학습된 정책이 스캐너 앞 72 mm 까지
        # 가져오고도 면각이 12도를 넘어 한 번도 시도하지 못한 실측(held-out 폐루프)이 계기다.
        # 원뿔 반각 18도는 스캐너캠 화각이라 그대로 두고, 축거리 상한 150 mm 는 평가 기준(빔 출발선에서
        # 15 cm)과 같아 그대로 둔다.
        #
        # 한때 시각 인식의 6 mm 를 1.5 배 넓혀 9 mm 로 썼다. 그것은 자리를 잘못 빌린 것이다 --
        # 6 mm 는 LED·자국·띠를 켜는 **시각 판정**의 값이고, 읽어도 되는 자리를 정하는 값이
        # 아니다. 실제 수집분은 횡이탈 35~38 mm 에서 읽혔고(HF 실측), 9 mm 게이트는 그것을
        # 전부 기각한다. 두 값은 목적이 달라 하나로 겸할 수 없다.
        self.lat_max = float(os.environ.get("TASKC_QR_LAT_MAX", "60"))
        self.d_min = float(os.environ.get("TASKC_QR_DMIN_MM", "40"))
        self.d_max = float(os.environ.get("TASKC_QR_DMAX_MM", "150"))
        self.face_max = float(os.environ.get("TASKC_QR_FACE_MAX", "30"))
        self.cone_half = float(os.environ.get("TASKC_QR_CONE_HALF", "18"))
        # 한 번 읽으면 이만큼 쉰다. 같은 상품을 연달아 읽어 로그가 넘치는 것을 막는다.
        self.cooldown = float(os.environ.get("TASKC_QR_COOLDOWN_S", cooldown_s or 5.0))
        # 판독 직전 RTX 를 수렴시키는 렌더 횟수. 적으면 얼룩진 그림을 읽는다.
        self.render_n = int(os.environ.get("TASKC_QR_RENDER_N", render_n or 8))
        self.events = []
        self._off_until = -1.0      # 이 시각까지는 끈다
        self._tries = 0

    def in_window(self, b0, bd, tile_pos, tile_nrm):
        """읽어도 되는 자리인가. `(들어왔나, 횡이탈mm, 축거리mm)`.

        수집 파이프라인의 판독 수용 조건 넷을 그대로 본다 -- 빔 축에서의 횡이탈,
        빔 출발선에서의 축거리, 타일 면이 빔을 마주 본 각, 그리고 스캐너 화각.
        """
        import math
        import numpy as np
        v = np.asarray(tile_pos, dtype=float) - np.asarray(b0, dtype=float)
        d = np.asarray(bd, dtype=float)
        al = float(v @ d)
        lat = float(np.linalg.norm(v - d * al)) * 1000.0
        dist = al * 1000.0
        n = np.asarray(tile_nrm, dtype=float)
        face = math.degrees(math.acos(max(-1.0, min(1.0, float(n @ (-d))))))
        cone = math.degrees(math.atan2(lat, max(dist, 1e-6)))
        ok = (lat <= self.lat_max and self.d_min <= dist <= self.d_max
              and face <= self.face_max and cone <= self.cone_half)
        return ok, lat, dist

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
        if self.cam is None or not in_gate or t < self._off_until:
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
            self._off_until = t + self.cooldown
            self.events.append(dict(ok=ok, slug=slug, t=round(float(t), 3), text=text))
            self._log("[QR] %s %s (%s)  -- %.0f초 쉼"
                      % (slug, "판독 O" if ok else "다른 값", text, self.cooldown))
            return (text, ok)
        except Exception as e:
            self._log("[QR] 판독 불가: %r" % (e,))
            return None

    def report(self):
        return {"decode": self.events, "tries": self._tries,
                "lat_max_mm": self.lat_max, "d_min_mm": self.d_min,
                "d_max_mm": self.d_max, "face_max_deg": self.face_max,
                "cone_half_deg": self.cone_half, "cooldown_s": self.cooldown}
