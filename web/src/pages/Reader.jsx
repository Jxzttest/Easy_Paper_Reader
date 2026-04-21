import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, MessageSquare, Send, Loader2,
  AlertCircle, CheckCircle2, BookOpen, Cpu, FileSearch, Info,
} from 'lucide-react';
import { getPaper, newSession, getSessionMessages, chatSend, listSessions } from '../api';
import { useToast } from '../components/Toast';

// ── Agent 执行过程 ────────────────────────────────────────────────────────
function AgentTrace({ events }) {
  if (!events?.length) return null;
  return (
    <div className="mb-2 px-3 py-2 bg-slate-50 rounded-xl border border-slate-100 space-y-1">
      {events.map((ev, i) => {
        if (ev.event === 'plan') return (
          <div key={i} className="flex items-start gap-1.5 text-[11px] text-slate-500">
            <Cpu size={10} className="mt-0.5 text-blue-400 flex-shrink-0" />
            <span>规划: {ev.data?.intent}</span>
          </div>
        );
        if (ev.event === 'agent') return (
          <div key={i} className="flex items-center gap-1.5 text-[11px] text-slate-500">
            <Loader2 size={10} className="text-amber-400 animate-spin flex-shrink-0" />
            <span>{ev.data?.name} 执行中...</span>
          </div>
        );
        if (ev.event === 'result') return (
          <div key={i} className="flex items-start gap-1.5 text-[11px] text-slate-500">
            <CheckCircle2 size={10} className="mt-0.5 text-emerald-400 flex-shrink-0" />
            <span>{ev.data?.name}: {ev.data?.summary}</span>
          </div>
        );
        if (ev.event === 'error') return (
          <div key={i} className="flex items-center gap-1.5 text-[11px] text-red-400">
            <AlertCircle size={10} className="flex-shrink-0" />
            <span>{ev.data?.message}</span>
          </div>
        );
        return null;
      })}
    </div>
  );
}

