# app/sockets/events.py
import logging
from flask import request
import time
import random
import math

logger = logging.getLogger("agribot-backend.socket")

# robot_id -> state
_dummy_state = {}

# simple safety limits
MAX_VX = 0.6
MAX_WZ = 1.2


def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def _get_state(robot_id: str):
    s = _dummy_state.get(robot_id)
    if not s:
        s = {
            "x": 0.0,
            "y": 0.0,
            "yaw": 0.0,
            "last_ts": time.time(),
            "phase": random.uniform(0, math.pi * 2),
        }
        _dummy_state[robot_id] = s
    return s

def add_dummy_odom_and_lidar_if_missing(data: dict) -> dict:
    """
    Adds odom + lidar ONLY if not already present.
    Keeps IMU and any real fields intact.
    """
    robot_id = str(data.get("robot_id", "unknown"))
    s = _get_state(robot_id)

    now = time.time()
    dt = max(0.05, min(now - s["last_ts"], 1.0))  # clamp dt
    s["last_ts"] = now

    # simulate velocity (use cmd if available, else oscillate)
    cmd = data.get("cmd") or {}
    vx = cmd.get("vx", None)
    wz = cmd.get("wz", None)

    if vx is None:
        vx = 0.25 + 0.15 * math.sin(now * 0.5 + s["phase"])  # 0.1..0.4
    if wz is None:
        wz = 0.20 * math.sin(now * 0.3 + s["phase"])         # -0.2..0.2

    # update yaw and position
    s["yaw"] += float(wz) * dt
    s["x"] += float(vx) * math.cos(s["yaw"]) * dt
    s["y"] += float(vx) * math.sin(s["yaw"]) * dt

    # Add odom if missing
    # if "odom" not in data or not isinstance(data.get("odom"), dict):
    #     data["odom"] = {
    #         "x": round(s["x"], 3),
    #         "y": round(s["y"], 3),
    #         "yaw": round(s["yaw"], 3),
    #     }

    # Add lidar if missing (simulate obstacle distances)
    # if "lidar" not in data or not isinstance(data.get("lidar"), dict):
    #     # base distances
    #     front = 1.2 + 0.6 * math.sin(now * 0.4 + s["phase"])   # ~0.6..1.8
    #     left  = 1.0 + 0.5 * math.sin(now * 0.3 + s["phase"]+1) # ~0.5..1.5
    #     right = 1.0 + 0.5 * math.sin(now * 0.35 + s["phase"]+2)

    #     # occasional "near obstacle" event in front
    #     if random.random() < 0.04:
    #         front = random.uniform(0.25, 0.55)

    #     data["lidar"] = {
    #         "min_front": round(max(0.15, front), 3),
    #         "min_left": round(max(0.15, left), 3),
    #         "min_right": round(max(0.15, right), 3),
    #     }

    # Optional: include speed_mps if UI uses it
    if "speed_mps" not in data:
        data["speed_mps"] = round(float(vx), 3)

    return data


def register_socket_events(socketio, store):
    @socketio.on("connect")
    def on_connect():
        sid = request.sid
        logger.info("Client connected sid=%s ip=%s", sid, request.remote_addr)
        socketio.emit("server_info", {"message": "Connected to telemetry server"}, to=sid)

        # Optional: send the latest cached telemetry immediately
        latest = store.get_latest()
        if latest and latest.get("data"):
            socketio.emit("telemetry", latest["data"], to=sid)

    @socketio.on("disconnect")
    def on_disconnect(*args):
        sid = getattr(request, "sid", None)
        logger.info("Client disconnected sid=%s args=%s", sid, args)

    @socketio.on_error_default
    def default_error_handler(e):
        logger.exception("Socket error: %s", e)

    # This is where ROS bridge will send telemetry
    @socketio.on("telemetry")
    def on_telemetry(data):
        sid = getattr(request, "sid", None)

        if not isinstance(data, dict):
            logger.warning("Invalid telemetry payload sid=%s type=%s", sid, type(data))
            return

        # ✅ Add dummy odom + lidar only if missing
        data = add_dummy_odom_and_lidar_if_missing(data)

        store.set_latest(data)
        socketio.emit("telemetry", data)

        # Logging additions
        robot_id = data.get("robot_id", "unknown")
        ts = data.get("ts") or 0.0

        imu = data.get("imu", {})
        ang = imu.get("ang_vel", {})
        acc = imu.get("lin_acc", {})

        odom = data.get("odom", {})
        lidar = data.get("lidar", {})

        logger.info(
            "Telemetry → frontend | robot=%s ts=%.3f "
            "ang_vel=(%.3f,%.3f,%.3f) lin_acc=(%.3f,%.3f,%.3f) "
            "odom=(%.2f,%.2f,yaw=%.2f) lidar=(F=%.2f L=%.2f R=%.2f)",
            robot_id, float(ts),
            float(ang.get("x", 0.0)), float(ang.get("y", 0.0)), float(ang.get("z", 0.0)),
            float(acc.get("x", 0.0)), float(acc.get("y", 0.0)), float(acc.get("z", 0.0)),
            float(odom.get("x", 0.0)), float(odom.get("y", 0.0)), float(odom.get("yaw", 0.0)),
            float(lidar.get("min_front", 0.0)), float(lidar.get("min_left", 0.0)), float(lidar.get("min_right", 0.0)),
        )
        
        @socketio.on("cmd_vel")
        def on_cmd_vel(data):
            if not isinstance(data, dict):
                return

            robot_id = str(data.get("robot_id", "unknown"))
            cmd = data.get("cmd_vel") or {}

            vx = float(cmd.get("vx", 0.0))
            vy = float(cmd.get("vy", 0.0))
            wz = float(cmd.get("wz", 0.0))

            # ✅ clamp for safety
            vx = clamp(vx, -MAX_VX, MAX_VX)
            wz = clamp(wz, -MAX_WZ, MAX_WZ)
            vy = 0.0  # keep diff-drive safe

            payload = {
                "robot_id": robot_id,
                "ts": time.time(),
                "cmd_vel": {"vx": vx, "vy": vy, "wz": wz},
                "source": "flutter",
            }

            # forward to robot clients (Pi bridge listens)
            socketio.emit("cmd_vel", payload)

            logger.info("cmd_vel robot=%s vx=%.2f wz=%.2f", robot_id, vx, wz)