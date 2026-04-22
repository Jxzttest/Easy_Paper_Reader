import { useState, useEffect, useCallback } from 'react';
import {
  Pause,
  Play,
  RotateCcw,
  X,
  Trash2,
  CheckCircle,
  AlertCircle,
  Loader2,
  Clock,
  ChevronDown,
  Bot,
  Calendar,
  Timer,
  Bell,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

const BASE = '/api';

// ── API helpers ────────────────────────────────────────────────────────────

async function fetchAllTasks() {
  const res = await fetch(`${BASE}/tasks/list?limit=30`);
  if (!res.ok) throw new Error('fetch tasks failed');
  const data = await res.json();
  return data.tasks || [];
}

async function cancelTask(taskId) {
  await fetch(`${BASE}/tasks/${taskId}/cancel`, { method: 'POST' });
}

async function retryTask(taskId) {
  await fetch(`${BASE}/tasks/${taskId}/retry`, { method: 'POST' });
}

async function fetchScheduledJobs() {
  const res = await fetch(`${BASE}/citation/schedule/list`);
  if (!res.ok) throw new Error('fetch jobs failed');
  const data = await res.json();
  return data.jobs || [];
}

async function cancelJob(jobId) {
  await fetch(`${BASE}/citation/schedule/${jobId}`, { method: 'DELETE' });
}

async function runJobNow(jobId) {
  await fetch(`${BASE}/citation/schedule/${jobId}/run-now`, { method: 'POST' });
}

// ── 状态常量 ───────────────────────────────────────────────────────────────

const TaskStatus = { PENDING: 'pending', RUNNING: 'running', SUCCESS: 'success', FAILED: 'failed', CANCELLED: 'cancelled' };

// backend task → UI task
function adaptTask(t) {
  const steps = (t.steps || []).map((s, i) => ({
    id: `${t.task_id}_s${i}`,
    name: s.name,
    status: s.status === 'success' ? 'completed' : s.status,
    time: s.finished_at ? new Date(s.finished_at).toLocaleTimeString('zh-CN') : null,
  }));

  const doneSteps = steps.filter(s => s.status === 'completed').length;
  const progress = steps.length > 0 ? Math.round((doneSteps / steps.length) * 100) : (t.status === 'success' ? 100 : 0);

  const runningStep = steps.find(s => s.status === 'running');
  const currentStep = runningStep?.name || (t.status === 'success' ? '任务已完成' : t.error || '');

  const typeLabel = {
    parse_pdf: '论文解析',
    citation_check: '引用检索',
    parse_citation_pdf: '引用论文解析',
  };

  return {
    id: t.task_id,
    name: typeLabel[t.task_type] || t.task_type,
    description: t.error ? `失败: ${t.error.slice(0, 40)}` : `步骤 ${doneSteps}/${steps.length}`,
    status: t.status === 'success' ? TaskStatus.SUCCESS : (t.status === 'cancelled' ? TaskStatus.CANCELLED : t.status),
    progress,
    currentStep,
    steps,
    createdAt: t.created_at ? new Date(t.created_at).toLocaleString('zh-CN') : '',
    completedAt: t.status === 'success' ? (t.updated_at ? new Date(t.updated_at).toLocaleString('zh-CN') : null) : null,
  };
}

// backend job → UI scheduled task
function adaptJob(j) {
  const cronDesc = {
    '0 9 * * *': '每天上午 9:00',
    '0 9 * * 1': '每周一 09:00',
    '0 */6 * * *': '每 6 小时',
  };

  const paperTitle = j.paper_uuid ? j.paper_uuid.slice(0, 8) + '...' : '-';

  return {
    id: j.job_id,
    name: `引用检索 · ${paperTitle}`,
    description: `paper: ${j.paper_uuid}`,
    status: j.is_active ? 'active' : 'disabled',
    cron: j.cron_expr,
    cronDescription: cronDesc[j.cron_expr] || j.cron_expr,
    lastRun: j.last_run_at ? new Date(j.last_run_at).toLocaleString('zh-CN') : '从未执行',
    nextRun: j.next_run_at ? new Date(j.next_run_at).toLocaleString('zh-CN') : (j.is_active ? '计算中' : '已停用'),
    runCount: j.run_count || 0,
    isRunning: !!j.is_running,
    createdAt: j.created_at ? new Date(j.created_at).toLocaleString('zh-CN') : '',
  };
}

// ── 组件 ───────────────────────────────────────────────────────────────────

const POLL_MS = 4000;

const TaskQueue = () => {
  const [tasks, setTasks] = useState([]);
  const [scheduledTasks, setScheduledTasks] = useState([]);
  const [isExpanded, setIsExpanded] = useState(true);
  const [activeTab, setActiveTab] = useState('instant');

  const loadTasks = useCallback(async () => {
    try {
      const raw = await fetchAllTasks();
      setTasks(raw.map(adaptTask));
    } catch { /* 静默失败 */ }
  }, []);

  const loadJobs = useCallback(async () => {
    try {
      const raw = await fetchScheduledJobs();
      setScheduledTasks(raw.map(adaptJob));
    } catch { /* 静默失败 */ }
  }, []);

  useEffect(() => {
    loadTasks();
    loadJobs();
    const timer = setInterval(() => { loadTasks(); loadJobs(); }, POLL_MS);
    return () => clearInterval(timer);
  }, [loadTasks, loadJobs]);

  const handleCancel = async (taskId) => {
    try {
      await cancelTask(taskId);
      await loadTasks();
      toast.success('任务已取消');
    } catch { toast.error('取消失败'); }
  };

  const handleRetry = async (taskId) => {
    try {
      await retryTask(taskId);
      await loadTasks();
      toast.success('任务已重试');
    } catch { toast.error('重试失败'); }
  };

  const handleCancelJob = async (jobId) => {
    try {
      await cancelJob(jobId);
      await loadJobs();
      toast.success('定时任务已停用');
    } catch { toast.error('停用失败'); }
  };

  const handleRunNow = async (jobId) => {
    try {
      await runJobNow(jobId);
      toast.success('已触发立即执行');
    } catch { toast.error('触发失败'); }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case TaskStatus.RUNNING:   return <Loader2 className="w-4 h-4 animate-spin text-blue-600" />;
      case TaskStatus.SUCCESS:   return <CheckCircle className="w-4 h-4 text-green-600" />;
      case TaskStatus.FAILED:    return <AlertCircle className="w-4 h-4 text-red-600" />;
      case TaskStatus.CANCELLED: return <X className="w-4 h-4 text-gray-400" />;
      default:                   return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  const getStatusBadge = (status) => {
    const map = {
      [TaskStatus.PENDING]:   ['bg-gray-100 text-gray-600',   '等待中'],
      [TaskStatus.RUNNING]:   ['bg-blue-100 text-blue-700',   '执行中'],
      [TaskStatus.SUCCESS]:   ['bg-green-100 text-green-700', '已完成'],
      [TaskStatus.FAILED]:    ['bg-red-100 text-red-700',     '失败'],
      [TaskStatus.CANCELLED]: ['bg-gray-100 text-gray-500',   '已取消'],
    };
    const [cls, label] = map[status] || map[TaskStatus.PENDING];
    return <Badge className={cn('text-xs font-medium border-0', cls)}>{label}</Badge>;
  };

  const runningCount = tasks.filter(t => t.status === TaskStatus.RUNNING).length;
  const activeJobCount = scheduledTasks.filter(t => t.status === 'active').length;

  return (
    <Card className="w-80 shadow-lg border-0 bg-white/95 backdrop-blur-sm">
      <CardHeader className="py-3 px-4 cursor-pointer" onClick={() => setIsExpanded(!isExpanded)}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="relative">
              <Bot className="w-5 h-5 text-blue-600" />
              {(runningCount > 0 || activeJobCount > 0) && (
                <span className="absolute -top-1 -right-1 w-2 h-2 bg-red-500 rounded-full animate-pulse" />
              )}
            </div>
            <CardTitle className="text-sm font-semibold">任务队列</CardTitle>
            {runningCount > 0 && (
              <Badge variant="secondary" className="text-xs">{runningCount} 运行中</Badge>
            )}
          </div>
          <ChevronDown className={cn('w-4 h-4 text-gray-400 transition-transform', !isExpanded && '-rotate-90')} />
        </div>
      </CardHeader>

      {isExpanded && (
        <CardContent className="px-3 pb-3 pt-0">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="grid w-full grid-cols-2 mb-3">
              <TabsTrigger value="instant" className="text-xs">
                <Timer className="w-3 h-3 mr-1" />
                即时任务
                {runningCount > 0 && <span className="ml-1 w-1.5 h-1.5 bg-blue-500 rounded-full" />}
              </TabsTrigger>
              <TabsTrigger value="scheduled" className="text-xs">
                <Calendar className="w-3 h-3 mr-1" />
                周期任务
                {activeJobCount > 0 && <span className="ml-1 w-1.5 h-1.5 bg-green-500 rounded-full" />}
              </TabsTrigger>
            </TabsList>

            {/* ── 即时任务 ── */}
            <TabsContent value="instant" className="mt-0">
              <ScrollArea className="h-64 pr-2">
                <div className="space-y-3">
                  {tasks.map((task) => (
                    <HoverCard key={task.id} openDelay={200}>
                      <HoverCardTrigger asChild>
                        <div className={cn(
                          'p-3 rounded-lg border transition-all cursor-pointer',
                          task.status === TaskStatus.RUNNING
                            ? 'bg-blue-50/50 border-blue-200'
                            : 'bg-gray-50 border-gray-100 hover:border-gray-200'
                        )}>
                          <div className="flex items-start justify-between mb-2">
                            <div className="flex items-center gap-2">
                              {getStatusIcon(task.status)}
                              <div>
                                <p className="text-sm font-medium text-gray-900">{task.name}</p>
                                <p className="text-xs text-gray-500">{task.description}</p>
                              </div>
                            </div>
                            {getStatusBadge(task.status)}
                          </div>

                          {task.status === TaskStatus.RUNNING && task.currentStep && (
                            <p className="text-xs text-blue-600 mb-2 flex items-center gap-1">
                              <Loader2 className="w-3 h-3 animate-spin" />
                              {task.currentStep}
                            </p>
                          )}

                          <div className="flex items-center gap-2">
                            <Progress value={task.progress} className="h-1.5 flex-1" />
                            <span className="text-xs text-gray-500 w-10 text-right">{task.progress}%</span>
                          </div>

                          <div className="flex items-center justify-end gap-1 mt-2">
                            {task.status === TaskStatus.FAILED && (
                              <Button
                                variant="ghost" size="sm"
                                className="h-7 w-7 p-0 text-blue-600 hover:text-blue-700 hover:bg-blue-50"
                                onClick={(e) => { e.stopPropagation(); handleRetry(task.id); }}
                                title="重试"
                              >
                                <RotateCcw className="w-3.5 h-3.5" />
                              </Button>
                            )}
                            {task.status === TaskStatus.RUNNING && (
                              <Button
                                variant="ghost" size="sm"
                                className="h-7 w-7 p-0 text-gray-400 hover:text-red-600 hover:bg-red-50"
                                onClick={(e) => { e.stopPropagation(); handleCancel(task.id); }}
                                title="取消"
                              >
                                <X className="w-3.5 h-3.5" />
                              </Button>
                            )}
                          </div>
                        </div>
                      </HoverCardTrigger>

                      <HoverCardContent className="w-72 p-0" align="end" side="left">
                        <div className="p-3 border-b bg-gray-50">
                          <p className="text-sm font-semibold text-gray-900">{task.name}</p>
                          <p className="text-xs text-gray-500">执行步骤详情</p>
                        </div>
                        <ScrollArea className="h-48 p-3">
                          <div className="space-y-2">
                            {task.steps.map((step) => (
                              <div key={step.id} className="flex items-start gap-2">
                                <div className={cn(
                                  'w-5 h-5 rounded-full flex items-center justify-center shrink-0 mt-0.5',
                                  step.status === 'completed' && 'bg-green-100',
                                  step.status === 'running'   && 'bg-blue-100',
                                  step.status === 'failed'    && 'bg-red-100',
                                  step.status === 'pending'   && 'bg-gray-100',
                                )}>
                                  {step.status === 'completed' && <CheckCircle className="w-3 h-3 text-green-600" />}
                                  {step.status === 'running'   && <Loader2 className="w-3 h-3 text-blue-600 animate-spin" />}
                                  {step.status === 'failed'    && <AlertCircle className="w-3 h-3 text-red-600" />}
                                  {step.status === 'pending'   && <div className="w-2 h-2 rounded-full bg-gray-300" />}
                                </div>
                                <div className="flex-1 min-w-0">
                                  <p className={cn(
                                    'text-xs',
                                    step.status === 'completed' && 'text-gray-900',
                                    step.status === 'running'   && 'text-blue-700 font-medium',
                                    step.status === 'failed'    && 'text-red-700',
                                    step.status === 'pending'   && 'text-gray-400',
                                  )}>
                                    {step.name}
                                  </p>
                                  {step.time && <p className="text-xs text-gray-400 mt-0.5">{step.time}</p>}
                                </div>
                              </div>
                            ))}
                            {task.steps.length === 0 && (
                              <p className="text-xs text-gray-400 text-center py-2">暂无步骤记录</p>
                            )}
                          </div>
                        </ScrollArea>
                        <div className="p-3 border-t bg-gray-50 text-xs text-gray-500">
                          <p>创建于: {task.createdAt}</p>
                          {task.completedAt && <p>完成于: {task.completedAt}</p>}
                        </div>
                      </HoverCardContent>
                    </HoverCard>
                  ))}

                  {tasks.length === 0 && (
                    <div className="text-center py-8">
                      <Timer className="w-10 h-10 text-gray-200 mx-auto mb-2" />
                      <p className="text-sm text-gray-400">暂无即时任务</p>
                    </div>
                  )}
                </div>
              </ScrollArea>
            </TabsContent>

            {/* ── 周期任务 ── */}
            <TabsContent value="scheduled" className="mt-0">
              <ScrollArea className="h-64 pr-2">
                <div className="space-y-3">
                  {scheduledTasks.map((task) => (
                    <HoverCard key={task.id} openDelay={200}>
                      <HoverCardTrigger asChild>
                        <div className={cn(
                          'p-3 rounded-lg border transition-all cursor-pointer',
                          task.status === 'active'
                            ? 'bg-green-50/50 border-green-200'
                            : 'bg-gray-50 border-gray-100 hover:border-gray-200'
                        )}>
                          <div className="flex items-start justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <Calendar className={cn(
                                'w-4 h-4',
                                task.status === 'active'   && 'text-green-600',
                                task.status === 'disabled' && 'text-gray-400',
                              )} />
                              <div>
                                <p className="text-sm font-medium text-gray-900">{task.name}</p>
                                <p className="text-xs text-gray-400">{task.cronDescription}</p>
                              </div>
                            </div>
                            <Badge className={cn(
                              'text-xs font-medium border-0',
                              task.status === 'active'   && 'bg-green-100 text-green-700',
                              task.status === 'disabled' && 'bg-gray-100 text-gray-500',
                            )}>
                              {task.status === 'active' ? '运行中' : '已停用'}
                            </Badge>
                          </div>

                          <div className="flex items-center gap-2 mb-2">
                            <Bell className="w-3 h-3 text-gray-400" />
                            <span className="text-xs text-gray-600">下次: {task.nextRun}</span>
                          </div>

                          <div className="flex items-center justify-between text-xs text-gray-500">
                            <span>已执行 {task.runCount} 次</span>
                            <div className="flex items-center justify-end gap-1">
                              {task.status === 'active' && (
                                <>
                                  <Button
                                    variant="ghost" size="sm"
                                    className="h-7 px-2 text-xs text-blue-600 hover:bg-blue-50"
                                    onClick={(e) => { e.stopPropagation(); handleRunNow(task.id); }}
                                    title="立即执行"
                                  >
                                    <Play className="w-3 h-3 mr-1" />
                                    立即
                                  </Button>
                                  <Button
                                    variant="ghost" size="sm"
                                    className="h-7 w-7 p-0 text-gray-400 hover:text-red-600 hover:bg-red-50"
                                    onClick={(e) => { e.stopPropagation(); handleCancelJob(task.id); }}
                                    title="停用"
                                  >
                                    <Trash2 className="w-3 h-3" />
                                  </Button>
                                </>
                              )}
                            </div>
                          </div>
                        </div>
                      </HoverCardTrigger>

                      <HoverCardContent className="w-72 p-0" align="end" side="left">
                        <div className="p-3 border-b bg-gray-50">
                          <p className="text-sm font-semibold text-gray-900">{task.name}</p>
                          <p className="text-xs text-gray-500">定时任务详情</p>
                        </div>
                        <div className="p-3 space-y-3">
                          <div className="space-y-1">
                            <p className="text-xs text-gray-500">执行周期 (Cron)</p>
                            <code className="text-xs bg-gray-100 px-2 py-1 rounded">{task.cron}</code>
                            <p className="text-xs text-gray-600">{task.cronDescription}</p>
                          </div>
                          <div className="grid grid-cols-1 gap-2">
                            <div className="flex justify-between text-xs">
                              <span className="text-gray-500">总执行次数</span>
                              <span className="font-medium">{task.runCount}</span>
                            </div>
                            <div className="flex justify-between text-xs">
                              <span className="text-gray-500">上次执行</span>
                              <span className="text-gray-700">{task.lastRun}</span>
                            </div>
                            <div className="flex justify-between text-xs">
                              <span className="text-gray-500">下次执行</span>
                              <span className={task.status === 'active' ? 'text-green-700' : 'text-gray-500'}>
                                {task.nextRun}
                              </span>
                            </div>
                          </div>
                        </div>
                        <div className="p-3 border-t bg-gray-50 text-xs text-gray-500">
                          <p>创建于: {task.createdAt}</p>
                        </div>
                      </HoverCardContent>
                    </HoverCard>
                  ))}

                  {scheduledTasks.length === 0 && (
                    <div className="text-center py-8">
                      <Calendar className="w-10 h-10 text-gray-200 mx-auto mb-2" />
                      <p className="text-sm text-gray-400">暂无周期任务</p>
                    </div>
                  )}
                </div>
              </ScrollArea>
            </TabsContent>
          </Tabs>
        </CardContent>
      )}
    </Card>
  );
};

export default TaskQueue;
