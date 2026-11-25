import { api, ApiError } from './api.js';
import { setCrumb, setMeeting } from './shell.js';

const $ = (id) => document.getElementById(id); 
const MAX_FILE_BYTES = 10 * 1024 * 1024;

let meeting = null;
let files = []; 
const uploaded = new Set();
const uploading = new Set(); // file đang gửi lên backend
const failed = new Map(); // file -> mã lỗi backend trả về (ApiError.code)
let agenda = null; // { items, dropped, duration, confirmed, edited } or null 
let loading = false;
let confirming = false;
let errorMessage = '';
let language = 'vi';
let points = []; // các ý dự định trình bày, mỗi ý một chip
let addingPoint = false;
let previousMeetings = [];

const REASON_LABEL = { exceeds_remaining_time: "doesn't fit in the remaining time" };
const UPLOAD_ERROR_LABEL = {
  FILE_TOO_LARGE: 'File too large',
  UNSUPPORTED_FILE_TYPE: 'Unsupported format',
};

const numberFormat = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 });
function formatSize(bytes) {
  if (bytes < 1024) return '< 1 KB';
  if (bytes < 1024 * 1024) return `${numberFormat.format(Math.ceil(bytes / 1024))} KB`;
  return `${numberFormat.format(bytes / (1024 * 1024))} MB`;
}

function fileStatus(file) {
  if (uploaded.has(file)) return { kind: 'done', label: 'Sent ✓' };
  if (uploading.has(file)) return { kind: 'uploading', label: 'Sending…' };
  if (failed.has(file)) {
    const code = failed.get(file);
    return { kind: 'error', label: `Error · ${UPLOAD_ERROR_LABEL[code] ?? 'upload failed'}` };
  }
  return { kind: 'pending', label: 'Waiting' };
}

const REMOVE_ICON =
  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>';

const isMinutesValid = (m) => Number.isInteger(m) && m >= 1 && m <= 480;
const isItemValid = (it) => !!it.title?.trim() && isMinutesValid(it.estimated_minutes);
const flag = (input, bad) => (bad ? input.setAttribute('aria-invalid', 'true') : input.removeAttribute('aria-invalid'));

function render() {
  $('error').hidden = !errorMessage;
  $('error').textContent = errorMessage;

  // Đã tạo cuộc họp trên backend thì không sửa được thông tin nữa (backend chưa có API sửa).
  for (const id of ['topic', 'duration']) $(id).disabled = !!meeting;
  $('previous').disabled = !!meeting || previousMeetings.length === 0;
  for (const btn of $('language').children) {
    btn.disabled = !!meeting;
    btn.setAttribute('aria-pressed', String(btn.dataset.value === language));
  }
  $('details-locked').hidden = !meeting;
  $('meeting-meta').textContent = meeting ? [meeting.id, meeting.status].join(' · ') : '';
  setCrumb(meeting?.topic || 'New meeting');
  if (meeting) setMeeting(meeting.id);

  // Bước 1 xong khi đã có agenda, bước 2 xong khi đã xác nhận; bước hiện tại tô đậm.
  const stage = agenda?.confirmed ? 2 : agenda ? 1 : 0;
  [...$('stepper').children].forEach((li, i) => {
    li.classList.toggle('step--done', i < stage);
    li.classList.toggle('step--current', i === stage);
  });

  renderFileList();
  renderPoints();

  $('generate').disabled = loading || !!agenda;
  $('generate').textContent = loading && !agenda ? 'Generating…' : 'Generate agenda';
  $('agenda-empty').hidden = !!agenda || loading;
  $('agenda-loading').hidden = !!agenda || !loading;
  $('agenda-content').hidden = !agenda;
  $('planned').hidden = !agenda;
  if (!agenda) return;

  const canStart = agenda.confirmed && meeting;
  $('go-during').setAttribute('aria-disabled', String(!canStart));
  if (canStart) $('go-during').href = `/during.html?meeting=${encodeURIComponent(meeting.id)}`;
  else $('go-during').removeAttribute('href');
  renderRows();
  renderDropped();
  renderSummary();
}

