// One server-to-client channel. Meeting commands always use REST.
export function connectMeetingSocket(meetingId, handlers = {}) {
  let socket = null;
  let retryTimer = null;
  let stopped = false;
  let attempt = 0;

  function connect() {
    if (stopped) return;
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(
      `${protocol}//${location.host}/ws/meetings/${encodeURIComponent(meetingId)}`
    );
    socket.addEventListener("open", () => {
      attempt = 0;
      handlers.onOpen?.();
    });
    socket.addEventListener("message", (event) => {
      let envelope;
      try {
        envelope = JSON.parse(event.data);
        if (envelope.meeting_id !== meetingId ||
            !Number.isInteger(envelope.seq) ||
            typeof envelope.type !== "string" ||
            !envelope.data || typeof envelope.data !== "object") {
          throw new Error("Invalid event envelope");
        }
      } catch {
        handlers.onError?.("Dữ liệu cập nhật không hợp lệ.");
        return;
      }
      handlers.onMessage?.(envelope);
    });
    socket.addEventListener("error", () => {
      handlers.onError?.("Mất kết nối cập nhật; các nút REST vẫn sử dụng được.");
    });
    socket.addEventListener("close", (event) => {
      if (stopped) return;
      handlers.onClose?.(event);
      if (event.code === 1008) {
        stopped = true;
        handlers.onError?.("Phiên không còn tồn tại. Kiểm tra trạng thái cuộc họp.");
        return;
      }
      const delay = Math.min(1000 * 2 ** attempt++, 10000);
      retryTimer = setTimeout(connect, delay);
    });
  }

  connect();
  return {
    close() {
      stopped = true;
      clearTimeout(retryTimer);
      socket?.close();
    },
  };
}
