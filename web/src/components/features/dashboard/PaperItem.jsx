import React from 'react';
import { FileText, Sparkles, Bot, MoreHorizontal } from 'lucide-react';

export const PaperItem = ({ id, title, date, status, tags, onClick }) => (
  <div onClick={onClick} className="flex items-center justify-between p-4 bg-white border border-slate-100 rounded-xl hover:border-blue-200 hover:shadow-md transition-all cursor-pointer group">
    <div className="flex items-center gap-4">
      <div className="w-10 h-10 rounded-lg bg-red-50 text-red-500 flex items-center justify-center">
        <FileText size={20} />
      </div>
      <div>
        <h4 className="font-semibold text-slate-800 group-hover:text-blue-600 transition-colors">{title}</h4>
        <div className="flex items-center gap-2 mt-1">
          <span className="text-xs text-slate-400">{date}</span>
          {tags.map(tag => (
            <span key={tag} className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-500 rounded-full">{tag}</span>
          ))}
        </div>
      </div>
    </div>
    
    <div className="flex items-center gap-6">
      <div className="flex flex-col items-end">
        {status === 'ready' && (
          <span className="flex items-center gap-1 text-xs font-medium text-emerald-600 bg-emerald-50 px-2 py-1 rounded-full">
            <Sparkles size={10} /> 翻译 & 分析完成
          </span>
        )}
        {status === 'processing' && (
          <span className="flex items-center gap-1 text-xs font-medium text-amber-600 bg-amber-50 px-2 py-1 rounded-full animate-pulse">
            <Bot size={10} /> 正在生成创新点...
          </span>
        )}
      </div>
      <button className="text-slate-300 hover:text-slate-600">
        <MoreHorizontal size={20} />
      </button>
    </div>
  </div>
);