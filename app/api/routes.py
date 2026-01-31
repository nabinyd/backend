from fileinput import filename
from flask import Blueprint, app, jsonify, send_from_directory
import socketio
import logging
logger = logging.getLogger("agribot-backend.api")
def create_api_blueprint(store):
    api = Blueprint('api', __name__)

    @api.get('/status')
    def status():
        return jsonify({"status": "ok"}), 200
    
    @api.get('/health')
    def health():
        return jsonify({"health": "bad"}), 200
    
    @api.get("/telemetry/latest")
    def latest_telemetry():
        return jsonify(store.get_latest() or {"ts": 0.0, "data": {}})
    

    @api.get("/uploads/<path:filename>")
    def uploads(filename):
        uploads_dir = api.config.get("UPLOADS_DIR", "uploads")
        return send_from_directory(uploads_dir, filename)

    
    return api