function renderFileList() {
  $('dropzone').classList.toggle('dropzone--disabled', loading);
  $('file-count').textContent = files.length ? ` · ${files.length} file${files.length > 1 ? 's' : ''}` : '';

  $('file-list').replaceChildren(
    ...files.map((file) => {
      const li = document.createElement('li');
      li.className = 'file-card';

      const ext = file.name.split('.').pop().toLowerCase();
      const { kind, label } = fileStatus(file);
      if (kind === 'error') li.classList.add('file-card--error');

      // Cắt tên dài bằng CSS (ellipsis), không cắt chuỗi trong JS để giữ nguyên dấu tiếng Việt.
      const body = document.createElement('div');
      body.className = 'file-card__body';
      const name = document.createElement('span');
      name.className = 'file-card__name';
      name.textContent = file.name;
      name.title = file.name;
      const meta = document.createElement('span');
      meta.className = 'file-card__meta';
      meta.textContent = [ext.toUpperCase(), formatSize(file.size), label].join(' · ');
      body.append(name, meta);

      li.append(body);

      // Backend chưa có API xoá tài liệu, nên file đã gửi lên thì không bỏ được.
      if (!uploaded.has(file)) {
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'icon-btn';
        remove.innerHTML = REMOVE_ICON;
        remove.disabled = uploading.has(file);
        remove.setAttribute('aria-label', `Remove ${file.name}`);
        remove.addEventListener('click', () => {
          files = files.filter((f) => f !== file);
          failed.delete(file);
          render();
        });
        li.append(remove);
      }
      return li;
    }),
  );
}

// Mỗi mục agenda = 1 bản sao của <template id="tpl-row"> trong index.html, điền dữ liệu vào.
function renderRows() {
  const rows = agenda.items.map((item, i) => {
    const tr = $('tpl-row').content.firstElementChild.cloneNode(true);
    const q = (name) => tr.querySelector(`[data-field="${name}"]`);

    const title = q('title');
    title.value = item.title ?? '';
    flag(title, !item.title?.trim());
    title.addEventListener('input', () => {
      item.title = title.value;
      flag(title, !title.value.trim());
      markEdited();
    });

    // Chỉ cập nhật dữ liệu khi gõ, KHÔNG vẽ lại hàng (vẽ lại sẽ làm mất con trỏ và hỏng bộ gõ tiếng Việt).
    const minutes = q('minutes');
    minutes.value = item.estimated_minutes ?? ''; // null = backend không biết -> để trống, không tự đoán
    flag(minutes, !isMinutesValid(item.estimated_minutes));
    minutes.addEventListener('input', () => {
      const raw = minutes.value.trim();
      item.estimated_minutes = /^\d+$/.test(raw) ? Number(raw) : NaN;
      flag(minutes, !isMinutesValid(item.estimated_minutes));
      markEdited();
    });

    q('num').textContent = `${i + 1}.`;
    // AI đề xuất thì phải ghi rõ bằng chữ cho tới khi người dùng xác nhận.
    q('badge').hidden = !item.needs_confirmation || agenda.confirmed;

    q('up').disabled = i === 0;
    q('down').disabled = i === agenda.items.length - 1;
    q('up').addEventListener('click', () => move(i, -1));
    q('down').addEventListener('click', () => move(i, +1));
    return tr;
  });
  $('agenda-rows').replaceChildren(...rows);
}

