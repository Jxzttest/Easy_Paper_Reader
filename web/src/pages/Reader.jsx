import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, MessageSquare, Languages, Share2, Download, ChevronRight, Play, CheckCircle2, X } from 'lucide-react';

// 引入拆分出去的组件
import { CitationCard } from '../components/features/reader/CitationCard';
import { CodeBlock } from '../components/features/agent/CodeBlock';

// Mock数据...
const MOCK_CONTENT = [
  {
    id: 1,
    en: "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder.",
    cn: "主流的序列转导模型基于复杂的循环神经网络或卷积神经网络，这些网络包含一个编码器和一个解码器。",
    citation: null
  },
  {
    id: 2,
    en: "The best performing models also connect the encoder and decoder through an attention mechanism.",
    cn: "表现最好的模型还通过注意力机制连接编码器和解码器。",
    citation: null
  },
  {
    id: 3,
    en: "We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely [1].",
    cn: "我们提出了一种新的简单网络架构——Transformer，它完全基于注意力机制，彻底摒弃了循环和卷积 [1]。",
    citation: {
      id: "ref-1",
      title: "Neural Machine Translation by Jointly Learning to Align and Translate",
      authors: "Bahdanau et al., 2014",
      abstract: "This paper introduces the attention mechanism in RNNs, allowing the model to search for parts of a source sentence that are relevant to predicting a target word."
    }
  }
];

