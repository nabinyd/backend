# AgriBot Telemetry Backend

Real-time telemetry backend for an autonomous farming robot.  
This backend receives live robot data from **ROS2**, broadcasts it via **WebSocket**, and serves it to **Flutter dashboards** and other clients.

---

## 🚜 System Overview

ROS2 Robot / Gazebo
↓ (topics: /odom, /cmd_vel, /joint_states)
Telemetry Bridge Node (Python, rclpy)
↓ (Socket.IO JSON @10Hz)
Flask + SocketIO Backend
↓ (WebSocket broadcast)
Flutter Mobile / Web Dashboard

This architecture allows:

- Real-time robot monitoring
- Multiple dashboard clients
- Clean separation between robot logic and UI

---

## 📁 Project Structure

agribot_backend/
├── app/
│ ├── api/
│ │ └── routes.py # REST endpoints
│ ├── sockets/
│ │ └── events.py # WebSocket handlers
│ ├── services/
│ │ └── telemetry_store.py # In-memory telemetry storage
│ ├── core/
│ │ ├── config.py # Environment configuration
│ │ └── logging.py # Logging setup
│ ├── init.py
│ └── main.py # App entry point
├── tests/
├── .env.example
├── .env
├── .gitignore
├── requirements.txt
└── README.md

---

---

## ⚙️ Tech Stack

- **Backend:** Flask
- **WebSockets:** Flask-SocketIO
- **Async Engine:** Eventlet
- **Robot Middleware:** ROS2
- **Client App:** Flutter (Socket.IO client)

---

## 🧪 Supported Telemetry Fields

Example telemetry packet sent by ROS2 bridge:

```json
{
  "ts": 1737111111.12,
  "speed_mps": 0.42,
  "cmd": { "vx": 0.5, "wz": 0.2 },
  "odom": { "x": 1.2, "y": -0.3, "yaw": 1.57 },
  "twist": { "vx": 0.41, "vy": 0.0, "wz": 0.18 },
  "wheels": { "left_vel": 3.2, "right_vel": 3.1 }
}

🚀 Getting Started
 ### 1. Clone the repository
```

git clone <your-repo-url>
cd agribot_backend

```

 ### 2. Create virtual environment
```

python3 -m venv .venv
source .venv/bin/activate

```

 ### 3. Install dependencies
```

pip install -r requirements.txt

```
 ### 4. Configure environment variables
```

cp .env.example .env

```

Edit .env if needed:

FLASK_ENV=development
SECRET_KEY=change-me
HOST=0.0.0.0
PORT=5000
CORS_ORIGINS=*

### 5. Run the backend server
```

python -m app.main

```

Server will start at:
```

http://localhost:5000

```

🔌 API Endpoints
Health Check
```

GET /api/health

```

Response:
```

{ "status": "ok" }

```

Latest Telemetry
GET /api/telemetry/latest


Returns the most recent telemetry packet received from the robot.

🔄 WebSocket Events
Incoming (from ROS2 bridge)

telemetry → JSON telemetry packet

Outgoing (to dashboards)

telemetry → Broadcasted live telemetry

server_info → Connection message

🤖 ROS2 Integration

The backend expects a ROS2 telemetry bridge node that:

Subscribes to:

/odom

/cmd_vel

/joint_states

Sends merged telemetry packets to:

http://<backend-ip>:5000


Recommended send rate:

10 Hz

📱 Flutter Integration

Flutter clients connect via:

IO.io(
  "http://<backend-ip>:5000",
  OptionBuilder()
    .setTransports(['websocket'])
    .build(),
);
```