function renderDropped() {
  $('dropped').replaceChildren(
    ...agenda.dropped.map((d) => {
      const banner = document.createElement('div');
      banner.className = 'banner banner--warn';
      const text = [d.title, d.estimated_minutes && `${d.estimated_minutes} min`, REASON_LABEL[d.reason] ?? d.reason];
      const body = document.createElement('span');
      body.className = 'banner__body';
      const lead = document.createElement('strong');
      lead.textContent = 'Left out: ';
      body.append(lead, text.filter(Boolean).join(' · '));

      // Người dùng quyết định thêm lại: thành một hàng thủ công, backend chỉ nhận khi bấm xác nhận.
      const add = document.createElement('button');
      add.type = 'button';
      add.className = 'btn btn--sm';
      add.textContent = 'Add anyway';
      add.addEventListener('click', () => {
        agenda.items.push({ title: d.title, estimated_minutes: d.estimated_minutes ?? null, source: 'manual' });
        agenda.dropped = agenda.dropped.filter((x) => x !== d);
        agenda.edited = true;
        agenda.confirmed = false;
        render();
      });
      banner.append(body, add);
      return banner;
    }),
  );
}

// Phần phụ thuộc vào số phút và trạng thái xác nhận (gọi lại mỗi khi người dùng gõ).
function renderSummary() {
  const planned = agenda.items.reduce((sum, it) => sum + (Number.isFinite(it.estimated_minutes) ? it.estimated_minutes : 0), 0);
  const over = Number.isFinite(agenda.duration) && planned > agenda.duration;
  $('planned-used').textContent = planned;
  $('planned-rest').textContent = ` of ${agenda.duration ?? '—'} min planned${over ? ` · ${planned - agenda.duration} min over` : ''}`;
  $('planned').classList.toggle('planned--over', over);
  $('planned-bar').classList.toggle('progress--over', over);
  $('planned-fill').style.width = `${agenda.duration > 0 ? Math.min(100, (planned / agenda.duration) * 100) : 0}%`;

  $('agenda-note').textContent = agenda.confirmed
    ? 'The agenda is confirmed and saved.'
    : 'Nothing is saved until you confirm. Edit a title or time, or reorder with the ↑ ↓ buttons.';

  const valid = agenda.items.length > 0 && agenda.items.every(isItemValid);
  $('agenda-invalid').hidden = valid || agenda.items.length === 0;

  $('confirm').disabled = confirming || loading || !valid || agenda.confirmed;
  $('confirm').textContent = confirming ? 'Saving…' : 'Confirm agenda';

  // Backend chỉ cho tạo agenda khi cuộc họp còn "draft".
  $('regenerate').disabled = loading || confirming || meeting?.status !== 'draft';
  $('regenerate').textContent = loading ? 'Generating…' : 'Regenerate';
}

// ============ 3. HÀNH ĐỘNG ============
const byOrder = (a, b) => (a.order ?? 0) - (b.order ?? 0);

function showError(e) {
  if (e instanceof ApiError) {
    if (e.code === 'MEETING_NOT_FOUND') {
      // Backend quên cuộc họp (vd. server khởi động lại): bỏ dữ liệu cũ để lần sau tạo mới.
      meeting = null;
      agenda = null;
      uploaded.clear();
      errorMessage = 'The backend no longer has this meeting (the server may have restarted). Press “Generate agenda” to try again.';
    } else if (e.code === 'BACKEND_UNREACHABLE') {
      errorMessage = 'Cannot reach the backend (127.0.0.1:8000). Is the server running?';
    } else if (e.code === 'REQUEST_TIMEOUT') {
      errorMessage = 'The backend took too long to respond.';
    } else {
      errorMessage = e.message || `Something went wrong (${e.code}).`;
    }
  } else {
    errorMessage = `Something went wrong: ${e.message}`;
  }
}

// Đọc form. Trả về null (và hiện lỗi) nếu chưa hợp lệ.
function readDetails() {
  const topic = $('topic').value.trim();
  const raw = $('duration').value.trim();
  const duration = /^\d+$/.test(raw) ? Number(raw) : NaN;
  if (!topic) return fail('Enter a topic to generate an agenda.');
  if (!isMinutesValid(duration)) return fail('Duration must be a whole number from 1 to 480 minutes.');
  return {
    topic,
    language,
    duration_minutes: duration,
    planned_points: points,
    previous_meeting_id: $('previous').value || null,
  };
}

