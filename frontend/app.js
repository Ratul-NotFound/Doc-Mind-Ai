/* ═══════════════════════════════════════════════════════════════════
   DocMind — app.js
   Full chat flow: upload → embed → retrieve → stream → display
═══════════════════════════════════════════════════════════════════ */

const API_BASE = "http://localhost:8000";

// ── State ──────────────────────────────────────────────────────────
let sessionId  = null;
let isStreaming = false;

// ── DOM refs ───────────────────────────────────────────────────────
const dropZone        = document.getElementById("dropZone");
const fileInput       = document.getElementById("fileInput");
const uploadProgress  = document.getElementById("uploadProgress");
const progressBar     = document.getElementById("progressBar");
const progressLabel   = document.getElementById("progressLabel");
const sessionSection  = document.getElementById("sessionSection");
const sessionFilename = document.getElementById("sessionFilename");
const sessionStats    = document.getElementById("sessionStats");
const suggestionsSection = document.getElementById("suggestionsSection");
const clearSessionBtn = document.getElementById("clearSession");
const suggestions     = document.getElementById("suggestions");

const emptyState      = document.getElementById("emptyState");
const messages        = document.getElementById("messages");
const sourcesPanel    = document.getElementById("sourcesPanel");
const sourcesToggle   = document.getElementById("sourcesToggle");
const sourcesCount    = document.getElementById("sourcesCount");
const sourcesList     = document.getElementById("sourcesList");

const questionInput   = document.getElementById("questionInput");
const sendBtn         = document.getElementById("sendBtn");
const themeToggle     = document.getElementById("themeToggle");


// ═══════════════════════════════════════════════════════════════════
// Theme
// ═══════════════════════════════════════════════════════════════════
const savedTheme = localStorage.getItem("docmind-theme") || "dark";
document.documentElement.setAttribute("data-theme", savedTheme);

themeToggle.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme");
  const next    = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("docmind-theme", next);
});


// ═══════════════════════════════════════════════════════════════════
// File Upload — Drag & Drop + Click
// ═══════════════════════════════════════════════════════════════════
dropZone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) handleFile(fileInput.files[0]);
});

dropZone.addEventListener("dragover",  e => { e.preventDefault(); dropZone.classList.add("dragover"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
dropZone.addEventListener("drop", e => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  const file = e.dataTransfer.files[0];
  if (file && file.type === "application/pdf") {
    handleFile(file);
  } else {
    showToast("Only PDF files are supported.", "error");
  }
});

async function handleFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showToast("Only PDF files are supported.", "error"); return;
  }

  // Show progress
  showProgress("Uploading PDF…", 10);

  const formData = new FormData();
  formData.append("file", file);

  try {
    showProgress("Extracting text…", 35);
    const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: formData });
    
    showProgress("Building vector index…", 70);

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Upload failed");
    }

    const data = await res.json();
    showProgress("Ready!", 100);

    setTimeout(() => {
      hideProgress();
      activateSession(data);
    }, 500);

    showToast(`✓ ${file.name} indexed (${data.chunks} chunks)`, "success");

  } catch (err) {
    hideProgress();
    showToast(err.message, "error");
  }
}

function showProgress(label, pct) {
  uploadProgress.hidden = false;
  progressBar.style.width = pct + "%";
  progressLabel.textContent = label;
}

function hideProgress() {
  uploadProgress.hidden = true;
  progressBar.style.width = "0%";
}

function activateSession(data) {
  sessionId = data.session_id;

  sessionFilename.textContent = data.filename;
  sessionStats.textContent    = `${data.pages} page${data.pages !== 1 ? "s" : ""} · ${data.chunks} chunks indexed`;

  sessionSection.hidden    = false;
  suggestionsSection.hidden = false;

  // Enable chat
  questionInput.disabled    = false;
  questionInput.placeholder = "Ask anything about the document…";
  updateSendBtn();

  // Switch to chat view
  emptyState.hidden  = false; // keep showing until first message
}

// Clear session
clearSessionBtn.addEventListener("click", async () => {
  if (!sessionId) return;
  await fetch(`${API_BASE}/session/${sessionId}`, { method: "DELETE" }).catch(() => {});
  resetState();
});

function resetState() {
  sessionId = null;
  sessionSection.hidden    = true;
  suggestionsSection.hidden = true;
  emptyState.hidden        = false;
  messages.hidden          = true;
  sourcesPanel.hidden      = true;
  messages.innerHTML       = "";
  questionInput.disabled   = true;
  questionInput.placeholder = "Upload a PDF first to start asking questions…";
  questionInput.value      = "";
  fileInput.value          = "";
  updateSendBtn();
}


// ═══════════════════════════════════════════════════════════════════
// Suggestion Chips
// ═══════════════════════════════════════════════════════════════════
suggestions.querySelectorAll(".suggestion-chip").forEach(chip => {
  chip.addEventListener("click", () => {
    if (!sessionId || isStreaming) return;
    questionInput.value = chip.textContent;
    autoResizeTextarea();
    updateSendBtn();
    sendQuestion();
  });
});


// ═══════════════════════════════════════════════════════════════════
// Input & Send
// ═══════════════════════════════════════════════════════════════════
questionInput.addEventListener("input", () => {
  autoResizeTextarea();
  updateSendBtn();
});

questionInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (!sendBtn.disabled) sendQuestion();
  }
});

sendBtn.addEventListener("click", sendQuestion);

