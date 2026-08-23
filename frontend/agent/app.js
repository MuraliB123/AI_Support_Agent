const POLL_MS = 2000;

const els = {
  queue: document.getElementById("queue-list"),
  refresh: document.getElementById("refresh-queue"),
  empty: document.getElementById("empty-review"),
  review: document.getElementById("review"),
  ticketId: document.getElementById("rev-ticket-id"),
  decision: document.getElementById("rev-decision"),
  confidence: document.getElementById("rev-confidence"),
  subject: document.getElementById("rev-subject"),
  summary: document.getElementById("rev-summary"),
  rationale: document.getElementById("rev-rationale"),
  draft: document.getElementById("draft-editor"),
  customerPreview: document.getElementById("customer-preview"),
  citations: document.getElementById("citations"),
  note: document.getElementById("hitl-note"),
  hint: document.getElementById("action-hint"),
};

const state = {
  selectedId: null,
  ticket: null,
  busy: false,
};

function setHint(text) {
  els.hint.textContent = text;
}

async function fetchQueue() {
  const res = await fetch("/api/hitl/queue");
  if (!res.ok) throw new Error(`queue ${res.status}`);
  return res.json();
}

async function fetchTicket(ticketId) {
  const res = await fetch(`/api/tickets/${ticketId}`);
  if (!res.ok) throw new Error(`ticket ${res.status}`);
  return res.json();
}

function renderQueue(tickets) {
  els.queue.innerHTML = "";
  if (!tickets.length) {
    const li = document.createElement("li");
    li.className = "queue-empty";
    li.textContent = "No tickets waiting.";
    els.queue.appendChild(li);
    return;
  }

  for (const item of tickets) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "queue-item" + (item.ticket_id === state.selectedId ? " active" : "");
    btn.innerHTML = `
      <div class="qid">${item.ticket_id}</div>
      <div class="qmeta">${item.subject || "(no subject)"}</div>
      <div class="qmeta">${item.decision || "—"} · conf ${
        item.confidence != null ? Number(item.confidence).toFixed(2) : "—"
      }</div>
    `;
    if (item.low_confidence) {
      const badge = document.createElement("span");
      badge.className = "badge-low";
      badge.textContent = "low confidence";
      btn.appendChild(badge);
    }
    btn.addEventListener("click", () => selectTicket(item.ticket_id));
    li.appendChild(btn);
    els.queue.appendChild(li);
  }
}

function renderCitations(ticket) {
  els.citations.innerHTML = "";
  const list =
    (ticket.citations && ticket.citations.length
      ? ticket.citations
      : (ticket.retrieved_chunks || []).map((c) => ({
          chunk_id: c.chunk_id,
          policy_id: c.policy_id,
          section_title: c.section_title,
          score: c.score,
        }))) || [];

  if (!list.length) {
    const li = document.createElement("li");
    li.className = "citations-empty";
    li.textContent = "None";
    els.citations.appendChild(li);
    return;
  }

  for (const c of list) {
    const li = document.createElement("li");
    const score =
      c.score != null && c.score !== ""
        ? ` · score ${Number(c.score).toFixed(3)}`
        : "";
    li.textContent = `${c.policy_id || "—"} · ${c.section_title || c.chunk_id || "—"}${score}`;
    els.citations.appendChild(li);
  }
}

function renderTicket(ticket) {
  state.ticket = ticket;
  els.empty.hidden = true;
  els.review.hidden = false;

  els.ticketId.textContent = ticket.ticket_id;
  els.decision.textContent = ticket.decision || ticket.action_type || "—";
  els.confidence.textContent =
    ticket.confidence != null ? Number(ticket.confidence).toFixed(2) : "—";
  els.subject.textContent = ticket.subject || "—";
  els.summary.textContent = ticket.context_summary || "—";
  els.rationale.textContent = ticket.decision_rationale || "—";
  els.draft.value = ticket.draft || "";

  const isEscalate =
    ticket.decision === "escalate" || ticket.action_type === "escalate";
  if (isEscalate) {
    els.customerPreview.hidden = false;
    els.customerPreview.textContent =
      "Customer will see: " +
      (ticket.customer_message_preview ||
        "Your request has been escalated. A support engineer will call you within 24 hours.");
  } else {
    els.customerPreview.hidden = true;
    els.customerPreview.textContent = "";
  }

  const note = ticket.hitl_note || "";
  if (note || ticket.low_confidence) {
    els.note.hidden = false;
    els.note.textContent =
      note ||
      "LOW CONFIDENCE: triage was unsure — review carefully before approving.";
  } else {
    els.note.hidden = true;
    els.note.textContent = "";
  }

  renderCitations(ticket);
  setHint(
    "Approve sends the draft back to the customer UI as agent-approved (still not auto-emailed)."
  );
}

async function selectTicket(ticketId) {
  state.selectedId = ticketId;
  const ticket = await fetchTicket(ticketId);
  if (ticket.phase !== "waiting_hitl") {
    setHint("This ticket is no longer waiting for HITL. Refreshing queue…");
    state.selectedId = null;
    els.review.hidden = true;
    els.empty.hidden = false;
    await refreshQueue();
    return;
  }
  renderTicket(ticket);
  await refreshQueue();
}

async function refreshQueue() {
  try {
    const data = await fetchQueue();
    renderQueue(data.tickets || []);
    if (
      state.selectedId &&
      !(data.tickets || []).some((t) => t.ticket_id === state.selectedId)
    ) {
      // Selected ticket left the queue (approved / still regenerating)
      if (state.ticket && state.ticket.phase === "waiting_hitl") {
        // still selected but maybe regenerating — keep panel
      } else {
        els.review.hidden = true;
        els.empty.hidden = false;
        state.selectedId = null;
      }
    }
  } catch (err) {
    console.error(err);
  }
}

async function submitAction(action) {
  if (!state.selectedId || state.busy) return;
  const body = { action };
  if (action === "edit") {
    body.edited_draft = els.draft.value;
  }

  state.busy = true;
  document.querySelectorAll(".actions .btn").forEach((b) => (b.disabled = true));
  setHint(`Submitting ${action}…`);

  try {
    const res = await fetch(`/api/tickets/${state.selectedId}/hitl`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(detail || `status ${res.status}`);
    }

    if (action === "request_regeneration" || action === "escalate") {
      setHint("Regenerating draft — this ticket will return to the queue shortly.");
      // Poll until waiting_hitl again or complete
      const ticketId = state.selectedId;
      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        const ticket = await fetchTicket(ticketId);
        if (ticket.phase === "waiting_hitl") {
          renderTicket(ticket);
          setHint("New draft ready for review.");
          break;
        }
        if (ticket.phase === "complete" || ticket.phase === "error") {
          setHint(`Ticket finished (${ticket.phase}).`);
          state.selectedId = null;
          els.review.hidden = true;
          els.empty.hidden = false;
          break;
        }
      }
    } else {
      setHint(`Action "${action}" accepted.`);
      state.selectedId = null;
      state.ticket = null;
      els.review.hidden = true;
      els.empty.hidden = false;
    }
    await refreshQueue();
  } catch (err) {
    console.error(err);
    setHint(`Failed: ${err.message || err}`);
  } finally {
    state.busy = false;
    document.querySelectorAll(".actions .btn").forEach((b) => (b.disabled = false));
  }
}

document.querySelectorAll(".actions .btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const action = btn.getAttribute("data-action");
    if (action) submitAction(action);
  });
});

els.refresh.addEventListener("click", () => refreshQueue());

refreshQueue();
setInterval(refreshQueue, POLL_MS);
