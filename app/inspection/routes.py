import os, json, uuid, time
from flask import Blueprint, request, jsonify, current_app
from app.inspection.models import InspectionFrame, InspectionRun

inspection_bp = Blueprint("inspection", __name__)

def _db():
    Session = current_app.config["DB_SESSION"]
    return Session()

@inspection_bp.post("/run/create")
def create_run():
    body = request.get_json(force=True, silent=True) or {}
    run_id = body.get("run_id") or str(uuid.uuid4())
    robot_id = str(body.get("robot_id", "agribot-01"))
    field_id = str(body.get("field_id", "field-01"))

    db = _db()
    try:
        run = InspectionRun(
            id=run_id,
            robot_id=robot_id,
            field_id=field_id,
            status="pending",
            started_at_ts=float(time.time()),
            total_frames=0,
            done_frames=0,
            failed_frames=0,
        )
        db.add(run)
        db.commit()
        return jsonify({"ok": True, "run_id": run_id}), 200
    finally:
        db.close()

@inspection_bp.post("/upload")
def upload_frame():
    if "image" not in request.files:
        return jsonify({"error": "image missing"}), 400

    meta_raw = request.form.get("meta", "{}")
    try:
        meta = json.loads(meta_raw)
    except Exception:
        return jsonify({"error": "invalid meta json"}), 400

    run_id = str(meta.get("run_id", "")).strip()
    if not run_id:
        return jsonify({"error": "run_id missing in meta"}), 400

    frame_id = meta.get("frame_id") or str(uuid.uuid4())
    robot_id = str(meta.get("robot_id", "unknown"))
    field_id = str(meta.get("field_id", "unknown"))
    ts = float(meta.get("ts", time.time()))

    uploads_dir = current_app.config.get("UPLOADS_DIR", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    ext = os.path.splitext(request.files["image"].filename)[1].lower() or ".jpg"
    save_path = os.path.join(uploads_dir, f"{frame_id}{ext}")
    request.files["image"].save(save_path)

    db = _db()
    try:
        # Ensure run exists
        run = db.query(InspectionRun).filter(InspectionRun.id == run_id).first()
        if not run:
            return jsonify({"error": f"run_id not found: {run_id}"}), 404

        row = InspectionFrame(
            id=frame_id,
            run_id=run_id,
            robot_id=robot_id,
            field_id=field_id,
            ts=ts,
            image_path=save_path,
            status="pending",
            meta_json=json.dumps(meta),
            findings_json=None,
        )
        db.add(row)

        run.total_frames += 1
        db.commit()

        return jsonify({"ok": True, "frame_id": frame_id, "run_id": run_id, "status": "pending"}), 200
    finally:
        db.close()

@inspection_bp.get("/runs")
def list_runs():
    field_id = request.args.get("field_id")
    robot_id = request.args.get("robot_id")
    limit = int(request.args.get("limit", 50))

    db = _db()
    try:
        q = db.query(InspectionRun)
        if field_id:
            q = q.filter(InspectionRun.field_id == field_id)
        if robot_id:
            q = q.filter(InspectionRun.robot_id == robot_id)
        rows = q.order_by(InspectionRun.started_at_ts.desc()).limit(limit).all()

        out = []
        for r in rows:
            out.append({
                "run_id": r.id,
                "robot_id": r.robot_id,
                "field_id": r.field_id,
                "status": r.status,
                "started_at_ts": r.started_at_ts,
                "ended_at_ts": r.ended_at_ts,
                "total_frames": r.total_frames,
                "done_frames": r.done_frames,
                "failed_frames": r.failed_frames,
            })
        return jsonify(out), 200
    finally:
        db.close()

@inspection_bp.get("/frames")
def list_frames():
    run_id = request.args.get("run_id")
    limit = int(request.args.get("limit", 100))

    db = _db()
    try:
        q = db.query(InspectionFrame)
        if run_id:
            q = q.filter(InspectionFrame.run_id == run_id)
        rows = q.order_by(InspectionFrame.ts.desc()).limit(limit).all()

        out = []
        for r in rows:
            out.append({
                "frame_id": r.id,
                "run_id": r.run_id,
                "robot_id": r.robot_id,
                "field_id": r.field_id,
                "ts": r.ts,
                "status": r.status,
                "image_path": r.image_path,
                "meta": json.loads(r.meta_json) if r.meta_json else None,
                "findings": json.loads(r.findings_json) if r.findings_json else None,
            })
        return jsonify(out), 200
    finally:
        db.close()

@inspection_bp.get("/report")
def get_report():
    run_id = request.args.get("run_id")
    if not run_id:
        return jsonify({"error": "run_id required"}), 400

    db = _db()
    try:
        run = db.query(InspectionRun).filter(InspectionRun.id == run_id).first()
        if not run:
            return jsonify({"error": "run not found"}), 404

        report_json = json.loads(run.report_json) if run.report_json else None
        report_text = json.loads(run.report_text) if run.report_text else None

        return jsonify({
            "run_id": run.id,
            "robot_id": run.robot_id,
            "field_id": run.field_id,
            "status": run.status,
            "started_at_ts": run.started_at_ts,
            "ended_at_ts": run.ended_at_ts,
            "total_frames": run.total_frames,
            "done_frames": run.done_frames,
            "failed_frames": run.failed_frames,
            "report_json": report_json,
            "report_text": report_text,
        }), 200
    finally:
        db.close()
