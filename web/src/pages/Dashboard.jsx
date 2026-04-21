import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  UploadCloud, Search, FileText, Sparkles,
  Trash2, RefreshCw, BookOpen, Zap, Globe, Clock,
} from 'lucide-react';
import { uploadPaper, listPapers, deletePaper, getTask } from '../api';
import { useToast } from '../components/Toast';

// ── Status badge ──────────────────────────────────────────────────────────
const STATUS_MAP = {
  ready:      { label: '已就绪',  dot: 'bg-emerald-400', text: 'text-emerald-600' },
  processing: { label: '解析中',  dot: 'bg-amber-400 animate-pulse', text: 'text-amber-600' },
  failed:     { label: '失败',    dot: 'bg-red-400',     text: 'text-red-500' },
  pending:    { label: '等待中',  dot: 'bg-slate-300',   text: 'text-slate-400' },
};

// ── Feature Card ──────────────────────────────────────────────────────────
function FeatureCard({ icon: Icon, title, desc, color }) {
  const colors = {
    blue:   'bg-blue-500   text-blue-50   ring-blue-100',
    violet: 'bg-violet-500 text-violet-50 ring-violet-100',
    teal:   'bg-teal-500   text-teal-50   ring-teal-100',
  };
  const ring = {
    blue: 'hover:ring-blue-100', violet: 'hover:ring-violet-100', teal: 'hover:ring-teal-100',
  };
  return (
    <div className={`bg-white rounded-2xl p-5 border border-slate-100 hover:shadow-md hover:ring-2 ${ring[color]} transition-all duration-200 cursor-default`}>
      <div className={`w-9 h-9 rounded-xl flex items-center justify-center mb-3.5 ${colors[color].split(' ').slice(0,2).join(' ')}`}>
        <Icon size={16} />
      </div>
      <h3 className="text-sm font-semibold text-slate-800 mb-1">{title}</h3>
      <p className="text-xs text-slate-400 leading-relaxed">{desc}</p>
    </div>
  );
}

// ── Paper Card ────────────────────────────────────────────────────────────
function PaperCard({ paper, onDelete, onClick }) {
  const s = STATUS_MAP[paper.status] || STATUS_MAP.pending;
  const date = paper.created_at
    ? new Date(paper.created_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
    : '';
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={e => e.key === 'Enter' && onClick()}
      className="flex items-center gap-4 px-4 py-3.5 bg-white rounded-xl border border-slate-100 hover:border-blue-200 hover:shadow-sm transition-all cursor-pointer group"
    >
      {/* PDF icon */}
      <div className="w-9 h-12 rounded-md bg-red-50 border border-red-100 flex flex-col items-center justify-center flex-shrink-0 gap-0.5">
        <FileText size={14} className="text-red-400" />
        <span className="text-[8px] font-bold text-red-300 tracking-widest">PDF</span>
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-800 truncate group-hover:text-blue-600 transition-colors">
          {paper.title || paper.filename || paper.paper_uuid}
        </p>
        <div className="flex items-center gap-3 mt-1.5">
          <span className={`flex items-center gap-1 text-[11px] font-medium ${s.text}`}>
            <span className={`w-1.5 h-1.5 rounded-full inline-block ${s.dot}`} />
            {s.label}
          </span>
          {paper.tags?.map(t => (
            <span key={t} className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-400 rounded-md">{t}</span>
          ))}
        </div>
      </div>

      {/* Date + delete */}
      <div className="flex items-center gap-3 flex-shrink-0">
        {date && (
          <span className="text-[11px] text-slate-300 flex items-center gap-1">
            <Clock size={10} /> {date}
          </span>
        )}
        <button
          type="button"
          aria-label={`删除论文 ${paper.title || paper.paper_uuid}`}
          onClick={e => { e.stopPropagation(); onDelete(paper.paper_uuid); }}
          className="opacity-0 group-hover:opacity-100 p-1.5 text-slate-300 hover:text-red-400 hover:bg-red-50 rounded-lg transition-all"
        >
          <Trash2 size={13} />
        </button>
      </div>
    </div>
  );
}

