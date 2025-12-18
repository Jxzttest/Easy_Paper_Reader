import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  UploadCloud, FileText, Sparkles, Search, Code, GitBranch, Clock, 
  ArrowRight, MoreHorizontal, Bot 
} from 'lucide-react';

const FeatureCard = ({ icon: Icon, title, desc, color }) => (
  <div className="group relative overflow-hidden bg-white p-6 rounded-2xl border border-slate-100 shadow-sm hover:shadow-xl transition-all duration-300 cursor-pointer">
    <div className={`absolute top-0 right-0 w-24 h-24 bg-${color}-50 rounded-bl-full -mr-4 -mt-4 transition-transform group-hover:scale-110`}></div>
    <div className={`w-12 h-12 rounded-xl bg-${color}-100 text-${color}-600 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}>
      <Icon size={24} />
    </div>
    <h3 className="font-bold text-slate-800 text-lg mb-2">{title}</h3>
    <p className="text-sm text-slate-500 leading-relaxed">{desc}</p>
    <div className="mt-4 flex items-center text-xs font-semibold text-slate-400 group-hover:text-blue-600 transition-colors">
      Try it now <ArrowRight size={14} className="ml-1" />
    </div>
  </div>
);