export default function Reader() {
  const navigate = useNavigate();
  const { id } = useParams();
  const [activeTab, setActiveTab] = useState('translation');
  const [activeCitation, setActiveCitation] = useState(null);
  
  return (
    <div className="h-screen flex flex-col bg-slate-50 overflow-hidden font-sans">
      <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-between px-4 shrink-0 z-20">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate('/dashboard')} className="p-2 hover:bg-slate-100 rounded-lg text-slate-600 transition-colors">
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="text-sm font-bold text-slate-800 truncate max-w-md">Attention Is All You Need (Paper ID: {id})</h1>
            <p className="text-xs text-slate-400 flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-green-500"></span> Online • Semantic Scholar Connected
            </p>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <div className="flex bg-slate-100 p-1 rounded-lg mr-4">
            <button 
              onClick={() => setActiveTab('translation')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${activeTab === 'translation' ? 'bg-white shadow text-blue-600' : 'text-slate-500 hover:text-slate-700'}`}
            >
              <Languages size={14} /> Translation
            </button>
            <button 
              onClick={() => setActiveTab('chat')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${activeTab === 'chat' ? 'bg-white shadow text-purple-600' : 'text-slate-500 hover:text-slate-700'}`}
            >
              <MessageSquare size={14} /> Copilot
            </button>
          </div>
          <button className="p-2 text-slate-400 hover:text-slate-600"><Share2 size={18} /></button>
          <button className="p-2 text-slate-400 hover:text-slate-600"><Download size={18} /></button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden relative">
        {showGuide && (
          <div className="absolute top-4 right-[420px] z-50 bg-blue-600 text-white p-4 rounded-xl shadow-xl max-w-xs animate-bounce-in">
            <div className="flex justify-between items-start mb-2">
              <h3 className="font-bold text-sm flex items-center gap-2"><Languages size={16}/> Translation Mode</h3>
              <button onClick={() => setShowGuide(false)}><X size={14} className="opacity-70 hover:opacity-100"/></button>
            </div>
            <p className="text-xs opacity-90 leading-relaxed mb-3">
              Sentences are aligned automatically. Hover over any text to see its translation. 
              Click citations like <span className="underline decoration-dashed">[1]</span> to read related papers instantly.
            </p>
            <button onClick={() => setShowGuide(false)} className="bg-white text-blue-600 px-3 py-1 rounded text-xs font-bold w-full">Got it</button>
          </div>
        )}

        <div className="flex-1 bg-slate-200 overflow-y-auto p-8 flex justify-center relative">
          {activeCitation && <CitationCard data={activeCitation} onClose={() => setActiveCitation(null)} />}
          
          <div className="w-[800px] bg-white shadow-lg min-h-[1200px] p-16 select-text">
            <h2 className="text-3xl font-bold mb-2">Attention Is All You Need</h2>
            <div className="text-sm text-slate-500 mb-12">Ashish Vaswani, Noam Shazeer, Niki Parmar...</div>
            
            <h3 className="text-lg font-bold mb-4 uppercase text-slate-700">1. Introduction</h3>
            <div className="space-y-4 text-justify leading-relaxed font-serif text-lg text-slate-800">
              {MOCK_CONTENT.map((sentence) => (
                <span 
                  key={sentence.id}
                  className={`
                    cursor-pointer transition-colors duration-200 rounded px-0.5
                    ${hoveredSentence === sentence.id ? 'bg-blue-100 text-blue-900' : 'hover:bg-slate-50'}
                  `}
                  onMouseEnter={() => setHoveredSentence(sentence.id)}
                  onMouseLeave={() => setHoveredSentence(null)}
                >
                  {sentence.en}
                  {sentence.citation && (
                    <span 
                      onClick={(e) => { e.stopPropagation(); handleCitationClick(sentence.citation); }}
                      className="text-blue-600 font-bold mx-1 cursor-pointer hover:underline decoration-blue-400 underline-offset-2"
                    >
                      [1]
                    </span>
                  )}
                  {" "}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="w-[400px] bg-white border-l border-slate-200 flex flex-col shadow-xl z-10">
          {activeTab === 'translation' && (
            <div className="flex-1 overflow-y-auto">
              <div className="p-4 border-b bg-slate-50">
                <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider">Sync Translation</h3>
              </div>
              <div className="divide-y divide-slate-100">
                {MOCK_CONTENT.map((item) => (
                  <div 
                    key={item.id} 
                    className={`p-4 transition-all duration-300 ${hoveredSentence === item.id ? 'bg-blue-50 border-l-4 border-blue-500' : 'hover:bg-slate-50 border-l-4 border-transparent'}`}
                    onMouseEnter={() => setHoveredSentence(item.id)}
                  >
                    <p className="text-xs text-slate-400 mb-2 font-mono">Sentence #{item.id}</p>
                    <p className="text-sm text-slate-600 leading-relaxed mb-2 font-serif bg-slate-100/50 p-2 rounded">{item.en}</p>
                    <p className="text-sm text-slate-900 leading-relaxed font-medium">{item.cn}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'chat' && (
            <div className="flex-1 flex flex-col">
              <div className="flex-1 overflow-y-auto p-4 space-y-6">
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded bg-gradient-to-br from-indigo-500 to-purple-600 flex-shrink-0 flex items-center justify-center text-white text-xs font-bold">AI</div>
                  <div className="space-y-2 max-w-[90%]">
                    <div className="bg-purple-50 p-4 rounded-2xl rounded-tl-none border border-purple-100 text-sm text-slate-800">
                      <p className="font-bold text-purple-800 mb-2 flex items-center gap-2">
                        <CheckCircle2 size={14}/> 
                        Innovation Analysis
                      </p>
                      <p className="mb-2">Compared to your uploaded papers (ResNet, RNNs), this paper's core contribution is:</p>
                      <ul className="list-disc list-inside space-y-1 text-slate-700">
                        <li>Parallelization of computation (unlike RNNs).</li>
                        <li>Constant path length between any two positions (O(1)).</li>
                      </ul>
                    </div>
                  </div>
                </div>
                <div className="flex gap-3 flex-row-reverse">
                  <div className="w-8 h-8 rounded bg-slate-200 flex-shrink-0 flex items-center justify-center">U</div>
                  <div className="bg-slate-800 text-white p-3 rounded-2xl rounded-tr-none text-sm shadow-md">
                     Can you implement the "Scaled Dot-Product Attention" mentioned in Eq(1)?
                  </div>
                </div>
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded bg-gradient-to-br from-indigo-500 to-purple-600 flex-shrink-0 flex items-center justify-center text-white text-xs font-bold">AI</div>
                  <div className="space-y-2 w-full">
                    <p className="text-xs text-slate-500 ml-1">Thinking Process: Retrieving Pytorch docs...</p>
                    <CodeBlock />
                    <div className="flex gap-2">
                       <button className="text-xs border px-2 py-1 rounded bg-white hover:bg-slate-50 flex items-center gap-1">
                          <Play size={10} /> Run in Sandbox
                       </button>
                    </div>
                  </div>
                </div>
              </div>

              <div className="p-4 border-t bg-white">
                <div className="relative">
                  <input 
                    type="text" 
                    placeholder="Ask about this paper..."
                    className="w-full pl-4 pr-10 py-3 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent text-sm bg-slate-50"
                  />
                  <button className="absolute right-2 top-2 p-1.5 bg-purple-600 text-white rounded-lg hover:bg-purple-700">
                    <ChevronRight size={16} />
                  </button>
                </div>
                <div className="flex gap-2 mt-2 overflow-x-auto pb-1">
                   {['Summarize Intro', 'Compare with BERT', 'Explain Math'].map(q => (
                     <button key={q} className="text-[10px] bg-slate-100 px-2 py-1 rounded-full text-slate-500 whitespace-nowrap hover:bg-slate-200 transition-colors">
                        {q}
                     </button>
                   ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}