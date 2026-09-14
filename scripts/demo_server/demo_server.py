"""데모 평가 서버 — 채점과 같은 프로토콜로 여러분의 정책 서버를 붙여 본다.

실평가와 같은 방향으로 동작한다: **이 스크립트가 클라이언트**가 되어 여러분의 정책
서버(WebSocket)에 접속하고, 관측(JPEG 3캠 + state dict + scan)을 보내고 액션 청크를
받아 시뮬레이션을 굴린다. 채점은 하지 않는다 — 씬이 어떻게 움직이는지는 GUI 로 띄워
눈으로 확인한다.

    # 컨테이너 안에서. 정책 서버는 호스트에서 미리 띄워 둔다 (예: random_policy.py --port 8000)
    cd /workspace/cyclo_lab
    ${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
        /workspace/challenge_scripts/demo_server/demo_server.py \
        --server ws://127.0.0.1:8000 --headless --enable_cameras

메시지 규약은 정책 서버 템플릿(eval-host-server)의 README 와 같다:
    reset -> ready, observation -> action, done. numpy 는 msgpack_numpy.

카메라 세 대는 **여기서 통째로 갈아 끼운다.** 끼우는 값은 이 저장소의
`scripts/FFW_SG2_REAL_cameras.py` 에서 오고, 그 파일은 대회 측이 학습 데이터를 모을 때
쓰는 것과 같은 파일이다 (실기 ai_worker 의 URDF·드라이버 설정과 ZED Mini / RealSense
D405 의 제조사 사양에서 온 값. 출처는 그 파일 안에 적혀 있다).

이미지 안 환경 코드의 카메라는 아직 옛 값이다 -- 2026-09-13 에 재 보니 머리 244x244 ·
focal 12 · 0.1~2 m, 손목 focal 18 · 0.1~2 m 였다. 그대로 두면 **2 m 보다 먼 것이 아예
안 그려지고**, 화각도 채점·학습 데이터와 다르다. 그래서 해상도만이 아니라 화각·보이는
거리·붙는 자리까지 전부 덮어쓴다.
"""

