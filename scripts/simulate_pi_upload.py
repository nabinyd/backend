import os, time, json, uuid, requests

SERVER = "http://127.0.0.1:5000"
IMG = "scripts/sample.jpg"  # put any jpg here

def main():
    frame_id = str(uuid.uuid4())
    meta = {
        "ts": time.time(),
        "robot_id": "agribot-01",
        "field_id": "field-01",
        "frame_id": frame_id,
        "odom": {"x": 1.2, "y": 0.3, "yaw": 0.1},
        "row_id": 3
    }

    url = f"{SERVER}/api/inspection/upload"
    with open(IMG, "rb") as f:
        files = {"image": ("sample.jpg", f, "image/jpeg")}
        data = {"meta": json.dumps(meta)}
        r = requests.post(url, files=files, data=data, timeout=10)

    print(r.status_code, r.text)

if __name__ == "__main__":
    main()
