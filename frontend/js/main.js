// Toàn bộ logic của trang "Tạo agenda". Đọc từ trên xuống dưới là hiểu:
//   1. Dữ liệu của trang (biến)           2. Hiển thị (render*)
//   3. Hành động (generate, confirm, ...) 4. Gắn sự kiện (click, input)
//
// Luồng chính:  bấm "Tạo agenda" -> generate() -> api.* (api.js) -> lưu kết quả vào `agenda`
//               -> render() đọc `agenda` và điền vào các ô có id trong index.html.
import { api, ApiError } from './api.js';

const $ = (id) => document.getElementById(id); // lấy phần tử HTML theo id
const MAX_FILE_BYTES = 10 * 1024 * 1024; // giới hạn upload trong API contract

// ============ 1. DỮ LIỆU (nằm trong bộ nhớ, tải lại trang là mất) ============
let meeting = null; // cuộc họp backend trả về sau khi tạo: { id, status, duration_minutes, ... }
let files = []; // các File người dùng đã chọn
const uploaded = new Set(); // các File đã gửi lên backend (để không gửi lại)
let agenda = null; // { items, dropped, duration, confirmed, edited } hoặc null khi chưa tạo
let loading = false; // đang tạo agenda
let confirming = false; // đang lưu agenda
let errorMessage = ''; // chữ hiện ở banner đỏ, '' = không có lỗi

// ============ 2. HIỂN THỊ ============
const SOURCE_LABEL = {
  carry_over: 'Từ buổi trước',
  planned_point: 'Ý dự định trình bày',
  document: 'Tài liệu',
  manual: 'Thêm thủ công',
};
const REASON_LABEL = { exceeds_remaining_time: 'không vừa thời gian còn lại' };

const isMinutesValid = (m) => Number.isInteger(m) && m >= 1 && m <= 480;
const isItemValid = (it) => !!it.title?.trim() && isMinutesValid(it.estimated_minutes);
const flag = (input, bad) => (bad ? input.setAttribute('aria-invalid', 'true') : input.removeAttribute('aria-invalid'));

// Vẽ lại toàn bộ trang từ các biến ở mục 1.
function render() {
  $('error').hidden = !errorMessage;
  $('error').textContent = errorMessage;

  // Đã tạo cuộc họp trên backend thì không sửa được thông tin nữa (backend chưa có API sửa).
  for (const id of ['topic', 'language', 'duration', 'points']) $(id).disabled = !!meeting;
  $('details-locked').hidden = !meeting;

  renderFileList();

  $('generate').disabled = loading || !!agenda;
  $('generate').textContent = loading && !agenda ? 'Đang tạo…' : 'Tạo agenda';
  $('agenda-empty').hidden = !!agenda || loading;
  $('agenda-loading').hidden = !!agenda || !loading;
  $('agenda-content').hidden = !agenda;
  $('planned').hidden = !agenda;
  if (!agenda) return;

  renderRows();
  renderDropped();
  renderSummary();
}

