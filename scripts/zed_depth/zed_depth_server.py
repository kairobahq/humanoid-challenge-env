"""ZED SDK depth 서버 -- 머리 두 눈 그림(672x376 RGB)을 받아 ZED SDK(NEURAL)가 계산한 depth(uint16 mm, 0 = 값 없음)와
SDK 가 정류한 왼쪽 그림을 돌려준다. 과제 A · B · C 공용이고, ZED SDK 컨테이너(docker/zed.yaml 의 zed_depth)에서 돈다.

그림은 SDK 의 가상 카메라 송신(sim streamer, ZED Mini 번호)으로 넘기고 같은 기계에서 받아(set_from_stream) 계산한다.
넘길 때 깨지지 않게 한다 (10 fps 로 흘려 보내니 받은 프레임의 약 17 % 가 앞 프레임 조각이 섞여 깨졌다):
- 보내는 쪽(자식 프로세스)은 지금 그림을 fps 로 되풀이해 보낸다 -- 스트림이 끊기면 받는 쪽 grab 이 CAMERA NOT INITIALIZED 가 된다.
- 새 그림은 앞 그림의 depth 를 받은 뒤에야 보낸다 -- 한 번에 한 그림만 오간다.
- 모든 장을 앞 장을 참고하지 않는 통째 그림(gop 1)으로 보낸다 -- 하나가 깨져도 같은 그림의 다음 되풀이를 받으면 된다.
- SDK 가 받은 (정류 전) 왼쪽 그림을 보낸 것과 견줘(스트림의 TV 범위 16~235 를 되돌린 뒤 평균 차이) 4 이상이면 다음 되풀이를 받는다.
보내는 쪽과 받는 쪽을 한 프로세스에 두면 cam.open 이 도는 동안 보내기가 멈춰 open 이 TIMEOUT 으로 끝난다 -- 그래서 둘로 나눈다.

calibration 은 zed_camera.py 의 방식(원본 렌즈 / 공개 값)대로 쓰고, 두 눈 사이를 --baseline-error 만큼 그린 값과 다르게 준다
(calibration 오차, 기본 +0.015 -- 무늬 있는 면이 약 1.5 % 멀게 읽힌다. 공지의 실기 1~2 %).

통신: multiprocessing.connection (표준 라이브러리). 요청 = JSON 머리, 왼쪽 RGB 바이트, 오른쪽 RGB 바이트.
답 = JSON(ok · rx_err · tries · ms · K_rect · baseline_mm · mode), depth 바이트(uint16, H x W), 정류된 왼쪽 RGB 바이트.

    python3 -u zed_depth_server.py                     # 127.0.0.1:7300
"""
import argparse
import ctypes
import json
import multiprocessing as mp
import os
import time
from multiprocessing.connection import Listener

import numpy as np
import pyzed.sl as sl

import zed_camera as ZC

W, H = 672, 376
AUTHKEY = b"taskd-zed-depth"
LIB_PATH = "/usr/local/zed/lib/libsl_zed.so"


class StreamingParameters(ctypes.Structure):   # zed-isaac-sim(main) include/types_c.h 와 같은 순서
    _fields_ = [("mode", ctypes.c_int), ("imu_cam_q", ctypes.c_float * 4), ("imu_cam_t", ctypes.c_float * 3),
                ("image_width", ctypes.c_int), ("image_height", ctypes.c_int), ("codec_type", ctypes.c_int),
                ("port", ctypes.c_ushort), ("fps", ctypes.c_int), ("serial_number", ctypes.c_int),
                ("alpha_channel_included", ctypes.c_bool), ("input_format", ctypes.c_int), ("verbose", ctypes.c_bool),
                ("transport_layer_mode", ctypes.c_int), ("bitrate", ctypes.c_int), ("chunk_size", ctypes.c_ushort),
                ("gop_size", ctypes.c_int), ("gpu_input", ctypes.c_bool), ("stream_depth", ctypes.c_bool),
                ("depth_width", ctypes.c_int), ("depth_height", ctypes.c_int), ("depth_bitrate", ctypes.c_int)]


class SimCameraInfo(ctypes.Structure):
    _fields_ = [("serial_number", ctypes.c_int), ("model", ctypes.c_int), ("lens_type", ctypes.c_int)]


