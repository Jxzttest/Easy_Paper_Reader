import { useState, useCallback, useRef } from 'react';
import {
  PdfHighlighter,
  PdfLoader,
  Highlight,
  Popup,
  AreaHighlight,
} from 'react-pdf-highlighter-extended';
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

// ── 主组件 ────────────────────────────────────────────────────────────────────
export default function PdfViewer({ url, onAskAI }) {
  const [highlights, setHighlights] = useState([]);
  const [translating, setTranslating] = useState(false);
  const [translationPopup, setTranslationPopup] = useState(null); // { text, position }
  const highlightIdRef = useRef(0);

  const nextId = () => `hl-${++highlightIdRef.current}`;

  // 添加高亮
  const addHighlight = useCallback((highlight, color = 'yellow') => {
    setHighlights(prev => [
      ...prev,
      {
        ...highlight,
        id: nextId(),
        color: COLORS[color] || COLORS.yellow,
      },
    ]);
  }, []);

  // 删除高亮
  const removeHighlight = useCallback((id) => {
    setHighlights(prev => prev.filter(h => h.id !== id));
  }, []);

  // 翻译选中文本
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

  // 构建选中文本的 SelectionTip（操作菜单）
  const selectionTip = useCallback(
    (highlight, hideTipAndSelection) => {
      const selectedText = highlight?.content?.text || '';
      return (
        <SelectionToolbar
          onTranslate={() => {
            handleTranslate(selectedText, highlight.position);
            hideTipAndSelection();
          }}
          onHighlight={(color) => {
            addHighlight(highlight, color);
            hideTipAndSelection();
          }}
          onAskAI={() => {
            onAskAI?.(selectedText);
            hideTipAndSelection();
          }}
        />
      );
    },
    [addHighlight, handleTranslate, onAskAI]
  );

  // 单个高亮的 Popup（点击高亮块后显示）
  const highlightPopup = useCallback(
    (highlight) => (
      <div className="flex gap-1 bg-white border border-gray-200 rounded-lg shadow-lg p-1">
        <Button
          size="sm"
          variant="ghost"
          className="text-xs h-7 px-2"
          onClick={() => handleTranslate(highlight.content?.text, highlight.position)}
        >
          <Languages className="w-3 h-3 mr-1" /> 翻译
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="text-xs h-7 px-2 text-red-500 hover:text-red-600"
          onClick={() => removeHighlight(highlight.id)}
        >
          <X className="w-3 h-3 mr-1" /> 删除
        </Button>
      </div>
    ),
    [handleTranslate, removeHighlight]
  );

  return (
    <div className="relative w-full h-full overflow-hidden bg-gray-100">
      <PdfLoader
        url={url}
        beforeLoad={
          <div className="w-full h-full flex items-center justify-center">
            <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
          </div>
        }
        errorMessage={
          <div className="w-full h-full flex items-center justify-center text-red-500 text-sm">
            PDF 加载失败，请检查文件是否存在
          </div>
        }
      >
        {(pdfDocument) => (
          <PdfHighlighter
            pdfDocument={pdfDocument}
            highlights={highlights}
            enableAreaSelection={(event) => event.altKey}
            selectionTip={selectionTip}
            onScrollChange={() => setTranslationPopup(null)}
            highlightTransform={(highlight, index, setTip, hideTip, viewportToScaled, screenshot, isScrolledTo) => {
              const isTextHighlight = highlight.content?.text !== undefined;
              const component = isTextHighlight ? (
                <Highlight
                  isScrolledTo={isScrolledTo}
                  position={highlight.position}
                  comment={{ text: '', emoji: '' }}
                  style={{ backgroundColor: highlight.color || COLORS.yellow }}
                />
              ) : (
                <AreaHighlight
                  isScrolledTo={isScrolledTo}
                  highlight={highlight}
                  onChange={(boundingRect) => {
                    setHighlights(prev =>
                      prev.map(h =>
                        h.id === highlight.id
                          ? { ...h, position: { ...h.position, boundingRect, rects: [boundingRect] } }
                          : h
                      )
                    );
                  }}
                />
              );
              return (
                <Popup
                  popupContent={highlightPopup(highlight)}
                  onMouseOver={(popupContent) => setTip(highlight, () => popupContent)}
                  onMouseOut={hideTip}
                  key={index}
                >
                  {component}
                </Popup>
              );
            }}
          />
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
