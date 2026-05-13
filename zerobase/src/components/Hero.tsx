import { motion } from 'motion/react';
import { Zap, ArrowRight, ChevronDown } from 'lucide-react';

export default function Hero() {
  return (
    <section className="relative min-h-[110vh] flex flex-col items-center justify-center pt-24 overflow-hidden px-6 bg-white">
      {/* Liquid-style background orbs */}
      <motion.div 
        animate={{ 
          x: [0, 50, -30, 0],
          y: [0, -40, 60, 0],
          scale: [1, 1.2, 0.9, 1]
        }}
        transition={{ duration: 15, repeat: Infinity, ease: "easeInOut" }}
        className="absolute top-1/4 left-1/3 w-[600px] h-[600px] bg-brand-primary/10 blur-[130px] rounded-full mix-blend-multiply" 
      />
      <motion.div 
        animate={{ 
          x: [0, -60, 40, 0],
          y: [0, 50, -30, 0],
          scale: [1, 0.8, 1.1, 1]
        }}
        transition={{ duration: 18, repeat: Infinity, ease: "easeInOut", delay: 1 }}
        className="absolute bottom-1/4 right-1/3 w-[700px] h-[700px] bg-brand-secondary/10 blur-[150px] rounded-full mix-blend-multiply" 
      />

      {/* Main Prism Stage */}
      <div className="relative w-full max-w-6xl aspect-[16/10] flex items-center justify-center mb-12">
        <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-[0.04] pointer-events-none z-20" />
        
        {/* The Glass Container with Reeded Effect */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1.2 }}
          className="relative w-full h-full flex items-center justify-center"
        >
          {/* Reeded Layers */}
          <div className="absolute inset-0 reeded-glass rounded-[4rem] border border-white/50 shadow-[0_40px_100px_rgba(0,0,0,0.03)] overflow-hidden">
             {/* Dynamic Light Sweep */}
             <motion.div
               animate={{ x: ['-100%', '200%'] }}
               transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
               className="absolute inset-0 w-1/2 bg-gradient-to-r from-transparent via-white/10 to-transparent skew-x-12"
             />
          </div>

          {/* Floating Glass Cube / Prism Core */}
          <motion.div
            initial={{ scale: 0, opacity: 0 }}
            animate={{ 
              scale: 1, 
              opacity: 1,
              rotateX: [-10, 10],
              rotateY: [-15, 15],
              y: [-15, 15]
            }}
            transition={{ 
              scale: { duration: 2, ease: [0.16, 1, 0.3, 1] },
              opacity: { duration: 1.5 },
              rotateX: { duration: 8, repeat: Infinity, ease: "easeInOut", repeatType: "mirror" },
              rotateY: { duration: 8, repeat: Infinity, ease: "easeInOut", repeatType: "mirror" },
              y: { duration: 8, repeat: Infinity, ease: "easeInOut", repeatType: "mirror" }
            }}
            className="relative z-10 w-64 h-64 md:w-80 md:h-80 transform-gpu preserve-3d"
          >
            {/* Front Shadow/Glow */}
            <div className="absolute inset-0 bg-white/20 backdrop-blur-3xl rounded-[3rem] border border-white/60 shadow-[0_0_80px_rgba(255,255,204,0.15)] flex items-center justify-center">
               <div className="text-center">
                  <div className="w-16 h-16 bg-gradient-to-br from-brand-primary to-brand-secondary rounded-2xl mx-auto mb-4 flex items-center justify-center shadow-lg transform rotate-45">
                    <Zap className="w-8 h-8 text-white -rotate-45" />
                  </div>
                  <h2 className="font-display font-black text-4xl tracking-tighter text-slate-900">
                    ZERO<span className="text-brand-primary italic inline-block pr-1">BASE</span>
                  </h2>
               </div>
            </div>
          </motion.div>
        </motion.div>
      </div>

      {/* Main Content */}
      <div className="relative z-30 text-center max-w-4xl mt-12 pb-20">
        <motion.div
           initial={{ opacity: 0, y: 20 }}
           animate={{ opacity: 1, y: 0 }}
           transition={{ delay: 0.5 }}
           className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-slate-50 border border-slate-100 text-[10px] font-bold uppercase tracking-widest text-brand-primary mb-8 shadow-sm"
        >
          <Zap className="w-3 h-3 fill-brand-primary" />
          The Future of Building Energy Intelligence
        </motion.div>
        
        <motion.h1 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
          className="text-5xl md:text-8xl font-display font-black mb-8 leading-[1.0] text-slate-900 tracking-tighter break-keep"
        >
          건물 에너지 시뮬레이션 <br />
          <span className="text-gradient font-black italic inline-block pr-4 pb-2">zerobase</span>
        </motion.h1>
        
        <motion.p 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.7 }}
          className="text-xl text-slate-400 mb-12 max-w-xl mx-auto leading-tight font-medium break-keep"
        >
          BIM 데이터로 손쉽게 에너지 분석 가능한 플랫폼입니다. <br />
          정확성 높은 데이터로 리모델링의 미래를 설계하세요!
        </motion.p>
        
        {/* Button removed as requested */}
      </div>
    </section>
  );
}
