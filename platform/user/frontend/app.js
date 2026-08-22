const API = "";  // same origin (FastAPI serves this file too)

const agentSwitcher = document.getElementById("agentSwitcher");
const chatPanel = document.getElementById("chatPanel");
const graphPanel = document.getElementById("graphPanel");
const graphFormFields = document.getElementById("graphFormFields");
const graphOutput = document.getElementById("graphOutput");
const threadIdInput = document.getElementById("threadIdInput");

let AGENTS = [];
let currentAgent = null;
const sessionId = "session-" + Math.random().toString(36).slice(2, 10);

// Per-graph form field definitions
const GRAPH_FIELDS = {
  study_abroad: [
    { id: "student_id", label: "student_id", type: "number", value: 1 },
    { id: "student_email", label: "student_email", type: "text", value: "omar.k@brightpeak.edu" },
  ],
  scholarship: [
    { id: "student_id", label: "student_id", type: "number", value: 1 },
    { id: "requested_amount", label: "requested_amount", type: "number", value: 1000 },
    { id: "sponsor_name", label: "sponsor_name", type: "text", value: "Demo Sponsor" },
  ],
  internship: [
    { id: "student_id", label: "student_id", type: "number", value: 1 },
    { id: "target_role_title", label: "target_role_title", type: "text", value: "Data Scientist" },
  ],
};

async function loadAgents() {
  const res = await fetch(`${API}/api/agents`);
  AGENTS = await res.json();
  agentSwitcher.innerHTML = AGENTS.map(a => `<option value="${a.id}">${a.name}</option>`).join("");
  agentSwitcher.addEventListener("change", onAgentChange);
  onAgentChange();
}

function onAgentChange() {
  currentAgent = AGENTS.find(a => a.id === agentSwitcher.value);
  if (currentAgent.type === "chat") {
    chatPanel.classList.remove("hidden");
    graphPanel.classList.add("hidden");
  } else {
    chatPanel.classList.add("hidden");
    graphPanel.classList.remove("hidden");
    renderGraphForm(currentAgent.id);
  }
}

function renderGraphForm(graphId) {
  const fields = GRAPH_FIELDS[graphId] || [];
  graphFormFields.innerHTML = fields
    .map(f => `<input id="gf_${f.id}" type="${f.type}" placeholder="${f.label}" value="${f.value}" />`)
    .join("");
  graphOutput.textContent = "";
  threadIdInput.value = "";
}

function collectGraphFields(graphId) {
  const fields = GRAPH_FIELDS[graphId] || [];
  const out = { graph: graphId };
  for (const f of fields) {
    const el = document.getElementById(`gf_${f.id}`);
    out[f.id] = f.type === "number" ? Number(el.value) : el.value;
  }
  return out;
}

document.getElementById("graphStart").addEventListener("click", async () => {
  const body = collectGraphFields(currentAgent.id);
  const res = await fetch(`${API}/api/graph/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  threadIdInput.value = data.thread_id || "";
  graphOutput.textContent = JSON.stringify(data, null, 2);
  refreshAdmin();
});

document.getElementById("graphResume").addEventListener("click", async () => {
  const res = await fetch(`${API}/api/graph/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ graph: currentAgent.id, thread_id: threadIdInput.value }),
  });
  const data = await res.json();
  graphOutput.textContent = JSON.stringify(data, null, 2);
  refreshAdmin();
});

// --- Chat (memory/RAG/planning) ---

const chatLog = document.getElementById("chatLog");

function appendChatMsg(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
}

document.getElementById("sendChat").addEventListener("click", async () => {
  const input = document.getElementById("chatInput");
  const studentId = Number(document.getElementById("studentIdChat").value);
  const message = input.value.trim();
  if (!message) return;

  appendChatMsg("user", message);
  input.value = "";

  const res = await fetch(`${API}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, student_id: studentId, message }),
  });
  const data = await res.json();
  appendChatMsg("assistant", `[${data.intent}] ${data.answer}`);
});

// --- Admin-lite: HITL + tickets ---

async function refreshAdmin() {
  const hitlRes = await fetch(`${API}/api/hitl/pending`);
  const hitlTasks = await hitlRes.json();
  document.getElementById("hitlList").innerHTML = hitlTasks.length
    ? hitlTasks.map(t => `
        <div class="hitl-item">
          <div>#${t.id} — thread: ${t.thread_id}</div>
          <div>${t.reason}</div>
          <button onclick="decideHitl(${t.id}, '${t.thread_id}', 'approved')">Approve</button>
          <button onclick="decideHitl(${t.id}, '${t.thread_id}', 'rejected')">Reject</button>
        </div>`).join("")
    : "<i>لا يوجد</i>";

  const ticketsRes = await fetch(`${API}/api/tickets/open`);
  const tickets = await ticketsRes.json();
  document.getElementById("ticketList").innerHTML = tickets.length
    ? tickets.map(t => `
        <div class="ticket-item">
          <div>#${t.id} — thread: ${t.thread_id} — node: ${t.node_name}</div>
          <div>${t.error_message}</div>
          <button onclick="resolveTicket(${t.id})">Resolve & Resume</button>
        </div>`).join("")
    : "<i>لا يوجد</i>";
}

async function decideHitl(taskId, threadId, decision) {
  const graph = currentAgent && currentAgent.type === "graph" ? currentAgent.id : threadId.split("-")[0];
  const res = await fetch(`${API}/api/hitl/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_id: taskId, decision, graph, thread_id: threadId }),
  });
  const data = await res.json();
  graphOutput.textContent = JSON.stringify(data, null, 2);
  refreshAdmin();
}

async function resolveTicket(ticketId) {
  const res = await fetch(`${API}/api/tickets/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticket_id: ticketId }),
  });
  const data = await res.json();
  graphOutput.textContent = JSON.stringify(data, null, 2);
  refreshAdmin();
}

document.getElementById("refreshAdmin").addEventListener("click", refreshAdmin);

loadAgents();
refreshAdmin();