def sender(conn, port, fps, bitrate):
    """자식 프로세스: 가상 ZED Mini 로 지금 그림을 fps 로 되풀이해 보낸다. (왼쪽, 오른쪽) RGBA 바이트가 오면 그 그림으로 바꾸고
    그 그림의 첫 timestamp 를 알린다. None 이 오면 끝낸다."""
    lib = ctypes.CDLL(LIB_PATH)
    lib.init_streamer.argtypes = [ctypes.c_int, ctypes.POINTER(StreamingParameters)]
    lib.stream_rgb.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_longlong] + [ctypes.c_float] * 7
    lib.get_virtual_camera_info.restype = ctypes.POINTER(SimCameraInfo)
    cnt = ctypes.c_int(0)
    info = lib.get_virtual_camera_info(ctypes.byref(cnt))
    sn = next(info[i].serial_number for i in range(cnt.value) if info[i].model == 1)     # 1 = ZED Mini
    p = StreamingParameters()
    p.mode, p.image_width, p.image_height, p.codec_type = 1, W, H, 1
    p.imu_cam_q[:] = [0, 0, 0, 1]
    p.port, p.fps, p.serial_number = port, fps, sn
    p.alpha_channel_included, p.verbose = True, False
    # 네트워크 전송(IPC 는 받는 쪽이 못 찾았다) · RGBA 를 준다 (표시는 BGR 이지만 BGRA 를 주면 R · B 가 뒤바뀐다).
    p.transport_layer_mode, p.input_format = 0, 1
    p.bitrate, p.chunk_size, p.gop_size = bitrate, 4096, 1
    rc = lib.init_streamer(0, ctypes.byref(p))                  # 이 SDK(5.5)는 성공에 0 을 돌려준다
    gray = np.full((H, W, 4), 128, np.uint8)
    gray[..., 3] = 255
    cur_l, cur_r = gray, gray.copy()
    period = int(1e9 / fps)
    t0 = time.time_ns()
    seq, last = 0, 0.0
    conn.send((sn, rc))

    def one():
        nonlocal seq, last
        wait = last + 1.0 / fps - time.time()                   # StreamingParameters.fps 보다 잦은 그림은 버려진다
        if wait > 0:
            time.sleep(wait)
        seq += 1
        ts = t0 + seq * period
        code = lib.stream_rgb(0, cur_l.ctypes.data, cur_r.ctypes.data, ts, 1, 0, 0, 0, 0, 0, 0)
        last = time.time()
        return ts, code

    while True:
        if conn.poll():
            msg = conn.recv()
            if msg is None:
                break
            cur_l = np.frombuffer(msg[0], np.uint8).reshape(H, W, 4).copy()
            cur_r = np.frombuffer(msg[1], np.uint8).reshape(H, W, 4).copy()
            conn.send(one())
        else:
            one()
    lib.close_streamer(0)