function fail(message) {
  errorMessage = message;
  render();
  return null;
}

async function generate() {
  if (loading) return;
  const details = meeting ? {} : readDetails();
  if (!details) return;

  loading = true;
  errorMessage = '';
  render();
  try {
    if (!meeting) meeting = await api.createMeeting(details);

    // Backend sẽ đọc file .md và tự tách thành các đầu mục; UI chỉ gửi file nguyên bản.
    for (const file of files) {
      if (uploaded.has(file)) continue;
      failed.delete(file);
      uploading.add(file);
      renderFileList();
      try {
        await api.uploadDocument(meeting.id, file);
        uploaded.add(file);
      } catch (e) {
        failed.set(file, e instanceof ApiError ? e.code : 'UNKNOWN');
        throw e;
      } finally {
        uploading.delete(file);
      }
    }

    const res = await api.generateAgenda(meeting.id);
    agenda = {
      items: [...(res.items ?? [])].sort(byOrder),
      dropped: res.dropped ?? [],
      duration: res.duration_minutes ?? meeting.duration_minutes ?? null,
      confirmed: false,
      edited: false,
    };
  } catch (e) {
    showError(e);
  } finally {
    loading = false;
    render();
  }
}

function regenerate() {
  if (agenda.edited && !window.confirm('Your edits will be lost. Regenerate the agenda?')) return;
  agenda = null;
  generate();
}

// Người dùng sửa chữ/số: chỉ đánh dấu, chưa vẽ lại cả bảng.
function markEdited() {
  agenda.edited = true;
  agenda.confirmed = false;
  renderSummary();
}

function move(index, step) {
  const to = index + step;
  const items = agenda.items;
  [items[index], items[to]] = [items[to], items[index]];
  agenda.edited = true;
  agenda.confirmed = false;
  renderRows();
  renderSummary();
}

// PUT agenda = người dùng xác nhận. Backend là nơi quyết định trạng thái cuộc họp mới.
async function confirm() {
  confirming = true;
  errorMessage = '';
  renderSummary();
  try {
    const payload = agenda.items.map((it, i) => ({
      ...(it.id ? { id: it.id } : {}),
      title: it.title.trim(),
      estimated_minutes: it.estimated_minutes,
      order: i + 1,
    }));
    const res = await api.saveAgenda(meeting.id, payload);
    // Giữ lại các trường (vd. source) mà backend không trả lại, lấy id/thứ tự từ phản hồi.
    agenda.items = [...res.items].sort(byOrder).map((saved, i) => ({ ...agenda.items[i], ...saved }));
    agenda.confirmed = true;
    agenda.edited = false;
    meeting = await api.getMeeting(meeting.id);
  } catch (e) {
    showError(e);
  } finally {
    confirming = false;
    render();
  }
}

function addFiles(picked) {
  const problems = [];
  for (const file of picked) {
    if (!/\.(md|txt|pdf|docx|doc)$/i.test(file.name)) problems.push(`${file.name}: only .md .txt .pdf .docx are accepted`);
    else if (file.size > MAX_FILE_BYTES) problems.push(`${file.name}: larger than 10 MB`);
    else if (files.some((f) => f.name === file.name)) problems.push(`${file.name}: already added`);
    else files.push(file);
  }
  errorMessage = problems.join('. ');
  render();
}

