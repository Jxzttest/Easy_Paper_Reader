import React from 'react';
import { Network, X } from 'lucide-react';

export const CitationCard = ({ data, onClose }) => (
  <div className="absolute top-20 left-10 z-50 w-80 bg-white border border-slate-200 shadow-2xl rounded-xl p-4 animate-in fade-in zoom-in-95 duration-200">
    <div className="flex justify-between items-start mb-2">
      <div className="flex items-center gap-2">
         <div className="bg-blue-100 text-blue-600 p-1 rounded">
           <Network size={14} />
         </div>
         <span className="text-xs font-bold text-slate-500 uppercase">Citation Preview</span>
      </div>
      <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={14} /></button>
    </div>
    <h4 className="font-bold text-slate-800 text-sm mb-1 leading-tight hover:text-blue-600 cursor-pointer">{data.title}</h4>
    <p className="text-xs text-slate-500 mb-3">{data.authors}</p>
    <p className="text-xs text-slate-600 bg-slate-50 p-2 rounded leading-relaxed border border-slate-100">
      {data.abstract}
    </p>
    <div className="mt-3 flex gap-2">
      <button className="flex-1 bg-slate-900 text-white text-xs py-1.5 rounded hover:bg-slate-700 transition-colors">Read Full Paper</button>
      <button className="flex-1 bg-white border border-slate-300 text-slate-700 text-xs py-1.5 rounded hover:bg-slate-50">Add to Queue</button>
    </div>
  </div>
);