def rgba(rgb):
    return np.ascontiguousarray(np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7300)
    ap.add_argument("--stream-port", type=int, default=30500)
    ap.add_argument("--depth-mode", default="NEURAL")          # 공지: 실기 head_l_depth 는 NEURAL
    ap.add_argument("--stabilization", type=int, default=0)    # 관측 때만 계산하므로 떨어진 그림끼리 섞지 않는다
    ap.add_argument("--confidence", type=int, default=95)       # 실기 ROS 설정 (ai_worker common_stereo.yaml)
    ap.add_argument("--texture-conf", type=int, default=100)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--bitrate", type=int, default=20000)
    ap.add_argument("--tries", type=int, default=4)
    ap.add_argument("--workdir", default="/tmp/zed_depth")
    ap.add_argument("--baseline-error", type=float, default=0.015, help="SDK 에 주는 두 눈 사이 = 그린 값 x (1 + 이 값)")
    a = ap.parse_args()
    os.makedirs(a.workdir, exist_ok=True)

    ctx = mp.get_context("spawn")
    conn, child_conn = ctx.Pipe()
    child = ctx.Process(target=sender, args=(child_conn, a.stream_port, a.fps, a.bitrate), daemon=True)
    child.start()
    sn, rc = conn.recv()
    cpath = os.path.join(a.workdir, "calib.yml")
    ZC.write_calib(cpath, ZC.MODE, a.baseline_error)
    init = sl.InitParameters()
    init.set_from_stream("127.0.0.1", a.stream_port)
    init.depth_mode = getattr(sl.DEPTH_MODE, a.depth_mode)
    init.coordinate_units = sl.UNIT.MILLIMETER
    init.depth_minimum_distance = 100                            # 실기 zedm.yaml min_depth 0.1 m
    init.depth_maximum_distance = 10000                          # max_depth 10 m
    init.depth_stabilization = a.stabilization
    init.open_timeout_sec = 120.0
    init.enable_image_validity_check = 0                         # 같은 그림의 되풀이를 깨진 프레임으로 보지 않게
    init.camera_disable_self_calib = True                        # 시뮬은 calibration 이 정확하다 -- SDK 가 그림으로 고치지 않게
    init.optional_opencv_calibration_file = cpath
    cam = sl.Camera()
    err = cam.open(init)
    if err != sl.ERROR_CODE.SUCCESS:
        print(f"[zed-depth] open -> {err}", flush=True)
        conn.send(None)
        raise SystemExit(1)
    cc = cam.get_camera_information().camera_configuration
    Lc = cc.calibration_parameters.left_cam
    K_rect = [round(float(v), 4) for v in (Lc.fx, Lc.fy, Lc.cx, Lc.cy)]
    base_rect = round(float(cc.calibration_parameters.get_camera_baseline()), 3)
    print(f"[zed-depth] open -> {err} · 가상 ZED Mini {sn} (init_streamer {rc}) · {a.depth_mode} · "
          f"{'원본 렌즈 방식 (SDK 가 정류)' if ZC.MODE == 'raw' else '공개 값 방식 (정류된 그림)'} · 두 눈 사이 오차 {a.baseline_error:+.3f} · "
          f"SDK 정류 K {K_rect} · 두 눈 사이 {base_rect} mm", flush=True)
    rt = sl.RuntimeParameters()
    rt.confidence_threshold = a.confidence
    rt.texture_confidence_threshold = a.texture_conf
    rt.remove_saturated_areas = True
    dmat, img = sl.Mat(), sl.Mat()

    def depth_of(left, right):
        t_start = time.time()
        conn.send((rgba(left).tobytes(), rgba(right).tobytes()))
        ts0, _code = conn.recv()                                 # 이 그림의 첫 timestamp -- 이후 오는 장은 이 그림의 되풀이
        tries, rx_err, deadline = 0, float("nan"), time.time() + 5.0
        last = None
        while time.time() < deadline and tries < a.tries:
            if cam.grab(rt) != sl.ERROR_CODE.SUCCESS:
                continue
            if cam.get_timestamp(sl.TIME_REFERENCE.IMAGE).get_nanoseconds() < ts0:
                continue                                         # 앞 그림의 되풀이
            tries += 1
            cam.retrieve_image(img, sl.VIEW.LEFT_UNRECTIFIED)            # 보낸 그림 그대로 -- 깨졌는지 견준다
            rx = img.get_data()[..., [2, 1, 0]].astype(np.float32)          # BGRA -> RGB
            rx_err = float(np.abs((rx - 16.0) * (255.0 / 219.0) - left).mean())
            cam.retrieve_measure(dmat, sl.MEASURE.DEPTH)
            d = np.nan_to_num(dmat.get_data(), nan=0.0, posinf=0.0, neginf=0.0)
            last = np.where((d >= 1.0) & (d <= 65535.0), np.rint(d), 0.0).astype(np.uint16)
            cam.retrieve_image(img, sl.VIEW.LEFT)                         # SDK 가 정류한 왼쪽 -- depth 가 정합된 그림
            rect = np.clip(np.rint((img.get_data()[..., [2, 1, 0]].astype(np.float32) - 16.0) * (255.0 / 219.0)),
                           0, 255).astype(np.uint8)                         # 스트림의 TV 범위(16~235)를 되돌린다
            info = {"rx_err": round(rx_err, 2), "tries": tries, "ms": round(1000 * (time.time() - t_start), 1),
                    "K_rect": K_rect, "baseline_mm": base_rect, "mode": ZC.MODE}
            if rx_err < 4.0:
                return last, rect, {"ok": True, **info}
        if last is None:
            last, rect = np.zeros((H, W), np.uint16), np.zeros((H, W, 3), np.uint8)
            info = {"rx_err": round(rx_err, 2), "tries": tries, "ms": round(1000 * (time.time() - t_start), 1),
                    "K_rect": K_rect, "baseline_mm": base_rect, "mode": ZC.MODE}
        return last, rect, {"ok": False, **info}

    listener = Listener((a.host, a.port), authkey=AUTHKEY)
    print(f"[zed-depth] {a.host}:{a.port} 에서 기다립니다", flush=True)
    try:
        while True:
            c = listener.accept()
            n = 0
            try:
                while True:
                    hdr = json.loads(c.recv_bytes())
                    w, h = hdr["w"], hdr["h"]
                    if (w, h) != (W, H):
                        raise ValueError(f"그림 크기 {w}x{h} -- {W}x{H} 이어야 합니다")
                    left = np.frombuffer(c.recv_bytes(), np.uint8).reshape(H, W, 3)
                    right = np.frombuffer(c.recv_bytes(), np.uint8).reshape(H, W, 3)
                    d, rect, info = depth_of(left, right)
                    c.send_bytes(json.dumps(info).encode())
                    c.send_bytes(d.tobytes())
                    c.send_bytes(np.ascontiguousarray(rect).tobytes())
                    n += 1
                    if n % 50 == 1 or not info["ok"]:
                        print(f"[zed-depth] #{n} {info}", flush=True)
            except EOFError:
                print(f"[zed-depth] 연결이 끝났습니다 ({n} 장)", flush=True)
            finally:
                c.close()
    finally:
        cam.close()
        conn.send(None)
        child.join(timeout=10)


if __name__ == "__main__":
    main()
