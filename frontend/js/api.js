// Nơi DUY NHẤT gọi backend. Mỗi hàm trong `api` = 1 endpoint trong docs/system_design/api-contract.md.
// Muốn thêm tính năng mới: thêm 1 dòng vào `api`, rồi gọi nó từ main.js.

const BASE = '/api/v1'; // Vite chuyển /api sang http://127.0.0.1:8000 (xem vite.config.js)

// Lỗi chuẩn của app. Luôn kiểm tra `code`, không so sánh `message`.
export class ApiError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

// Gửi request, trả về dữ liệu JSON đã được đổi thành object JS.
async function request(method, path, { json, form, timeoutMs = 30_000 } = {}) {
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: json ? { 'Content-Type': 'application/json' } : {},
      body: json ? JSON.stringify(json) : form, // object JS -> chuỗi JSON
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (e) {
    // fetch chỉ ném lỗi khi không nói chuyện được với server (sập, quá giờ)
    throw new ApiError(e.name === 'TimeoutError' ? 'REQUEST_TIMEOUT' : 'BACKEND_UNREACHABLE', e.message);
  }

  const data = await res.json().catch(() => null); // chuỗi JSON -> object JS (null nếu không phải JSON)

  if (!res.ok) {
    if (data?.error?.code) throw new ApiError(data.error.code, data.error.message); // lỗi do backend báo
    // Vite trả 5xx rỗng khi không tới được backend
    throw new ApiError(res.status >= 500 && !data ? 'BACKEND_UNREACHABLE' : `HTTP_${res.status}`, res.statusText);
  }
  return data;
}

export const api = {
  // POST /meetings -> { id, topic, status, ... }
  createMeeting: (body) => request('POST', '/meetings', { json: body }),

  // GET /meetings/{id} -> { id, status, ... }
  getMeeting: (id) => request('GET', `/meetings/${id}`),

  // POST /meetings/{id}/documents -> { id, filename, ... }   (file = đối tượng File của trình duyệt)
  uploadDocument: (id, file) => {
    const form = new FormData();
    form.append('file', file);
    return request('POST', `/meetings/${id}/documents`, { form });
  },

  // POST /meetings/{id}/agenda/generate -> { items, dropped, duration_minutes }
  // Backend đọc file .md, tách đầu mục và chấm điểm. Gọi LLM nên cho chờ lâu hơn.
  generateAgenda: (id) => request('POST', `/meetings/${id}/agenda/generate`, { timeoutMs: 120_000 }),

  // PUT /meetings/{id}/agenda -> { items }   (đây là lúc người dùng xác nhận agenda)
  saveAgenda: (id, items) => request('PUT', `/meetings/${id}/agenda`, { json: { items } }),
};
