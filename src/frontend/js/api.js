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
  // GET /meetings?status=... -> { items: Meeting[] }
  listMeetings: (status) =>
    request('GET', status ? `/meetings?status=${encodeURIComponent(status)}` : '/meetings'),

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
  getAgenda: (id) => request('GET', `/meetings/${id}/agenda`),

  // POST /meetings/{id}/recording/start | stop -> Meeting (status "live" | "processing")
  startRecording: (id) => request('POST', `/meetings/${id}/recording/start`),
  stopRecording: (id) => request('POST', `/meetings/${id}/recording/stop`),

  // GET /meetings/{id}/extractions -> { items: Extraction[] }  (after stop the backend may run the LLM once)
  getExtractions: (id) => request('GET', `/meetings/${id}/extractions`, { timeoutMs: 100_000 }),

  // GET /meetings/{id}/conflicts -> { items: Conflict[] }
  getConflicts: (id) => request('GET', `/meetings/${id}/conflicts`),
  // POST /meetings/{id}/conflicts/{cid}/resolve {chosen_value} -> Conflict (resolved)
  resolveConflict: (id, cid, chosenValue) =>
    request('POST', `/meetings/${id}/conflicts/${cid}/resolve`, { json: { chosen_value: chosenValue } }),
  // POST /meetings/{id}/ask {question} -> { intent, answer, sources: segment ids, is_ai_suggestion }
  ask: (id, question) => request('POST', `/meetings/${id}/ask`, { json: { question }, timeoutMs: 60_000 }),

  // GET /meetings/{id}/transcript -> { segments: TranscriptSegment[] }
  getTranscript: (id) => request('GET', `/meetings/${id}/transcript`),

  // POST /meetings/{id}/transcribe -> { transcript }  (ElevenLabs can take a while)
  transcribe: (id) => request('POST', `/meetings/${id}/transcribe`, { timeoutMs: 180_000 }),
  // POST /meetings/{id}/minutes/generate -> Minutes (meeting status -> "review")
  convertToMinutes: (id) => request('POST', `/meetings/${id}/minutes/generate`, { timeoutMs: 100_000}),

  // GET /meetings/{id}/minutes -> Minutes  (409 MINUTES_NOT_READY khi chưa generate)
  getMinutes: (id) => request('GET', `/meetings/${id}/minutes`),

  // POST /meetings/{id}/minutes/confirm -> Meeting (status "archived")  (uploads the meeting folder to Supabase; uploaded docs can be up to 10 MB each)
  confirmMinutes: (id) => request('POST', `/meetings/${id}/minutes/confirm`, { timeoutMs: 180_000 }),

  // PUT /meetings/{id}/minutes { markdown } -> Minutes   (allowed in "review" and after confirming)
  saveMinutes: (id, markdown) => request('PUT', `/meetings/${id}/minutes`, { json: { markdown } }),

  // GET /workspaces -> { items: Workspace[] }
  getWorkspaces: () => request('GET', '/workspaces'),
  // POST /workspaces { name, icon, color } -> Workspace
  createWorkspace: (body) => request('POST', '/workspaces', { json: body }),
  // PATCH /workspaces/{id} { name?, icon?, color? } -> Workspace
  updateWorkspace: (id, body) => request('PATCH', `/workspaces/${id}`, { json: body }),
  // DELETE /workspaces/{id} -> { items } (its meetings stay, without a workspace)
  deleteWorkspace: (id) => request('DELETE', `/workspaces/${id}`),
  // PUT /meetings/{id}/workspace { workspace_id | null } -> Meeting   (confirmed meetings only)
  assignWorkspace: (id, workspaceId) => request('PUT', `/meetings/${id}/workspace`, { json: { workspace_id: workspaceId } }),

  // GET /settings -> { keys: [{ name, is_set, source, hint }] }   (a key's value is never returned)
  getSettings: () => request('GET', '/settings'),
  // PUT /settings { values: { NAME: "key" | null } } -> same as GET; null removes the saved key
  saveSettings: (values) => request('PUT', '/settings', { json: { values } }),

};
