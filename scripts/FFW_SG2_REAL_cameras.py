# Copyright 2026.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""FFW-SG2 rev1 follower cameras set to the REAL robot's specification.

Decision (2026-09-11 meeting): the robot keeps the simulation settings as they are
(``FFW_SG2_MOBILE_CFG`` -- USD, gains, swerve, masses, joint limits are untouched), and
only the cameras follow the real hardware: mount position, field of view and resolution.
See ``FFW_SG2_REAL_cameras.md`` next to this file for every value's source, why that
source was used, and the conflicts checked.

Sources (pinned):
  AW   ROBOTIS-GIT/ai_worker@be8ed6238407          real robot: URDF mounts, camera drivers
  PAT  ROBOTIS-GIT/physical_ai_tools@27192daf75fa   real recording tool: camera keys
  DOCS ROBOTIS-GIT/docs@6c80b0c5eae5                product spec sheet
  MFR  Stereolabs (ZED Mini) / Intel (RealSense D405) published per-mode specs
  CL   ROBOTIS-GIT/cyclo_lab@42dcd8256651           sim robot USD (unchanged)

The camera focal lengths are NOT in any ROBOTIS repository -- the real drivers read each
unit's factory calibration at start-up and publish it on ``camera_info`` only. The models
are named there (AW ``zedm.yaml:7`` ``camera_model: 'zedm'``, AW-URDF ``sensor_d405``), so
the field of view comes from the manufacturers' published spec for the mode the robot uses.

