import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  UploadCloud, Search, FileText, Sparkles,
  Trash2, RefreshCw, BookOpen, Zap, Globe, Clock,
  Brain, ChevronRight, ArrowUpRight, Library, Plus,
} from 'lucide-react';
import { uploadPaper, listPapers, deletePaper, getTask } from '../api';
import { useToast } from '../components/Toast';

const STATUS_MAP = {
  ready:      { label: '已就绪',  dot: 'bg-emerald-400', text: 'text-emerald-600', bg: 'bg-emerald-50 border-emerald-100' },
  processing: { label: '解析中',  dot: 'bg-amber-400 animate-pulse', text: 'text-amber-600', bg: 'bg-amber-50 border-amber-100' },
  failed:     { label: '失败',    dot: 'bg-red-400',     text: 'text-red-500', bg: 'bg-red-50 border-red-100' },
  pending:    { label: '等待中',  dot: 'bg-slate-300',   text: 'text-slate-400', bg: 'bg-slate-50 border-slate-100' },
};

function StatCard({ value, label, icon: Icon, gradient }) {
  return (
    <div className={`relative overflow-hidden rounded-2xl p-5 ${gradient} text-white`}>
      <div className="absolute -right-4 -top-4 w-24 h-24 rounded-full bg-white/10" />
      <div className="absolute -right-2 -bottom-6 w-20 h-20 rounded-full bg-white/10" />
      <div className="relative">
        <Icon size={18} className="mb-3 opacity-80" />
        <p className="text-3xl font-bold tracking-tight">{value}</p>
        <p className="text-sm mt-0.5 opacity-75">{label}</p>
      </div>
    </div>
  );
}