import argparse
import importlib.util as _ilu
import os as _os
import uuid

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--server", required=True, help="정책 서버 주소 (ws://HOST:PORT 또는 wss://...)")
parser.add_argument("--token", default=None, help="Bearer 토큰. 정책 서버가 인증을 켰으면 같은 값")
parser.add_argument("--task", default="Cyclo-TaskB-FFW-SG2-ConvStore-Unified-v0")
parser.add_argument("--episodes", type=int, default=1)
parser.add_argument("--minutes", type=float, default=10.0, help="에피소드당 시뮬 시간 상한(분)")
parser.add_argument("--instruction", default="Task B demo episode",
                    help="정책에 보낼 지시문. 씬 생성기가 붙으면 씬이 정한다")
parser.add_argument("--chunk-mode", choices=["exhaust", "periodic"], default="exhaust")
parser.add_argument("--inference-hz", type=float, default=2.0, help="periodic 일 때 재추론 주기")
parser.add_argument("--max-chunk-len", type=int, default=50)
parser.add_argument("--infer-timeout", type=float, default=60.0, help="액션 응답 대기(초)")
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()

app_launcher = AppLauncher(args)
simulation_app = app_launcher.app

import gymnasium as gym                                               # noqa: E402
import msgpack                                                        # noqa: E402
import msgpack_numpy                                                  # noqa: E402
import numpy as np                                                    # noqa: E402
import torch                                                          # noqa: E402
from isaaclab_tasks.utils import parse_env_cfg                        # noqa: E402
from websockets.sync.client import connect                            # noqa: E402

import cyclo_lab.simulation_tasks.manager_based.manipulation.pick_place.config.ffw_sg2_convstore  # noqa: E402,F401

# 카메라 값. **이미지가 아니라 이 저장소**에서 온다 -- 이 파일의 두 단계 위, `scripts/` 바로
# 아래다. 경로로 읽는 이유는 `scripts/` 가 패키지가 아니기 때문이다.
_REALCAM_PATH = _os.path.join(                                        # noqa: E402
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "FFW_SG2_REAL_cameras.py")
_spec = _ilu.spec_from_file_location("FFW_SG2_REAL_cameras", _REALCAM_PATH)  # noqa: E402
REALCAM = _ilu.module_from_spec(_spec)                                # noqa: E402
_spec.loader.exec_module(REALCAM)                                     # noqa: E402

try:
    import cv2

    def encode_jpeg(rgb):
        ok, buf = cv2.imencode(".jpg", rgb[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 85])
        assert ok
        return buf.tobytes()
except ImportError:
    from io import BytesIO

    from PIL import Image

    def encode_jpeg(rgb):
        out = BytesIO()
        Image.fromarray(rgb).save(out, "JPEG", quality=85)
        return out.getvalue()

# 씬 센서 이름 -> (와이어 키, FFW_SG2_REAL_cameras 안의 카메라 이름).
# 해상도를 여기 적지 않는다 -- 그 값은 REALCAM 한 곳에서만 나온다.
CAMS = {"head_cam": ("head_l", "cam_head"),
        "left_wrist_cam": ("wrist_l", "cam_wrist_left"),
        "right_wrist_cam": ("wrist_r", "cam_wrist_right")}


def pack(msg):
    return msgpack.packb(msg, default=msgpack_numpy.encode, use_bin_type=True)


def unpack(data):
    return msgpack.unpackb(data, object_hook=msgpack_numpy.decode, raw=False)


def to_chunk(actions, action_dim):
    """정책 응답 -> (T, action_dim) float32. 구조화 dict(joint_q/lift/mobile)와 평탄 배열 둘 다.

    누락 그룹은 0으로 채운다. NaN/Inf 는 계약대로 에피소드 실패다.
    """
    if isinstance(actions, dict):
        parts = {k: np.atleast_2d(np.asarray(v, np.float32)) for k, v in actions.items()}
        T = max(p.shape[0] for p in parts.values())
        out = np.zeros((T, action_dim), np.float32)
        spans = {"joint_q": slice(0, 18), "lift": slice(18, 19), "mobile": slice(19, 22)}
        for key, span in spans.items():
            if key in parts:
                out[:, span] = parts[key]
        actions = out
    actions = np.atleast_2d(np.asarray(actions, np.float32))
    if actions.shape[1] != action_dim:
        raise ValueError(f"action_dim {actions.shape[1]} != {action_dim}")
    if not np.isfinite(actions).all():
        raise ValueError("NaN/Inf in actions")
    return actions


def build_observation(policy_obs, sim_time, instruction):
    imgs = {}
    for scene_name, (wire_key, _cam_name) in CAMS.items():
        del scene_name
        rgb = policy_obs[wire_key][0].cpu().numpy().astype(np.uint8)
        imgs[wire_key] = encode_jpeg(rgb)
    jp = policy_obs["joint_pos"][0].cpu().numpy().astype(np.float32)   # STATE 순서 19: 0-17 + lift
    msg = {"type": "observation", "sim_time": float(sim_time), "images": imgs,
           "state": {"joint_q": jp[:18], "lift": jp[18:19],
                     "mobile": np.zeros(3, np.float32)},
           "instruction": instruction}
    if "scan" in policy_obs:
        msg["scan"] = policy_obs["scan"][0].cpu().numpy().astype(np.float32)
    return msg


def run_episode(env, idx, conf, control_hz, max_ticks):
    """에피소드 하나 = 연결 하나 (실평가와 같다). 끝나면 done 을 보내고 닫는다."""
    headers = {"Authorization": f"Bearer {args.token}"} if args.token else None
    device = env.unwrapped.device
    obs, _ = env.reset()
    ticks, reason = 0, "max_ticks"

    with connect(args.server, additional_headers=headers, max_size=None) as ws:
        ws.send(pack({"type": "reset", "episode_id": uuid.uuid4().hex, "task_id": args.task,
                      "instruction": args.instruction, "conf": conf,
                      "server_info": {"type": "Start", "info": f"Task B-{idx}"}}))
        while unpack(ws.recv(timeout=args.infer_timeout)).get("type") != "ready":
            pass                                   # 모르는 type 은 무시한다

        # periodic: inference_hz 마다 재추론 -- 청크에서 앞 rows 만 쓰고 나머지는 버린다.
        rows_per_infer = max(1, round(control_hz / args.inference_hz))
        while ticks < max_ticks:
            ws.send(pack(build_observation(obs["policy"], ticks / control_hz,
                                           args.instruction)))
            while True:
                reply = unpack(ws.recv(timeout=args.infer_timeout))
                if reply.get("type") == "action":
                    break
            try:
                chunk = to_chunk(reply["actions"], conf["action_dim"])[:args.max_chunk_len]
            except ValueError as e:
                print(f"[demo] 액션 거부: {e}")
                reason = "bad_action"
                break
            if args.chunk_mode == "periodic":
                chunk = chunk[:rows_per_infer]
            done = False
            for row in chunk:
                action = torch.as_tensor(row, device=device).unsqueeze(0)
                obs, _rew, term, trunc, _info = env.step(action)
                ticks += 1
                done = bool(term[0]) or bool(trunc[0])
                if done or ticks >= max_ticks:
                    break
            if done:
                reason = "terminated"
                break

        ws.send(pack({"type": "done", "reason": reason,
                      "server_info": {"type": "Done",
                                      "info": f"Task B-{idx} | {reason}"}}))
    print(f"[demo] 에피소드 {idx}: {ticks} 틱, 종료 사유 {reason}")


def main():
    cfg = parse_env_cfg(args.task, num_envs=1)
    # 카메라 셋을 통째로 갈아 끼운다 (파일 머리 주석 참조). 해상도만 바꾸면 화각과 보이는
    # 거리는 이미지의 옛 값(focal 12/18 · 0.1~2 m)이 그대로 남는다.
    #
    # 옛 설정에서 가져오는 것은 둘뿐이다 -- 찍는 주기와 받을 데이터 종류. 그 둘은 task 가
    # 관측을 어떻게 읽는지에 매인 값이라 카메라 사양이 아니다. 나머지(해상도·화각·보이는
    # 거리·붙는 자리)는 전부 REALCAM 이 정한다.
    for scene_name, (_key, cam_name) in CAMS.items():
        old = getattr(cfg.scene, scene_name, None)
        if old is None:
            continue
        new = REALCAM.camera_cfg(cam_name,
                                 update_period=old.update_period,
                                 data_types=old.data_types)
        setattr(cfg.scene, scene_name, new)
        print(f"[demo] {scene_name}: {new.width}x{new.height} · 가로 "
              f"{REALCAM.fov_deg(cam_name)[0]:.1f}° · {new.spawn.clipping_range[0]}~"
              f"{new.spawn.clipping_range[1]} m")
    env = gym.make(args.task, cfg=cfg)
    control_hz = 1.0 / env.unwrapped.step_dt
    conf = {"action_dim": env.action_space.shape[-1], "control_hz": control_hz,
            "chunk_mode": args.chunk_mode, "inference_hz": args.inference_hz,
            "max_chunk_len": args.max_chunk_len}
    max_ticks = int(args.minutes * 60 * control_hz)
    print(f"[demo] {args.task} | control {control_hz:.0f} Hz | "
          f"에피소드 {args.episodes} x {max_ticks} 틱 | 서버 {args.server}")
    for idx in range(1, args.episodes + 1):
        run_episode(env, idx, conf, control_hz, max_ticks)
    env.close()
    simulation_app.close()


main()
