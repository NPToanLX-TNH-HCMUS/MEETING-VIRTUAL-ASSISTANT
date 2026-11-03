const BASE = '/api/v1'; 

export class ApiError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

async function request(method, path, { json, form, timeoutMs = 30_000 } = {}) {
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: json ? { 'Content-Type': 'application/json' } : {},
      body: json ? JSON.stringify(json) : form, 
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (e) {
    throw new ApiError(e.name === 'TimeoutError' ? 'REQUEST_TIMEOUT' : 'BACKEND_UNREACHABLE', e.message);
  }

  const data = await res.json().catch(() => null);

  if (!res.ok) {
    if (data?.error?.code) throw new ApiError(data.error.code, data.error.message);
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
  generateAgenda: (id) => request('POST', `/meetings/${id}/agenda/generate`, { timeoutMs: 120_000 }),

  // PUT /meetings/{id}/agenda -> { items } 
  saveAgenda: (id, items) => request('PUT', `/meetings/${id}/agenda`, { json: { items } }),
};
