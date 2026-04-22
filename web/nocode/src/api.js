const BASE = '/api';

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

export async function listSessions(paperUuid = '') {
  const params = new URLSearchParams({ user_uuid: USER_UUID });
  if (paperUuid) params.append('paper_uuid', paperUuid);
  const res = await fetch(`${BASE}/chat/session/list?${params}`);
  if (!res.ok) throw new Error(`List sessions failed: ${res.status}`);
  return res.json();
}

export async function getSessionMessages(sessionId, limit = 50) {
  const res = await fetch(`${BASE}/chat/session/${sessionId}?limit=${limit}`);
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

export async function renameSession(sessionId, title) {
  const res = await fetch(`${BASE}/chat/session/${sessionId}/title?title=${encodeURIComponent(title)}`, {
    method: 'PATCH',
  });
  if (!res.ok) throw new Error(`Rename session failed: ${res.status}`);
  return res.json();
}

// ── Chat SSE ───────────────────���──────────────────────────────────────────

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

// ── Citation Graph (stub) ──────────────────────────────────────────────────
// 后端暂无该接口，返回模拟数据

export async function getCitationGraph() {
  return {
    papers: [
      { id: '1', name: 'Attention Is All You Need', category: 0, value: 150, authors: 'Vaswani et al.' },
      { id: '2', name: 'BERT: Pre-training', category: 1, value: 120, authors: 'Devlin et al.' },
      { id: '3', name: 'GPT-4 Technical Report', category: 2, value: 100, authors: 'OpenAI' },
      { id: '4', name: 'Deep Residual Learning', category: 3, value: 130, authors: 'He et al.' },
      { id: '5', name: 'ImageNet Classification', category: 3, value: 110, authors: 'Krizhevsky et al.' },
      { id: '6', name: 'Generative Adversarial Nets', category: 4, value: 90, authors: 'Goodfellow et al.' },
      { id: '7', name: 'Variational Autoencoder', category: 4, value: 85, authors: 'Kingma et al.' },
      { id: '8', name: 'Diffusion Models Beat GANs', category: 4, value: 70, authors: 'Dhariwal et al.' },
      { id: '9', name: 'CLIP', category: 5, value: 95, authors: 'Radford et al.' },
      { id: '10', name: 'MAE', category: 3, value: 80, authors: 'He et al.' },
      { id: '11', name: 'Transformer-XL', category: 0, value: 60, authors: 'Dai et al.' },
      { id: '12', name: 'RoBERTa', category: 1, value: 65, authors: 'Liu et al.' },
      { id: '13', name: 'GPT-3', category: 2, value: 105, authors: 'Brown et al.' },
      { id: '14', name: 'InstructGPT', category: 2, value: 75, authors: 'Ouyang et al.' },
      { id: '15', name: 'ResNeXt', category: 3, value: 55, authors: 'Xie et al.' },
    ],
    categories: [
      { name: 'Transformer', itemStyle: { color: '#5470c6' } },
      { name: 'BERT系列', itemStyle: { color: '#91cc75' } },
      { name: 'GPT系列', itemStyle: { color: '#fac858' } },
      { name: 'CNN架构', itemStyle: { color: '#ee6666' } },
      { name: '生成模型', itemStyle: { color: '#73c0de' } },
      { name: '多模态', itemStyle: { color: '#3ba272' } },
    ],
    links: [
      { source: '1', target: '2' }, { source: '1', target: '3' }, { source: '1', target: '11' },
      { source: '2', target: '12' }, { source: '3', target: '13' }, { source: '3', target: '14' },
      { source: '4', target: '5' }, { source: '4', target: '10' }, { source: '4', target: '15' },
      { source: '6', target: '7' }, { source: '6', target: '8' }, { source: '9', target: '2' },
      { source: '9', target: '3' }, { source: '13', target: '14' }, { source: '1', target: '9' },
      { source: '5', target: '4' }, { source: '7', target: '8' }, { source: '11', target: '2' },
      { source: '12', target: '2' },
    ],
  };
}
