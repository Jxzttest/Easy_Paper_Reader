import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, MessageSquare, Send, Loader2,
  AlertCircle, CheckCircle2, BookOpen, Cpu, Info,
  Zap, RotateCcw, ChevronDown, ChevronUp, User, Bot,
  Sparkles, FileSearch, Copy, Check,
} from 'lucide-react';
import { getPaper, newSession, getSessionMessages, chatSend, listSessions } from '../api';
import { useToast } from '../components/Toast';

// ── Agent event icons ─────────────────────────────────────────────────────
const AGENT_ICONS = {
  rag_agent:         { icon: FileSearch, label: 'RAG 检索',  color: 'text-blue-500',   bg: 'bg-blue-50' },
  writing_agent:     { icon: Sparkles,   label: '写作助手',  color: 'text-violet-500', bg: 'bg-violet-50' },
  translation_agent: { icon: Zap,        label: '翻译',      color: 'text-teal-500',   bg: 'bg-teal-50' },
  check_agent:       { icon: CheckCircle2, label: '质量检查', color: 'text-emerald-500', bg: 'bg-emerald-50' },
};

// ── Agent Trace ───────────────────────────────────────────────────────────
function AgentTrace({ events }) {
  const [expanded, setExpanded] = useState(false);
  if (!events?.length) return null;

  const planEvent = events.find(e => e.event === 'plan');
  const hasError = events.some(e => e.event === 'error');
  const agentEvents = events.filter(e => ['agent', 'result'].includes(e.event));

  return (
    <div className="mb-3 rounded-xl border border-slate-100 bg-slate-50 overflow-hidden text-[11px]">
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between px-3.5 py-2.5 hover:bg-slate-100 transition-colors text-left"
      >
        <div className="flex items-center gap-2 text-slate-500">
          <Cpu size={11} className="text-blue-400" />
          <span className="font-medium">
            {planEvent ? `意图：${planEvent.data?.intent}` : 'Agent 执行过程'}
          </span>
          {hasError && <AlertCircle size={10} className="text-red-400" />}
        </div>
        {expanded
          ? <ChevronUp size={11} className="text-slate-400" />
          : <ChevronDown size={11} className="text-slate-400" />
        }
      </button>

      {expanded && (
        <div className="px-3.5 pb-3 space-y-1.5 border-t border-slate-100 pt-2.5">
          {events.map((ev, i) => {
            if (ev.event === 'plan') return (
              <div key={i} className="flex items-start gap-2 text-slate-500">
                <Cpu size={10} className="mt-0.5 text-blue-400 flex-shrink-0" />
                <span>规划：{ev.data?.plan?.join(' → ')}</span>
              </div>
            );
            if (ev.event === 'agent') {
              const info = AGENT_ICONS[ev.data?.name] || { icon: Bot, label: ev.data?.name, color: 'text-slate-400', bg: 'bg-slate-100' };
              const Icon = info.icon;
              return (
                <div key={i} className={`flex items-center gap-2 px-2 py-1 rounded-lg ${info.bg}`}>
                  <Loader2 size={10} className={`${info.color} animate-spin flex-shrink-0`} />
                  <span className={`${info.color} font-medium`}>{info.label} 执行中...</span>
                </div>
              );
            }
            if (ev.event === 'result') {
              const info = AGENT_ICONS[ev.data?.name] || { icon: CheckCircle2, label: ev.data?.name, color: 'text-emerald-500', bg: 'bg-emerald-50' };
              return (
                <div key={i} className="flex items-start gap-2 text-slate-500">
                  <CheckCircle2 size={10} className="mt-0.5 text-emerald-400 flex-shrink-0" />
                  <span className="text-slate-500 line-clamp-2">{ev.data?.summary}</span>
                </div>
              );
            }
            if (ev.event === 'check') return (
              <div key={i} className={`flex items-center gap-2 text-[10px] px-2 py-1 rounded-lg ${ev.data?.passed ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}>
                <CheckCircle2 size={10} />
                <span>质量评分 {(ev.data?.score * 100).toFixed(0)}% — {ev.data?.passed ? '通过' : '重新规划'}</span>
              </div>
            );
            if (ev.event === 'error') return (
              <div key={i} className="flex items-center gap-2 text-red-400 bg-red-50 px-2 py-1 rounded-lg">
                <AlertCircle size={10} className="flex-shrink-0" />
                <span>{ev.data?.message}</span>
              </div>
            );
            return null;
          })}
        </div>
      )}
    </div>
  );
}

// ── Source citations ──────────────────────────────────────────────────────
function Sources({ sources }) {
  if (!sources?.length) return null;
  return (
    <div className="mt-3 pt-3 border-t border-slate-100">
      <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">参考来源</p>
      <div className="space-y-1.5">
        {sources.slice(0, 3).map((s, i) => (
          <div key={i} className="flex items-start gap-2 text-[11px] text-slate-500 bg-slate-50 rounded-lg px-2.5 py-1.5">
            <span className="font-semibold text-blue-500 flex-shrink-0">[{i + 1}]</span>
            <span className="line-clamp-2 leading-relaxed">{typeof s === 'string' ? s : s.content || s.text || JSON.stringify(s)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Copy button ───────────────────────────────────────────────────────────
function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async (e) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(text).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      type="button"
      onClick={handleCopy}
      className="p-1 rounded text-slate-300 hover:text-slate-500 transition-colors"
      aria-label="复制内容"
    >
      {copied ? <Check size={11} className="text-emerald-500" /> : <Copy size={11} />}
    </button>
  );
}

// ── Chat Message ──────────────────────────────────────────────────────────
function ChatMessage({ msg }) {
  const lastAnswerEvent = msg.events?.findLast?.(e => e.event === 'answer');
  const sources = lastAnswerEvent?.data?.sources || msg.sources || [];

  if (msg.role === 'user') {
    return (
      <div className="flex justify-end gap-2.5 animate-fade-in">
        <div className="max-w-[80%] bg-slate-900 text-white text-sm px-4 py-3 rounded-2xl rounded-tr-sm leading-relaxed shadow-sm">
          {msg.content}
        </div>
        <div className="w-7 h-7 rounded-xl bg-slate-200 flex-shrink-0 flex items-center justify-center mt-auto">
          <User size={13} className="text-slate-500" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-2.5 animate-fade-in">
      <div className="w-7 h-7 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex-shrink-0 flex items-center justify-center shadow-sm shadow-blue-500/30 mt-0.5">
        <Bot size={13} className="text-white" />
      </div>
      <div className="flex-1 min-w-0">
        <AgentTrace events={msg.events} />
        {msg.content ? (
          <div className="bg-white border border-slate-200 text-sm px-4 py-3.5 rounded-2xl rounded-tl-sm leading-relaxed text-slate-700 whitespace-pre-wrap shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <span className="flex-1">{msg.content}</span>
              <CopyButton text={msg.content} />
            </div>
            <Sources sources={sources} />
          </div>
        ) : msg.loading ? (
          <div className="bg-white border border-slate-200 px-4 py-3.5 rounded-2xl rounded-tl-sm shadow-sm">
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span>思考中...</span>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ── Quick questions ───────────────────────────────────────────────────────
const QUICK_QUESTIONS = [
  { label: '总结这篇论文', icon: '📝' },
  { label: '核心创新点是什么', icon: '💡' },
  { label: '解释实验方法', icon: '🔬' },
  { label: '有哪些局限性', icon: '⚠️' },
];

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

  useEffect(() => {
    getPaper(paperUuid).then(setPaper).catch(() => {
      toast({ type: 'warning', message: '论文元数据加载失败' });
    });
  }, [paperUuid]);

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
            last.sources = ev.data?.sources || [];
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
    <div className="h-screen flex flex-col bg-[#f6f7fb] font-sans overflow-hidden">
      {/* Header */}
      <header className="bg-white border-b border-slate-100 flex items-center justify-between px-5 py-3 flex-shrink-0 z-20 shadow-sm">
        <div className="flex items-center gap-3 min-w-0">
          <button
            type="button"
            onClick={() => navigate('/dashboard')}
            aria-label="返回论文工作台"
            className="p-2 hover:bg-slate-100 rounded-xl text-slate-500 hover:text-slate-700 transition-colors flex-shrink-0"
          >
            <ArrowLeft size={15} />
          </button>
          <div className="w-px h-4 bg-slate-200 flex-shrink-0" />
          <div className="w-7 h-7 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg flex items-center justify-center flex-shrink-0 shadow-sm shadow-blue-500/30">
            <BookOpen size={13} className="text-white" />
          </div>
          <div className="min-w-0">
            <h1 className="text-sm font-semibold text-slate-800 truncate max-w-xs leading-tight">
              {paperTitle}
            </h1>
            <p className="text-[10px] text-slate-400 flex items-center gap-1 mt-0.5">
              <span className={`w-1.5 h-1.5 rounded-full inline-block ${sessionId ? 'bg-emerald-400' : 'bg-amber-400 animate-pulse'}`} />
              {sessionId ? '会话就绪' : '初始化中...'}
            </p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center bg-slate-100 p-1 rounded-xl gap-0.5 flex-shrink-0">
          {[
            { key: 'chat', icon: MessageSquare, label: '对话' },
            { key: 'info', icon: Info,          label: '详情' },
          ].map(({ key, icon: Icon, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => setActiveTab(key)}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all
                ${activeTab === key ? 'bg-white shadow-sm text-slate-700' : 'text-slate-400 hover:text-slate-600'}`}
            >
              <Icon size={12} /> {label}
            </button>
          ))}
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: paper content */}
        <div className="flex-1 overflow-hidden flex items-stretch bg-white border-r border-slate-100">
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-2xl mx-auto py-10 px-10">
              {paper ? (
                <article>
                  <div className="mb-6">
                    <div className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-blue-600 bg-blue-50 px-2.5 py-1 rounded-full border border-blue-100 mb-4">
                      <FileSearch size={10} /> 论文内容
                    </div>
                    <h2 className="text-2xl font-bold text-slate-900 mb-3 leading-tight">
                      {paper.title || paper.filename}
                    </h2>
                    {paper.authors && (
                      <p className="text-sm text-slate-500 flex items-center gap-1.5">
                        <User size={12} className="text-slate-400" />
                        {paper.authors}
                      </p>
                    )}
                  </div>

                  {paper.abstract ? (
                    <>
                      <div className="flex items-center gap-3 mb-4">
                        <div className="flex-1 h-px bg-gradient-to-r from-slate-200 to-transparent" />
                        <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Abstract</span>
                        <div className="flex-1 h-px bg-gradient-to-l from-slate-200 to-transparent" />
                      </div>
                      <p className="text-sm text-slate-700 leading-[1.9] text-justify">
                        {paper.abstract}
                      </p>
                    </>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-28 text-center">
                      <div className="w-16 h-16 rounded-3xl bg-gradient-to-br from-slate-100 to-slate-50 flex items-center justify-center mb-5 border border-slate-200">
                        <BookOpen size={24} className="text-slate-300" />
                      </div>
                      <p className="text-sm text-slate-400 font-semibold mb-2">论文内容预览</p>
                      <p className="text-xs text-slate-300 max-w-[200px] leading-relaxed">
                        PDF 全文渲染即将上线，请使用右侧面板与 AI 对话分析论文
                      </p>
                    </div>
                  )}
                </article>
              ) : (
                <div className="flex justify-center py-24">
                  <Loader2 size={24} className="animate-spin text-slate-300" />
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right panel: chat / info */}
        <div className="w-[400px] flex-shrink-0 bg-[#f6f7fb] flex flex-col">
          {activeTab === 'chat' ? (
            <>
              {/* Messages area */}
              <div className="flex-1 overflow-y-auto px-4 py-5 space-y-5">
                {messages.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-14 text-center animate-fade-in">
                    <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center mb-4 shadow-md shadow-blue-500/25">
                      <MessageSquare size={16} className="text-white" />
                    </div>
                    <p className="text-sm font-semibold text-slate-600 mb-1">开始与论文对话</p>
                    <p className="text-xs text-slate-400 max-w-[180px] leading-relaxed">
                      AI 基于论文内容智能回答，支持深度检索与多轮对话
                    </p>
                  </div>
                )}
                {messages.map((msg, i) => <ChatMessage key={i} msg={msg} />)}
                <div ref={chatEndRef} />
              </div>

              {/* Quick questions */}
              <div className="px-4 pb-3 pt-2 border-t border-slate-200/60">
                <p className="text-[10px] text-slate-400 mb-2 font-medium">快捷提问</p>
                <div className="flex gap-1.5 flex-wrap">
                  {QUICK_QUESTIONS.map(q => (
                    <button
                      key={q.label}
                      type="button"
                      onClick={() => sendMessage(q.label)}
                      disabled={sending || !sessionId}
                      className="text-[11px] px-2.5 py-1.5 bg-white text-slate-600 rounded-lg border border-slate-200 hover:border-blue-300 hover:text-blue-600 hover:bg-blue-50 disabled:opacity-40 transition-all shadow-sm"
                    >
                      {q.icon} {q.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Input */}
              <div className="p-4 border-t border-slate-200/60 bg-white">
                <form onSubmit={e => { e.preventDefault(); sendMessage(input); }} className="flex gap-2 items-end">
                  <textarea
                    ref={inputRef}
                    value={input}
                    onChange={e => {
                      setInput(e.target.value);
                      e.target.style.height = 'auto';
                      e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
                    }}
                    onKeyDown={e => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        sendMessage(input);
                      }
                    }}
                    placeholder={!sessionId ? '初始化中...' : sending ? '等待回复...' : '向 AI 提问... (Enter 发送，Shift+Enter 换行)'}
                    disabled={sending || !sessionId}
                    aria-label="聊天输入框"
                    rows={1}
                    className="flex-1 px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 focus:border-transparent focus:bg-white disabled:opacity-50 transition-all placeholder:text-slate-300 resize-none overflow-hidden leading-relaxed"
                    style={{ minHeight: '42px' }}
                  />
                  <button
                    type="submit"
                    aria-label="发送消息"
                    disabled={!input.trim() || sending || !sessionId}
                    className="w-10 h-10 bg-gradient-to-br from-blue-500 to-indigo-600 text-white rounded-xl flex items-center justify-center hover:from-blue-600 hover:to-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed active:scale-95 transition-all flex-shrink-0 shadow-sm shadow-blue-500/30"
                  >
                    {sending
                      ? <Loader2 size={14} className="animate-spin" />
                      : <Send size={14} />
                    }
                  </button>
                </form>
                <p className="text-[10px] text-slate-300 mt-1.5 text-center">
                  AI 回答基于论文内容生成，请注意核实
                </p>
              </div>
            </>
          ) : (
            <div className="flex-1 overflow-y-auto p-5">
              <h3 className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-5">
                论文详情
              </h3>
              {paper ? (
                <div className="space-y-4">
                  {[
                    ['标题',    paper.title],
                    ['文件名',  paper.filename],
                    ['作者',    paper.authors],
                    ['上传时间', paper.created_at ? new Date(paper.created_at).toLocaleString('zh-CN') : null],
                    ['解析状态', paper.status],
                    ['论文 ID', paper.paper_uuid],
                  ].filter(([, v]) => v).map(([k, v]) => (
                    <div key={k} className="bg-white rounded-xl border border-slate-100 px-4 py-3">
                      <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">{k}</p>
                      <p className="text-xs text-slate-700 break-all leading-relaxed">{v}</p>
                    </div>
                  ))}

                  {/* Actions */}
                  <div className="pt-2">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-3">操作</p>
                    <button
                      type="button"
                      onClick={() => navigate('/dashboard')}
                      className="w-full flex items-center justify-center gap-2 py-2.5 text-xs font-medium text-slate-600 bg-white border border-slate-200 rounded-xl hover:border-blue-300 hover:text-blue-600 hover:bg-blue-50 transition-all"
                    >
                      <ArrowLeft size={12} />
                      返回论文库
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex justify-center py-12">
                  <Loader2 size={18} className="animate-spin text-slate-300" />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