function renderFileList() {
  $('file-list').replaceChildren(
    ...files.map((file) => {
      const li = document.createElement('li');
      li.textContent = `${file.name} · ${Math.ceil(file.size / 1024)} KB`;
      // Backend chưa có API xoá tài liệu, nên file đã gửi lên thì không bỏ được.
      if (!uploaded.has(file)) {
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'icon-btn';
        remove.textContent = '×';
        remove.setAttribute('aria-label', `Bỏ ${file.name}`);
        remove.addEventListener('click', () => {
          files = files.filter((f) => f !== file);
          render();
        });
        li.append(' ', remove);
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

    q('source').textContent = SOURCE_LABEL[item.source] ?? item.source ?? '—';
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
      const text = [d.title, d.estimated_minutes && `${d.estimated_minutes} phút`, REASON_LABEL[d.reason] ?? d.reason];
      banner.textContent = `Bị loại: ${text.filter(Boolean).join(' · ')}`;
      return banner;
    }),
  );
}

// Phần phụ thuộc vào số phút và trạng thái xác nhận (gọi lại mỗi khi người dùng gõ).
function renderSummary() {
  const planned = agenda.items.reduce((sum, it) => sum + (Number.isFinite(it.estimated_minutes) ? it.estimated_minutes : 0), 0);
  const over = Number.isFinite(agenda.duration) && planned > agenda.duration;
  $('planned').textContent = `${planned} / ${agenda.duration ?? '—'} phút đã xếp${over ? ` · vượt ${planned - agenda.duration} phút` : ''}`;
  $('planned').classList.toggle('planned--over', over);

  $('agenda-note').textContent = agenda.confirmed
    ? 'Agenda đã được xác nhận và lưu.'
    : 'Chưa có gì được lưu cho đến khi bạn xác nhận. Sửa tiêu đề, thời lượng hoặc đổi thứ tự bằng nút ↑ ↓.';

  const valid = agenda.items.length > 0 && agenda.items.every(isItemValid);
  $('agenda-invalid').hidden = valid || agenda.items.length === 0;

  $('confirm').disabled = confirming || loading || !valid || agenda.confirmed;
  $('confirm').textContent = confirming ? 'Đang lưu…' : 'Xác nhận agenda';

  // Backend chỉ cho tạo agenda khi cuộc họp còn "draft".
  $('regenerate').disabled = loading || confirming || meeting?.status !== 'draft';
  $('regenerate').textContent = loading ? 'Đang tạo…' : 'Tạo lại';
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
      errorMessage = 'Backend không còn cuộc họp này (có thể server vừa khởi động lại). Nhấn “Tạo agenda” để thử lại.';
    } else if (e.code === 'BACKEND_UNREACHABLE') {
      errorMessage = 'Không kết nối được backend (127.0.0.1:8000). Server đã chạy chưa?';
    } else if (e.code === 'REQUEST_TIMEOUT') {
      errorMessage = 'Backend phản hồi quá lâu.';
    } else {
      errorMessage = e.message || `Đã có lỗi (${e.code}).`;
    }
  } else {
    errorMessage = `Đã có lỗi: ${e.message}`;
  }
}

// Đọc form. Trả về null (và hiện lỗi) nếu chưa hợp lệ.
function readDetails() {
  const topic = $('topic').value.trim();
  const raw = $('duration').value.trim();
  const duration = /^\d+$/.test(raw) ? Number(raw) : NaN;
  if (!topic) return fail('Nhập chủ đề để tạo agenda.');
  if (!isMinutesValid(duration)) return fail('Thời lượng phải là số nguyên từ 1 đến 480 phút.');
  return {
    topic,
    language: $('language').value,
    duration_minutes: duration,
    planned_points: $('points').value.split('\n').map((s) => s.trim()).filter(Boolean),
    previous_meeting_id: null, // backend chưa liệt kê được buổi họp trước
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
      await api.uploadDocument(meeting.id, file);
      uploaded.add(file);
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
  if (agenda.edited && !window.confirm('Các chỉnh sửa của bạn sẽ mất. Tạo lại agenda?')) return;
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
    if (!/\.(md|txt)$/i.test(file.name)) problems.push(`${file.name}: chỉ nhận .md và .txt`);
    else if (file.size > MAX_FILE_BYTES) problems.push(`${file.name}: lớn hơn 10 MB`);
    else if (files.some((f) => f.name === file.name)) problems.push(`${file.name}: đã được thêm`);
    else files.push(file);
  }
  errorMessage = problems.join('. ');
  render();
}

// ============ 4. GẮN SỰ KIỆN ============
$('generate').addEventListener('click', generate);
$('regenerate').addEventListener('click', regenerate);
$('confirm').addEventListener('click', confirm);
$('restart').addEventListener('click', () => location.reload()); // mọi thứ chỉ nằm trong bộ nhớ nên tải lại = làm lại từ đầu
$('files').addEventListener('change', (e) => {
  addFiles([...e.target.files]);
  e.target.value = ''; // cho phép chọn lại cùng một file
});

render();
