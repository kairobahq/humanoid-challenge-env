"""실기 ZED Mini 같은 머리 depth 를 재생 중에 남긴다 -- 과제 A · B · C 재생기(task_*_replay.py)의 `--zed-depth` 가 부른다.

시뮬의 depth 는 렌더러가 주는 정답(노이즈 · 왜곡 없음)이지만, 실기 로봇이 주는 `head_l_depth` 는 머리 ZED Mini 의 두 그림을
ZED SDK(NEURAL)가 계산한 것이라 무늬 없는 넓은 면이 휘고, 물체 가장자리가 섞이고, 무늬 있는 면도 1~2 % 멀게 읽힌다
(공지 2026-10-05). 여기서는 같은 계산을 시뮬에서 한다:

  1. 머리에 두 눈(zed_left · zed_right)을 단다 -- 원래 head_cam 은 그대로 두고 따로 단다 (camera_cfgs).
  2. 매장 조명의 세기와 색온도를 돌릴 때마다 무작위로 바꾼다 (jitter_lights).
  3. 기록 프레임마다 두 그림을 실기 렌즈 그림으로 만들고(zed_camera.Eyes) 렌즈 흐림 · 센서 잡음을 넣어(zed_camera.Sensor)
     ZED SDK 컨테이너의 zed_depth_server.py 로 보내 depth 를 받는다. SDK 가 정류한 왼쪽 그림이 head_l, 그 depth 가
     head_l_depth 다. 렌더러의 정답 depth 를 같은 픽셀로 옮겨 depth_sim 으로 같이 남긴다 (Recorder).

남기는 것 (--zed-out/<이름>/):
    head_l/<프레임>.jpg · depth_zed/<프레임>.png · depth_sim/<프레임>.png   (depth 는 uint16 mm 16-bit PNG, 0 = 값 없음)
    raw_l/<프레임>.jpg   ZED 에 보낸 왼쪽 그림 (50 프레임마다)
    compare.mp4          네 칸: head_l · 시뮬 depth · ZED depth · ZED - 시뮬 (±50 mm, 파랑 = ZED 가 가깝게, 빨강 = 멀게)
    stats.csv            프레임마다 시뮬 depth 3 m 안 픽셀의 |ZED - 시뮬| 중앙값 · 90 % · 20 mm 넘는 비율 · ZED 값 없음
    summary.json         설정(방식 · 조명 · 잡음 · 카메라)과 시뮬 depth 거리 구간별 차이

이 파일은 Isaac 을 불러오지 않는다 -- Isaac 을 쓰는 것은 함수 안에서 불러오므로 AppLauncher 앞에서 읽어도 된다.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zed_camera as ZC  # noqa: E402

NEAR_MM = 3000
DIST_BINS = [(0, 600), (600, 900), (900, 1200), (1200, 2000), (2000, 3000)]


def add_args(parser):
    g = parser.add_argument_group("실기 같은 머리 depth (zed_depth/)")
    g.add_argument("--zed-depth", action="store_true",
                   help="머리 두 눈을 달아 ZED SDK depth 를 남긴다 (ZED 컨테이너가 떠 있어야 한다: docker/zed.yaml)")
    g.add_argument("--zed-server", default="127.0.0.1:7300", help="zed_depth_server.py 의 HOST:PORT")
    g.add_argument("--zed-out", default="/workspace/user/zed_depth", help="남길 곳")
    g.add_argument("--zed-every", type=int, default=1, help="기록 몇 프레임마다 depth 를 낼까")
    g.add_argument("--zed-frames", type=int, default=0, help="앞에서 몇 번만 낼까 (0 = 전부, 시험용)")
    g.add_argument("--zed-no-sensor", action="store_true", help="렌즈 흐림 · 가장자리 어두워짐 · 센서 잡음을 넣지 않는다")
    g.add_argument("--zed-no-video", action="store_true", help="compare.mp4 를 만들지 않는다")
    g.add_argument("--light-scale", type=float, nargs=2, default=(1.5, 3.0), metavar=("LO", "HI"),
                   help="매장 조명 세기 배수의 범위 (매장 씬 원래 값 = 1). 3 배를 넘으면 흰 면이 하얗게 날기 시작한다")
    g.add_argument("--light-temp", type=float, nargs=2, default=(3500.0, 6500.0), metavar=("LO", "HI"),
                   help="색온도 범위 (K)")
    g.add_argument("--light-seed", type=int, default=None, help="조명 씨앗. 안 주면 돌릴 때마다 새로 뽑는다")
    g.add_argument("--no-light-jitter", action="store_true", help="매장 조명을 바꾸지 않는다")


def load_realcam():
    """scripts/FFW_SG2_REAL_cameras.py -- 세 과제가 같이 쓰는 카메라 값 파일."""
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "FFW_SG2_REAL_cameras.py")
    spec = importlib.util.spec_from_file_location("FFW_SG2_REAL_cameras", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def camera_cfgs(realcam=None):
    """머리 두 눈의 CameraCfg {"zed_left": ..., "zed_right": ...}. head_link2 에 붙고, 왼쪽 눈은 head_cam 과 같은 자리,
    오른쪽 눈은 두 눈 사이만큼 오른쪽(head_link2 의 -y)이다. 왼쪽 눈은 정답 depth 도 낸다. realcam 을 안 주면
    scripts/FFW_SG2_REAL_cameras.py 를 읽는다."""
    import isaaclab.sim as sim_utils
    from isaaclab.sensors import CameraCfg
    realcam = realcam or load_realcam()
    w, h, fx, base = ZC.render_spec()
    spec = realcam.CAMERA_SPECS["cam_head"]
    p = spec["offset_pos"]
    out = {}
    for eye, dy in (("left", 0.0), ("right", base)):
        cfg = realcam.head_camera_cfg(
            width=w, height=h, update_period=1.0e9, update_latest_camera_pose=True,
            data_types=["rgb", "distance_to_image_plane"] if eye == "left" else ["rgb"],
            spawn=sim_utils.PinholeCameraCfg(focal_length=fx * realcam.H_APERTURE / w,
                                             focus_distance=spec["focus_distance"],
                                             horizontal_aperture=realcam.H_APERTURE,
                                             clipping_range=spec["clipping_range"]),
            offset=CameraCfg.OffsetCfg(pos=(p[0], p[1] - dy, p[2]), rot=spec["offset_rot"], convention="world"))
        cfg.prim_path = cfg.prim_path.replace("/cam_head", f"/zed_{eye}")
        out[f"zed_{eye}"] = cfg
    return out


def jitter_lights(root_path, args):
    """root_path 아래 조명(매장 씬의 돔 · 해 · 냉장고 RectLight)의 세기와 색온도를 바꾼다. 바꾼 값을 돌려준다.
    sim.reset() 앞에서 부른다. --no-light-jitter 면 아무것도 안 하고 None."""
    if args.no_light_jitter:
        return None
    import omni.usd
    from pxr import Usd, UsdLux
    seed = args.light_seed
    if seed is None:
        seed = int(np.random.SeedSequence().entropy % (2 ** 31))
    rng = np.random.default_rng(seed)
    scale, temp = float(rng.uniform(*args.light_scale)), float(rng.uniform(*args.light_temp))
    root = omni.usd.get_context().get_stage().GetPrimAtPath(root_path)
    if not (root and root.IsValid()):
        raise SystemExit(f"[zed] 조명을 찾을 매장 프림이 없다: {root_path}")
    n = 0
    for prim in Usd.PrimRange(root):
        if not (prim.IsA(UsdLux.BoundableLightBase) or prim.IsA(UsdLux.NonboundableLightBase)):
            continue
        light = UsdLux.LightAPI(prim)
        a = light.GetIntensityAttr()
        a.Set(float(a.Get() or 0.0) * scale)
        light.CreateEnableColorTemperatureAttr().Set(True)
        light.CreateColorTemperatureAttr().Set(temp)
        n += 1
    print(f"[zed] 조명 {n} 개: 세기 x{scale:.2f} · 색온도 {temp:.0f} K (씨앗 {seed} -- --light-seed {seed} 로 다시 낸다)",
          flush=True)
    return {"lights": n, "seed": seed, "scale": round(scale, 3), "temperature_k": round(temp, 1),
            "scale_range": list(args.light_scale), "temp_range": list(args.light_temp)}


# ---------------------------------------------------------------- 견주기 · 그림
def frame_stats(d_sim, d_zed):
    s_, z_ = d_sim.astype(np.float32), d_zed.astype(np.float32)
    near = (s_ > 0) & (s_ <= NEAR_MM)
    both = near & (z_ > 0)
    out = {"pixels": int(near.sum()), "zed_holes": round(1.0 - both.sum() / max(int(near.sum()), 1), 4)}
    if both.any():
        e = z_[both] - s_[both]
        a = np.abs(e)
        out.update(median_mm=round(float(np.median(e)), 1), abs_median_mm=round(float(np.median(a)), 1),
                   abs_p90_mm=round(float(np.percentile(a, 90)), 1),
                   over20=round(float((a > 20).mean()), 4), over50=round(float((a > 50).mean()), 4))
    return out


def accumulate(acc, d_sim, d_zed):
    """거리 구간마다 오차(ZED - 시뮬, mm)의 도수 -1000..1000 (밖은 끝 칸) 과 ZED 가 값을 못 낸 수."""
    s_, z_ = d_sim.astype(np.int32), d_zed.astype(np.int32)
    for lo, hi in DIST_BINS:
        m = (s_ > lo) & (s_ <= hi)
        b = acc.setdefault(f"{lo}-{hi}", {"hist": np.zeros(2001, np.int64), "holes": 0, "pixels": 0})
        b["pixels"] += int(m.sum())
        b["holes"] += int((m & (z_ == 0)).sum())
        e = (z_ - s_)[m & (z_ > 0)]
        b["hist"] += np.bincount(np.clip(e, -1000, 1000) + 1000, minlength=2001)


def hist_summary(h):
    n = int(h.sum())
    if not n:
        return None
    vals = np.arange(-1000, 1001)
    cdf = np.cumsum(h) / n
    habs = np.zeros(1001, np.int64)
    np.add.at(habs, np.abs(vals), h)
    cabs = np.cumsum(habs) / n
    return {"n": n, "median_mm": int(vals[np.searchsorted(cdf, 0.5)]),
            "abs_median_mm": int(np.searchsorted(cabs, 0.5)), "abs_p90_mm": int(np.searchsorted(cabs, 0.9)),
            "over20": round(float(1.0 - cabs[20]), 4), "over50": round(float(1.0 - cabs[50]), 4)}


def colour_depth(d, lo=400, hi=2000):
    import cv2
    x = ((np.clip(d.astype(np.float32), lo, hi) - lo) / (hi - lo) * 255).astype(np.uint8)
    c = cv2.applyColorMap(x, cv2.COLORMAP_TURBO)
    c[d == 0] = 0
    return c


def colour_diff(d_sim, d_zed, lim=50.0):
    """ZED - 시뮬. 파랑 = ZED 가 가깝게, 흰색 = 같음, 빨강 = ZED 가 멀게. 검정 = 어느 한쪽 값 없음."""
    t = np.clip((d_zed.astype(np.float32) - d_sim.astype(np.float32)) / lim, -1.0, 1.0)
    c = (np.dstack([np.where(t < 0, 1.0, 1.0 - t), 1.0 - np.abs(t), np.where(t > 0, 1.0, 1.0 + t)]) * 255).astype(np.uint8)
    c[(d_sim == 0) | (d_zed == 0)] = 0
    return c


def compare_panel(head_l, d_sim, d_zed, i, t, st):
    """2x2: head_l · 시뮬 depth / ZED depth · ZED - 시뮬. 글씨는 cv2 가 한글을 못 그려 영어로 쓴다."""
    import cv2

    def titled(img, text):
        bar = np.zeros((26, img.shape[1], 3), np.uint8)
        cv2.putText(bar, text, (8, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        return np.vstack([bar, img])
    a = titled(np.ascontiguousarray(head_l[..., ::-1]), f"head_l (ZED rectified)   frame {i}  t {t:.1f} s")
    b = titled(colour_depth(d_sim), "sim depth (renderer)   400-2000 mm")
    c = titled(colour_depth(d_zed), "ZED depth (NEURAL)   400-2000 mm")
    d = titled(colour_diff(d_sim, d_zed), f"ZED - sim  +-50 mm  |  median |diff| {st.get('abs_median_mm', '-')} mm  "
                                          f">20mm {100 * st.get('over20', 0):.0f}%  holes {100 * st['zed_holes']:.0f}%")
    return np.vstack([np.hstack([a, b]), np.hstack([c, d])])


# ---------------------------------------------------------------- 기록기
class Recorder:
    """재생기가 기록 프레임마다 capture(i) 를 부르고, 끝에 close() 를 부른다.

    scene 에는 camera_cfgs 의 zed_left · zed_right 가 있어야 한다. 두 카메라는 갱신 주기가 아주 길어 스스로 그리지 않고,
    capture 가 낡았다고 표시하고 다시 그리게 한다 (task_a_replay.py 의 --record 와 같은 방식).
    """

    def __init__(self, scene, sim, args, name, record_hz, physics_dt, extra=None):
        import cv2  # noqa: F401  -- 여기서 없으면 일찍 알린다
        from zed_depth_client import ZedDepthClient
        self.scene, self.sim, self.args = scene, sim, args
        self.record_hz, self.physics_dt = float(record_hz), float(physics_dt)
        self.out = os.path.join(args.zed_out, name)
        for d in ("head_l", "depth_sim", "depth_zed", "raw_l"):
            os.makedirs(os.path.join(self.out, d), exist_ok=True)
        host, port = args.zed_server.rsplit(":", 1)
        try:
            self.zed = ZedDepthClient(host, int(port))
        except (ConnectionRefusedError, OSError) as e:
            raise SystemExit(f"[zed] depth 서버 {args.zed_server} 에 붙지 못했다 ({e!r}) -- ZED 컨테이너를 먼저 띄운다: "
                             f"cd docker && docker compose -f docker-compose.yaml -f zed.yaml up -d")
        self.cams = [scene["zed_left"], scene["zed_right"]]
        self.eyes = ZC.Eyes()
        self.sensor = None if args.zed_no_sensor else ZC.Sensor()
        self.rows, self.acc, self.video, self.info0 = [], {}, None, None
        self.extra = dict(extra or {})
        self.n = 0
        print(f"[zed] 머리 depth 를 {self.out} 에 남긴다 -- {'원본 렌즈' if ZC.MODE == 'raw' else '공개 값'} 방식, "
              f"기록 {max(1, args.zed_every)} 프레임마다", flush=True)

    def capture(self, i):
        import cv2
        a = self.args
        if i % max(1, a.zed_every) or (a.zed_frames and self.n >= a.zed_frames):
            return
        self.sim.render()                     # RTX 는 비동기라 두 번 민다 (task_a_replay.py --record 와 같다)
        self.sim.render()
        for c in self.cams:
            c._is_outdated[:] = True
            c.update(self.physics_dt, force_recompute=True)
        wl = self.cams[0].data.output["rgb"][0].detach().cpu().numpy()[..., :3].astype(np.uint8)
        wr = self.cams[1].data.output["rgb"][0].detach().cpu().numpy()[..., :3].astype(np.uint8)
        wd = self.cams[0].data.output["distance_to_image_plane"][0].detach().cpu().numpy().squeeze()
        sl_, sr_ = self.eyes.to_sensor(wl, wr)
        if self.sensor is not None:
            sl_, sr_ = self.sensor(sl_), self.sensor(sr_)
        d_zed, head_l, info = self.zed.depth(sl_, sr_)
        if info.get("mode") != ZC.MODE:
            raise SystemExit(f"[zed] depth 서버는 {info.get('mode')} 방식인데 여기는 {ZC.MODE} 방식이다 -- "
                             f"두 쪽의 zed_depth/ 가 같아야 한다 (internal_raw_lens.json 이 한쪽에만 있다)")
        self.info0 = self.info0 or info
        d_sim = self.eyes.gt_depth_mm(wd, info["K_rect"])
        f = f"{i:06d}"
        cv2.imwrite(os.path.join(self.out, "head_l", f + ".jpg"), np.ascontiguousarray(head_l[..., ::-1]),
                    [cv2.IMWRITE_JPEG_QUALITY, 95])
        cv2.imwrite(os.path.join(self.out, "depth_sim", f + ".png"), d_sim)
        cv2.imwrite(os.path.join(self.out, "depth_zed", f + ".png"), d_zed)
        if self.n % 50 == 0:
            cv2.imwrite(os.path.join(self.out, "raw_l", f + ".jpg"), np.ascontiguousarray(sl_[..., ::-1]),
                        [cv2.IMWRITE_JPEG_QUALITY, 95])
        st = frame_stats(d_sim, d_zed)
        accumulate(self.acc, d_sim, d_zed)
        t = i / self.record_hz
        self.rows.append({"frame": i, "t": round(t, 2), "zed_ok": info["ok"], "rx_err": info["rx_err"],
                          "zed_ms": info["ms"], **st})
        if not a.zed_no_video:
            panel = compare_panel(head_l, d_sim, d_zed, i, t, st)
            if self.video is None:
                self.video = cv2.VideoWriter(os.path.join(self.out, "compare.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
                                             self.record_hz / max(1, a.zed_every), (panel.shape[1], panel.shape[0]))
            self.video.write(panel)
        self.n += 1

    def close(self):
        self.zed.close()
        if self.video is not None:
            self.video.release()
        keys = []
        for r in self.rows:
            keys += [k for k in r if k not in keys]
        with open(os.path.join(self.out, "stats.csv"), "w", encoding="utf-8") as fh:
            fh.write(",".join(keys) + "\n")
            for r in self.rows:
                fh.write(",".join(str(r.get(k, "")) for k in keys) + "\n")
        total = sum(b["hist"] for b in self.acc.values()) if self.acc else np.zeros(2001, np.int64)
        s = self.sensor
        summary = {**self.extra, "frames": len(self.rows), "zed_failed": sum(1 for r in self.rows if not r["zed_ok"]),
                   "zed_ms_median": float(np.median([r["zed_ms"] for r in self.rows])) if self.rows else None,
                   "camera": {"mode": ZC.MODE, "sdk_rect_K": (self.info0 or {}).get("K_rect"),
                              "sdk_baseline_mm": (self.info0 or {}).get("baseline_mm"),
                              "robot_rect_K_public": ZC.RECT_K_PUBLIC},
                   "sensor": None if s is None else {"blur_sigma": s.blur_sigma, "vignette": s.vignette,
                                                     "shot": s.shot, "read": s.read},
                   "within_3m": hist_summary(total),
                   "by_distance_mm": {k: {**(hist_summary(b["hist"]) or {}),
                                          "zed_holes": round(b["holes"] / max(b["pixels"], 1), 4)}
                                      for k, b in self.acc.items()}}
        json.dump(summary, open(os.path.join(self.out, "summary.json"), "w"), indent=1, ensure_ascii=False)
        w = summary["within_3m"] or {}
        print(f"[zed] {len(self.rows)} 프레임 · ZED 실패 {summary['zed_failed']} · 시뮬 depth 3 m 안 |ZED-시뮬| 중앙값 "
              f"{w.get('abs_median_mm')} mm · 90 % {w.get('abs_p90_mm')} mm · 20 mm 넘게 {100 * w.get('over20', 0):.1f} % "
              f"· 남긴 곳 {self.out}", flush=True)
        for k, v in summary["by_distance_mm"].items():
            print(f"[zed]   시뮬 depth {k:>9s} mm: |ZED-시뮬| 중앙값 {v.get('abs_median_mm')} mm · 90 % {v.get('abs_p90_mm')} mm"
                  f" · 20 mm 넘게 {100 * v.get('over20', 0):.1f} % · ZED 값 없음 {100 * v['zed_holes']:.1f} %", flush=True)
        return summary
