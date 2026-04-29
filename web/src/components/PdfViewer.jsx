import { useState, useCallback, useRef } from 'react';
import { GlobalWorkerOptions } from 'pdfjs-dist';
import {
  PdfHighlighter,
  PdfLoader,
  TextHighlight,
  AreaHighlight,
  MonitoredHighlightContainer,
  useHighlightContainerContext,
} from 'react-pdf-highlighter-extended';

// 强制使用本地 worker，避免 CDN 版本与本地 pdfjs-dist 版本不一致
const WORKER_SRC = '/pdf.worker.min.mjs';
GlobalWorkerOptions.workerSrc = WORKER_SRC;
import { Loader2, Languages, Highlighter, MessageSquare, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { translateText } from '@/api';

// ── 高亮颜色常量 ──────────────────────────────────────────────────────────────
const COLORS = {
  yellow: '#FEF08A',
  green: '#BBF7D0',
  blue: '#BFDBFE',
};

// ── 选中文本弹出的操作菜单 ────────────────────────────────────────────────────
function SelectionToolbar({ onTranslate, onHighlight, onAskAI }) {
  return (
    <div className="flex gap-1 bg-white border border-gray-200 rounded-lg shadow-lg p-1">
      <Button
        size="sm"
        variant="ghost"
        className="flex items-center gap-1 text-xs h-7 px-2"
        onClick={onTranslate}
      >
        <Languages className="w-3 h-3" />
        翻译
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="flex items-center gap-1 text-xs h-7 px-2"
        onClick={() => onHighlight('yellow')}
      >
        <Highlighter className="w-3 h-3 text-yellow-500" />
        高亮
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="flex items-center gap-1 text-xs h-7 px-2"
        onClick={onAskAI}
      >
        <MessageSquare className="w-3 h-3 text-blue-500" />
        问 AI
      </Button>
    </div>
  );
}

// ── 翻译结果浮层 ──────────────────────────────────────────────────────────────
function TranslationPopup({ text, onClose }) {
  return (
    <div className="bg-white border border-blue-200 rounded-lg shadow-xl p-3 max-w-sm">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-blue-600 flex items-center gap-1">
          <Languages className="w-3 h-3" /> 翻译结果
        </span>
        <Button size="icon" variant="ghost" className="w-5 h-5" onClick={onClose}>
          <X className="w-3 h-3" />
        </Button>
      </div>
      <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">{text}</p>
    </div>
  );
}

// ── 单个高亮容器（v8 通过 context 获取 highlight 信息）────────────────────────
function HighlightContainer({ onTranslate, onRemove, onUpdatePosition }) {
  const { highlight, isScrolledTo, highlightBindings, viewportToScaled } =
    useHighlightContainerContext();

  const isText = highlight.type === 'text';

  const highlightTip = {
    position: highlight.position,
    content: (
      <div className="flex gap-1 bg-white border border-gray-200 rounded-lg shadow-lg p-1">
        <Button
          size="sm"
          variant="ghost"
          className="text-xs h-7 px-2"
          onClick={() => onTranslate(highlight.text, highlight.position)}
        >
          <Languages className="w-3 h-3 mr-1" /> 翻译
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="text-xs h-7 px-2 text-red-500 hover:text-red-600"
          onClick={() => onRemove(highlight.id)}
        >
          <X className="w-3 h-3 mr-1" /> 删除
        </Button>
      </div>
    ),
  };

  return (
    <MonitoredHighlightContainer highlightTip={highlightTip}>
      {isText ? (
        <TextHighlight
          highlight={highlight}
          isScrolledTo={isScrolledTo}
          style={{ backgroundColor: highlight.color || COLORS.yellow }}
        />
      ) : (
        <AreaHighlight
          highlight={highlight}
          isScrolledTo={isScrolledTo}
          onChange={(boundingRect) => {
            onUpdatePosition(highlight.id, {
              boundingRect: viewportToScaled(boundingRect),
              rects: [viewportToScaled(boundingRect)],
            });
          }}
          bounds={highlightBindings.textLayer.parentElement}
        />
      )}
    </MonitoredHighlightContainer>
  );
}

// ── 主组件 ────────────────────────────────────────────────────────────────────
export default function PdfViewer({ url, onAskAI }) {
  const [highlights, setHighlights] = useState([]);
  const [translating, setTranslating] = useState(false);
  const [translationPopup, setTranslationPopup] = useState(null);
  const highlightIdRef = useRef(0);

  const nextId = () => `hl-${++highlightIdRef.current}`;

  const addHighlight = useCallback((ghostHighlight, color = 'yellow') => {
    setHighlights((prev) => [
      ...prev,
      {
        ...ghostHighlight,
        id: nextId(),
        color: COLORS[color] || COLORS.yellow,
        type: ghostHighlight.type,
        // 保留文字供翻译使用（避免直接依赖已废弃的 content 字段）
        text: ghostHighlight.content?.text ?? '',
      },
    ]);
  }, []);

  const removeHighlight = useCallback((id) => {
    setHighlights((prev) => prev.filter((h) => h.id !== id));
  }, []);

  const updateHighlightPosition = useCallback((id, position) => {
    setHighlights((prev) =>
      prev.map((h) => (h.id === id ? { ...h, position: { ...h.position, ...position } } : h))
    );
  }, []);

  const handleTranslate = useCallback(async (selectedText, position) => {
    if (!selectedText?.trim()) return;
    setTranslating(true);
    setTranslationPopup({ text: '翻译中...', position });
    try {
      const result = await translateText(selectedText);
      setTranslationPopup({ text: result, position });
    } catch {
      setTranslationPopup({ text: '翻译失败，请重试', position });
    } finally {
      setTranslating(false);
    }
  }, []);

  // selectionTip: 选中文本后显示的操作菜单（v8 直接传 ReactNode，通过 onSelection 回调处理）
  const buildSelectionTip = useCallback(
    (selection, hideTipAndSelection) => (
      <SelectionToolbar
        onTranslate={() => {
          handleTranslate(selection.content?.text, selection.position);
          hideTipAndSelection();
        }}
        onHighlight={(color) => {
          addHighlight(selection.makeGhostHighlight(), color);
          hideTipAndSelection();
        }}
        onAskAI={() => {
          onAskAI?.(selection.content?.text);
          hideTipAndSelection();
        }}
      />
    ),
    [addHighlight, handleTranslate, onAskAI]
  );

  if (!url) {
    return (
      <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">
        暂无 PDF
      </div>
    );
  }

  return (
    <div className="relative w-full h-full overflow-hidden bg-gray-100">
      <PdfLoader
        document={url}
        workerSrc={WORKER_SRC}
        beforeLoad={
          <div className="w-full h-full flex items-center justify-center">
            <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
          </div>
        }
        errorMessage={(error) => (
          <div className="w-full h-full flex items-center justify-center text-red-500 text-sm">
            PDF 加载失败：{error?.message || '请检查文件是否存在'}
          </div>
        )}
      >
        {(pdfDocument) => (
          <PdfHighlighter
            pdfDocument={pdfDocument}
            highlights={highlights}
            enableAreaSelection={(event) => event.altKey}
            onScrollAway={() => setTranslationPopup(null)}
            onSelection={buildSelectionTip}
          >
            <HighlightContainer
              onTranslate={handleTranslate}
              onRemove={removeHighlight}
              onUpdatePosition={updateHighlightPosition}
            />
          </PdfHighlighter>
        )}
      </PdfLoader>

      {/* 翻译结果浮层 */}
      {translationPopup && (
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-50">
          <TranslationPopup
            text={translating ? '翻译中...' : translationPopup.text}
            onClose={() => setTranslationPopup(null)}
          />
        </div>
      )}
    </div>
  );
}
