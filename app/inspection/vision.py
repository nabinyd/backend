import os
from ultralytics import YOLO

# Load once (worker process)
_MODEL = None

def get_model():
    global _MODEL
    if _MODEL is None:
        model_path = os.getenv("YOLO_MODEL_PATH", "models/leaf_disease_yolo.pt")
        _MODEL = YOLO(model_path)
    return _MODEL

def run_vision(image_path: str) -> dict:
    """
    Returns structured findings JSON.
    bbox is xyxy in pixels (recommended), normalized optional.
    """
    model = get_model()
    result = model(image_path, verbose=False)[0]

    issues = []
    for box in result.boxes:
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        name = result.names[cls]

        xyxy = [float(x) for x in box.xyxy[0].tolist()]  # [x1,y1,x2,y2] pixels

        issues.append({
            "type": str(name),
            "confidence": round(conf, 3),
            "severity": "high" if conf >= 0.85 else ("medium" if conf >= 0.7 else "low"),
            "bbox": [round(v, 2) for v in xyxy],
        })

    plant_health = "healthy" if len(issues) == 0 else "stressed"
    recommendation_tags = ["ok"] if plant_health == "healthy" else ["disease_risk"]

    return {
        "plant_health": plant_health,
        "issues": issues,
        "recommendation_tags": recommendation_tags,
    }