// ── Chat Message ──────────────────────────────────────────────────────────
function ChatMessage({ msg }) {
  if (msg.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[82%] bg-slate-900 text-white text-sm px-4 py-2.5 rounded-2xl rounded-tr-md leading-relaxed">
          {msg.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-2.5">
      <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex-shrink-0 flex items-center justify-center text-white text-[9px] font-bold mt-0.5">
        AI
      </div>
      <div className="flex-1 min-w-0">
        <AgentTrace events={msg.events} />
        {msg.content ? (
          <div className="bg-white border border-slate-200 text-sm px-4 py-3 rounded-2xl rounded-tl-md leading-relaxed text-slate-800 whitespace-pre-wrap shadow-sm">
            {msg.content}
          </div>
        ) : msg.loading ? (
          <div className="flex items-center gap-2 text-xs text-slate-400 py-2">
            <Loader2 size={11} className="animate-spin" />
            <span>思考中...</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ── Quick questions ───────────────────────────────────────────────────────
const QUICK_QUESTIONS = ['总结这篇论文', '核心创新点是什么', '解释实验方法', '有哪些局限性'];

// ── Reader Page ───────────────────────────────────────────────────────────
export default function Reader() {
  const navigate = useNavigate();
  const { id: paperUuid } = useParams();
  const toast = useToast();

  const [activeTab, setActiveTab] = useState('chat');
  const [paper, setPaper] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);

  const chatEndRef = useRef(null);
  const inputRef = useRef(null);

  // Load paper
  useEffect(() => {
    getPaper(paperUuid).then(setPaper).catch(() => {
      toast({ type: 'warning', message: '论文元数据加载失败' });
    });
  }, [paperUuid]);

  // Load / create session
  useEffect(() => {
    (async () => {
      try {
        const { sessions } = await listSessions();
        const existing = sessions?.find(s => s.paper_uuid === paperUuid);
        if (existing) {
          setSessionId(existing.session_id);
          const { messages: hist } = await getSessionMessages(existing.session_id);
          setMessages((hist || []).map(m => ({ role: m.role, content: m.content })));
        } else {
          const { session_id } = await newSession(paperUuid);
          setSessionId(session_id);
        }
      } catch { /* ignore */ }
    })();
  }, [paperUuid]);

  // Auto scroll
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || sending || !sessionId) return;
    setSending(true);
    setInput('');

    setMessages(prev => [
      ...prev,
      { role: 'user', content: text },
      { role: 'assistant', content: '', events: [], loading: true },
    ]);

    chatSend({
      sessionId,
      message: text,
      paperUuids: [paperUuid],
      onEvent: (ev) => {
        setMessages(prev => {
          const msgs = [...prev];
          const last = { ...msgs[msgs.length - 1] };
          if (ev.event === 'answer') {
            last.content = ev.data?.content || '';
          } else {
            last.events = [...(last.events || []), ev];
          }
          msgs[msgs.length - 1] = last;
          return msgs;
        });
      },
      onDone: () => {
        setMessages(prev => {
          const msgs = [...prev];
          msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], loading: false };
          return msgs;
        });
        setSending(false);
        inputRef.current?.focus();
      },
      onError: (err) => {
        setMessages(prev => {
          const msgs = [...prev];
          msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: '请求失败：' + err.message, loading: false };
          return msgs;
        });
        setSending(false);
        toast({ type: 'error', message: '请求失败：' + err.message });
      },
    });
  }, [sessionId, paperUuid, sending]);

  const paperTitle = paper?.title || paper?.filename || `论文 ${paperUuid?.slice(0, 8)}`;

  return (
    <div className="h-screen flex flex-col bg-slate-100 font-sans overflow-hidden">
      {/* Header */}
      <header className="bg-white border-b border-slate-100 flex items-center justify-between px-4 py-2.5 flex-shrink-0 z-20 shadow-sm">
        <div className="flex items-center gap-3 min-w-0">
          <button
            type="button"
            onClick={() => navigate('/dashboard')}
            aria-label="返回论文工作台"
            className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-700 transition-colors flex-shrink-0"
          >
            <ArrowLeft size={16} />
          </button>
          <div className="min-w-0">
            <h1 className="text-sm font-semibold text-slate-800 truncate max-w-xs leading-tight">
              {paperTitle}
            </h1>
            <p className="text-[10px] text-slate-400 flex items-center gap-1 mt-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
              已连接 · {sessionId ? '会话就绪' : '初始化中...'}
            </p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center bg-slate-100 p-1 rounded-xl gap-0.5 flex-shrink-0">
          {[
            { key: 'chat', icon: MessageSquare, label: '对话', active: 'text-blue-600' },
            { key: 'info', icon: Info,          label: '详情', active: 'text-slate-700' },
          ].map(({ key, icon: Icon, label, active }) => (
            <button
              key={key}
              type="button"
              onClick={() => setActiveTab(key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all
                ${activeTab === key ? `bg-white shadow-sm ${active}` : 'text-slate-400 hover:text-slate-600'}`}
            >
              <Icon size={12} /> {label}
            </button>
          ))}
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: paper content */}
        <div className="flex-1 overflow-hidden flex items-stretch">
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-2xl mx-auto py-10 px-8">
              {paper ? (
                <article>
                  <h2 className="text-xl font-bold text-slate-900 mb-2 leading-tight">
                    {paper.title || paper.filename}
                  </h2>
                  {paper.authors && (
                    <p className="text-sm text-slate-500 mb-6">{paper.authors}</p>
                  )}
                  {paper.abstract ? (
                    <>
                      <div className="flex items-center gap-2 mb-3">
                        <div className="flex-1 h-px bg-slate-200" />
                        <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Abstract</span>
                        <div className="flex-1 h-px bg-slate-200" />
                      </div>
                      <p className="text-sm text-slate-700 leading-relaxed text-justify">{paper.abstract}</p>
                    </>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-24 text-center">
                      <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
                        <BookOpen size={22} className="text-slate-300" />
                      </div>
                      <p className="text-sm text-slate-400 font-medium">PDF 内容预览即将上线</p>
                      <p className="text-xs text-slate-300 mt-1">请使用右侧面板与 AI 对话</p>
                    </div>
                  )}
                </article>
              ) : (
                <div className="flex justify-center py-20">
                  <Loader2 size={22} className="animate-spin text-slate-400" />
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right panel */}
        <div className="w-[380px] bg-white border-l border-slate-100 flex flex-col">
          {activeTab === 'chat' ? (
            <>
              {/* Messages area */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-14 text-center animate-fade-in">
                    <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center mb-3 shadow-sm shadow-blue-500/30">
                      <MessageSquare size={15} className="text-white" />
                    </div>
                    <p className="text-sm font-medium text-slate-600">开始与论文对话</p>
                    <p className="text-xs text-slate-400 mt-1 max-w-[180px] leading-relaxed">
                      AI 会基于论文内容回答您的问题
                    </p>
                  </div>
                )}
                {messages.map((msg, i) => <ChatMessage key={i} msg={msg} />)}
                <div ref={chatEndRef} />
              </div>

              {/* Quick questions */}
              <div className="px-4 pb-2 pt-1 flex gap-1.5 flex-wrap border-t border-slate-50">
                {QUICK_QUESTIONS.map(q => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => sendMessage(q)}
                    disabled={sending || !sessionId}
                    className="text-[10px] px-2.5 py-1 bg-slate-100 text-slate-500 rounded-full hover:bg-blue-50 hover:text-blue-600 disabled:opacity-40 transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>

              {/* Input */}
              <div className="p-3 border-t border-slate-100 bg-slate-50/50">
                <form onSubmit={e => { e.preventDefault(); sendMessage(input); }} className="flex gap-2">
                  <input
                    ref={inputRef}
                    type="text"
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    placeholder={!sessionId ? '初始化中...' : sending ? '等待回复...' : '向 AI 提问...'}
                    disabled={sending || !sessionId}
                    aria-label="聊天输入框"
                    className="flex-1 px-3 py-2.5 bg-white border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 focus:border-transparent disabled:opacity-50 transition-all placeholder:text-slate-300"
                  />
                  <button
                    type="submit"
                    aria-label="发送消息"
                    disabled={!input.trim() || sending || !sessionId}
                    className="w-9 h-9 bg-blue-600 text-white rounded-xl flex items-center justify-center hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex-shrink-0 shadow-sm shadow-blue-500/25"
                  >
                    {sending
                      ? <Loader2 size={13} className="animate-spin" />
                      : <Send size={13} />
                    }
                  </button>
                </form>
              </div>
            </>
          ) : (
            <div className="flex-1 overflow-y-auto p-5">
              <h3 className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-5">
                论文详情
              </h3>
              {paper ? (
                <div className="space-y-5">
                  {[
                    ['标题',    paper.title],
                    ['文件名',  paper.filename],
                    ['论文 ID', paper.paper_uuid],
                    ['上传时间', paper.created_at ? new Date(paper.created_at).toLocaleString('zh-CN') : null],
                    ['解析状态', paper.status],
                    ['作者',    paper.authors],
                  ].filter(([, v]) => v).map(([k, v]) => (
                    <div key={k}>
                      <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">{k}</p>
                      <p className="text-xs text-slate-700 break-all leading-relaxed">{v}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex justify-center py-10">
                  <Loader2 size={16} className="animate-spin text-slate-400" />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
