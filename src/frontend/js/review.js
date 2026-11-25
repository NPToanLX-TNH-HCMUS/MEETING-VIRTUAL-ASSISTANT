// The shared "needs review" pieces for the During and After pages. Display only: every
// flag comes from fields the backend sent; the UI never decides a value itself.

export const TYPE_LABELS = {
  decision: "Decision",
  action_item: "Action item",
  deadline: "Deadline",
  unresolved_issue: "Unresolved issue",
};

const FIELD_LABELS = { assignee: "Assignee", deadline: "Deadline" };

// Seconds from the meeting start (pauses excluded) as m:ss; "—" when the backend sent no time.
export function formatTime(seconds) {
  if (typeof seconds !== "number") return "—";
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

// "2026-10-30" -> "30/10"; split instead of Date so no time zone can shift the day.
export function formatDeadline(deadline) {
  const [, month, day] = deadline.split("-");
  return `${day}/${month}`;
}

const formatValue = (field, value) => (field === "deadline" ? formatDeadline(value) : value);

export const openConflicts = (conflicts) => [...conflicts].filter((c) => !c.resolved);

// Owner, due date and what is missing or disputed; a missing field is said in words, never guessed.
export function extractionDetails(item, conflicts = []) {
  return [
    item.assignee,
    item.deadline && `due ${formatDeadline(item.deadline)}`,
    ...item.missing_fields.map((field) => `${field} missing`),
    ...openConflicts(conflicts)
      .filter((c) => c.extraction_id === item.id)
      .map((c) => `${c.field} conflict`),
  ].filter(Boolean);
}

// Why an item needs review, as text chips (never colour alone).
function reasons(item) {
  return [
    ...item.missing_fields.map((field) => `${FIELD_LABELS[field] ?? field}: Not stated`),
    !item.evidence.segment_ids.length && "No evidence in the transcript",
    item.is_low_confidence && "Low confidence audio",
  ].filter(Boolean);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function evidenceText(evidence, segmentsById) {
  const times = evidence.segment_ids.map((id) => formatTime(segmentsById.get(id)?.start_seconds));
  return times.length ? `Said at ${times.join(", ")}` : "No evidence";
}

// A conflict: every stated value is a button with its evidence. Nothing is pre-selected.
function conflictCard(conflict, item, segmentsById, onChoose, canChoose) {
  const card = el("li", "review review--conflict");
  card.append(
    el("p", "review__type", `Conflict · ${FIELD_LABELS[conflict.field] ?? conflict.field}`),
    el("p", "review__content", item ? item.content : conflict.extraction_id),
    el("p", "capture__meta", canChoose
      ? "Two different values were said. Pick the right one."
      : "Two different values were said. It can no longer be changed here."),
  );
  const options = el("div", "review__options");
  for (const option of conflict.options) {
    const button = el("button", "review__option");
    button.type = "button";
    button.disabled = !canChoose;
    button.append(
      el("strong", null, formatValue(conflict.field, option.value)),
      el("span", "review__evidence", evidenceText(option.evidence, segmentsById)),
    );
    if (option.evidence.quote) {
      button.append(el("span", "review__quote", `“${option.evidence.quote}”`));
    }
    button.setAttribute("aria-label", `Choose ${formatValue(conflict.field, option.value)}`);
    button.addEventListener("click", () => {
      options.querySelectorAll("button").forEach((b) => { b.disabled = true; });
      onChoose(conflict, option.value);
    });
    options.append(button);
  }
  card.append(options);
  return card;
}

function itemCard(item, segmentsById) {
  const card = el("li", "review");
  card.append(
    el("p", "review__type", TYPE_LABELS[item.type] ?? item.type),
    el("p", "review__content", item.content),
  );
  const details = [item.assignee, item.deadline && `due ${formatDeadline(item.deadline)}`].filter(Boolean);
  if (details.length) card.append(el("p", "capture__meta", details.join(" · ")));
  const chips = el("div", "review__reasons");
  chips.append(...reasons(item).map((text) => el("span", "review__reason", text)));
  card.append(chips);
  if (item.evidence.segment_ids.length) {
    const evidence = el("p", "capture__meta", evidenceText(item.evidence, segmentsById));
    evidence.title = `“${item.evidence.quote}”`;
    card.append(evidence);
  }
  return card;
}

/**
 * Fill a list with what needs the user: open conflicts first, then flagged items.
 * Returns how many entries were rendered.
 */
export function renderReviewList(list, { items, conflicts, segmentsById, onChoose, canChoose }) {
  const byId = new Map(items.map((item) => [item.id, item]));
  const open = openConflicts(conflicts);
  const disputed = new Set(open.map((c) => c.extraction_id));
  // An item with an open conflict is already shown by its conflict card.
  const flagged = items.filter((item) => item.needs_confirmation && !disputed.has(item.id));
  list.replaceChildren(
    ...open.map((c) => conflictCard(c, byId.get(c.extraction_id), segmentsById, onChoose, canChoose)),
    ...flagged.map((item) => itemCard(item, segmentsById)),
  );
  return open.length + flagged.length;
}
