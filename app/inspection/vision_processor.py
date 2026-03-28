# app/vision/processor.py
import os
import logging
import numpy as np
from PIL import Image
import io
import base64
from ultralytics import YOLO
import time
from typing import Optional, Dict, List, Union

logger = logging.getLogger("agribot-backend.vision")

class VisionProcessor:
    """Handles YOLO-based vision processing for plant disease detection"""
    
    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or os.getenv("YOLO_MODEL_PATH", "models/leaf_disease_yolo.pt")
        self.model = None
        self.load_model()
        self._last_saved_ts = 0
        self._save_interval = 5.0  # seconds, to prevent saving too many images in a short time
    
    def load_model(self):
        """Load the YOLO model"""
        try:
            if not os.path.exists(self.model_path):
                logger.warning(f"Model not found at {self.model_path}")
                return
            
            self.model = YOLO(self.model_path)
            logger.info(f"Loaded YOLO model from {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self.model = None
    
    def process_image(self, image_data: Union[bytes, str, np.ndarray]) -> Dict:
        """
        Process an image through the YOLO model
        
        Args:
            image_data: Can be bytes, base64 string, or numpy array
        
        Returns:
            Dictionary with detection results
        """
        if self.model is None:
            return self._error_response("Model not loaded")
        
        try:
            # Convert input to PIL Image
            image = self._load_image(image_data)
            if image is None:
                return self._error_response("Failed to load image")
            
            current_time = time.time()
            image_path = ""

            if current_time - self._last_saved_ts >= self._save_interval:
                image_path = self._save_image_to_storage(image)
                self._last_saved_ts = current_time
            
            # Convert to numpy array for YOLO
            image_np = np.array(image)
            
            # Run inference
            results = self.model(image_np, verbose=False)[0]
            
            # Parse results
            issues = []
            for box in results.boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                name = results.names[cls]
    
                xyxy = [float(x) for x in box.xyxy[0].tolist()]
    
                severity = "high" if conf >= 0.85 else ("medium" if conf >= 0.7 else "low")
    
                issues.append({
                    "type": str(name),
                    "confidence": round(conf, 3),
                    "severity": severity,
                    "bbox": [round(v, 2) for v in xyxy],
                })
    
            plant_health = "healthy" if len(issues) == 0 else "stressed"
            recommendation_tags = self._generate_recommendations(issues, plant_health)
    
            return {
                "plant_health": plant_health,
                "issues": issues,
                "recommendation_tags": recommendation_tags,
                "total_detections": len(issues),
                "image_path": image_path,
                "timestamp": time.time(),
                "success": True
            }

            
        except Exception as e:
            logger.error(f"Vision processing error: {e}", exc_info=True)
            return self._error_response(str(e))
    
    def _load_image(self, image_data: Union[bytes, str, np.ndarray]) -> Optional[Image.Image]:
        """Load image from various input formats"""
        try:
            if isinstance(image_data, bytes):
                return Image.open(io.BytesIO(image_data))
            elif isinstance(image_data, str):
                # Check if it's base64
                if image_data.startswith('data:image'):
                    image_data = image_data.split(',')[1]
                if ',' in image_data:
                    image_data = image_data.split(',')[1]
                try:
                    # Try to decode as base64
                    image_bytes = base64.b64decode(image_data)
                    return Image.open(io.BytesIO(image_bytes))
                except:
                    # Try as file path
                    return Image.open(image_data)
            elif isinstance(image_data, np.ndarray):
                return Image.fromarray(image_data)
            else:
                logger.error(f"Unsupported image type: {type(image_data)}")
                return None
        except Exception as e:
            logger.error(f"Failed to load image: {e}")
            return None
    
    def _generate_recommendations(self, issues: List[Dict], plant_health: str) -> List[str]:
        """Generate recommendation tags based on detected issues"""
        if plant_health == "healthy":
            return ["ok", "monitor_regularly"]
        
        tags = ["disease_risk", "inspect_plant"]
        
        for issue in issues:
            issue_type = issue["type"].lower()
            confidence = issue["confidence"]
            
            if confidence > 0.9:
                tags.append("urgent_action")
            
            if "rust" in issue_type:
                tags.extend(["fungal_treatment", "remove_affected_leaves"])
            elif "blight" in issue_type:
                tags.extend(["quarantine_plant", "remove_infected"])
            elif "spot" in issue_type:
                tags.append("monitor_spread")
            elif "mildew" in issue_type:
                tags.extend(["increase_airflow", "reduce_humidity"])
            elif "mosaic" in issue_type:
                tags.extend(["viral_infection", "remove_plant"])
        
        # Remove duplicates while preserving order
        return list(dict.fromkeys(tags))
    
    def _error_response(self, error_msg: str) -> Dict:
        """Create error response"""
        return {
            "plant_health": "error",
            "issues": [],
            "recommendation_tags": ["vision_error"],
            "error": error_msg,
            "success": False,
            "timestamp": time.time()
        }
    
    def _save_image_to_storage(self, image: Image.Image) -> str:
        """Save image to storage directory and return path"""
        try:
            storage_dir = os.path.join("storage", "inspection_frames")
            os.makedirs(storage_dir, exist_ok=True)

            filename = f"{int(time.time() * 1000)}.jpg"
            filepath = os.path.join(storage_dir, filename)

            # Compress image (VERY IMPORTANT)
            image.save(filepath, format="JPEG", quality=70, optimize=True)

            return filepath
        except Exception as e:
            logger.error(f"Failed to save image: {e}")
            return ""

# Singleton instance
_vision_processor = None

def get_vision_processor() -> VisionProcessor:
    """Get or create the global vision processor instance"""
    global _vision_processor
    if _vision_processor is None:
        _vision_processor = VisionProcessor()
    return _vision_processor


