import json, time, logging
from sqlalchemy import func
from app.inspection.models import InspectionFrame, InspectionRun
from app.inspection.vision import run_vision
from app.inspection.aggregate import aggregate_run
from app.inspection.llm import generate_farmer_report

logger = logging.getLogger("agribot-backend.worker")

def run_worker(app, poll_sec: float = 1.0, batch: int = 10):
    with app.app_context():
        Session = app.config["DB_SESSION"]
        logger.info("Inspection worker started (vision + report)...")

        while True:
            db = Session()
            try:
                # 1) Process pending frames
                pending = (
                    db.query(InspectionFrame)
                    .filter(InspectionFrame.status == "pending")
                    .order_by(InspectionFrame.created_at.asc())
                    .limit(batch)
                    .all()
                )

                if pending:
                    for row in pending:
                        try:
                            row.status = "processing"
                            db.commit()

                            findings = run_vision(row.image_path)
                            row.findings_json = json.dumps(findings)
                            row.status = "done"
                            db.commit()

                            # update run counters
                            run = db.query(InspectionRun).filter(InspectionRun.id == row.run_id).first()
                            if run:
                                run.done_frames += 1
                                db.commit()

                            logger.info("Frame done id=%s run=%s health=%s issues=%d",
                                        row.id, row.run_id, findings.get("plant_health"), len(findings.get("issues", [])))
                        except Exception as e:
                            row.status = "failed"
                            db.commit()

                            run = db.query(InspectionRun).filter(InspectionRun.id == row.run_id).first()
                            if run:
                                run.failed_frames += 1
                                db.commit()

                            logger.exception("Frame failed id=%s err=%s", row.id, e)

                # 2) Build report for runs that are ready (processed == total_frames)
                runs = (
                    db.query(InspectionRun)
                    .filter(InspectionRun.status.in_(["pending", "processing"]))
                    .order_by(InspectionRun.created_at.asc())
                    .limit(5)
                    .all()
                )

                for run in runs:
                    total = db.query(func.count(InspectionFrame.id)).filter(InspectionFrame.run_id == run.id).scalar() or 0
                    done = db.query(func.count(InspectionFrame.id)).filter(
                        InspectionFrame.run_id == run.id,
                        InspectionFrame.status == "done"
                    ).scalar() or 0
                    failed = db.query(func.count(InspectionFrame.id)).filter(
                        InspectionFrame.run_id == run.id,
                        InspectionFrame.status == "failed"
                    ).scalar() or 0
                
                    run.total_frames = int(total)
                    run.done_frames = int(done)
                    run.failed_frames = int(failed)
                
                    if total == 0:
                        run.status = "pending"
                        db.commit()
                        continue
                    
                    if done + failed < total:
                        run.status = "processing"
                        db.commit()
                        continue
                    
                    # ✅ all frames finished (done or failed)
                    # prevent regenerating report repeatedly
                    if run.report_json and run.report_text:
                        run.status = "done"
                        if run.ended_at_ts is None:
                            run.ended_at_ts = time.time()
                        db.commit()
                        continue
                    
                    frames = (
                        db.query(InspectionFrame)
                        .filter(InspectionFrame.run_id == run.id)
                        .order_by(InspectionFrame.ts.asc())
                        .all()
                    )
                
                    report_json = aggregate_run(frames)
                    run.report_json = json.dumps(report_json)
                    db.commit()
                
                    # ✅ LLM report with fallback so pipeline completes
                    try:
                        report_text = generate_farmer_report(report_json, lang="ne")
                    except Exception as e:
                        report_text = {
                            "lang": "ne",
                            "risk_level": report_json.get("risk_level", "medium"),
                            "summary": "AI रिपोर्ट बनाउन सकेनौं (quota/connection). Stats मात्र देखाइयो।",
                            "key_findings": [],
                            "priority_actions": [],
                            "notes": [str(e)],
                        }
                
                    run.report_text = json.dumps(report_text, ensure_ascii=False)
                    run.status = "done"
                    run.ended_at_ts = time.time()
                    db.commit()
                
                    logger.info("Run finished run=%s total=%d done=%d failed=%d", run.id, total, done, failed)


                if not pending:
                    time.sleep(poll_sec)

            finally:
                db.close()
