from flask import Flask, app
from flask_socketio import SocketIO
from app.core.config import settings
from app.core.logging import setup_logging
from app.api.routes import create_api_blueprint
from app.sockets.events import register_socket_events
from app.services.telemetry_store import TelemetryStore
from app.db import make_engine, make_session_factory, Base
import os
from app.inspection.routes import inspection_bp
from app.weather.routes import weather_bp


def create_app():
    setup_logging()

    app = Flask(__name__)
    app.config['SECRET_KEY'] = settings.secret_key

    socketio = SocketIO(app, cors_allowed_origins=settings.cors_origins, async_mode='eventlet')

    store = TelemetryStore()

        # DB
    db_url = os.getenv("DATABASE_URL")
    engine = make_engine(db_url)
    Base.metadata.create_all(engine)   # ok for dev
    app.config["DB_SESSION"] = make_session_factory(engine) 

    # Uploads
    app.config["UPLOADS_DIR"] = os.getenv("UPLOADS_DIR", "uploads")

    app.register_blueprint(create_api_blueprint(store), url_prefix='/api')
    app.register_blueprint(inspection_bp, url_prefix='/api/inspection')
    app.register_blueprint(weather_bp, url_prefix='/api/weather')

    register_socket_events(socketio, store, app)

    return app, socketio

