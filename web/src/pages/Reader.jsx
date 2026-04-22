import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Send,
  Sparkles,
  ChevronLeft,
  FileText,
  MessageSquare,
  Settings,
  History,
  Plus,
  Loader2,
  Trash2,
  CheckCircle2,
  XCircle,
  Clock,
  CalendarClock,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { toast } from 'sonner';
import {
  getPaper,
  newSession,
  listSessions,
  getSessionMessages,
  deleteSession,
  chatSend,
  getPaperFileUrl,
  confirmTask,
  rejectTask,
} from '@/api';
import PdfViewer from '@/components/PdfViewer';

const quickQuestions = [
  '总结这篇论文',
  '核心创新点是什么',
  '解释实验方法',
  '有哪些局限性',
  '翻译摘要',
  '润色引言',
];

function buildStepsFromEvents(events) {
  return events
    .filter(ev => ev.event === 'agent' || ev.event === 'result' || ev.event === 'check')
    .map(ev => {
      if (ev.event === 'agent') return { agent: ev.data.name, action: `${ev.data.name} 运行中`, status: ev.data.status };
      if (ev.event === 'result') return { agent: ev.data.name, action: ev.data.summary || `${ev.data.name} 完成`, status: 'completed' };
      if (ev.event === 'check') return { agent: 'CheckAgent', action: ev.data.passed ? '质量检查通过' : `质量问题: ${ev.data.issue}`, status: 'completed' };
      return null;
    })
    .filter(Boolean);
}

function adaptMessage(m) {
  return {
    id: m.message_id,
    role: m.role,
    content: m.content,
    agent: m.role === 'assistant' ? 'Agent' : null,
    timestamp: m.timestamp ? new Date(m.timestamp).toLocaleTimeString('zh-CN') : '',
    steps: [],
  };
}