// ── Upload Zone ────────────────────────────────────────────────────────────
function UploadZone({ onUploadDone }) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState('');
  const inputRef = useRef();
  const pollerRef = useRef();
  const toast = useToast();

  const handleFile = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      toast({ type: 'error', message: '请上传 PDF 格式的文件' });
      return;
    }
    setUploading(true);
    setProgress('上传中...');
    try {
      const { task_id } = await uploadPaper(file);
      setProgress('后台解析中...');
      pollerRef.current = setInterval(async () => {
        try {
          const task = await getTask(task_id);
          if (task.status === 'done' || task.status === 'success') {
            clearInterval(pollerRef.current);
            setUploading(false);
            setProgress('');
            toast({ type: 'success', message: `《${file.name}》解析完成！` });
            onUploadDone();
          } else if (task.status === 'failed') {
            clearInterval(pollerRef.current);
            setUploading(false);
            setProgress('');
            toast({ type: 'error', message: '解析失败：' + (task.error || '未知错误'), duration: 5000 });
          } else {
            setProgress(`解析中 (${task.current_step || task.status})...`);
          }
        } catch { /* ignore poll errors */ }
      }, 2000);
    } catch (err) {
      setUploading(false);
      setProgress('');
      toast({ type: 'error', message: '上传失败：' + err.message });
    }
  };

  return (
    <div
      role="region"
      aria-label="PDF 上传区域"
      aria-dropeffect="copy"
      className={`relative border-2 border-dashed rounded-2xl p-10 text-center transition-all duration-200 select-none
        ${isDragging ? 'border-blue-400 bg-blue-50/70 scale-[1.005]' : 'border-slate-200 bg-white hover:border-blue-200 hover:bg-slate-50/50'}
        ${uploading ? 'pointer-events-none' : 'cursor-pointer'}
      `}
      onClick={() => !uploading && inputRef.current?.click()}
      onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={e => { e.preventDefault(); setIsDragging(false); handleFile(e.dataTransfer.files[0]); }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf"
        className="hidden"
        aria-hidden="true"
        onChange={e => handleFile(e.target.files[0])}
      />

      <div className={`w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-4 transition-all
        ${uploading ? 'bg-blue-100' : isDragging ? 'bg-blue-100' : 'bg-slate-100'}`}>
        {uploading
          ? <RefreshCw size={20} className="text-blue-500 animate-spin" />
          : <UploadCloud size={20} className={isDragging ? 'text-blue-500' : 'text-slate-400'} />
        }
      </div>

      {uploading ? (
        <>
          <p className="text-sm font-medium text-slate-700 mb-1">{progress}</p>
          <p className="text-xs text-slate-400">请勿关闭页面</p>
        </>
      ) : (
        <>
          <p className="text-sm font-medium text-slate-700 mb-1">
            {isDragging ? '松开即可上传' : '拖拽 PDF 到这里，或点击选择'}
          </p>
          <p className="text-xs text-slate-400 mb-5">上传后自动解析文本、构建向量索引</p>
          <button
            type="button"
            className="px-5 py-2 bg-slate-900 text-white text-sm rounded-xl hover:bg-slate-700 transition-colors font-medium shadow-sm"
          >
            选择文件
          </button>
        </>
      )}
    </div>
  );
}

// ── Dashboard ─────────────────────────────────────────────────────────────
export default function Dashboard() {
  const navigate = useNavigate();
  const toast = useToast();
  const [papers, setPapers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const data = await listPapers();
      setPapers(data.papers || []);
    } catch {
      setPapers([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleDelete = async (uuid) => {
    const paper = papers.find(p => p.paper_uuid === uuid);
    const name = paper?.title || paper?.filename || uuid.slice(0, 8);
    if (!confirm(`确认删除《${name}》？此操作不可撤销。`)) return;
    try {
      await deletePaper(uuid);
      toast({ type: 'success', message: `已删除《${name}》` });
      load();
    } catch (err) {
      toast({ type: 'error', message: '删除失败：' + err.message });
    }
  };

  const filtered = papers.filter(p =>
    !search || (p.title || p.filename || '').toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-[#f6f7fb] font-sans text-slate-900">
      {/* Nav */}
      <nav className="bg-white/80 backdrop-blur border-b border-slate-100 px-8 py-3.5 sticky top-0 z-50 flex justify-between items-center">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg flex items-center justify-center shadow-sm shadow-blue-500/30">
            <BookOpen size={13} className="text-white" />
          </div>
          <span className="text-sm font-bold text-slate-800 tracking-tight">Easy Paper Reader</span>
        </div>

        <div className="relative">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          <input
            type="search"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="搜索论文..."
            aria-label="搜索论文"
            className="pl-8 pr-4 py-2 bg-slate-100 rounded-xl text-xs w-52 focus:outline-none focus:ring-2 focus:ring-blue-200 focus:bg-white transition-all"
          />
        </div>
      </nav>

      <main className="max-w-3xl mx-auto px-6 py-10">
        {/* Hero */}
        <div className="mb-7">
          <h1 className="text-xl font-bold text-slate-900 mb-0.5">论文工作台</h1>
          <p className="text-xs text-slate-400">上传 PDF，AI 自动解析 · 翻译 · 对话，加速研究洞察</p>
        </div>

        {/* Feature Cards */}
        <div className="grid grid-cols-3 gap-3 mb-7">
          <FeatureCard icon={Zap}      title="智能问答" desc="基于论文内容多轮对话与深度分析" color="blue" />
          <FeatureCard icon={Globe}    title="同步翻译" desc="句级对齐中英双语，悬停即查译文" color="violet" />
          <FeatureCard icon={Sparkles} title="创新挖掘" desc="知识图谱构建，精准定位创新点"   color="teal" />
        </div>

        {/* Upload */}
        <div className="mb-7">
          <UploadZone onUploadDone={load} />
        </div>

        {/* Paper list */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-semibold text-slate-600 uppercase tracking-wider">
              我的论文库
              {!loading && papers.length > 0 && (
                <span className="ml-2 font-normal text-slate-400 normal-case tracking-normal">({papers.length})</span>
              )}
            </h2>
            <button
              type="button"
              onClick={load}
              aria-label="刷新论文列表"
              className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-blue-500 transition-colors"
            >
              <RefreshCw size={11} /> 刷新
            </button>
          </div>

          {loading ? (
            <div className="space-y-2.5">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-[62px] rounded-xl bg-slate-200/70 animate-pulse" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-slate-300">
              <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
                <FileText size={24} className="text-slate-300" />
              </div>
              <p className="text-sm text-slate-400 font-medium">
                {search ? `未找到包含"${search}"的论文` : '还没有上传任何论文'}
              </p>
              {!search && (
                <p className="text-xs text-slate-300 mt-1">上传 PDF 后它会出现在这里</p>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              {filtered.map(p => (
                <PaperCard
                  key={p.paper_uuid}
                  paper={p}
                  onDelete={handleDelete}
                  onClick={() => navigate(`/read/${p.paper_uuid}`)}
                />
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
