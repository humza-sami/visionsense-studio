import time


class ZoneTracker:
    def __init__(self):
        self.total_seconds = 0.0
        self.is_active = False
        self.sessions = 0
        self._session_start = None

    def update(self, phone_detected: bool):
        now = time.time()
        if phone_detected and not self.is_active:
            self.is_active = True
            self._session_start = now
            self.sessions += 1
        elif not phone_detected and self.is_active:
            self.total_seconds += now - self._session_start
            self.is_active = False
            self._session_start = None

    def get_stats(self):
        total = self.total_seconds
        if self.is_active and self._session_start is not None:
            total += time.time() - self._session_start
        return {
            'total_seconds': total,
            'is_active': self.is_active,
            'sessions': self.sessions,
        }

    def reset(self):
        self.total_seconds = 0.0
        self.is_active = False
        self.sessions = 0
        self._session_start = None
