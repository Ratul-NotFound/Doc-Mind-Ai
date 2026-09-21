/* ═══════════════════════════════════════════════════════════════════
   DocMind — app.js
   Full chat flow: upload → embed → retrieve → stream → display
   Modern Standard AI UI: Collapsible Sidebar, Expansive Chat Stream,
   Persistent Sessions, Multi-Turn Context, and 1-Click Copy.
═══════════════════════════════════════════════════════════════════ */

const API_BASE = window.location.origin.startsWith("http")
  ? window.location.origin
  : "http://localhost:8000";

// ── State ──────────────────────────────────────────────────────────
let sessionId   = null;
let isStreaming = false;
let chatHistory = []; // {role: 'user' | 'assistant', content: string}

// ── DOM refs ───────────────────────────────────────────────────────
const sidebar         = document.getElementById("sidebar");
const sidebarToggle   = document.getElementById("sidebarToggle");
const sidebarCloseBtn = document.getElementById("sidebarCloseBtn");
const sidebarOverlay  = document.getElementById("sidebarOverlay");

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

const chatScrollContainer = document.getElementById("chatScrollContainer");
const emptyState      = document.getElementById("emptyState");
const emptyUploadTrigger = document.getElementById("emptyUploadTrigger");
const messages        = document.getElementById("messages");
const sourcesPanel    = document.getElementById("sourcesPanel");
const sourcesToggle   = document.getElementById("sourcesToggle");
const sourcesCount    = document.getElementById("sourcesCount");
const sourcesList     = document.getElementById("sourcesList");

const questionInput   = document.getElementById("questionInput");
const sendBtn         = document.getElementById("sendBtn");
const clearChatBtn    = document.getElementById("clearChatBtn");
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
// Sidebar Toggle (Standard Collapsible Layout)
// ═══════════════════════════════════════════════════════════════════
function toggleSidebar() {
  const isCollapsed = sidebar.classList.toggle("collapsed");
  sidebarOverlay.classList.toggle("open", !isCollapsed && window.innerWidth <= 768);
  localStorage.setItem("docmind-sidebar", isCollapsed ? "collapsed" : "open");
}

function closeMobileSidebar() {
  sidebar.classList.add("collapsed");
  sidebarOverlay.classList.remove("open");
}

sidebarToggle.addEventListener("click", toggleSidebar);
if (sidebarCloseBtn) sidebarCloseBtn.addEventListener("click", closeMobileSidebar);
if (sidebarOverlay) sidebarOverlay.addEventListener("click", closeMobileSidebar);

// Restore sidebar state
if (window.innerWidth <= 768) {
  sidebar.classList.add("collapsed");
} else if (localStorage.getItem("docmind-sidebar") === "collapsed") {
  sidebar.classList.add("collapsed");
}


// ═══════════════════════════════════════════════════════════════════
// Session Restore
// ═══════════════════════════════════════════════════════════════════
window.addEventListener("DOMContentLoaded", async () => {
  const savedSession = localStorage.getItem("docmind_active_session");
  if (savedSession) {
    try {
      const sessionData = JSON.parse(savedSession);
      if (sessionData && sessionData.session_id) {
        const res = await fetch(`${API_BASE}/session/${sessionData.session_id}`);
        if (res.ok) {
          const verifiedData = await res.json();
          activateSession(verifiedData, false);
          showToast(`Restored: ${verifiedData.filename || 'PDF Document'}`, "info");
        } else {
          localStorage.removeItem("docmind_active_session");
        }
      }
    } catch (e) {
      console.warn("Could not restore session:", e);
    }
  }
});


// ═══════════════════════════════════════════════════════════════════
// File Upload
// ═══════════════════════════════════════════════════════════════════
dropZone.addEventListener("click", () => fileInput.click());
if (emptyUploadTrigger) emptyUploadTrigger.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) handleFile(fileInput.files[0]);
});

