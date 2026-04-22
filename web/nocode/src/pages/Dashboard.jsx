import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Upload,
  Search,
  FileText,
  MoreVertical,
  Trash2,
  Clock,
  CheckCircle,
  AlertCircle,
  Loader2,
  Grid3X3,
  LayoutGrid,
  ChevronLeft,
  ChevronRight,
  BookOpen,
  Brain,
  Zap,
  Network,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import { listPapers, uploadPaper, deletePaper, getTask } from '@/api';

const features = [
  {
    icon: Brain,
    title: '多 Agent 协同',
    description: 'Supervisor、RAG、Writing、Translation、Check 五大 Agent 智能协作'
  },
  {
    icon: Zap,
    title: 'SSE 流式对话',
    description: '实时推送 Agent 执行过程，流畅的交互体验'
  },
  {
    icon: Network,
    title: '深度检索',
    description: 'SimpleRAG 自动升级为 DeepSearch，确保回答质量'
  },
  {
    icon: BookOpen,
    title: '智能引用',
    description: '即时引用检索与定时任务，追踪论文引用关系'
  }
];

const statusConfig = {
  pending:  { label: '等待中', color: 'bg-gray-100 text-gray-600',   icon: Clock },
  parsing:  { label: '解析中', color: 'bg-yellow-100 text-yellow-700', icon: Loader2 },
  ready:    { label: '已就绪', color: 'bg-green-100 text-green-700',  icon: CheckCircle },
  failed:   { label: '失败',   color: 'bg-red-100 text-red-700',     icon: AlertCircle },
};

// backend paper → UI paper
function adaptPaper(p) {
  let status = 'pending';
  if (p.status === 'parsing') status = 'parsing';
  else if (p.is_processed === 1 || p.is_processed === true) status = 'ready';
  else if (p.status === 'failed') status = 'failed';
  else if (p.is_processed === 0 || p.is_processed === false) status = 'pending';

  const filename = p.file_path
    ? p.file_path.split('/').pop().replace(/^[^_]+_/, '')
    : null;

  return {
    id: p.paper_uuid,
    title: p.title || filename || '未命名论文',
    authors: Array.isArray(p.authors) ? p.authors.join(', ') : (p.authors || '未知作者'),
    abstract: p.abstract || '',
    status,
    uploadTime: p.created_at ? new Date(p.created_at).toLocaleString('zh-CN') : '',
    parsedAt: null,
    coverImage: null,
    taskId: p.taskId || null,
  };
}

const POLL_INTERVAL = 3000;

