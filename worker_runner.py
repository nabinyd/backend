from app import create_app
from app.inspection.worker import run_worker

if __name__ == "__main__":
    app, _socketio = create_app()
    run_worker(app)
