"""실기 ZED Mini 처럼 머리 두 눈 그림을 만든다 -- 과제 A · B · C 공용 (zed_record.py 가 쓴다).

방식은 둘이다. 같은 폴더에 `internal_raw_lens.json` 이 있으면 **원본 렌즈 방식**, 없으면 **공개 값 방식**이다
(환경 변수 ZED_DEPTH_MODE=rect · raw 로 고를 수도 있다).

  원본 렌즈 방식  두 눈을 넓은 바늘구멍 그림(WIDE_WH, fx = WIDE_F, 중심 한가운데)으로 그리고, 원본 픽셀마다 실기 원본 렌즈
                  (어안형 왜곡, internal_raw_lens.json)의 광선으로 가져온다. 이 원본 그림을 ZED SDK 가 실기처럼 정류한다.
  공개 값 방식    두 눈을 정류된 실기 값(공지 camera_intrinsics_2026-10-05.json 의 head_l: fx = fy 363.97, 중심 (336.63,
                  180.86))으로 바로 그린다. Isaac 은 중심점을 옮기지 못하므로(Isaac Lab utils/sensors.py 는 aperture
                  offset 을 0 으로 둔다) 674x391 로 그려 [14:390, 0:672] 를 자른다 -> 중심 (336.5, 181.0). 두 눈 사이는
                  ZED Mini 공칭 63 mm.

어느 방식이든 그림에는 렌즈 흐림 · 가장자리 어두워짐 · 센서 잡음을 넣는다 (Sensor). 좌표는 ROS 기준(첫 픽셀의 가운데가 0)이다.
"""
import json
import os

import cv2
import numpy as np

W, H = 672, 376
HERE = os.path.dirname(os.path.abspath(__file__))
INTERNAL_PATH = os.path.join(HERE, "internal_raw_lens.json")

# 공개 값 (공지 camera_intrinsics_2026-10-05.json · ZED Mini 공칭)
RECT_K_PUBLIC = (363.9717712402344, 363.9717712402344, 336.6287536621094, 180.86094665527344)
BASELINE_NOMINAL_M = 0.063
CROP_WH, CROP_RC = (674, 391), (14, 0)
CROP_K = (RECT_K_PUBLIC[0], RECT_K_PUBLIC[1], 336.5, 181.0)      # 674x391 를 [14:390, 0:672] 로 자른 그림의 K

# 원본 렌즈 방식의 넓은 그림 -- 원본 픽셀의 모든 광선이 들어가는 크기 (어안형이라 모서리가 약 57°, raw_maps 가 확인한다)
WIDE_F = 386.0
WIDE_WH = (1180, 700)


def load_internal():
    if not os.path.exists(INTERNAL_PATH):
        return None
    d = json.load(open(INTERNAL_PATH))
    return {"left": {"K": tuple(d["left"]["K"]), "D": tuple(d["left"]["D"])},
            "right": {"K": tuple(d["right"]["K"]), "D": tuple(d["right"]["D"])},
            "baseline_m": float(d["baseline_m"])}


RAW = load_internal()
# 환경 변수 ZED_DEPTH_MODE=rect 면 파일이 있어도 공개 값 방식으로 돈다 (depth 서버와 재생기에 같은 값을 준다).
MODE = os.environ.get("ZED_DEPTH_MODE") or ("raw" if RAW is not None else "rect")
if MODE not in ("raw", "rect") or (MODE == "raw" and RAW is None):
    raise SystemExit(f"[zed] ZED_DEPTH_MODE={MODE!r} -- rect 이거나, raw 면 {INTERNAL_PATH} 가 있어야 한다")


def render_spec(mode=MODE):
    """두 눈을 그릴 바늘구멍 카메라: (가로, 세로, fx, 두 눈 사이 m)."""
    if mode == "raw":
        return WIDE_WH[0], WIDE_WH[1], WIDE_F, RAW["baseline_m"]
    return CROP_WH[0], CROP_WH[1], CROP_K[0], BASELINE_NOMINAL_M


def crop(img):
    return img[CROP_RC[0]:CROP_RC[0] + H, CROP_RC[1]:CROP_RC[1] + W]


def wide_center():
    """Isaac 은 그림 한가운데를 중심으로 그린다 -- ROS 기준으로 ((W-1)/2, (H-1)/2)."""
    return (WIDE_WH[0] - 1) / 2.0, (WIDE_WH[1] - 1) / 2.0


def raw_maps(eye):
    """원본 그림 픽셀 (u, v) -> 넓은 바늘구멍 그림의 자리 (map_x, map_y). 어안형(equidistant) 모델의 역."""
    fx, fy, cx, cy = RAW[eye]["K"]
    Kr = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], np.float64)
    Dr = np.array(RAW[eye]["D"], np.float64).reshape(4, 1)
    u, v = np.meshgrid(np.arange(W, dtype=np.float64), np.arange(H, dtype=np.float64))
    xy = cv2.fisheye.undistortPoints(np.stack([u.ravel(), v.ravel()], -1).reshape(-1, 1, 2), Kr, Dr).reshape(H, W, 2)
    wcx, wcy = wide_center()
    mx = (WIDE_F * xy[..., 0] + wcx).astype(np.float32)
    my = (WIDE_F * xy[..., 1] + wcy).astype(np.float32)
    if mx.min() < 0 or my.min() < 0 or mx.max() > WIDE_WH[0] - 1 or my.max() > WIDE_WH[1] - 1:
        raise ValueError(f"{eye}: 원본 광선이 넓은 그림 밖으로 나간다 -- WIDE_WH 를 키운다")
    return mx, my