function autoResizeTextarea() {
  questionInput.style.height = "auto";
  questionInput.style.height = Math.min(questionInput.scrollHeight, 160) + "px";
}

function updateSendBtn() {
  const hasText = questionInput.value.trim().length > 0;
  const ready   = sessionId && hasText && !isStreaming;
  sendBtn.disabled = !ready;
}


// ═══════════════════════════════════════════════════════════════════
// Send Question → Get Answer (JSON + client-side typewriter)
// ═══════════════════════════════════════════════════════════════════
async function sendQuestion() {
  const question = questionInput.value.trim();
  if (!question || !sessionId || isStreaming) return;

  isStreaming = true;
  updateSendBtn();
  sendBtn.classList.add("loading");

  // Clear input
  questionInput.value = "";
  questionInput.style.height = "auto";

  // Show chat
  emptyState.hidden = true;
  messages.hidden   = false;

  // Append user message
  appendMessage("user", question);

  // Append AI placeholder with thinking animation
  const aiMsgEl = appendMessage("ai", "", true);
  const aiBubble = aiMsgEl.querySelector(".msg-bubble");

  try {
    const res = await fetch(`${API_BASE}/ask/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, question }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Request failed" }));
      throw new Error(err.detail || "Request failed");
    }

    const data = await res.json();
    const fullText = data.answer || "";
    const sources  = data.sources || [];

    // Typewriter animation — makes it feel like streaming
    await typewriterEffect(aiBubble, fullText);

    if (sources.length > 0) renderSources(sources);
    scrollToBottom();

  } catch (err) {
    aiBubble.innerHTML = `<span style="color:var(--danger)">⚠ ${err.message}</span>`;
  } finally {
    isStreaming = false;
    sendBtn.classList.remove("loading");
    updateSendBtn();
    questionInput.focus();
  }
}

// Typewriter effect — renders text word-by-word for a streaming feel
async function typewriterEffect(el, fullText) {
  const words = fullText.split(" ");
  let built = "";
  for (let i = 0; i < words.length; i++) {
    built += (i > 0 ? " " : "") + words[i];
    el.innerHTML = renderMarkdown(built) + '<span class="cursor"></span>';
    scrollToBottom();
    // Small random delay per word: 12–28ms feels natural
    await sleep(12 + Math.random() * 16);
  }
  el.innerHTML = renderMarkdown(fullText);
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}


// ═══════════════════════════════════════════════════════════════════
// Message Rendering
// ═══════════════════════════════════════════════════════════════════
function appendMessage(role, text, withCursor = false) {
  const wrap = document.createElement("div");
  wrap.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.textContent = role === "user" ? "U" : "AI";

  const content = document.createElement("div");
  content.className = "msg-content";

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";

  if (role === "user") {
    bubble.textContent = text;
  } else if (text === "" && withCursor) {
    bubble.innerHTML = '<div class="thinking-dots"><span></span><span></span><span></span></div>';
  } else {
    bubble.innerHTML = renderMarkdown(text);
  }

  content.appendChild(bubble);
  wrap.appendChild(avatar);
  wrap.appendChild(content);
  messages.appendChild(wrap);
  scrollToBottom();
  return wrap;
}

function scrollToBottom() {
  messages.scrollTop = messages.scrollHeight;
}


// ═══════════════════════════════════════════════════════════════════
// Sources Panel
// ═══════════════════════════════════════════════════════════════════
function renderSources(sources) {
  sourcesPanel.hidden = false;
  sourcesCount.textContent = `${sources.length} source${sources.length !== 1 ? "s" : ""} used`;

  sourcesList.innerHTML = sources
    .map(s => `
      <div class="source-item">
        <span class="source-page">Page ${s.page}</span>
        <span class="source-text">${escapeHtml(s.text)}</span>
      </div>
    `)
    .join("");
}

sourcesToggle.addEventListener("click", () => {
  const isOpen = sourcesList.classList.toggle("open");
  sourcesToggle.classList.toggle("open", isOpen);
});


// ═══════════════════════════════════════════════════════════════════
// Markdown Renderer (lightweight, no library needed)
// ═══════════════════════════════════════════════════════════════════
function renderMarkdown(text) {
  if (!text) return "";
  return text
    // Bold **text**
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    // Italic *text*
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    // Inline code `code`
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    // Bullet lists
    .replace(/^[\s]*[-•]\s+(.+)/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>")
    // Numbered lists
    .replace(/^\d+\.\s+(.+)/gm, "<li>$1</li>")
    // Paragraphs (double newline)
    .replace(/\n\n+/g, "</p><p>")
    // Single newlines
    .replace(/\n/g, "<br>")
    // Wrap in paragraph
    .replace(/^(.+)/, "<p>$1</p>");
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}


// ═══════════════════════════════════════════════════════════════════
// Toast Notifications
// ═══════════════════════════════════════════════════════════════════
function showToast(message, type = "info", duration = 4000) {
  const existing = document.querySelector(".toast");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.className = `toast ${type}`;

  const icons = {
    success: "✓",
    error:   "⚠",
    info:    "ℹ",
  };

  toast.innerHTML = `<span>${icons[type] || "ℹ"}</span><span>${escapeHtml(message)}</span>`;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.transition = "opacity 300ms ease, transform 300ms ease";
    toast.style.opacity    = "0";
    toast.style.transform  = "translateY(10px)";
    setTimeout(() => toast.remove(), 300);
  }, duration);
}
