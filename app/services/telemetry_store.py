from typing import Any, Dict, Optional
from threading import Lock
import time

class TelemetryStore:
    def __init__(self):
        self.__lock = Lock()
        self.__latest: Dict[str, Any] = {"ts": 0.0, "data": {}}


    def set_latest(self, data: Dict[str, Any]) -> None:
        with self.__lock:
            self.__latest = {"ts": time.time(), "data": data}
    
    def get_latest(self) -> Optional[Dict[str, Any]]:
        with self.__lock:
            return dict(self.__latest) if self.__latest["data"] else None