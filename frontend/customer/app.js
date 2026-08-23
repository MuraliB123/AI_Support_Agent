const POLL_INTERVAL_MS = 1200;

const els = {
  chat: document.getElementById("chat-scroll"),
  intro: document.getElementById("intro"),
  form: document.getElementById("composer"),
  subject: document.getElementById("subject-input"),
  message: document.getElementById("message-input"),
  send: document.getElementById("send-button"),
  hint: document.getElementById("composer-hint"),
  feed: document.getElementById("status-feed"),
  badge: document.getElementById("ticket-badge"),
  ticketId: document.getElementById("ticket-id"),
};

const state = {
  ticketId: null,
  lastSeq: 0,
  phase: null,
  pollTimer: null,
  askedQuestions: new Set(),
};

function addBubble(text, role, sender) {
  els.intro?.remove();
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  if (sender) {
    const label = document.createElement("span");
    label.className = "sender";
    label.textContent = sender;
    bubble.appendChild(label);
  }
  bubble.appendChild(document.createTextNode(text));
  els.chat.appendChild(bubble);
  els.chat.scrollTop = els.chat.scrollHeight;
}

function showTyping(on) {
  const existing = document.getElementById("typing");
  if (!on) {
    existing?.remove();
    return;
  }
  if (existing) return;
  const node = document.createElement("div");
  node.className = "typing";
  node.id = "typing";
  node.innerHTML = "<span></span><span></span><span></span>";
  els.chat.appendChild(node);
  els.chat.scrollTop = els.chat.scrollHeight;
}

function addStatus(event) {
  const empty = els.feed.querySelector(".status-empty");
  empty?.remove();

  const item = document.createElement("li");
  item.className = "status-item";
  item.dataset.stage = event.stage;

  const stage = document.createElement("div");
  stage.className = "status-stage";
  stage.textContent = event.stage.replace(/_/g, " ");

  const message = document.createElement("div");
  message.className = "status-message";
  message.textContent = event.message || "—";

  const time = document.createElement("div");
  time.className = "status-time";
  time.textContent = new Date(event.created_at).toLocaleTimeString();

  item.append(stage, message, time);
  els.feed.appendChild(item);
  els.feed.scrollTop = els.feed.scrollHeight;
}

function setComposerMode(mode) {
  if (mode === "followup") {
    els.subject.hidden = true;
    els.subject.required = false;
    els.message.placeholder = "Type your answer...";
    els.message.disabled = false;
    els.send.disabled = false;
    els.hint.textContent = "The assistant is waiting for your answer.";
    els.message.focus();
  } else if (mode === "locked") {
    els.message.disabled = true;
    els.send.disabled = true;
    els.hint.textContent = "Working on your ticket...";
  } else if (mode === "done") {
    els.message.disabled = true;
    els.send.disabled = true;
    els.hint.textContent =
      "Intake complete. A human agent reviews every reply before it is sent.";
  }
}

async function pollEvents() {
  if (!state.ticketId) return;

  try {
    const res = await fetch(
      `/api/tickets/${state.ticketId}/events?after=${state.lastSeq}`
    );
    if (!res.ok) throw new Error(`status ${res.status}`);
    const data = await res.json();

    for (const event of data.events) {
      state.lastSeq = Math.max(state.lastSeq, event.seq);
      addStatus(event);

      if (event.stage === "waiting_user" && event.message) {
        if (!state.askedQuestions.has(event.seq)) {
          state.askedQuestions.add(event.seq);
          showTyping(false);
          addBubble(event.message, "agent", "Assistant");
        }
      }
      if (event.stage === "error") {
        showTyping(false);
        addBubble(event.message, "system");
      }
      if (event.stage === "info_complete" && event.data?.summary) {
        showTyping(false);
        addBubble(`Summary: ${event.data.summary}`, "system");
      }
    }

    state.phase = data.phase;

    if (data.phase === "waiting_user") {
      showTyping(false);
      setComposerMode("followup");
    } else if (data.phase === "running") {
      showTyping(true);
      setComposerMode("locked");
    } else {
      showTyping(false);
      setComposerMode("done");
      stopPolling();
    }
  } catch (err) {
    console.error("poll failed", err);
  }
}

function startPolling() {
  stopPolling();
  state.pollTimer = setInterval(pollEvents, POLL_INTERVAL_MS);
  pollEvents();
}

function stopPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
}

async function createTicket(subject, message) {
  const res = await fetch("/api/tickets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subject, message }),
  });
  if (!res.ok) throw new Error(`create failed: ${res.status}`);
  return res.json();
}

async function sendReply(message) {
  const res = await fetch(`/api/tickets/${state.ticketId}/reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(`reply failed: ${res.status}`);
  return res.json();
}

els.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = els.message.value.trim();
  if (!message) return;

  els.send.disabled = true;
  els.message.disabled = true;

  try {
    if (!state.ticketId) {
      const subject = els.subject.value.trim();
      if (!subject) {
        els.subject.focus();
        return;
      }
      addBubble(message, "user", "You");
      const data = await createTicket(subject, message);
      state.ticketId = data.ticket_id;
      els.ticketId.textContent = data.ticket_id;
      els.badge.hidden = false;
      els.subject.hidden = true;
      els.subject.required = false;
    } else {
      addBubble(message, "user", "You");
      await sendReply(message);
    }

    els.message.value = "";
    showTyping(true);
    setComposerMode("locked");
    startPolling();
  } catch (err) {
    console.error(err);
    addBubble("Could not reach the support service. Please retry.", "system");
    els.message.disabled = false;
    els.send.disabled = false;
  }
});

els.message.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    els.form.requestSubmit();
  }
});
