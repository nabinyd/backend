# app/sockets/events.py (updated)
import logging
import time
import random
import math
import json
import uuid
from cv2 import data
from flask import request
from threading import Lock

from app.inspection.models import ActiveInspection, InspectionRun
from app.inspection.vision_processor import get_vision_processor
from app.inspection.worker import get_inspection_worker

logger = logging.getLogger("agribot-backend.socket")

# robot_id -> state
_dummy_state = {}
_state_lock = Lock()

# simple safety limits
MAX_VX = 0.6
MAX_WZ = 1.2

# Track active inspections in memory (robot_id -> run_id)
_active_inspections = {}
_active_inspections_lock = Lock()

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def _get_state(robot_id: str):
    with _state_lock:
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
    """Adds odom + lidar ONLY if not already present."""
    robot_id = str(data.get("robot_id", "unknown"))
    s = _get_state(robot_id)

    now = time.time()
    dt = max(0.05, min(now - s["last_ts"], 1.0))
    s["last_ts"] = now

    cmd = data.get("cmd") or {}
    vx = cmd.get("vx", None)
    wz = cmd.get("wz", None)

    if vx is None:
        vx = 0.25 + 0.15 * math.sin(now * 0.5 + s["phase"])
    if wz is None:
        wz = 0.20 * math.sin(now * 0.3 + s["phase"])

    s["yaw"] += float(wz) * dt
    s["x"] += float(vx) * math.cos(s["yaw"]) * dt
    s["y"] += float(vx) * math.sin(s["yaw"]) * dt

    # if "odom" not in data or not isinstance(data.get("odom"), dict):
    #     data["odom"] = {
    #         "x": round(s["x"], 3),
    #         "y": round(s["y"], 3),
    #         "yaw": round(s["yaw"], 3),
    #     }

    # if "lidar" not in data or not isinstance(data.get("lidar"), dict):
    #     front = 1.2 + 0.6 * math.sin(now * 0.4 + s["phase"])
    #     left  = 1.0 + 0.5 * math.sin(now * 0.3 + s["phase"]+1)
    #     right = 1.0 + 0.5 * math.sin(now * 0.35 + s["phase"]+2)

    #     if random.random() < 0.04:
    #         front = random.uniform(0.25, 0.55)

    #     data["lidar"] = {
    #         "min_front": round(max(0.15, front), 3),
    #         "min_left": round(max(0.15, left), 3),
    #         "min_right": round(max(0.15, right), 3),
    #     }

    # if "speed_mps" not in data:
    #     data["speed_mps"] = round(float(vx), 3)

    return data


