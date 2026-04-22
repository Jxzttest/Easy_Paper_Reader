import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import { 
  ArrowLeft, 
  Search, 
  Filter, 
  Info,
  BookOpen,
  Share2,
  Maximize2,
  Minimize2,
  RotateCcw
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { getCitationGraph } from '@/api';

const KnowledgeGraph = () => {
  const navigate = useNavigate();
  const chartRef = useRef(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [graphData, setGraphData] = useState({ papers: [], categories: [], links: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await getCitationGraph();
        setGraphData(data);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const filteredPapers = searchQuery
    ? graphData.papers.filter(p =>
        p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        p.authors.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : graphData.papers;

  const filteredIds = new Set(filteredPapers.map(p => p.id));

  const getOption = () => ({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        if (params.dataType === 'node') {
          return `
            <div style="padding: 8px;">
              <div style="font-weight: bold; margin-bottom: 4px;">${params.data.name}</div>
              <div style="font-size: 12px; color: #666;">作者: ${params.data.authors}</div>
              <div style="font-size: 12px; color: #666;">引用量: ${params.data.value}</div>
            </div>
          `;
        }
        return `${params.data.source} > ${params.data.target}`;
      },
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: '#e5e7eb',
      borderWidth: 1,
      textStyle: { color: '#1f2937' },
    },
    legend: {
      data: graphData.categories.map(c => c.name),
      bottom: 20,
      left: 'center',
      itemGap: 20,
      textStyle: { fontSize: 12, color: '#6b7280' },
    },
    series: [
      {
        type: 'graph',
        layout: 'force',
        data: graphData.papers.map(paper => ({
          ...paper,
          symbolSize: Math.sqrt(paper.value) * 3,
          itemStyle: searchQuery && !filteredIds.has(paper.id)
            ? { opacity: 0.15 }
            : {},
          label: {
            show: true,
            position: 'bottom',
            formatter: '{b}',
            fontSize: 11,
            color: '#4b5563',
          },
          emphasis: {
            focus: 'adjacency',
            label: { fontSize: 13, fontWeight: 'bold' },
            lineStyle: { width: 3 },
          },
        })),
        links: graphData.links,
        categories: graphData.categories,
        roam: true,
        draggable: true,
        force: {
          repulsion: 300,
          gravity: 0.1,
          edgeLength: [80, 150],
          layoutAnimation: true,
        },
        lineStyle: { color: 'source', curveness: 0.3, width: 2, opacity: 0.6 },
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 8],
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 4, opacity: 1 },
        },
      },
    ],
  });

  const handleChartClick = (params) => {
    if (params.dataType === 'node') {
      setSelectedNode(params.data);
    }
  };

  const handleReset = () => {
    if (chartRef.current) {
      chartRef.current.getEchartsInstance().dispatchAction({
        type: 'restore'
      });
    }
  };

  const getRelatedPapers = (nodeId) => {
    const related = [];
    graphData.links.forEach(link => {
      if (link.source === nodeId) {
        const target = graphData.papers.find(p => p.id === link.target);
        if (target) related.push({ ...target, relation: '引用' });
      }
      if (link.target === nodeId) {
        const source = graphData.papers.find(p => p.id === link.source);
        if (source) related.push({ ...source, relation: '被引用' });
      }
    });
    return related;
  };

  return (
    <div className={`flex flex-col bg-gray-50 ${isFullscreen ? 'fixed inset-0 z-50' : 'min-h-screen'}`}>
      {/* Header */}
      <header className="bg-white border-b border-gray-200 h-16 flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate('/')}>
            <ArrowLeft className="w-4 h-4 mr-1" />
            返回
          </Button>
          <Separator orientation="vertical" className="h-6" />
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gradient-to-br from-purple-500 to-pink-600 rounded-lg flex items-center justify-center">
              <Share2 className="w-4 h-4 text-white" />
            </div>
            <div>
              <h1 className="font-semibold text-gray-900">知识图谱</h1>
              <p className="text-xs text-gray-500">论文引用关系可视化</p>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          <div className="relative hidden md:block">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              placeholder="搜索论文..."
              className="pl-10 w-64"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          
          <Button variant="outline" size="icon" onClick={handleReset} title="重置视图">
            <RotateCcw className="w-4 h-4" />
          </Button>
          
          <Button 
            variant="outline" 
            size="icon" 
            onClick={() => setIsFullscreen(!isFullscreen)}
            title={isFullscreen ? '退出全屏' : '全屏'}
          >
            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden relative">
        <div className="flex-1 relative">
          <ReactECharts
            ref={chartRef}
            option={getOption()}
            style={{ width: '100%', height: '100%' }}
            onEvents={{
              click: handleChartClick
            }}
          />
          
          {/* Legend/Filter Overlay */}
          <div className="absolute top-4 left-4 bg-white/90 backdrop-blur-sm rounded-lg shadow-lg p-4 max-w-xs">
            <h3 className="font-semibold text-sm mb-3 flex items-center gap-2">
              <Filter className="w-4 h-4" />
              论文类别
            </h3>
            <div className="space-y-2">
              {graphData.categories.map((cat, idx) => (
                <div key={idx} className="flex items-center gap-2 text-xs">
                  <div 
                    className="w-3 h-3 rounded-full" 
                    style={{ backgroundColor: cat.itemStyle.color }}
                  />
                  <span className="text-gray-600">{cat.name}</span>
                </div>
              ))}
            </div>
          </div>
          
          {/* Instructions */}
          <div className="absolute bottom-4 right-4 bg-white/90 backdrop-blur-sm rounded-lg shadow-lg p-3 text-xs text-gray-500">
            <p>🖱️ 滚轮缩放 · 拖拽移动 · 点击节点查看详情</p>
          </div>
        </div>

        {/* Detail Panel */}
        <Sheet open={!!selectedNode} onOpenChange={() => setSelectedNode(null)}>
          <SheetContent className="w-96">
            <SheetHeader>
              <SheetTitle className="flex items-start gap-3">
                <div 
                  className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
                  style={{ 
                    backgroundColor: selectedNode ? 
                      graphData.categories[selectedNode.category]?.itemStyle.color + '20' : 
                      'transparent' 
                  }}
                >
                  <BookOpen className="w-5 h-5" style={{ 
                    color: selectedNode ? 
                      graphData.categories[selectedNode.category]?.itemStyle.color : 
                      '#6b7280' 
                  }} />
                </div>
                <div className="flex-1">
                  <div className="text-base leading-tight mb-1">{selectedNode?.name}</div>
                  <div className="text-xs text-gray-500 font-normal">{selectedNode?.authors}</div>
                </div>
              </SheetTitle>
            </SheetHeader>
            
            {selectedNode && (
              <div className="mt-6 space-y-6">
                <div className="grid grid-cols-2 gap-3">
                  <Card className="bg-gray-50 border-0">
                    <CardContent className="p-3 text-center">
                      <div className="text-2xl font-bold text-gray-900">{selectedNode.value}</div>
                      <div className="text-xs text-gray-500">引用次数</div>
                    </CardContent>
                  </Card>
                  <Card className="bg-gray-50 border-0">
                    <CardContent className="p-3 text-center">
                      <div className="text-2xl font-bold text-gray-900">
                        {getRelatedPapers(selectedNode.id).length}
                      </div>
                      <div className="text-xs text-gray-500">关联论文</div>
                    </CardContent>
                  </Card>
                </div>

                <div>
                  <h4 className="text-sm font-semibold mb-2">所属类别</h4>
                  <Badge 
                    variant="outline"
                    style={{ 
                      borderColor: graphData.categories[selectedNode.category]?.itemStyle.color,
                      color: graphData.categories[selectedNode.category]?.itemStyle.color,
                      backgroundColor: graphData.categories[selectedNode.category]?.itemStyle.color + '10'
                    }}
                  >
                    {graphData.categories[selectedNode.category]?.name}
                  </Badge>
                </div>

                <div>
                  <h4 className="text-sm font-semibold mb-3">关联论文</h4>
                  <ScrollArea className="h-64">
                    <div className="space-y-2">
                      {getRelatedPapers(selectedNode.id).map((paper) => (
                        <Card 
                          key={paper.id} 
                          className="cursor-pointer hover:bg-gray-50 transition-colors"
                          onClick={() => setSelectedNode(paper)}
                        >
                          <CardContent className="p-3">
                            <div className="flex items-start gap-3">
                              <div 
                                className="w-2 h-2 rounded-full mt-2 shrink-0"
                                style={{ backgroundColor: graphData.categories[paper.category]?.itemStyle.color }}
                              />
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium truncate">{paper.name}</p>
                                <div className="flex items-center gap-2 mt-1">
                                  <Badge variant="secondary" className="text-xs">
                                    {paper.relation}
                                  </Badge>
                                  <span className="text-xs text-gray-400">{paper.authors}</span>
                                </div>
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  </ScrollArea>
                </div>

                <div className="flex gap-2">
                  <Button className="flex-1" onClick={() => navigate(`/reader/${selectedNode.id}`)}>
                    <BookOpen className="w-4 h-4 mr-2" />
                    阅读论文
                  </Button>
                  <Button variant="outline" onClick={() => setSelectedNode(null)}>
                    关闭
                  </Button>
                </div>
              </div>
            )}
          </SheetContent>
        </Sheet>
      </div>
    </div>
  );
};

export default KnowledgeGraph;
