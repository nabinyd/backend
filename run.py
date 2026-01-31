import logging
from app import create_app
from app.core.config import settings

logger = logging.getLogger("agribot-backend")

app, socketio = create_app()

if __name__ == "__main__":
    logger.info("Starting server...")
    logger.info(
        "ENV=%s HOST=%s PORT=%s CORS=%s",
        settings.flask_env, settings.host, settings.port, settings.cors_origins
    )

    socketio.run(app, host=settings.host, port=settings.port)
