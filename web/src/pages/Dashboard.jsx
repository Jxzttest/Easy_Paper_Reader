import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, Search, Code, GitBranch, Clock } from 'lucide-react';

// 引入拆分出去的组件
import { FeatureCard } from '../components/features/dashboard/FeatureCard';
import { PaperItem } from '../components/features/dashboard/PaperItem';

export default function Dashboard() {
  const [isDragging, setIsDragging] = useState(false);
  const navigate = useNavigate();

  const handlePaperClick = (id) => {
    navigate(`/read/${id}`);
  };

  const recentPapers = [
    { id: 1, title: "Deep Residual Learning for Image Recognition", date: "2 hours ago", status: "ready", tags: ["CV", "ResNet"] },
    { id: 2, title: "Attention Is All You Need", date: "Yesterday", status: "ready", tags: ["NLP", "Transformer"] },
    { id: 3, title: "A Survey on Large Language Models", date: "3 days ago", status: "processing", tags: ["LLM", "Survey"] },
  ];

  return (
      <div className="min-h-screen bg-slate-50 font-sans text-slate-900">
        <nav className="bg-white border-b border-slate-200 px-8 py-4 sticky top-0 z-50 flex justify-between items-center shadow-sm">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold">S</div>
            <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-indigo-600">
              ScholarAgent
            </span>
          </div>
          <div className="flex items-center gap-4">
            <div className="relative">
              <Search size={16} className="absolute left-3 top-2.5 text-slate-400" />
              <input 
                type="text" 
                placeholder="Search Semantic Scholar..." 
                className="pl-9 pr-4 py-2 bg-slate-100 rounded-full text-sm w-64 focus:w-80 transition-all focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
            </div>
            <div className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-purple-500 rounded-full cursor-pointer"></div>
          </div>
        </nav>
  
        <main className="max-w-6xl mx-auto px-8 py-12">
          <section className="mb-12">
            <h1 className="text-3xl font-bold text-slate-900 mb-2">Welcome back, Researcher.</h1>
            <p className="text-slate-500 mb-8">Ready to accelerate your discovery? Choose a workflow or upload a new paper.</p>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <FeatureCard 
                icon={GitBranch} 
                title="Innovation Mining" 
                desc="Upload multiple papers. I'll construct a knowledge graph and pinpoint exactly how your idea differs from SOTA."
                color="blue"
              />
              <FeatureCard 
                icon={Code} 
                title="Algo to Code" 
                desc="Highlight pseudocode in any paper, and I will generate executable Python/PyTorch implementations instantly."
                color="emerald"
              />
              <FeatureCard 
                icon={Clock} 
                title="Time Travel Search" 
                desc="Use vector retrieval to find papers from specific eras that laid the foundation for your current topic."
                color="purple"
              />
            </div>
          </section>
  
          <section className="mb-12">
            <div 
              className={`
                relative border-2 border-dashed rounded-2xl p-12 text-center transition-all duration-300 ease-in-out cursor-pointer
                ${isDragging ? 'border-blue-500 bg-blue-50/50 scale-[1.01]' : 'border-slate-300 bg-white hover:border-slate-400'}
              `}
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(e) => { e.preventDefault(); setIsDragging(false); alert('Backend integration needed for file upload'); }}
            >
              <div className="w-16 h-16 bg-blue-50 text-blue-600 rounded-full flex items-center justify-center mx-auto mb-4">
                <UploadCloud size={32} />
              </div>
              <h2 className="text-xl font-semibold text-slate-800 mb-2">Drop your PDF here</h2>
              <p className="text-slate-500 max-w-md mx-auto mb-6">
                Support PDF, ArXiv links. Once uploaded, the Agent will automatically start 
                <span className="text-blue-600 font-medium"> analyzing innovation points</span> and 
                <span className="text-blue-600 font-medium"> pre-translating</span>.
              </p>
              <button className="px-6 py-2.5 bg-slate-900 text-white rounded-lg font-medium hover:bg-slate-800 transition-shadow shadow-lg shadow-blue-500/20">
                Select Files
              </button>
            </div>
          </section>
  
          <section>
            <div className="flex justify-between items-end mb-6">
              <h2 className="text-xl font-bold text-slate-800">Recent Workspace</h2>
              <button className="text-sm text-blue-600 font-medium hover:underline">View all library</button>
            </div>
            <div className="space-y-4">
              {recentPapers.map((paper) => (
                <PaperItem key={paper.id} {...paper} onClick={() => handlePaperClick(paper.id)} />
              ))}
            </div>
          </section>
        </main>
      </div>
    );
}