function renderPoints() {
  const chips = points.map((text, i) => {
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.append(text);
    if (!meeting) {
      const x = document.createElement('button');
      x.type = 'button';
      x.className = 'chip__remove';
      x.textContent = '×';
      x.setAttribute('aria-label', `Remove point ${text}`);
      x.addEventListener('click', () => {
        points.splice(i, 1);
        render();
      });
      chip.append(x);
    }
    return chip;
  });

  if (!meeting && addingPoint) {
    const input = document.createElement('input');
    input.className = 'chip__input';
    input.setAttribute('aria-label', 'New point');
    // Enter khi đang gõ dấu (IME) chỉ là chốt chữ, không phải thêm chip.
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.isComposing) commit(input);
      if (e.key === 'Escape') {
        addingPoint = false;
        render();
      }
    });
    input.addEventListener('blur', () => commit(input));
    chips.push(input);
    queueMicrotask(() => input.focus());
  } else if (!meeting) {
    const add = document.createElement('button');
    add.type = 'button';
    add.className = 'chip chip--add';
    add.textContent = '+ Add a point';
    add.addEventListener('click', () => {
      addingPoint = true;
      render();
    });
    chips.push(add);
  }
  $('points').replaceChildren(...chips);
}

function commit(input) {
  if (!addingPoint) return; // blur bắn thêm một lần sau Enter
  addingPoint = false;
  const text = input.value.trim();
  if (text && !points.includes(text)) points.push(text);
  render();
}

$('language').addEventListener('click', (e) => {
  const btn = e.target.closest('button');
  if (!btn || meeting) return;
  language = btn.dataset.value;
  render();
});

$('generate').addEventListener('click', generate);
$('regenerate').addEventListener('click', regenerate);
$('confirm').addEventListener('click', confirm);
$('restart').addEventListener('click', () => location.reload()); // mọi thứ chỉ nằm trong bộ nhớ nên tải lại = làm lại từ đầu
$('files').addEventListener('change', (e) => {
  addFiles([...e.target.files]);
  e.target.value = ''; // cho phép chọn lại cùng một file
});

// Bấm vào vùng kéo thả (hoặc nút "chọn tệp") đều mở hộp chọn tệp.
$('dropzone').addEventListener('click', () => {
  if (!loading) $('files').click();
});

// Đếm độ sâu vì dragenter/dragleave bắn cả khi rê qua phần tử con, nếu không viền sẽ nhấp nháy.
let dragDepth = 0;
const dropzone = $('dropzone');
dropzone.addEventListener('dragenter', (e) => {
  e.preventDefault();
  dragDepth += 1;
  dropzone.classList.add('dropzone--over');
});
dropzone.addEventListener('dragover', (e) => e.preventDefault());
dropzone.addEventListener('dragleave', () => {
  dragDepth = Math.max(0, dragDepth - 1);
  if (dragDepth === 0) dropzone.classList.remove('dropzone--over');
});
dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  dragDepth = 0;
  dropzone.classList.remove('dropzone--over');
  if (!loading) addFiles([...e.dataTransfer.files]);
});
// Thả tệp lệch ra ngoài vùng thì trình duyệt sẽ mở tệp và mất trang; chặn lại.
for (const type of ['dragover', 'drop']) window.addEventListener(type, (e) => e.preventDefault());

async function loadPreviousMeetings() {
  const select = $('previous');
  try {
    const res = await api.listMeetings('archived');
    previousMeetings = res.items ?? [];
    if (previousMeetings.length === 0) {
      const empty = document.createElement('option');
      empty.value = '';
      empty.textContent = 'No archived meetings yet';
      select.replaceChildren(empty);
    } else {
      const none = document.createElement('option');
      none.value = '';
      none.textContent = 'None (start fresh)';
      const opts = previousMeetings.map((m) => {
        const opt = document.createElement('option');
        opt.value = m.id;
        const date = new Date(m.created_at).toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric',
          year: 'numeric',
        });
        opt.textContent = `${m.topic} · ${date}`;
        return opt;
      });
      select.replaceChildren(none, ...opts);
    }
  } catch {
    previousMeetings = [];
    const errOpt = document.createElement('option');
    errOpt.value = '';
    errOpt.textContent = 'Unable to load previous meetings';
    select.replaceChildren(errOpt);
  } finally {
    render();
  }
}

render();
loadPreviousMeetings();
