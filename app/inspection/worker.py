# app/inspection/worker.py (updated to handle camera streams)
import json
import time
import logging
import os
import base64
from datetime import datetime
from typing import Dict, Optional
from sqlalchemy import func
from app.inspection.models import ActiveInspection, InspectionFrame, InspectionRun
from app.inspection.vision import run_vision
from app.inspection.aggregate import aggregate_run
from app.inspection.llm import generate_farmer_report
from app.inspection.vision_processor import get_vision_processor

logger = logging.getLogger("agribot-backend.worker")

class InspectionWorker:
    """Enhanced worker that can handle both file-based and streaming camera frames"""
    
    # For streaming frames, we expect base64 image data and metadata to be sent via the queue_camera_frame method.
    def __init__(self, app, poll_sec: float = 1.0, batch: int = 10):
        self.app = app
        self.poll_sec = poll_sec
        self.batch = batch
        self.running = True
        self.active_inspections = {}  # robot_id -> run_id mapping
        
    # Start and stop methods to manage the worker thread
    def start(self):
        """Start the worker in a background thread"""
        import threading
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        logger.info("Inspection worker started")
        
    def stop(self):
        """Stop the worker"""
        self.running = False
        logger.info("Inspection worker stopping")
    
    # Main loop to process pending frames and completed runs
    def run(self):
        """Main worker loop"""
        with self.app.app_context():
            logger.info("Inspection worker running...")
            
            while self.running:
                try:
                    self._process_pending_frames()
                    self._process_completed_runs()
                    time.sleep(self.poll_sec)
                except Exception as e:
                    logger.error(f"Worker error: {e}", exc_info=True)
                    time.sleep(5)
    
    # Internal methods to process frames and runs
    def _process_pending_frames(self):
        """Process pending frames from the database"""
        Session = self.app.config["DB_SESSION"]
        db = Session()

        try:
            # Get pending frames
            pending = (
                db.query(InspectionFrame)
                .filter(InspectionFrame.status == "pending")
                .order_by(InspectionFrame.created_at.asc())
                .limit(self.batch)
                .all()
            )
            
            if pending:
                for frame in pending:
                    try:
                        # Update status to processing
                        frame.status = "processing"
                        db.commit()
                        
                        # Process with YOLO
                        if frame.image_path and os.path.exists(frame.image_path):
                            # File-based processing
                            findings = run_vision(frame.image_path)
                        else:
                            # If no file path, use stored image data from meta_json
                            meta = json.loads(frame.meta_json) if frame.meta_json else {}
                            image_data = meta.get("image_base64")
                            if image_data:
                                vision_processor = get_vision_processor()
                                findings = vision_processor.process_image(image_data)
                            else:
                                raise ValueError("No image data available")
                        
                        # Store findings
                        frame.findings_json = json.dumps(findings)
                        frame.status = "done"
                        db.commit()
                        
                        # Update run counters
                        run = db.query(InspectionRun).filter(InspectionRun.id == frame.run_id).first()
                        if run:
                            run.done_frames += 1
                            db.commit()
                        
                        logger.info(f"Frame done id={frame.id} run={frame.run_id} "
                                  f"health={findings.get('plant_health')} "
                                  f"issues={len(findings.get('issues', []))}")
                        
                    except Exception as e:
                        frame.status = "failed"
                        db.commit()
                        
                        run = db.query(InspectionRun).filter(InspectionRun.id == frame.run_id).first()
                        if run:
                            run.failed_frames += 1
                            db.commit()
                        
                        logger.exception(f"Frame failed id={frame.id} err={e}")
                        
        finally:
            db.close()
    
    # This method checks for runs that are pending or processing, and if all their frames are done/failed, it generates the aggregate report and LLM report, then marks the run as done.
    def _process_completed_runs(self):
        """Process completed inspection runs and generate reports"""
        Session = self.app.config["DB_SESSION"]
        db = Session()
        try:
            runs = (
                db.query(InspectionRun)
                .filter(InspectionRun.status.in_(["pending", "processing"]))
                .order_by(InspectionRun.created_at.asc())
                .limit(5)
                .all()
            )
            
            for run in runs:
                # Get frame statistics
                total = db.query(func.count(InspectionFrame.id)).filter(
                    InspectionFrame.run_id == run.id
                ).scalar() or 0
                
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
                
                # All frames finished - generate report
                if not run.report_json or not run.report_text:
                    frames = (
                        db.query(InspectionFrame)
                        .filter(InspectionFrame.run_id == run.id)
                        .order_by(InspectionFrame.ts.asc())
                        .all()
                    )
                    
                    # Generate aggregate report
                    report_json = aggregate_run(frames)
                    run.report_json = json.dumps(report_json)
                    db.commit()
                    
                    # Generate LLM report
                    try:
                        report_text = generate_farmer_report(report_json, lang="ne")
                    except Exception as e:
                        report_text = {
                            "lang": "ne",
                            "risk_level": report_json.get("risk_level", "medium"),
                            "summary": "AI रिपोर्ट बनाउन सकेनौं। तथ्यांक मात्र देखाइयो।",
                            "key_findings": [],
                            "priority_actions": [],
                            "notes": [str(e)],
                        }
                    
                    run.report_text = json.dumps(report_text, ensure_ascii=False)
                    run.status = "done"
                    run.ended_at_ts = time.time()
                    db.commit()
                    
                    logger.info(f"Run finished run={run.id} total={total} done={done} failed={failed}")
                    
        finally:
            db.close()
    
    # Method to queue camera frames for processing
    def queue_camera_frame(self, robot_id: str, run_id: str, image_data: str, 
                          timestamp: float, metadata: Dict = None):
        """
        Queue a camera frame for processing and storage
        
        Args:
            robot_id: Robot identifier
            run_id: Inspection run ID
            image_data: Base64 encoded image
            timestamp: Frame timestamp
            metadata: Additional metadata (frame_id, field_id, etc.)
        """
        import uuid
        
        Session = self.app.config["DB_SESSION"]
        db = Session()
        try:
            # Check if inspection is still active
            if run_id not in self._get_active_runs():
                logger.warning(f"Discarding frame for inactive inspection: run={run_id}")
                return
            
            frame_id = str(uuid.uuid4())
            field_id = metadata.get("field_id", "unknown") if metadata else "unknown"
            
            # Save image to disk
            image_path = self._save_image(frame_id, robot_id, run_id, image_data, timestamp)
            
            # Create frame record
            frame = InspectionFrame(
                id=frame_id,
                run_id=run_id,
                robot_id=robot_id,
                field_id=field_id,
                ts=timestamp,
                image_path=image_path,
                status="pending",
                meta_json=json.dumps({
                    **metadata,
                    "image_base64": image_data  # Store for processing if file not accessible
                })
            )
            db.add(frame)
            db.commit()
            
            logger.debug(f"Queued frame {frame_id} for run {run_id}")
            
        except Exception as e:
            logger.error(f"Failed to queue frame: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()
    
    # Helper method to save base64 image data to disk and return the file path
    def _save_image(self, frame_id: str, robot_id: str, run_id: str, 
                    image_data: str, timestamp: float) -> str:
        """Save base64 image to disk and return file path"""
        try:
            # Create directory structure
            storage_path = self.app.config.get("INSPECTION_STORAGE_PATH", "storage/inspection_images")
            frame_dir = os.path.join(storage_path, robot_id, run_id)
            os.makedirs(frame_dir, exist_ok=True)
            
            # Generate filename
            filename = f"{frame_id}_{int(timestamp)}.jpg"
            filepath = os.path.join(frame_dir, filename)
            
            # Decode and save image
            if image_data.startswith('data:image'):
                image_data = image_data.split(',')[1]
            
            image_bytes = base64.b64decode(image_data)
            with open(filepath, 'wb') as f:
                f.write(image_bytes)
            
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to save image: {e}")
            raise
    
    # Helper method to get active inspection runs from the database
    def _get_active_runs(self) -> set:
        """Get set of active run IDs"""
        Session = self.app.config["DB_SESSION"]
        db = Session()
        try:
            
            active = db.query(ActiveInspection).filter(
                ActiveInspection.is_active == True
            ).all()
            return {a.run_id for a in active}
        finally:
            db.close()
    
    # Methods to manage active inspections (called when new run starts or ends)
    def set_active_inspection(self, robot_id: str, run_id: str):
        """Set active inspection for a robot"""
        self.active_inspections[robot_id] = run_id
        logger.info(f"Active inspection set: robot={robot_id} run={run_id}")
    
    # This method can be called when an inspection run is completed or cancelled to clear the active status
    def clear_active_inspection(self, robot_id: str):
        """Clear active inspection for a robot"""
        if robot_id in self.active_inspections:
            del self.active_inspections[robot_id]
            logger.info(f"Active inspection cleared: robot={robot_id}")

# Singleton instance
_worker_instance = None

# Function to get or create the global worker instance
def get_inspection_worker(app=None) -> InspectionWorker:
    """Get or create the global inspection worker instance"""
    global _worker_instance
    if _worker_instance is None and app:
        _worker_instance = InspectionWorker(app)
        _worker_instance.start()
    return _worker_instance