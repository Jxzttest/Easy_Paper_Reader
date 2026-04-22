const BASE = '/api';

// ── Papers ────────────────────────────────────────────────────────────────

export async function uploadPaper(file, parseMode = 'pymupdf') {
  const form = new FormData();
  form.append('pdf_file', file);
  form.append('parse_mode', parseMode);
  const res = await fetch(`${BASE}/papers/upload`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

export async function listPapers() {
  const res = await fetch(`${BASE}/papers/list`);
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

export function getPaperFileUrl(paperUuid) {
  return `${BASE}/papers/${paperUuid}/file`;
}

// ── Tasks ─────────────────────────────────────────────────────────────────

export async function getTask(taskId) {
  const res = await fetch(`${BASE}/tasks/${taskId}`);
  if (!res.ok) throw new Error(`Get task failed: ${res.status}`);
  return res.json();
}

export async function confirmTask(token) {
  const res = await fetch(`${BASE}/tasks/confirm/${token}`, { method: 'POST' });
  if (!res.ok) throw new Error(`Confirm task failed: ${res.status}`);
  return res.json();
}

export async function rejectTask(token) {
  const res = await fetch(`${BASE}/tasks/confirm/${token}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Reject task failed: ${res.status}`);
  return res.json();
}

// ── Sessions ──────────────────────────────────────────────────────────────

export async function newSession(paperUuid = '') {
  const res = await fetch(`${BASE}/chat/session/new`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paper_uuid: paperUuid }),
  });
  if (!res.ok) throw new Error(`New session failed: ${res.status}`);
  return res.json();
}

export async function listSessions(paperUuid = '') {
  const params = paperUuid ? `?paper_uuid=${encodeURIComponent(paperUuid)}` : '';
  const res = await fetch(`${BASE}/chat/session/list${params}`);
  if (!res.ok) throw new Error(`List sessions failed: ${res.status}`);
  return res.json();
}

export async function getSessionMessages(sessionId, limit = 50) {
  const res = await fetch(`${BASE}/chat/session/${sessionId}?limit=${limit}`);
  if (!res.ok) throw new Error(`Get session failed: ${res.status}`);
  return res.json();
}

export async function deleteSession(sessionId) {
  const res = await fetch(`${BASE}/chat/session/${sessionId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Delete session failed: ${res.status}`);
  return res.json();
}

export async function renameSession(sessionId, title) {
  const res = await fetch(`${BASE}/chat/session/${sessionId}/title?title=${encodeURIComponent(title)}`, {
    method: 'PATCH',
  });
  if (!res.ok) throw new Error(`Rename session failed: ${res.status}`);
  return res.json();
}

// ── Chat SSE ──────────────────────────────────────────────────────────────

export function chatSend({ sessionId, message, paperUuids = [], onEvent, onDone, onError }) {
  const body = JSON.stringify({
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
        buf = lines.pop();
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

// ── Translate ─────────────────────────────────────────────────────────────

export async function translateText(text, targetLang = 'auto') {
  const res = await fetch(`${BASE}/translate/text`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, target_lang: targetLang }),
  });
  if (!res.ok) throw new Error(`Translate failed: ${res.status}`);
  const data = await res.json();
  return data.result || '';
}

// ── Citation Graph ─────────────────────────────────────────────────────────

const CATEGORY_COLORS = [
  '#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272',
  '#fc8452', '#9a60b4', '#ea7ccc',
];

export async function getCitationGraph() {
  const res = await fetch(`${BASE}/papers/graph`);
  if (!res.ok) throw new Error(`Get graph failed: ${res.status}`);
  const data = await res.json();

  // 后端返回的节点无分类，这里按字母顺序简单分组（0 类）
  // 真实分类需要后端提供
  const categories = [{ name: '已解析论文', itemStyle: { color: CATEGORY_COLORS[0] } }];

  const papers = (data.nodes || []).map((n) => ({
    id: n.id,
    name: n.name,
    authors: n.authors || '',
    value: n.value || 50,
    category: 0,
  }));

  return {
    papers,
    categories,
    links: data.links || [],
  };
}