dropZone.addEventListener("dragover",  e => { e.preventDefault(); dropZone.classList.add("dragover"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
dropZone.addEventListener("drop", e => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  const file = e.dataTransfer.files[0];
  if (file && (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"))) {
    handleFile(file);
  } else {
    showToast("Only PDF files are supported.", "error");
  }
});

async function handleFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showToast("Only PDF files are supported.", "error");
    return;
  }

  showProgress("Uploading PDF…", 15);

  const formData = new FormData();
  formData.append("file", file);

  try {
    showProgress("Extracting & parsing text…", 40);
    const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: formData });
    
    showProgress("Building FAISS semantic index…", 75);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Upload failed" }));
      throw new Error(err.detail || "Upload failed");
    }

    const data = await res.json();
    showProgress("Ready!", 100);

    setTimeout(() => {
      hideProgress();
      activateSession(data, true);
    }, 400);

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

function activateSession(data, isNew = true) {
  sessionId = data.session_id;
  localStorage.setItem("docmind_active_session", JSON.stringify(data));

  sessionFilename.textContent = data.filename || "document.pdf";
  sessionStats.textContent    = `${data.pages || 0} page${data.pages !== 1 ? "s" : ""} · ${data.chunks || 0} chunks indexed`;

  sessionSection.hidden     = false;
  suggestionsSection.hidden = false;

  questionInput.disabled    = false;
  questionInput.placeholder = "Ask anything about this document…";
  updateSendBtn();

  if (isNew) {
    clearChat();
  }
}

clearSessionBtn.addEventListener("click", async () => {
  if (!sessionId) return;
  const currentId = sessionId;
  resetState();
  localStorage.removeItem("docmind_active_session");
  await fetch(`${API_BASE}/session/${currentId}`, { method: "DELETE" }).catch(() => {});
  showToast("Document session removed.", "info");
});

function resetState() {
  sessionId = null;
  chatHistory = [];
  sessionSection.hidden     = true;
  suggestionsSection.hidden = true;
  clearChat();
  questionInput.disabled    = true;
  questionInput.placeholder = "Upload a PDF to begin asking questions…";
  questionInput.value       = "";
  fileInput.value           = "";
  updateSendBtn();
}


// ═══════════════════════════════════════════════════════════════════
// Clear Chat Action
// ═══════════════════════════════════════════════════════════════════
function clearChat() {
  chatHistory = [];
  messages.innerHTML = "";
  messages.hidden = true;
  emptyState.hidden = false;
  sourcesPanel.hidden = true;
}

clearChatBtn.addEventListener("click", () => {
  if (messages.children.length > 0) {
    clearChat();
    showToast("Chat history cleared.", "info");
  }
});