const Dashboard = () => {
  const navigate = useNavigate();
  const [papers, setPapers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(12);
  const [viewMode, setViewMode] = useState('grid');
  const pollingRef = useRef({});

  const fetchPapers = useCallback(async () => {
    try {
      const data = await listPapers();
      setPapers((data.papers || []).map(adaptPaper));
    } catch (e) {
      toast.error('加载论文列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPapers();
  }, [fetchPapers]);

  // Poll task status for papers still processing
  useEffect(() => {
    const processingPapers = papers.filter(p => p.status === 'parsing' && p.taskId);
    for (const paper of processingPapers) {
      if (pollingRef.current[paper.id]) continue;
      pollingRef.current[paper.id] = setInterval(async () => {
        try {
          const task = await getTask(paper.taskId);
          if (task.status === 'done' || task.status === 'failed') {
            clearInterval(pollingRef.current[paper.id]);
            delete pollingRef.current[paper.id];
            await fetchPapers();
          }
        } catch {
          clearInterval(pollingRef.current[paper.id]);
          delete pollingRef.current[paper.id];
        }
      }, POLL_INTERVAL);
    }
    return () => {
      // Clean up polls for papers no longer in processing
      const processingIds = new Set(processingPapers.map(p => p.id));
      for (const [id, timer] of Object.entries(pollingRef.current)) {
        if (!processingIds.has(id)) {
          clearInterval(timer);
          delete pollingRef.current[id];
        }
      }
    };
  }, [papers, fetchPapers]);

  useEffect(() => {
    return () => {
      for (const timer of Object.values(pollingRef.current)) clearInterval(timer);
    };
  }, []);

  const filteredPapers = papers.filter(paper =>
    paper.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    paper.authors.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const totalPages = Math.ceil(filteredPapers.length / pageSize);
  const startIndex = (currentPage - 1) * pageSize;
  const paginatedPapers = filteredPapers.slice(startIndex, startIndex + pageSize);

  const handleDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files).filter(f => f.type === 'application/pdf');
    if (files.length > 0) handleUpload(files[0]);
  };

  const handleUpload = async (file) => {
    const tempId = `uploading-${Date.now()}`;
    const tempPaper = {
      id: tempId,
      title: file.name.replace('.pdf', ''),
      authors: '未知作者',
      abstract: '正在上传中...',
      status: 'parsing',
      uploadTime: new Date().toLocaleString('zh-CN'),
      parsedAt: null,
      coverImage: null,
      taskId: null,
    };
    setPapers(prev => [tempPaper, ...prev]);
    toast.success(`开始上传: ${file.name}`);

    try {
      const result = await uploadPaper(file);
      // Replace temp entry after refresh
      await fetchPapers();
      // Start polling the new task
      if (result.task_id) {
        const pollTimer = setInterval(async () => {
          try {
            const task = await getTask(result.task_id);
            if (task.status === 'done' || task.status === 'failed') {
              clearInterval(pollTimer);
              await fetchPapers();
              if (task.status === 'done') toast.success('论文解析完成');
              else toast.error('论文解析失败');
            }
          } catch {
            clearInterval(pollTimer);
          }
        }, POLL_INTERVAL);
      }
    } catch (e) {
      setPapers(prev => prev.filter(p => p.id !== tempId));
      toast.error(`上传失败: ${e.message}`);
    }
  };

  const handleDelete = async (id) => {
    try {
      await deletePaper(id);
      setPapers(prev => prev.filter(p => p.id !== id));
      toast.success('论文已删除');
    } catch (e) {
      toast.error(`删除失败: ${e.message}`);
    }
  };

  const handleOpenReader = (paperId) => navigate(`/reader/${paperId}`);
  const handlePageChange = (newPage) => {
    if (newPage >= 1 && newPage <= totalPages) setCurrentPage(newPage);
  };

  const getGridCols = () => {
    if (viewMode === 'compact') return 'grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8';
    return 'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4';
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex items-center justify-center">
        <div className="flex items-center gap-3 text-gray-500">
          <Loader2 className="w-6 h-6 animate-spin" />
          <span>加载中...</span>
        </div>
      </div>
    );
  }

  if (papers.length === 0) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex flex-col">
        <header className="bg-white/80 backdrop-blur-md border-b border-gray-200 sticky top-0 z-10">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl flex items-center justify-center shadow-lg">
                <BookOpen className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">Easy Paper Reader</h1>
                <p className="text-xs text-gray-500">AI 论文阅读助手</p>
              </div>
            </div>
          </div>
        </header>

        <main className="flex-1 flex items-center justify-center p-8">
          <div className="max-w-5xl w-full">
            <div className="text-center mb-12">
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-blue-100 text-blue-700 text-sm font-medium mb-6">
                <Zap className="w-4 h-4" />
                AI 驱动的学术研究助手
              </div>
              <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">让论文阅读更智能</h1>
              <p className="text-lg text-gray-600 max-w-2xl mx-auto mb-8">
                基于多 Agent 协同架构，支持智能问答、深度检索与引用追踪
              </p>
            </div>

            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4 mb-12">
              {features.map((feature, idx) => (
                <Card key={idx} className="bg-white/60 backdrop-blur-sm border-0 shadow-sm hover:shadow-md transition-all">
                  <CardContent className="p-6 text-center">
                    <div className="w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center mx-auto mb-3">
                      <feature.icon className="w-6 h-6 text-blue-600" />
                    </div>
                    <h3 className="font-semibold text-gray-900 mb-1">{feature.title}</h3>
                    <p className="text-xs text-gray-500 leading-relaxed">{feature.description}</p>
                  </CardContent>
                </Card>
              ))}
            </div>

            <Card
              className={`border-2 border-dashed transition-all duration-300 cursor-pointer hover:shadow-lg ${
                isDragging ? 'border-blue-500 bg-blue-50 scale-105' : 'border-gray-300 bg-white/50'
              }`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => document.getElementById('file-input-empty').click()}
            >
              <CardContent className="py-16">
                <div className="text-center">
                  <div className="w-20 h-20 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-lg">
                    <Upload className="w-10 h-10 text-white" />
                  </div>
                  <h3 className="text-xl font-bold text-gray-900 mb-2">拖拽 PDF 文件到此处上传</h3>
                  <p className="text-sm text-gray-500 mb-6">支持批量上传，自动解析论文内容并构建向量索引</p>
                  <Button size="lg" className="gap-2">
                    <Upload className="w-4 h-4" />
                    选择文件上传
                  </Button>
                  <input
                    id="file-input-empty"
                    type="file"
                    accept=".pdf"
                    multiple
                    className="hidden"
                    onChange={(e) => {
                      Array.from(e.target.files || []).forEach(file => handleUpload(file));
                      e.target.value = '';
                    }}
                  />
                </div>
              </CardContent>
            </Card>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl flex items-center justify-center shadow-md">
              <BookOpen className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">Easy Paper Reader</h1>
              <p className="text-xs text-gray-500">论文库 ({filteredPapers.length} 篇)</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="relative hidden sm:block">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <Input
                placeholder="搜索论文..."
                className="pl-10 w-64"
                value={searchQuery}
                onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
              />
            </div>

            <Button
              variant="outline"
              size="icon"
              onClick={() => setViewMode(viewMode === 'grid' ? 'compact' : 'grid')}
              title={viewMode === 'grid' ? '紧凑视图' : '网格视图'}
            >
              {viewMode === 'grid' ? <LayoutGrid className="w-4 h-4" /> : <Grid3X3 className="w-4 h-4" />}
            </Button>

            <Button onClick={() => document.getElementById('file-input').click()}>
              <Upload className="w-4 h-4 mr-2" />
              上传
            </Button>
            <input
              id="file-input"
              type="file"
              accept=".pdf"
              multiple
              className="hidden"
              onChange={(e) => {
                Array.from(e.target.files || []).forEach(file => handleUpload(file));
                e.target.value = '';
              }}
            />
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 w-full">
        <Card
          className={`mb-6 border-2 border-dashed transition-all duration-200 ${
            isDragging ? 'border-blue-500 bg-blue-50' : 'border-gray-200 bg-white'
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <CardContent className="py-4">
            <div className="flex items-center justify-center gap-4">
              <Upload className="w-5 h-5 text-gray-400" />
              <span className="text-sm text-gray-600">拖拽 PDF 文件到此处上传，或</span>
              <Button variant="link" className="p-0 h-auto" onClick={() => document.getElementById('file-input').click()}>
                点击选择文件
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500">每页显示：</span>
            <Select value={pageSize.toString()} onValueChange={(v) => { setPageSize(Number(v)); setCurrentPage(1); }}>
              <SelectTrigger className="w-20"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="12">12</SelectItem>
                <SelectItem value="24">24</SelectItem>
                <SelectItem value="48">48</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <span>共 {filteredPapers.length} 篇</span>
            <span>·</span>
            <span>第 {currentPage}/{totalPages || 1} 页</span>
          </div>
        </div>

        <div className={`grid ${getGridCols()} gap-4 mb-8`}>
          {paginatedPapers.map((paper) => {
            const status = statusConfig[paper.status] || statusConfig.pending;
            const StatusIcon = status.icon;

            return (
              <Card
                key={paper.id}
                className="group cursor-pointer hover:shadow-lg transition-all duration-200 overflow-hidden border-0 shadow-sm bg-white"
                onClick={() => paper.status === 'ready' && handleOpenReader(paper.id)}
              >
                <div className="aspect-[4/3] bg-gray-100 relative overflow-hidden">
                  {paper.coverImage ? (
                    <img
                      src={paper.coverImage}
                      alt={paper.title}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-gray-100 to-gray-200">
                      <FileText className="w-12 h-12 text-gray-300" />
                    </div>
                  )}

                  <div className="absolute top-2 right-2">
                    <Badge className={`${status.color} text-xs font-medium border-0`}>
                      <StatusIcon className={`w-3 h-3 mr-1 ${paper.status === 'parsing' ? 'animate-spin' : ''}`} />
                      {status.label}
                    </Badge>
                  </div>

                  <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                    {paper.status === 'ready' && (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={(e) => { e.stopPropagation(); handleOpenReader(paper.id); }}
                      >
                        <BookOpen className="w-4 h-4 mr-1" />
                        阅读
                      </Button>
                    )}
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button size="sm" variant="secondary" onClick={(e) => e.stopPropagation()}>
                          <MoreVertical className="w-4 h-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onClick={(e) => { e.stopPropagation(); handleDelete(paper.id); }}
                          className="text-red-600"
                        >
                          <Trash2 className="w-4 h-4 mr-2" />
                          删除
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>

                <CardContent className="p-3">
                  <h3 className="font-semibold text-gray-900 text-sm line-clamp-2 mb-1 leading-tight min-h-[2.5rem]">
                    {paper.title}
                  </h3>
                  <p className="text-xs text-gray-500 line-clamp-1 mb-2">{paper.authors}</p>
                  <div className="flex items-center justify-between text-xs text-gray-400">
                    <span>{paper.uploadTime.split(' ')[0]}</span>
                    {paper.status === 'ready' && (
                      <span className="text-green-600 flex items-center gap-1">
                        <CheckCircle className="w-3 h-3" />
                        已解析
                      </span>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2">
            <Button variant="outline" size="sm" onClick={() => handlePageChange(currentPage - 1)} disabled={currentPage === 1}>
              <ChevronLeft className="w-4 h-4 mr-1" />
              上一页
            </Button>

            <div className="flex items-center gap-1">
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                let pageNum;
                if (totalPages <= 5) pageNum = i + 1;
                else if (currentPage <= 3) pageNum = i + 1;
                else if (currentPage >= totalPages - 2) pageNum = totalPages - 4 + i;
                else pageNum = currentPage - 2 + i;
                return (
                  <Button
                    key={pageNum}
                    variant={currentPage === pageNum ? 'default' : 'outline'}
                    size="sm"
                    className="w-8 h-8 p-0"
                    onClick={() => handlePageChange(pageNum)}
                  >
                    {pageNum}
                  </Button>
                );
              })}
            </div>

            <Button variant="outline" size="sm" onClick={() => handlePageChange(currentPage + 1)} disabled={currentPage === totalPages}>
              下一页
              <ChevronRight className="w-4 h-4 ml-1" />
            </Button>
          </div>
        )}
      </main>
    </div>
  );
};

export default Dashboard;
