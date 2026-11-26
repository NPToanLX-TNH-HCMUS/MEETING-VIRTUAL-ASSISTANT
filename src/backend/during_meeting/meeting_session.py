import asyncio
from datetime import datetime
from time import monotonic


class MeetingSession:
    def __init__(self, meeting_id: str):
        self.meeting_id = meeting_id

        # Điều khiển nhận diện.
        self.stop_event = asyncio.Event()
        self.pause_event = asyncio.Event()
        # Tín hiệu xác nhận từ tác vụ microphone.
        self.ready_ack = asyncio.Event()
        self.paused_ack = asyncio.Event()
        self.resumed_ack = asyncio.Event()
        self.stopped_ack = asyncio.Event()

        # Tác vụ của cuộc họp.
        self.stream_task = None
        self.summary_task = None
        self.timer_task = None

        # Dữ liệu cuộc họp.
        self.temp_transcript = []
        self.transcript_segments = []
        self.summary_history = []
        self.transcript_saved = False
        self.pipeline_error = None
        self.processing_task = None
        self.analysis_task = None
        self.analysis_lock = asyncio.Lock()
        self.analysis_revision = 0

        # Điều phối các lệnh REST.
        self.control_lock = asyncio.Lock()

        # Phát sự kiện cho các kết nối WebSocket.
        self.seq = 0
        self.subscribers = set()
        self.event_lock = asyncio.Lock()

        # Thời gian thực tế, không tính khoảng tạm dừng.
        self.started_at = None
        self.started_monotonic = None
        self.paused_at = None
        self.paused_seconds = 0.0
        self.stopped_at = None

    def mark_started(self):
        self.started_at = (
            datetime.now()
            .astimezone()
            .isoformat(timespec="seconds")
        )

        self.started_monotonic = monotonic()
        self.paused_at = None
        self.paused_seconds = 0.0
        self.stopped_at = None

    def mark_paused(self):
        if self.paused_at is None:
            self.paused_at = monotonic()

    def mark_resumed(self):
        if self.paused_at is not None:
            self.paused_seconds += monotonic() - self.paused_at
            self.paused_at = None

    def mark_stopped(self):
        if self.stopped_at is not None:
            return

        self.stopped_at = monotonic()

        if self.paused_at is not None:
            self.paused_seconds += (
                self.stopped_at - self.paused_at
            )
            self.paused_at = None

    def elapsed_seconds(self):
        if self.started_monotonic is None:
            return 0.0

        current = (
            self.stopped_at
            if self.stopped_at is not None
            else monotonic()
        )

        paused = self.paused_seconds

        if self.paused_at is not None:
            paused += current - self.paused_at

        return max(
            0.0,
            current - self.started_monotonic - paused,
        )

    def control_response(self, status, duration_seconds):
        elapsed = self.elapsed_seconds()

        return {
            "status": status,
            "started_at": self.started_at,
            "elapsed_seconds": round(elapsed, 2),
            "remaining_seconds": round(
                max(0.0, duration_seconds - elapsed),
                2,
            ),
        }

    def subscribe(self):
        queue = asyncio.Queue(maxsize=200)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue):
        self.subscribers.discard(queue)

    async def publish(self, event_type: str, data: dict):
        async with self.event_lock:
            self.seq += 1

            event = {
                "type": event_type,
                "meeting_id": self.meeting_id,
                "seq": self.seq,
                "at": (
                    datetime.now()
                    .astimezone()
                    .isoformat(timespec="seconds")
                ),
                "data": data,
            }

            for queue in list(self.subscribers):
                try:
                    queue.put_nowait(event)

                except asyncio.QueueFull:
                    self.unsubscribe(queue)

                    while not queue.empty():
                        queue.get_nowait()

                    # Yêu cầu tác vụ gửi đóng kết nối chậm.
                    queue.put_nowait(None)

            return event