The data part of this module (``CAMERA_SPECS``, ``mount_transform``, ``fov_deg``) is plain
Python so converters and tools can import it without Isaac Sim. Only ``camera_cfg`` and its
wrappers import Isaac Lab, and only when called.
"""

from __future__ import annotations

import math

H_APERTURE = 20.955
"""Horizontal film aperture handed to Isaac (tenths of a metre, like the focal length).
Only the ratio focal/aperture matters: fx = width * focal / aperture."""

CAMERA_FPS = 30
"""Rate both real camera drivers publish at (AW ``zedm.yaml:10``, ``camera_realsense.launch.py:406``).
How often a dataset records is up to each task."""

ROBOT_PRIM = "{ENV_REGEX_NS}/Robot/ffw_sg2_follower"
"""Root of the articulation inside the spawned ``FFW_SG2_MOBILE_CFG`` (same as every existing camera cfg)."""


def _fx_from_hfov(width: int, hfov_deg: float) -> float:
    return (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)


# --- head: Stereolabs ZED Mini, left rectified image -------------------------------------------------
# Resolution: AW ffw_bringup/config/common/zedm.yaml:9-10 (grab_resolution 'VGA', 30 fps) and
#   common_stereo.yaml:27 (pub_resolution 'NATIVE') -> ZED VGA = 672 x 376. The SG2 follower bringup loads
#   these files: ffw_sg2_follower_ai.launch.py:48-62 -> camera.launch.py:40-42 -> camera_zed.launch.py:141,149-153.
# Field of view: Stereolabs "What is the camera focal length and field of view?" -- ZED Mini, WVGA (672x376):
#   focal 367 px, 85 deg (H) x 54 deg (V), nominal. (A measured camera_info on the competition robot gave
#   fx = fy = 364.0, i.e. within 1 %.) DOCS hardware.mdx:110 lists "102 (H) x 57 (V)" -- a maximum-sensor
#   figure that is not the WVGA mode and cannot hold for a 672x376 image at both angles at once.
# Mount: AW-URDF ffw_sg2_follower.urdf:780-783 zed_joint (0.0238122, -0.00651797, -0.0242094) on head_link2,
#   :751-754 camera centre +0.01325 z, :757-760 left eye +0.0315 y, optical axis = +x (rpy 0). The recorded
#   topic is the LEFT rectified image (PAT ffw_sg2_rev1_config.yaml:11), hence the left eye.
HEAD_FX = 367.0

# --- wrists: Intel RealSense D405, colour stream ---------------------------------------------------
# Resolution: AW ffw_bringup/launch/camera_realsense.launch.py:406,408 depth_module.color_profile '424,240,30'.
# Field of view: D405 87 deg (H) x 58 deg (V) (Intel product spec; DOCS hardware.mdx:124). The colour comes
#   from the left imager, so it shares that field of view. With square pixels one angle has to be chosen:
#   87 deg (H) gives fx 223.4 and 56.5 deg (V). (Measured camera_info on the robot: fx 218.4 / 217.6.)
# Mount: AW-URDF :996-997 camera_left_joint on arm_l_link7 xyz (0.108236, -0.021, -0.062552)
#   rpy (-pi/2, 1.66678943569, 0), :1002-1003 camera_left_link +(0.01085, 0.009, 0.021); right :1240-1247.
#   Our USD carries the same frames (camera_{l,r}_bottom_screw_frame/camera_{l,r}_link), 0.0 mm / 0.0 deg apart
#   from the URDF. The camera sits at camera_link with its optical axis along the link's +x and up along +z
#   (RealSense camera_link convention). On a real frame from the old recording tool (RobotisSW PickTunaCan8,
#   no rotation applied) the fingers show on the LEFT of the image, one above the other -- what this pose gives.
WRIST_FX = _fx_from_hfov(424, 87.0)

# (w, x, y, z) identity in Isaac's "world" camera convention = forward +X, up +Z.
_IDENTITY = (1.0, 0.0, 0.0, 0.0)

CAMERA_SPECS: dict[str, dict] = {
    "cam_head": {
        "model": "Stereolabs ZED Mini (left, rectified)",
        "parent": "head_link2",                     # rigid body the camera rides on
        "prim": "head_link2/cam_head",              # below ROBOT_PRIM
        "offset_pos": (0.0238122, 0.0249820, -0.0109594),
        "offset_rot": _IDENTITY,
        "width": 672, "height": 376,
        "fx": HEAD_FX, "fy": HEAD_FX, "cx": 336.0, "cy": 188.0,
        "clipping_range": (0.1, 100.0),             # sim adjustment: task B saw a flat grey image at 0.01
        "focus_distance": 200.0,
        "topic": "/zed/zed_node/left/image_rect_color",
        "source": {
            "resolution": "AW zedm.yaml:9-10, common_stereo.yaml:27",
            "mount": "AW ffw_sg2_follower.urdf:780-783, 751-754, 757-760",
            "fov": "Stereolabs ZED Mini WVGA table (367 px, 85x54 deg)",
            "key": "PAT ffw_sg2_rev1_config.yaml:5,11",
        },
    },
    "cam_wrist_left": {
        "model": "Intel RealSense D405 (colour)",
        "parent": "arm_l_link7",
        "prim": "arm_l_link7/camera_l_bottom_screw_frame/camera_l_link/cam_wrist_left",
        "offset_pos": (0.0, 0.0, 0.0),
        "offset_rot": _IDENTITY,
        "width": 424, "height": 240,
        "fx": WRIST_FX, "fy": WRIST_FX, "cx": 212.0, "cy": 120.0,
        "clipping_range": (0.03, 100.0),            # sim adjustment: the fingers are 75-132 mm ahead
        "focus_distance": 400.0,
        "topic": "/camera_left/camera_left/color/image_rect_raw",
        "source": {
            "resolution": "AW camera_realsense.launch.py:406",
            "mount": "AW ffw_sg2_follower.urdf:996-997, 1002-1003",
            "fov": "Intel D405 87x58 deg; DOCS hardware.mdx:124",
            "key": "PAT ffw_sg2_rev1_config.yaml:6,12",
        },
    },
    "cam_wrist_right": {
        "model": "Intel RealSense D405 (colour)",
        "parent": "arm_r_link7",
        "prim": "arm_r_link7/camera_r_bottom_screw_frame/camera_r_link/cam_wrist_right",
        "offset_pos": (0.0, 0.0, 0.0),
        "offset_rot": _IDENTITY,
        "width": 424, "height": 240,
        "fx": WRIST_FX, "fy": WRIST_FX, "cx": 212.0, "cy": 120.0,
        "clipping_range": (0.03, 100.0),
        "focus_distance": 400.0,
        "topic": "/camera_right/camera_right/color/image_rect_raw",
        "source": {
            "resolution": "AW camera_realsense.launch.py:408",
            "mount": "AW ffw_sg2_follower.urdf:1240-1241, 1246-1247",
            "fov": "Intel D405 87x58 deg; DOCS hardware.mdx:124",
            "key": "PAT ffw_sg2_rev1_config.yaml:7,13",
        },
    },
}

CAMERA_NAMES = tuple(CAMERA_SPECS)
"""Real dataset keys (PAT ffw_sg2_rev1_config.yaml:5-7): observation.images.<name>."""


def focal_length(name: str) -> float:
    """Isaac ``PinholeCameraCfg.focal_length`` for the camera (same units as ``H_APERTURE``)."""
    s = CAMERA_SPECS[name]
    return s["fx"] * H_APERTURE / s["width"]


def fov_deg(name: str) -> tuple[float, float]:
    """(horizontal, vertical) field of view in degrees implied by fx, fy and the resolution."""
    s = CAMERA_SPECS[name]
    return (math.degrees(2.0 * math.atan(s["width"] / 2.0 / s["fx"])),
            math.degrees(2.0 * math.atan(s["height"] / 2.0 / s["fy"])))


# --- mount transforms (camera frame relative to the rigid body it rides on) -------------------------
def _q_mul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw)


def _q_rot(q, v):
    w, x, y, z = q
    p = _q_mul(_q_mul(q, (0.0, *v)), (w, -x, -y, -z))
    return p[1:]


def _q_rpy(r, p, y):
    """URDF fixed-axis roll/pitch/yaw -> (w, x, y, z)."""
    cr, sr = math.cos(r / 2), math.sin(r / 2)
    cp, sp = math.cos(p / 2), math.sin(p / 2)
    cy, sy = math.cos(y / 2), math.sin(y / 2)
    return (cr * cp * cy + sr * sp * sy, sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy, cr * cp * sy - sr * sp * cy)


# AW-URDF :996-1003 (left) and :1240-1247 (right) -- identical numbers on both arms, not mirrored.
_D405_SCREW = ((0.108236, -0.021, -0.062552), _q_rpy(-1.57079632679, 1.66678943569, 0.0))
_D405_LINK = (0.01085, 0.009, 0.021)


def mount_transform(name: str) -> list[float]:
    """[tx, ty, tz, qw, qx, qy, qz] of the camera (world convention: +X forward, +Z up) in its ``parent`` link.

    Same format as ``Task-A/sim/mount_tf.py``, so tools that run without cameras can use it directly.
    """
    s = CAMERA_SPECS[name]
    if name == "cam_head":
        p, q = s["offset_pos"], s["offset_rot"]
    else:
        t0, q0 = _D405_SCREW
        p = tuple(a + b for a, b in zip(t0, _q_rot(q0, _D405_LINK)))
        q = _q_mul(q0, s["offset_rot"])
    return [*p, *q]


# --- Isaac Lab configs (import Isaac only when called) ----------------------------------------------
def camera_cfg(name: str, robot_prim: str = ROBOT_PRIM, **overrides):
    """A ready-to-use ``CameraCfg`` for one of ``CAMERA_NAMES``; keyword arguments override fields."""
    import isaaclab.sim as sim_utils
    from isaaclab.sensors import CameraCfg

    s = CAMERA_SPECS[name]
    kw = dict(
        prim_path=f"{robot_prim}/{s['prim']}",
        update_period=0.0,
        height=s["height"],
        width=s["width"],
        data_types=["rgb"],
        update_latest_camera_pose=True,
        spawn=sim_utils.PinholeCameraCfg(
            focal_length=focal_length(name),
            focus_distance=s["focus_distance"],
            horizontal_aperture=H_APERTURE,
            clipping_range=s["clipping_range"],
        ),
        offset=CameraCfg.OffsetCfg(pos=s["offset_pos"], rot=s["offset_rot"], convention="world"),
    )
    kw.update(overrides)
    return CameraCfg(**kw)


def head_camera_cfg(**overrides):
    return camera_cfg("cam_head", **overrides)


def wrist_camera_cfg(side: str, **overrides):
    if side not in ("left", "right"):
        raise ValueError(f"side must be 'left' or 'right', got {side!r}")
    return camera_cfg(f"cam_wrist_{side}", **overrides)
