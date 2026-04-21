const BASE = 'http://localhost:8800';

// 固定的演示用 user_uuid（真实项目应换成登录态）
export const USER_UUID = 'demo-user-001';

// ── Papers ────────────────────────────────────────────────────────────────
export async function uploadPaper(file, parseMode = 'pymupdf') {
  const form = new FormData();
  form.append('pdf_file', file);
  form.append('uploader_uuid', USER_UUID);
  form.append('parse_mode', parseMode);
  const res = await fetch(`${BASE}/papers/upload`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

export async function listPapers() {
  const res = await fetch(`${BASE}/papers/list?uploader_uuid=${USER_UUID}`);
  if (!res.ok) throw new Error(`List papers failed: ${res.status}`);
  return res.json();
}

export async function getPaper(paperUuid) {
  const res = await fetch(`${BASE}/papers/${paperUuid}`);
  if (!res.ok) throw new Error(`Get paper failed: ${res.status}`);
  return res.json();
}

export async function deletePaper(paperUuid) {
  const res = await fetch(`${BASE}/papers/${paperUuid}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Delete paper failed: ${res.status}`);
  return res.json();
}

// ── Tasks ─────────────────────────────────────────────────────────────────
export async function getTask(taskId) {
  const res = await fetch(`${BASE}/tasks/${taskId}`);
  if (!res.ok) throw new Error(`Get task failed: ${res.status}`);
  return res.json();
}

// ── Sessions ──────────────────────────────────────────────────────────────
export async function newSession(paperUuid = '') {
  const res = await fetch(`${BASE}/chat/session/new`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_uuid: USER_UUID, paper_uuid: paperUuid }),
  });
  if (!res.ok) throw new Error(`New session failed: ${res.status}`);
  return res.json();
}

export async function listSessions() {
  const res = await fetch(`${BASE}/chat/session/list?user_uuid=${USER_UUID}`);
  if (!res.ok) throw new Error(`List sessions failed: ${res.status}`);
  return res.json();
}

export async function getSessionMessages(sessionId) {
  const res = await fetch(`${BASE}/chat/session/${sessionId}`);
  if (!res.ok) throw new Error(`Get session failed: ${res.status}`);
  return res.json();
}

export async function deleteSession(sessionId) {
  const res = await fetch(`${BASE}/chat/session/${sessionId}?user_uuid=${USER_UUID}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Delete session failed: ${res.status}`);
  return res.json();
}

// ── Chat SSE ──────────────────────────────────────────────────────────────
// 返回 EventSource，调用方负责关闭
export function chatSend({ sessionId, message, paperUuids = [], onEvent, onDone, onError }) {
  const body = JSON.stringify({
    user_uuid: USER_UUID,
    session_id: sessionId,
    message,
    paper_uuids: paperUuids,
  });

  let closed = false;

  const run = async () => {
    try {
      const res = await fetch(`${BASE}/chat/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      });
      if (!res.ok) throw new Error(`Chat send failed: ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done || closed) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop(); // last may be incomplete
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const raw = line.slice(6).trim();
            if (!raw) continue;
            try {
              const ev = JSON.parse(raw);
              if (ev.event === 'done') { onDone?.(); return; }
              onEvent?.(ev);
            } catch { /* ignore parse errors */ }
          }
        }
      }
      onDone?.();
    } catch (err) {
      onError?.(err);
    }
  };

  run();
  return { close: () => { closed = true; } };
}
