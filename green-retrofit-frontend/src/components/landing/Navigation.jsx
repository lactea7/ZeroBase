import React from 'react';
import { motion } from 'framer-motion';
import { Hexagon } from 'lucide-react';

export default function Navigation({ onStart }) {
  return (
    <motion.nav 
      initial={{ y: -100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-8 py-6 bg-white/70 backdrop-blur-md border-b border-slate-100"
    >
      <div className="flex items-center gap-2">
        <div className="w-10 h-10 bg-gradient-to-br from-brand-primary to-brand-secondary rounded-xl flex items-center justify-center p-0.5 shadow-lg shadow-brand-primary/20">
          <div className="w-full h-full bg-white rounded-lg flex items-center justify-center">
            <Hexagon className="w-6 h-6 text-brand-primary fill-brand-primary/10" />
          </div>
        </div>
        <span className="font-display font-bold text-xl tracking-tight text-slate-900">ZeroBase</span>
      </div>
      
      <div className="flex items-center gap-8">
        {['가이드', 'LCC 분석', '문의'].map((item) => (
          <a key={item} href={`#${item}`} className="text-sm font-semibold text-slate-500 hover:text-brand-primary transition-colors">
            {item}
          </a>
        ))}
        <button 
          onClick={onStart}
          className="px-5 py-2.5 bg-slate-900 text-white rounded-full text-sm font-bold hover:bg-brand-primary transition-all shadow-lg shadow-slate-200"
        >
          시작하기
        </button>
      </div>
    </motion.nav>
  );
}
