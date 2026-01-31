import os
import json
import time
from flask import Blueprint, request, jsonify, current_app, url_for
from sqlalchemy import select

from app.models import Mission, Frame, MissionReport
from app.services.storage import save_frame_file
from app.services.openai_ai import extract_findings_from_image_url, generate_report_from_findings

mission_api = Blueprint("mission_api", __name__)

def _db():
    return current_app.config["DB_SESSION"]()

@mission_api.post("/missions")
def create_mission():
    body = request.get_json(force=True) or {}
    crop = body.get("crop", "unknown")
    field_name = body.get("field_name", "unknown")
    spray_type = body.get("spray_type")

    db = _db()
    m = Mission(crop=crop, field_name=field_name, spray_type=spray_type, status="created")
    db.add(m)
    db.commit()
    return jsonify({"mission_id": m.id, "status": m.status})

@mission_api.post("/missions/<mission_id>/frames")
def upload_frame(mission_id):
    db = _db()
    mission = db.get(Mission, mission_id)
    if not mission:
        return jsonify({"error": "Mission not found"}), 404

    if "image" not in request.files:
        return jsonify({"error": "Missing image file field 'image'"}), 400

    # metadata in form-data fields
    row = request.form.get("row", type=int)
    x = request.form.get("x", type=float)
    y = request.form.get("y", type=float)
    yaw = request.form.get("yaw", type=float)
    ts = request.form.get("ts", type=float) or time.time()

    uploads_dir = current_app.config["UPLOADS_DIR"]
    image_path = save_frame_file(request.files["image"], mission_id, uploads_dir)

    fr = Frame(
        mission_id=mission_id,
        image_path=image_path,
        ts=ts,
        row=row, x=x, y=y, yaw=yaw,
        analyzed=0
    )
    db.add(fr)
    db.commit()

    return jsonify({"frame_id": fr.id, "saved": True})

@mission_api.post("/missions/<mission_id>/analyze")
def analyze_pending_frames(mission_id):
    """
    For MVP: analyze up to N pending frames on demand.
    Later: run this in a background queue (Celery/RQ).
    """
    limit = request.args.get("limit", default=5, type=int)

    db = _db()
    mission = db.get(Mission, mission_id)
    if not mission:
        return jsonify({"error": "Mission not found"}), 404

    pending = db.execute(
        select(Frame).where(Frame.mission_id == mission_id, Frame.analyzed == 0).limit(limit)
    ).scalars().all()

    analyzed_ids = []
    for fr in pending:
        # Build a URL to serve the image (simple local serving below)
        # This assumes you expose an endpoint to fetch images by frame_id
        image_url = url_for("mission_api.get_frame_image", frame_id=fr.id, _external=True)

        findings = extract_findings_from_image_url(image_url=image_url, crop=mission.crop)
        fr.findings_json = json.dumps(findings, ensure_ascii=False)
        fr.analyzed = 1
        analyzed_ids.append(fr.id)

    db.commit()
    return jsonify({"analyzed": analyzed_ids, "count": len(analyzed_ids)})

@mission_api.post("/missions/<mission_id>/report")
def generate_report(mission_id):
    db = _db()
    mission = db.get(Mission, mission_id)
    if not mission:
        return jsonify({"error": "Mission not found"}), 404

    frames = db.execute(
        select(Frame).where(Frame.mission_id == mission_id, Frame.analyzed == 1)
    ).scalars().all()

    findings_list = []
    for fr in frames:
        try:
            f = json.loads(fr.findings_json or "{}")
        except Exception:
            f = {}
        findings_list.append({
            "frame_id": fr.id,
            "row": fr.row,
            "pose": {"x": fr.x, "y": fr.y, "yaw": fr.yaw},
            "ts": fr.ts,
            "findings": f
        })

    mission_context = {
        "mission": {
            "id": mission.id,
            "crop": mission.crop,
            "field_name": mission.field_name,
            "spray_type": mission.spray_type,
        },
        "frames_analyzed": len(frames),
        "findings": findings_list
    }

    report = generate_report_from_findings(mission_context)

    # upsert report
    if mission.report:
        mission.report.report_json = json.dumps(report, ensure_ascii=False)
    else:
        db.add(MissionReport(mission_id=mission_id, report_json=json.dumps(report, ensure_ascii=False)))

    db.commit()
    return jsonify({"mission_id": mission_id, "report": report})

@mission_api.get("/missions/<mission_id>/report")
def get_report(mission_id):
    db = _db()
    mission = db.get(Mission, mission_id)
    if not mission or not mission.report:
        return jsonify({"error": "Report not found"}), 404
    return jsonify({"mission_id": mission_id, "report": json.loads(mission.report.report_json)})

@mission_api.get("/frames/<frame_id>/image")
def get_frame_image(frame_id):
    """
    Minimal image serving for testing.
    In production: serve via nginx or object storage URL.
    """
    from flask import send_file
    db = _db()
    fr = db.get(Frame, frame_id)
    if not fr:
        return jsonify({"error": "Frame not found"}), 404
    return send_file(fr.image_path)
