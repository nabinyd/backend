import os
import uuid
from werkzeug.utils import secure_filename

ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def save_frame_file(file_storage, mission_id: str, uploads_dir: str) -> str:
    filename = secure_filename(file_storage.filename or "frame.jpg")
    ext = filename.split(".")[-1].lower()

    if ext not in ALLOWED_EXT:
        raise ValueError(f"Unsupported file type: {ext}")

    frame_id = str(uuid.uuid4())
    folder = os.path.join(uploads_dir, mission_id)
    ensure_dir(folder)

    out_path = os.path.join(folder, f"{frame_id}.{ext}")
    file_storage.save(out_path)
    return out_path
