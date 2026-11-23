export function connectTranscriptTest(meetingId, handlers) {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";

  const url =
    `${protocol}//${location.host}` +
    `/ws/meetings/${encodeURIComponent(meetingId)}/transcript-test`;

  const socket = new WebSocket(url);

  socket.addEventListener("open", () => {
    handlers.onOpen?.();
  });

  socket.addEventListener("message", (event) => {
    try {
      const message = JSON.parse(event.data);
      handlers.onMessage?.(message);
    } catch {
      handlers.onError?.("Could not read the transcript data.");
    }
  });

  socket.addEventListener("error", () => {
    handlers.onError?.("Could not connect to the WebSocket.");
  });

  socket.addEventListener("close", () => {
    handlers.onClose?.();
  });

  return socket;
}