def register_socket_events(socketio, store, app=None):
    """Register socket events with app context for worker"""
    
    # Get or create worker instance
    worker = get_inspection_worker(app) if app else None
    
    @socketio.on("connect")
    def on_connect():
        sid = request.sid
        logger.info("Client connected sid=%s ip=%s", sid, request.remote_addr)
        socketio.emit("server_info", {"message": "Connected to telemetry server"}, to=sid)

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

    @socketio.on("telemetry")
    def on_telemetry(data):
        sid = getattr(request, "sid", None)

        if not isinstance(data, dict):
            logger.warning("Invalid telemetry payload sid=%s type=%s", sid, type(data))
            return

        data = add_dummy_odom_and_lidar_if_missing(data)
        store.set_latest(data)
        logger.debug("Received telemetry sid=%s data=%s", sid, data)
        socketio.emit("telemetry", data)

        robot_id = data.get("robot_id", "unknown")
        ts = data.get("ts") or 0.0

        imu = data.get("imu", {})
        ang = imu.get("ang_vel", {})
        acc = imu.get("lin_acc", {})

        odom = data.get("odom", {})
        lidar = data.get("lidar", {})

        # logger.info(
        #     "Telemetry → frontend | robot=%s ts=%.3f "
        #     "ang_vel=(%.3f,%.3f,%.3f) lin_acc=(%.3f,%.3f,%.3f) "
        #     "odom=(%.2f,%.2f,yaw=%.2f) lidar=(F=%.2f L=%.2f R=%.2f)",
        #     robot_id, float(ts),
        #     float(ang.get("x", 0.0)), float(ang.get("y", 0.0)), float(ang.get("z", 0.0)),
        #     float(acc.get("x", 0.0)), float(acc.get("y", 0.0)), float(acc.get("z", 0.0)),
        #     float(odom.get("x", 0.0)), float(odom.get("y", 0.0)), float(odom.get("yaw", 0.0)),
        #     float(lidar.get("min_front", 0.0)), float(lidar.get("min_left", 0.0)), float(lidar.get("min_right", 0.0)),
        # )
        
    @socketio.on("cmd_vel")
    def on_cmd_vel(data):
        if not isinstance(data, dict):
            return
        robot_id = str(data.get("robot_id", "unknown"))
        cmd = data.get("cmd_vel") or {}
        vx = float(cmd.get("vx", 0.0))
        vy = float(cmd.get("vy", 0.0))
        wz = float(cmd.get("wz", 0.0))
        vx = clamp(vx, -MAX_VX, MAX_VX)
        wz = clamp(wz, -MAX_WZ, MAX_WZ)
        vy = 0.0
        payload = {
            "robot_id": robot_id,
            "ts": time.time(),
            "cmd_vel": {"vx": vx, "vy": vy, "wz": wz},
            "source": "flutter",
        }
        socketio.emit("cmd_vel", payload)
        logger.info("cmd_vel robot=%s vx=%.2f wz=%.2f", robot_id, vx, wz)
    
    @socketio.on("start_inspection")
    def on_start_inspection(data):
        """Start a new inspection task and activate the worker"""
        try:
            robot_id = data.get("robot_id")
            field_id = data.get("field_id")
            total_frames = data.get("total_frames", 0)
            
            if not robot_id or not field_id:
                socketio.emit("inspection_error", {
                    "error": "Missing robot_id or field_id",
                    "timestamp": time.time()
                }, to=request.sid)
                return
            
            # Create new inspection run in database
            Session = app.config["DB_SESSION"]
            db = Session()
            try:
                run_id = str(uuid.uuid4())
                inspection_run = InspectionRun(
                    id=run_id,
                    robot_id=robot_id,
                    field_id=field_id,
                    status="processing",
                    started_at_ts=time.time(),
                    total_frames=total_frames,
                    done_frames=0,
                    failed_frames=0
                )
                db.add(inspection_run)
                
                # Deactivate previous active inspection for this robot
                db.query(ActiveInspection).filter(
                    ActiveInspection.robot_id == robot_id,
                    ActiveInspection.is_active == True
                ).update({"is_active": False})
                
                # Activate new inspection
                active = ActiveInspection(
                    robot_id=robot_id,
                    run_id=run_id,
                    field_id=field_id,
                    started_at=time.time(),
                    is_active=True
                )
                db.add(active)
                db.commit()
                
                # Update memory cache
                with _active_inspections_lock:
                    _active_inspections[robot_id] = run_id
                
                # Update worker
                if worker:
                    worker.set_active_inspection(robot_id, run_id)
                
                # Send success response
                socketio.emit("inspection_started", {
                    "run_id": run_id,
                    "robot_id": robot_id,
                    "field_id": field_id,
                    "status": "processing",
                    "timestamp": time.time()
                }, to=request.sid)
                
                logger.info(f"Started inspection run {run_id} for robot {robot_id}, field {field_id}")
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error starting inspection: {e}", exc_info=True)
            socketio.emit("inspection_error", {
                "error": str(e),
                "timestamp": time.time()
            }, to=request.sid)
    
    @socketio.on("stop_inspection")
    def on_stop_inspection(data):
        """Stop the current inspection for a robot"""
        try:
            robot_id = data.get("robot_id")
            
            if not robot_id:
                return
            
            Session = app.config["DB_SESSION"]
            db = Session()
            try:
                # Deactivate active inspection
                active = db.query(ActiveInspection).filter(
                    ActiveInspection.robot_id == robot_id,
                    ActiveInspection.is_active == True
                ).first()
                
                if active:
                    active.is_active = False
                    
                    # Update inspection run status
                    run = db.query(InspectionRun).filter(InspectionRun.id == active.run_id).first()
                    if run and run.status == "processing":
                        run.status = "done"
                        run.ended_at_ts = time.time()
                    
                    db.commit()
                    
                    # Remove from memory cache
                    with _active_inspections_lock:
                        if robot_id in _active_inspections:
                            del _active_inspections[robot_id]
                    
                    # Update worker
                    if worker:
                        worker.clear_active_inspection(robot_id)
                    
                    socketio.emit("inspection_stopped", {
                        "robot_id": robot_id,
                        "run_id": active.run_id,
                        "timestamp": time.time()
                    }, to=request.sid)
                    
                    logger.info(f"Stopped inspection run {active.run_id} for robot {robot_id}")
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error stopping inspection: {e}", exc_info=True)
            socketio.emit("inspection_error", {
                "error": str(e),
                "timestamp": time.time()
            }, to=request.sid)
    
    @socketio.on("camera")                 # for picam change to "camera"
    def on_camera(data):
        """Handle camera frames from ROS2 with YOLO processing and storage"""
        try:
            sid = request.sid
            logger.debug("Received camera data from sid=%s", sid)
            
            # Parse camera data
            if not isinstance(data, dict):
                logger.warning("Invalid camera payload sid=%s type=%s", sid, type(data))
                return

            # Get image data
            image_data = None
            if "image_base64" in data:
                image_data = data["image_base64"]
            elif "image" in data:
                image_data = data["image"]
            else:
                logger.warning("No image data found in camera payload")
                return

            robot_id = data.get("robot_id", "unknown")
            timestamp = data.get("ts", time.time())
            frame_id = data.get("frame_id", 0)
            
            # Check if there's an active inspection for this robot
            with _active_inspections_lock:
                active_run_id = _active_inspections.get(robot_id)
            
            # Queue frame for storage if inspection is active
            if active_run_id and worker:
                # Queue frame for background processing
                worker.queue_camera_frame(
                    robot_id=robot_id,
                    run_id=active_run_id,
                    image_data=image_data,
                    timestamp=timestamp,
                    metadata={
                        "frame_id": frame_id,
                        "field_id": data.get("field_id", "unknown"),
                        "source": "camera_stream",
                        "odom": data.get("odom", {}),
                        "imu": data.get("imu", {})
                    }
                )
                logger.debug(f"Queued frame {frame_id} for inspection {active_run_id}")
            
            # Process in real-time for immediate frontend feedback
            vision_processor = get_vision_processor()
            vision_results = vision_processor.process_image(image_data)
            
            # Add metadata to results
            vision_results.update({
                "robot_id": robot_id,
                "timestamp": timestamp,
                "frame_id": frame_id,
                "inspection_run_id": active_run_id
            })
            
            # Emit real-time vision results to frontend
            socketio.emit("vision_results", vision_results)
            
            # Also forward raw camera feed
            socketio.emit("camera", data)      # for picam change to "camera"
            
        except Exception as e:
            logger.error(f"Error processing camera frame: {e}", exc_info=True)
            socketio.emit("vision_error", {
                "error": str(e),
                "timestamp": time.time(),
                "robot_id": data.get("robot_id", "unknown") if isinstance(data, dict) else "unknown"
            }, to=request.sid)

    @socketio.on("espcamera")                 # for picam change to "camera"
    def on_camera(data):
        """Handle camera frames from ROS2 with YOLO processing and storage"""
        try:
            sid = request.sid
            logger.debug("Received camera data from sid=%s", sid)
            
            # Parse camera data
            if not isinstance(data, dict):
                logger.warning("Invalid camera payload sid=%s type=%s", sid, type(data))
                return

            # Get image data
            image_data = None
            if "image_base64" in data:
                image_data = data["image_base64"]
            elif "image" in data:
                image_data = data["image"]
            else:
                logger.warning("No image data found in camera payload")
                return

            robot_id = data.get("robot_id", "unknown")
            timestamp = data.get("ts", time.time())
            frame_id = data.get("frame_id", 0)
            
            # Check if there's an active inspection for this robot
            with _active_inspections_lock:
                active_run_id = _active_inspections.get(robot_id)
            
            # Queue frame for storage if inspection is active
            if active_run_id and worker:
                # Queue frame for background processing
                worker.queue_camera_frame(
                    robot_id=robot_id,
                    run_id=active_run_id,
                    image_data=image_data,
                    timestamp=timestamp,
                    metadata={
                        "frame_id": frame_id,
                        "field_id": data.get("field_id", "unknown"),
                        "source": "camera_stream",
                        "odom": data.get("odom", {}),
                        "imu": data.get("imu", {})
                    }
                )
                logger.debug(f"Queued frame {frame_id} for inspection {active_run_id}")
            
            # Process in real-time for immediate frontend feedback
            vision_processor = get_vision_processor()
            vision_results = vision_processor.process_image(image_data)
            
            # Add metadata to results
            vision_results.update({
                "robot_id": robot_id,
                "timestamp": timestamp,
                "frame_id": frame_id,
                "inspection_run_id": active_run_id
            })
            
            # Emit real-time vision results to frontend
            socketio.emit("vision_results", vision_results)
            
            # Also forward raw camera feed
            socketio.emit("espcamera", data)      # for picam change to "camera"
            
        except Exception as e:
            logger.error(f"Error processing camera frame: {e}", exc_info=True)
            socketio.emit("vision_error", {
                "error": str(e),
                "timestamp": time.time(),
                "robot_id": data.get("robot_id", "unknown") if isinstance(data, dict) else "unknown"
            }, to=request.sid)
    
    @socketio.on("get_inspection_status")
    def on_get_inspection_status(data):
        """Get status of an inspection run"""
        try:
            run_id = data.get("run_id")
            robot_id = data.get("robot_id")
            
            if not run_id and not robot_id:
                socketio.emit("inspection_status", {
                    "error": "Missing run_id or robot_id"
                }, to=request.sid)
                return
            
            Session = app.config["DB_SESSION"]
            db = Session()
            try:
                if run_id:
                    run = db.query(InspectionRun).filter(InspectionRun.id == run_id).first()
                else:
                    # Get latest run for robot
                    run = db.query(InspectionRun).filter(
                        InspectionRun.robot_id == robot_id
                    ).order_by(InspectionRun.started_at_ts.desc()).first()
                
                if run:
                    response = {
                        "run_id": run.id,
                        "robot_id": run.robot_id,
                        "field_id": run.field_id,
                        "status": run.status,
                        "started_at": run.started_at_ts,
                        "ended_at": run.ended_at_ts,
                        "total_frames": run.total_frames,
                        "done_frames": run.done_frames,
                        "failed_frames": run.failed_frames,
                        "progress": (run.done_frames + run.failed_frames) / max(run.total_frames, 1) * 100
                    }
                    
                    if run.report_json:
                        response["report"] = json.loads(run.report_json)
                    if run.report_text:
                        response["report_text"] = json.loads(run.report_text)
                    
                    socketio.emit("inspection_status", response, to=request.sid)
                else:
                    socketio.emit("inspection_status", {
                        "error": "Inspection run not found"
                    }, to=request.sid)
                    
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting inspection status: {e}", exc_info=True)
            socketio.emit("inspection_status", {
                "error": str(e)
            }, to=request.sid)

    @socketio.on("set_mode")
    def set_mode(data):
        robot_id = data.get("robot_id")
        mode = data.get("mode")  # "auto" or "manual"

        socketio.emit("control_mode", {
            "robot_id": robot_id,
            "mode": mode
        })
    
    @socketio.on("arm_command")
    def handle_arm_command(data):
        """
        Handle arm control commands from frontend
        and forward to ROS2 bridge safely.

        Supported formats:

        1. Single joint:
        {
            "robot_id": "agribot-01",
            "motor": "A",
            "angle": 120
        }

        2. Multiple joints:
        {
            "robot_id": "agribot-01",
            "commands": [
                {"motor": "A", "angle": 90},
                {"motor": "B", "angle": 120}
            ]
        }
        """

        try:
            if not isinstance(data, dict):
                logger.warning("Invalid arm_command payload type=%s", type(data))
                return

            robot_id = str(data.get("robot_id", "unknown"))

            # 🔒 Safety limits
            def clamp_angle(angle):
                return max(0, min(180, float(angle)))

            commands = []

            # --- CASE 1: Single joint ---
            if "motor" in data and "angle" in data:
                commands.append({
                    "motor": str(data["motor"]),
                    "angle": clamp_angle(data["angle"])
                })
                logger.debug("Parsed single joint command for robot=%s motor=%s angle=%.1f",
                    robot_id, data["motor"], float(data["angle"])                )

            # --- CASE 2: Multiple joints ---
            elif "commands" in data and isinstance(data["commands"], list):
                for cmd in data["commands"]:
                    if not isinstance(cmd, dict):
                        continue

                    motor = cmd.get("motor")
                    angle = cmd.get("angle")

                    if motor is None or angle is None:
                        continue

                    commands.append({
                        "motor": str(motor),
                        "angle": clamp_angle(angle)
                    })
                logger.debug("Parsed multiple joint commands for robot=%s cmds=%s",
                    robot_id, commands)

            else:
                logger.warning("Invalid arm_command format: %s", data)
                return

            if not commands:
                logger.warning("No valid arm commands found")
                return

            # 📦 Final payload
            payload = {
                "robot_id": robot_id,
                "ts": time.time(),
                "commands": commands,
                "source": "frontend"
            }

            # 🔁 Broadcast to ROS2 bridge
            socketio.emit("arm_command", payload)

            logger.info(
                "Arm command robot=%s cmds=%s",
                robot_id,
                commands
            )

        except Exception as e:
            logger.error(f"Error in arm_command: {e}", exc_info=True)