// ═══════════════════════════════════════════════════════════════════
// Suggestions
// ═══════════════════════════════════════════════════════════════════
suggestions.querySelectorAll(".suggestion-chip").forEach(chip => {
  chip.addEventListener("click", () => {
    if (!sessionId || isStreaming) return;
    questionInput.value = chip.textContent.replace(/^[✨📊🔍📋]\s*/, "").trim();
    autoResizeTextarea();
    updateSendBtn();
    sendQuestion();
    if (window.innerWidth <= 768) closeMobileSidebar();
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
  questionInput.style.height = Math.min(questionInput.scrollHeight, 180) + "px";
}

function updateSendBtn() {
  const hasText = questionInput.value.trim().length > 0;
  const ready   = sessionId && hasText && !isStreaming;
  sendBtn.disabled = !ready;
}


// ═══════════════════════════════════════════════════════════════════
// Send Question & Streaming Typewriter
// ═══════════════════════════════════════════════════════════════════
async function sendQuestion() {
  const question = questionInput.value.trim();
  if (!question || !sessionId || isStreaming) return;

  isStreaming = true;
  updateSendBtn();

  questionInput.value = "";
  questionInput.style.height = "auto";

  emptyState.hidden = true;
  messages.hidden   = false;

  appendMessage("user", question);

  const aiMsgEl = appendMessage("ai", "", true);
  const aiBubble = aiMsgEl.querySelector(".msg-bubble");
  const aiContent = aiMsgEl.querySelector(".msg-content");

  try {
    const payload = {
      session_id: sessionId,
      question: question,
      history: chatHistory.slice(-4),
    };

    const res = await fetch(`${API_BASE}/ask/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Request failed" }));
      throw new Error(err.detail || "Request failed");
    }

    const data = await res.json();
    const fullText = data.answer || "No response generated.";
    const sources  = data.sources || [];

    await typewriterEffect(aiBubble, fullText);

    chatHistory.push({ role: "user", content: question });
    chatHistory.push({ role: "assistant", content: fullText });

    addMessageActions(aiContent, fullText);

    if (sources.length > 0) renderSources(sources);
    scrollToBottom();

  } catch (err) {
    aiBubble.innerHTML = `<span style="color:var(--danger)">⚠ ${escapeHtml(err.message)}</span>`;
  } finally {
    isStreaming = false;
    updateSendBtn();
    questionInput.focus();
  }
}

async function typewriterEffect(el, fullText) {
  const words = fullText.split(" ");
  let built = "";
  for (let i = 0; i < words.length; i++) {
    built += (i > 0 ? " " : "") + words[i];
    el.innerHTML = renderMarkdown(built) + '<span class="cursor"></span>';
    scrollToBottom();
    await sleep(8 + Math.random() * 12);
  }
  el.innerHTML = renderMarkdown(fullText);
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function addMessageActions(contentEl, text) {
  const actions = document.createElement("div");
  actions.className = "msg-actions";

  const copyBtn = document.createElement("button");
  copyBtn.className = "msg-action-btn";
  copyBtn.innerHTML = `
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
    </svg> Copy
  `;

  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(text);
      copyBtn.innerHTML = `✓ Copied!`;
      setTimeout(() => {
        copyBtn.innerHTML = `
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg> Copy
        `;
      }, 2000);
    } catch (e) {
      showToast("Could not copy to clipboard", "error");
    }
  });

  actions.appendChild(copyBtn);
  contentEl.appendChild(actions);
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
  if (role === "ai") wrap.appendChild(avatar);
  wrap.appendChild(content);
  messages.appendChild(wrap);
  scrollToBottom();
  return wrap;
}

function scrollToBottom() {
  if (chatScrollContainer) {
    chatScrollContainer.scrollTop = chatScrollContainer.scrollHeight;
  }
}


// ═══════════════════════════════════════════════════════════════════
// Sources Panel
// ═══════════════════════════════════════════════════════════════════
function renderSources(sources) {
  sourcesPanel.hidden = false;
  sourcesCount.textContent = `${sources.length} source passage${sources.length !== 1 ? "s" : ""} retrieved`;

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
// Markdown Renderer
// ═══════════════════════════════════════════════════════════════════
function renderMarkdown(raw) {
  if (!raw) return "";

  let text = escapeHtml(raw);

  // Fenced code blocks
  text = text.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre><code class="language-${lang}">${code.trim()}</code></pre>`;
  });

  // Inline code
  text = text.replace(/`([^`\n]+)`/g, "<code>$1</code>");

  // Headings
  text = text.replace(/^### (.*$)/gim, "<h3>$1</h3>");
  text = text.replace(/^## (.*$)/gim, "<h2>$1</h2>");
  text = text.replace(/^# (.*$)/gim, "<h1>$1</h1>");

  // Bold & Italic
  text = text.replace(/\*\*\*(.*?)\*\*\*/g, "<strong><em>$1</em></strong>");
  text = text.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");

  // Paragraphs & Lists
  const blocks = text.split(/\n{2,}/);
  const formattedBlocks = blocks.map(block => {
    block = block.trim();
    if (!block) return "";

    if (/^<(pre|h1|h2|h3|table)/i.test(block)) {
      return block;
    }

    const lines = block.split("\n");
    const isBulletList = lines.every(l => /^[\s]*[-•*]\s+/.test(l));
    if (isBulletList && lines.length > 0) {
      const items = lines.map(l => `<li>${l.replace(/^[\s]*[-•*]\s+/, "")}</li>`).join("");
      return `<ul>${items}</ul>`;
    }

    const isNumberedList = lines.every(l => /^[\s]*\d+\.\s+/.test(l));
    if (isNumberedList && lines.length > 0) {
      const items = lines.map(l => `<li>${l.replace(/^[\s]*\d+\.\s+/, "")}</li>`).join("");
      return `<ol>${items}</ol>`;
    }

    return `<p>${lines.join("<br>")}</p>`;
  });

  return formattedBlocks.join("");
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
function showToast(message, type = "info", duration = 3500) {
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
    toast.style.transition = "opacity 250ms ease, transform 250ms ease";
    toast.style.opacity    = "0";
    toast.style.transform  = "translateY(8px)";
    setTimeout(() => toast.remove(), 250);
  }, duration);
}