const Reader = () => {
  const { paperId } = useParams();
  const navigate = useNavigate();
  const [paper, setPaper] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [showSteps, setShowSteps] = useState(true);
  const [loadingPaper, setLoadingPaper] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const messagesEndRef = useRef(null);
  const streamRef = useRef(null);

  // ── 任务确认 ─────────────────────────────────────────────────────────────
  const handleConfirmTask = async (token) => {
    try {
      const result = await confirmTask(token);
      const successMsg = result.job_id
        ? `定时任务已设置 ✓（job: ${result.job_id}）`
        : `后台任务已开始执行 ✓（task: ${result.task_id}）`;
      toast.success(successMsg);
      // 把确认结果追加到对话里让用户看到
      setMessages(prev => prev.map(m =>
        m.confirmToken === token ? { ...m, confirmed: true, confirmResult: successMsg } : m
      ));
    } catch {
      toast.error('任务确认失败，请重试');
    }
  };

  const handleRejectTask = async (token) => {
    try {
      await rejectTask(token);
      toast.info('已取消该任务');
      setMessages(prev => prev.map(m =>
        m.confirmToken === token ? { ...m, confirmed: false, confirmResult: '您已取消该任务' } : m
      ));
    } catch {
      toast.error('操作失败');
    }
  };

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  useEffect(() => { scrollToBottom(); }, [messages]);

  // 加载论文信息
  useEffect(() => {
    (async () => {
      try {
        const p = await getPaper(paperId);
        const authors = Array.isArray(p.authors) ? p.authors.join(', ') : (p.authors || '未知作者');
        setPaper({ ...p, authorsDisplay: authors });
      } catch {
        toast.error('加载论文信息失败');
      } finally {
        setLoadingPaper(false);
      }
    })();
  }, [paperId]);

  // 加载会话列表，没有则自动创建
  useEffect(() => {
    (async () => {
      try {
        const data = await listSessions(paperId);
        const sess = data.sessions || [];
        setSessions(sess);
        if (sess.length > 0) {
          setCurrentSessionId(sess[0].session_id);
        } else {
          const created = await newSession(paperId);
          const newSess = { session_id: created.session_id, title: '新会话', last_message: '' };
          setSessions([newSess]);
          setCurrentSessionId(created.session_id);
        }
      } catch {
        toast.error('加载会话列表失败');
      }
    })();
  }, [paperId]);

  // 切换会话时加载消息
  useEffect(() => {
    if (!currentSessionId) return;
    setLoadingMessages(true);
    (async () => {
      try {
        const data = await getSessionMessages(currentSessionId);
        setMessages((data.messages || []).map(adaptMessage));
      } catch {
        toast.error('加载消息失败');
      } finally {
        setLoadingMessages(false);
      }
    })();
  }, [currentSessionId]);

  const handleSendMessage = () => {
    if (!inputMessage.trim() || isStreaming || !currentSessionId) return;

    const userMsg = {
      id: Date.now().toString(),
      role: 'user',
      content: inputMessage,
      timestamp: new Date().toLocaleTimeString('zh-CN'),
      steps: [],
    };
    setMessages(prev => [...prev, userMsg]);
    const sentText = inputMessage;
    setInputMessage('');
    setIsStreaming(true);

    const assistantId = (Date.now() + 1).toString();
    setMessages(prev => [...prev, {
      id: assistantId,
      role: 'assistant',
      content: '',
      agent: 'Agent',
      timestamp: new Date().toLocaleTimeString('zh-CN'),
      steps: [],
    }]);

    const collectedEvents = [];

    streamRef.current = chatSend({
      sessionId: currentSessionId,
      message: sentText,
      paperUuids: paperId ? [paperId] : [],
      onEvent(ev) {
        collectedEvents.push(ev);
        if (ev.event === 'answer') {
          const steps = buildStepsFromEvents(collectedEvents);
          setMessages(prev => prev.map(m =>
            m.id === assistantId
              ? { ...m, content: ev.data.content || '', steps, agent: 'SupervisorAgent' }
              : m
          ));
        } else if (ev.event === 'plan') {
          setMessages(prev => prev.map(m =>
            m.id === assistantId
              ? { ...m, content: `意图: ${ev.data.intent || ''}` }
              : m
          ));
        } else if (ev.event === 'confirm') {
          // 任务确认事件：在消息里插入确认卡片，不替换 content
          setMessages(prev => prev.map(m =>
            m.id === assistantId
              ? {
                  ...m,
                  content: ev.data.message || '',
                  confirmToken: ev.data.token,
                  confirmTaskType: ev.data.task_type,
                  confirmTaskDesc: ev.data.task_desc,
                  confirmCronExpr: ev.data.cron_expr,
                  confirmed: null,  // null = 待确认
                  agent: 'SupervisorAgent',
                }
              : m
          ));
        }
      },
      onDone() { setIsStreaming(false); streamRef.current = null; },
      onError(err) {
        toast.error(`对话出错: ${err.message}`);
        setIsStreaming(false);
        setMessages(prev => prev.map(m =>
          m.id === assistantId ? { ...m, content: '对话出错，请重试。' } : m
        ));
        streamRef.current = null;
      },
    });
  };

  const handleQuickQuestion = (question) => setInputMessage(question);

  const createNewSession = async () => {
    try {
      const created = await newSession(paperId);
      const newSess = { session_id: created.session_id, title: '新会话', last_message: '' };
      setSessions(prev => [newSess, ...prev]);
      setCurrentSessionId(created.session_id);
      setMessages([]);
      toast.success('新会话已创建');
    } catch {
      toast.error('创建会话失败');
    }
  };

  const handleSwitchSession = (sessionId) => {
    if (sessionId === currentSessionId) return;
    streamRef.current?.close();
    setIsStreaming(false);
    setCurrentSessionId(sessionId);
  };

  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation();
    try {
      await deleteSession(sessionId);
      const remaining = sessions.filter(s => s.session_id !== sessionId);
      setSessions(remaining);
      if (currentSessionId === sessionId) {
        if (remaining.length > 0) {
          setCurrentSessionId(remaining[0].session_id);
        } else {
          const created = await newSession(paperId);
          const newSess = { session_id: created.session_id, title: '新会话', last_message: '' };
          setSessions([newSess]);
          setCurrentSessionId(created.session_id);
          setMessages([]);
        }
      }
      toast.success('会话已删除');
    } catch {
      toast.error('删除会话失败');
    }
  };

  const handleClearSession = async () => {
    try {
      await deleteSession(currentSessionId);
      const created = await newSession(paperId);
      const newSess = { session_id: created.session_id, title: '新会话', last_message: '' };
      setSessions(prev => [newSess, ...prev.filter(s => s.session_id !== currentSessionId)]);
      setCurrentSessionId(created.session_id);
      setMessages([]);
      toast.success('会话已清空');
    } catch {
      toast.error('清空失败');
    }
  };

  if (loadingPaper) {
    return (
      <div className="h-screen flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 h-16 flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate('/')}>
            <ChevronLeft className="w-4 h-4 mr-1" />
            返回
          </Button>
          <Separator orientation="vertical" className="h-6" />
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center">
              <FileText className="w-4 h-4 text-blue-600" />
            </div>
            <div>
              <h1 className="font-semibold text-gray-900 max-w-xs truncate">
                {paper?.title || '加载中...'}
              </h1>
              <p className="text-xs text-gray-500">{paper?.authorsDisplay}</p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline" size="sm">
                <History className="w-4 h-4 mr-2" />
                会话历史
              </Button>
            </SheetTrigger>
            <SheetContent>
              <SheetHeader>
                <SheetTitle>会话管理</SheetTitle>
              </SheetHeader>
              <div className="mt-4 space-y-2">
                <Button className="w-full" onClick={createNewSession}>
                  <Plus className="w-4 h-4 mr-2" />
                  新建会话
                </Button>
                <Separator className="my-4" />
                <div className="space-y-2">
                  {sessions.map(session => (
                    <Card
                      key={session.session_id}
                      className={`cursor-pointer ${currentSessionId === session.session_id ? 'border-blue-500' : ''}`}
                      onClick={() => handleSwitchSession(session.session_id)}
                    >
                      <CardContent className="p-3">
                        <div className="flex items-start gap-3">
                          <MessageSquare className="w-4 h-4 text-gray-400 mt-0.5 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">{session.title || '新会话'}</p>
                            <p className="text-xs text-gray-500 truncate">{session.last_message || ''}</p>
                          </div>
                          <Button
                            size="icon" variant="ghost"
                            className="w-6 h-6 shrink-0 text-gray-400 hover:text-red-500"
                            onClick={(e) => handleDeleteSession(e, session.session_id)}
                          >
                            <Trash2 className="w-3 h-3" />
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            </SheetContent>
          </Sheet>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm">
                <Settings className="w-4 h-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setShowSteps(!showSteps)}>
                {showSteps ? '隐藏' : '显示'} Agent 执行步骤
              </DropdownMenuItem>
              <DropdownMenuItem className="text-red-600" onClick={handleClearSession}>
                清空当前会话
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* PDF Viewer */}
        <div className="flex-1 bg-gray-100 overflow-hidden">
          {paperId ? (
            <PdfViewer
              url={getPaperFileUrl(paperId)}
              onAskAI={(selectedText) => {
                setInputMessage(`请解释以下内容：\n"${selectedText}"`);
              }}
            />
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center">
              <FileText className="w-16 h-16 text-gray-300 mb-4" />
              <p className="text-gray-500">无法加载 PDF</p>
            </div>
          )}
        </div>

        {/* Chat Panel */}
        <div className="w-[450px] bg-white border-l border-gray-200 flex flex-col">
          <ScrollArea className="flex-1 p-4">
            <div className="space-y-4">
              {loadingMessages ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
                </div>
              ) : messages.length === 0 ? (
                <div className="text-center py-8">
                  <Sparkles className="w-12 h-12 text-blue-500 mx-auto mb-4" />
                  <h3 className="font-semibold text-gray-900 mb-2">开始对话</h3>
                  <p className="text-sm text-gray-500">选择下方快捷问题或输入自定义问题</p>
                </div>
              ) : null}

              {messages.map((message) => (
                <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[90%] ${message.role === 'user' ? 'bg-blue-600 text-white' : 'bg-gray-100'} rounded-2xl px-4 py-3`}>
                    {message.role === 'assistant' && message.agent && (
                      <div className="flex items-center gap-2 mb-2">
                        <Badge variant="secondary" className="text-xs">
                          <Sparkles className="w-3 h-3 mr-1" />
                          {message.agent}
                        </Badge>
                      </div>
                    )}
                    <div className={`text-sm whitespace-pre-wrap ${message.role === 'user' ? '' : 'text-gray-800'}`}>
                      {message.content || (message.role === 'assistant' && isStreaming ? '思考中...' : '')}
                    </div>

                    {/* 任务确认卡片 */}
                    {message.confirmToken && (
                      <div className="mt-3 border border-blue-200 rounded-xl bg-blue-50 p-3">
                        <div className="flex items-center gap-2 mb-2">
                          {message.confirmTaskType === 'periodic'
                            ? <CalendarClock className="w-4 h-4 text-blue-600" />
                            : <Clock className="w-4 h-4 text-blue-600" />}
                          <span className="text-xs font-semibold text-blue-700">
                            {message.confirmTaskType === 'periodic' ? '定时任务' : '后台任务'}
                          </span>
                          {message.confirmCronExpr && (
                            <span className="text-xs text-blue-500 font-mono">{message.confirmCronExpr}</span>
                          )}
                        </div>
                        <p className="text-xs text-gray-700 mb-3 leading-relaxed">{message.confirmTaskDesc}</p>

                        {message.confirmed === null && (
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              className="h-7 text-xs bg-blue-600 hover:bg-blue-700 flex items-center gap-1"
                              onClick={() => handleConfirmTask(message.confirmToken)}
                            >
                              <CheckCircle2 className="w-3 h-3" /> 确认执行
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 text-xs flex items-center gap-1"
                              onClick={() => handleRejectTask(message.confirmToken)}
                            >
                              <XCircle className="w-3 h-3" /> 取消
                            </Button>
                          </div>
                        )}

                        {message.confirmed === true && (
                          <div className="flex items-center gap-1 text-xs text-green-600">
                            <CheckCircle2 className="w-3 h-3" />
                            {message.confirmResult}
                          </div>
                        )}
                        {message.confirmed === false && (
                          <div className="flex items-center gap-1 text-xs text-gray-400">
                            <XCircle className="w-3 h-3" />
                            {message.confirmResult}
                          </div>
                        )}
                      </div>
                    )}

                    <div className={`text-xs mt-2 ${message.role === 'user' ? 'text-blue-200' : 'text-gray-400'}`}>
                      {message.timestamp}
                    </div>

                    {showSteps && message.role === 'assistant' && message.steps?.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-gray-200">
                        <div className="space-y-1">
                          {message.steps.map((step, idx) => (
                            <div key={idx} className="flex items-center gap-2 text-xs text-gray-500">
                              <div className="w-1.5 h-1.5 bg-green-500 rounded-full" />
                              <span className="font-medium">{step.agent}:</span>
                              <span>{step.action}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {isStreaming && messages[messages.length - 1]?.role !== 'assistant' && (
                <div className="flex justify-start">
                  <div className="bg-gray-100 rounded-2xl px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
                      <span className="text-sm text-gray-600">Agent 思考中...</span>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </ScrollArea>

          {/* Quick Questions */}
          <div className="px-4 py-2 border-t border-gray-100">
            <div className="flex gap-2 overflow-x-auto pb-2">
              {quickQuestions.map((question, idx) => (
                <Button
                  key={idx} variant="outline" size="sm"
                  className="whitespace-nowrap text-xs"
                  onClick={() => handleQuickQuestion(question)}
                >
                  {question}
                </Button>
              ))}
            </div>
          </div>

          {/* Input Area */}
          <div className="p-4 border-t border-gray-200">
            <div className="flex gap-2">
              <Input
                placeholder="输入问题，AI 将基于论文内容回答..."
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
                className="flex-1"
                disabled={isStreaming}
              />
              <Button onClick={handleSendMessage} disabled={!inputMessage.trim() || isStreaming}>
                <Send className="w-4 h-4" />
              </Button>
            </div>
            <p className="text-xs text-gray-400 mt-2 text-center">
              Powered by Multi-Agent System • RAG + DeepSearch
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Reader;