function FeatureCard({ icon: Icon, title, desc, accent }) {
  const accents = {
    blue:   { bg: 'bg-blue-500',   ring: 'group-hover:ring-blue-100',   text: 'text-blue-600', light: 'bg-blue-50' },
    violet: { bg: 'bg-violet-500', ring: 'group-hover:ring-violet-100', text: 'text-violet-600', light: 'bg-violet-50' },
    teal:   { bg: 'bg-teal-500',   ring: 'group-hover:ring-teal-100',   text: 'text-teal-600', light: 'bg-teal-50' },
    rose:   { bg: 'bg-rose-500',   ring: 'group-hover:ring-rose-100',   text: 'text-rose-600', light: 'bg-rose-50' },
  };
  const a = accents[accent];
  return (
    <div className={`group bg-white rounded-2xl p-5 border border-slate-100 hover:shadow-lg hover:ring-2 ${a.ring} hover:-translate-y-0.5 transition-all duration-200 cursor-default`}>
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center mb-4 ${a.light}`}>
        <Icon size={18} className={a.text} />
      </div>
      <h3 className="text-sm font-semibold text-slate-800 mb-1.5">{title}</h3>
      <p className="text-xs text-slate-400 leading-relaxed">{desc}</p>
    </div>
  );
}

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
      className="group flex items-center gap-4 px-5 py-4 bg-white rounded-2xl border border-slate-100 hover:border-blue-200 hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 cursor-pointer"
    >
      {/* PDF icon */}
      <div className="w-10 h-13 rounded-xl bg-gradient-to-b from-red-50 to-red-100 border border-red-100 flex flex-col items-center justify-center flex-shrink-0 gap-0.5 shadow-sm">
        <FileText size={14} className="text-red-400" />
        <span className="text-[7px] font-bold text-red-300 tracking-widest mt-0.5">PDF</span>
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-slate-800 truncate group-hover:text-blue-600 transition-colors">
          {paper.title || paper.filename || paper.paper_uuid}
        </p>
        <div className="flex items-center gap-2 mt-2">
          <span className={`inline-flex items-center gap-1.5 text-[11px] font-medium px-2 py-0.5 rounded-full border ${s.bg} ${s.text}`}>
            <span className={`w-1.5 h-1.5 rounded-full inline-block ${s.dot}`} />
            {s.label}
          </span>
          {paper.tags?.map(t => (
            <span key={t} className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-400 rounded-full">{t}</span>
          ))}
        </div>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3 flex-shrink-0">
        {date && (
          <span className="text-[11px] text-slate-300 flex items-center gap-1">
            <Clock size={10} /> {date}
          </span>
        )}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            type="button"
            aria-label={`删除论文 ${paper.title || paper.paper_uuid}`}
            onClick={e => { e.stopPropagation(); onDelete(paper.paper_uuid); }}
            className="p-1.5 text-slate-300 hover:text-red-400 hover:bg-red-50 rounded-lg transition-all"
          >
            <Trash2 size={13} />
          </button>
          <div className="p-1.5 text-slate-300 group-hover:text-blue-400 rounded-lg">
            <ChevronRight size={13} />
          </div>
        </div>
      </div>
    </div>
  );
}

function UploadZone({ onUploadDone }) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState('');
  const [progressPct, setProgressPct] = useState(0);
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
    setProgressPct(20);
    try {
      const { task_id } = await uploadPaper(file);
      setProgress('后台解析中...');
      setProgressPct(50);
      pollerRef.current = setInterval(async () => {
        try {
          const task = await getTask(task_id);
          if (task.status === 'done' || task.status === 'success') {
            clearInterval(pollerRef.current);
            setProgressPct(100);
            setTimeout(() => {
              setUploading(false);
              setProgress('');
              setProgressPct(0);
            }, 600);
            toast({ type: 'success', message: `《${file.name}》解析完成！` });
            onUploadDone();
          } else if (task.status === 'failed') {
            clearInterval(pollerRef.current);
            setUploading(false);
            setProgress('');
            setProgressPct(0);
            toast({ type: 'error', message: '解析失败：' + (task.error || '未知错误'), duration: 5000 });
          } else {
            setProgress(`解析中 (${task.current_step || task.status})...`);
            setProgressPct(p => Math.min(p + 5, 90));
          }
        } catch { /* ignore poll errors */ }
      }, 2000);
    } catch (err) {
      setUploading(false);
      setProgress('');
      setProgressPct(0);
      toast({ type: 'error', message: '上传失败：' + err.message });
    }
  };

  return (
    <div
      role="region"
      aria-label="PDF 上传区域"
      aria-dropeffect="copy"
      className={`relative border-2 border-dashed rounded-2xl transition-all duration-300 select-none overflow-hidden
        ${isDragging ? 'border-blue-400 bg-blue-50/70 scale-[1.005]' : 'border-slate-200 bg-white hover:border-blue-300 hover:bg-slate-50/50'}
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

      {/* Progress bar */}
      {uploading && (
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-slate-100">
          <div
            className="h-full bg-blue-500 transition-all duration-500 ease-out"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      )}

      <div className="flex flex-col items-center justify-center py-10 px-6">
        <div className={`w-14 h-14 rounded-2xl flex items-center justify-center mb-5 transition-all shadow-sm
          ${uploading ? 'bg-blue-100 shadow-blue-200' : isDragging ? 'bg-blue-100 shadow-blue-200' : 'bg-slate-100'}`}>
          {uploading
            ? <RefreshCw size={22} className="text-blue-500 animate-spin" />
            : <UploadCloud size={22} className={isDragging ? 'text-blue-500' : 'text-slate-400'} />
          }
        </div>

        {uploading ? (
          <>
            <p className="text-sm font-semibold text-slate-700 mb-1">{progress}</p>
            <p className="text-xs text-slate-400">请勿关闭页面，正在后台处理</p>
          </>
        ) : (
          <>
            <p className="text-sm font-semibold text-slate-700 mb-1.5">
              {isDragging ? '松开以上传 PDF' : '拖拽 PDF 到此处，或点击选择'}
            </p>
            <p className="text-xs text-slate-400 mb-5 text-center leading-relaxed">
              上传后自动解析文本、构建向量索引，支持 PyMuPDF / PaddleOCR
            </p>
            <button
              type="button"
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-slate-900 text-white text-sm rounded-xl hover:bg-slate-700 active:scale-95 transition-all font-medium shadow-sm"
            >
              <Plus size={14} />
              选择文件
            </button>
          </>
        )}
      </div>
    </div>
  );
}

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

  const readyCount = papers.filter(p => p.status === 'ready').length;
  const processingCount = papers.filter(p => p.status === 'processing' || p.status === 'pending').length;

  return (
    <div className="min-h-screen bg-[#f6f7fb] font-sans text-slate-900">
      {/* Nav */}
      <nav className="bg-white/80 backdrop-blur-md border-b border-slate-100/80 px-8 py-3.5 sticky top-0 z-50">
        <div className="max-w-5xl mx-auto flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl flex items-center justify-center shadow-sm shadow-blue-500/30">
              <BookOpen size={14} className="text-white" />
            </div>
            <div>
              <span className="text-sm font-bold text-slate-800 tracking-tight">Easy Paper Reader</span>
              <span className="ml-2 text-[10px] text-slate-400 font-medium bg-slate-100 px-1.5 py-0.5 rounded-md">Beta</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="relative">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              <input
                type="search"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="搜索论文..."
                aria-label="搜索论文"
                className="pl-8 pr-4 py-2 bg-slate-100 rounded-xl text-xs w-56 focus:outline-none focus:ring-2 focus:ring-blue-200 focus:bg-white transition-all placeholder:text-slate-400"
              />
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-5xl mx-auto px-6 py-10">
        {/* Hero */}
        <div className="mb-10">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-semibold text-blue-600 bg-blue-50 px-2.5 py-1 rounded-full border border-blue-100">
              AI 驱动的学术助手
            </span>
          </div>
          <h1 className="text-3xl font-bold text-slate-900 mb-2 leading-tight">
            论文工作台
          </h1>
          <p className="text-slate-500 text-sm">上传 PDF，AI 自动解析、翻译、智能问答，加速您的研究洞察</p>
        </div>

        {/* Stats */}
        {!loading && papers.length > 0 && (
          <div className="grid grid-cols-3 gap-4 mb-8">
            <StatCard
              value={papers.length}
              label="论文总数"
              icon={Library}
              gradient="bg-gradient-to-br from-blue-500 to-indigo-600"
            />
            <StatCard
              value={readyCount}
              label="已就绪"
              icon={Sparkles}
              gradient="bg-gradient-to-br from-emerald-500 to-teal-600"
            />
            <StatCard
              value={processingCount}
              label="处理中"
              icon={RefreshCw}
              gradient="bg-gradient-to-br from-amber-500 to-orange-600"
            />
          </div>
        )}

        {/* Feature Cards */}
        <div className="grid grid-cols-4 gap-3 mb-8">
          <FeatureCard
            icon={Zap}
            title="智能问答"
            desc="基于论文内容多轮对话，深度理解研究内容"
            accent="blue"
          />
          <FeatureCard
            icon={Globe}
            title="同步翻译"
            desc="中英双语对照，一键翻译学术段落"
            accent="violet"
          />
          <FeatureCard
            icon={Sparkles}
            title="创新挖掘"
            desc="自动提取核心贡献，精准定位创新点"
            accent="teal"
          />
          <FeatureCard
            icon={Brain}
            title="深度检索"
            desc="DeepSearch 模式，跨文档关联分析"
            accent="rose"
          />
        </div>

        {/* Upload */}
        <div className="mb-8">
          <UploadZone onUploadDone={load} />
        </div>

        {/* Paper list */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-slate-700">我的论文库</h2>
              {!loading && papers.length > 0 && (
                <span className="text-xs px-2 py-0.5 bg-slate-100 text-slate-500 rounded-full font-medium">
                  {search ? `${filtered.length} / ${papers.length}` : papers.length}
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={load}
              aria-label="刷新论文列表"
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-blue-500 hover:bg-blue-50 px-2.5 py-1.5 rounded-lg transition-all"
            >
              <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
              刷新
            </button>
          </div>

          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-[74px] rounded-2xl bg-slate-200/60 animate-pulse" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-slate-300">
              <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mb-5">
                <FileText size={28} className="text-slate-300" />
              </div>
              <p className="text-sm text-slate-400 font-semibold mb-1">
                {search ? `未找到包含"${search}"的论文` : '论文库为空'}
              </p>
              <p className="text-xs text-slate-300">
                {search ? '尝试其他关键词' : '上传 PDF 后，它会出现在这里'}
              </p>
            </div>
          ) : (
            <div className="space-y-2.5">
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