def rect_maps(K_rect):
    """정류된 그림 픽셀 -> 넓은 바늘구멍 그림의 자리. 정류 회전이 0 이라 같은 광선이고 depth(앞축 거리)도 같다."""
    fx, fy, cx, cy = K_rect
    u, v = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    wcx, wcy = wide_center()
    return (WIDE_F * (u - cx) / fx + wcx).astype(np.float32), (WIDE_F * (v - cy) / fy + wcy).astype(np.float32)


class Sensor:
    """렌즈 흐림 · 가장자리 어두워짐 · 센서 잡음. 잡음은 밝기에 따라 커지고(빛 알갱이) 바닥이 있다(읽기 잡음):
    sigma = sqrt(shot * 밝기 + read^2), 8 bit 기준. 프레임마다 · 눈마다 새로 뽑는다."""

    def __init__(self, seed=None, blur_sigma=0.6, vignette=0.2, shot=0.04, read=2.0):
        self.rng = np.random.default_rng(seed)
        self.blur_sigma, self.vignette, self.shot, self.read = blur_sigma, vignette, shot, read
        u, v = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
        r2 = ((u - W / 2) ** 2 + (v - H / 2) ** 2) / ((W / 2) ** 2 + (H / 2) ** 2)
        self.gain = (1.0 - vignette * r2)[..., None]

    def __call__(self, rgb):
        x = rgb.astype(np.float32) * self.gain
        if self.blur_sigma > 0:
            x = cv2.GaussianBlur(x, (0, 0), self.blur_sigma)
        sigma = np.sqrt(self.shot * np.clip(x, 0, 255) + self.read ** 2)
        x = x + self.rng.standard_normal(x.shape).astype(np.float32) * sigma
        return np.clip(np.rint(x), 0, 255).astype(np.uint8)


class Eyes:
    """그린 두 눈(넓은 그림 또는 674x391)과 왼쪽 정답 depth 를, ZED SDK 에 보낼 두 그림과 정류된 왼쪽 그림 픽셀의 정답 depth 로."""

    def __init__(self, mode=MODE):
        self.mode = mode
        self.maps = {e: raw_maps(e) for e in ("left", "right")} if mode == "raw" else None
        self._rect = {}

    def to_sensor(self, left, right):
        if self.mode == "raw":
            return (cv2.remap(left, *self.maps["left"], cv2.INTER_LINEAR),
                    cv2.remap(right, *self.maps["right"], cv2.INTER_LINEAR))
        return np.ascontiguousarray(crop(left)), np.ascontiguousarray(crop(right))

    def gt_depth_mm(self, depth_m, K_rect):
        """렌더러의 depth(앞축 거리, m)를 SDK 가 정류한 왼쪽 그림의 픽셀로 옮겨 uint16 mm (0 = 값 없음)."""
        if self.mode == "raw":
            if self._rect.get("K") != tuple(K_rect):
                self._rect = {"K": tuple(K_rect), "maps": rect_maps(K_rect)}
            d = cv2.remap(depth_m.astype(np.float32), *self._rect["maps"], cv2.INTER_NEAREST)
        else:
            d = crop(depth_m)
        return np.where(np.isfinite(d), np.clip(np.rint(d * 1000.0), 0, 65535), 0).astype(np.uint16)


def write_calib(path, mode=MODE, baseline_error=0.0):
    """ZED SDK 의 optional_opencv_calibration_file (Stereolabs zed-opencv-calibration 의 saveCalibOpenCV 와 같은 키).
    두 눈 사이는 그린 값 x (1 + baseline_error) -- calibration 오차."""
    def mat(name, rows, cols, vals):
        return (f"{name}: !!opencv-matrix\n   rows: {rows}\n   cols: {cols}\n   dt: d\n"
                f"   data: [ {', '.join(repr(float(v)) for v in vals)} ]\n")
    txt = "%YAML:1.0\n---\n" + f"Size: [ {W}, {H} ]\n"
    if mode == "raw":
        for side, c in (("LEFT", RAW["left"]), ("RIGHT", RAW["right"])):
            fx, fy, cx, cy = c["K"]
            txt += mat(f"K_{side}", 3, 3, [fx, 0, cx, 0, fy, cy, 0, 0, 1])
        txt += mat("D_LEFT_FE", 1, 4, RAW["left"]["D"]) + mat("D_RIGHT_FE", 1, 4, RAW["right"]["D"])
        base_mm = 1000.0 * RAW["baseline_m"]
    else:
        fx, fy, cx, cy = CROP_K
        for side in ("LEFT", "RIGHT"):
            txt += mat(f"K_{side}", 3, 3, [fx, 0, cx, 0, fy, cy, 0, 0, 1])
        txt += mat("D_LEFT", 1, 5, [0] * 5) + mat("D_RIGHT", 1, 5, [0] * 5)
        base_mm = 1000.0 * BASELINE_NOMINAL_M
    txt += mat("R", 3, 1, [0, 0, 0]) + mat("T", 3, 1, [-base_mm * (1.0 + baseline_error), 0, 0])
    open(path, "w").write(txt)
