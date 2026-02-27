import { motion } from 'framer-motion'
import { Sparkles, Code, ArrowLeftRight, Bug, ArrowRight } from 'lucide-react'
import { PROVIDERS, SUGGESTIONS } from '../utils/constants'

const iconMap = { Sparkles, Code, ArrowLeftRight, Bug }

const containerVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.15 } },
}

const itemVariants = {
  hidden: { opacity: 0, y: 15, scale: 0.97 },
  show: { opacity: 1, y: 0, scale: 1 },
}

export default function Welcome({ provider, onSuggestion }) {
  const p = PROVIDERS[provider]

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: '40px 20px',
    }}>
      {/* Icon with glow */}
      <motion.div
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 200, damping: 20, delay: 0.05 }}
        style={{
          width: 60, height: 60, borderRadius: 18,
          background: p.dimColor,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          marginBottom: 24, position: 'relative',
        }}
      >
        <div style={{
          position: 'absolute', inset: -2, borderRadius: 20,
          background: `linear-gradient(135deg, ${p.color}, transparent)`,
          opacity: 0.25, zIndex: 0,
        }} />
        <Sparkles size={28} style={{ color: p.color, position: 'relative', zIndex: 1 }} />
      </motion.div>

      {/* Animated gradient title */}
      <motion.h1
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        style={{
          fontSize: 32, fontWeight: 800, letterSpacing: -0.8,
          marginBottom: 10, textAlign: 'center',
          background: `linear-gradient(135deg, ${p.color}, ${lighten(p.color)}, ${p.color})`,
          backgroundSize: '200% 200%',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          animation: 'gradientShift 5s ease infinite',
        }}
      >
        {p.name}
      </motion.h1>

      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2 }}
        style={{
          fontSize: 15, color: 'var(--text-muted)',
          textAlign: 'center', maxWidth: 400, lineHeight: 1.6, marginBottom: 40,
        }}
      >
        {provider === 'google' && 'Search-powered AI responses with live web data'}
        {provider === 'gemini' && 'Advanced reasoning, analysis, and research'}
        {provider === 'chatgpt' && 'Versatile AI for code, writing, and analysis'}
      </motion.p>

      {/* Suggestion cards */}
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr',
          gap: 10, width: '100%', maxWidth: 540,
        }}
      >
        {SUGGESTIONS.map((s, i) => {
          const Icon = iconMap[s.icon] || Sparkles
          return (
            <motion.div
              key={i}
              variants={itemVariants}
              whileHover={{
                y: -2, borderColor: 'var(--border-hover)',
                backgroundColor: 'rgba(255,255,255,0.04)',
              }}
              whileTap={{ scale: 0.98 }}
              onClick={() => onSuggestion(s.text)}
              style={{
                padding: '15px 16px',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                background: 'rgba(255,255,255,0.015)',
                cursor: 'pointer', display: 'flex', alignItems: 'center',
                gap: 12, fontSize: 13, color: 'var(--text-secondary)',
                lineHeight: 1.4, transition: 'border-color 0.2s',
              }}
            >
              <div style={{
                width: 34, height: 34, borderRadius: 9,
                background: 'rgba(255,255,255,0.04)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0, color: 'var(--text-muted)',
              }}>
                <Icon size={16} />
              </div>
              <span style={{ flex: 1 }}>{s.text}</span>
              <ArrowRight size={14} style={{ opacity: 0, flexShrink: 0, color: 'var(--text-muted)' }} className="suggestion-arrow" />
            </motion.div>
          )
        })}
      </motion.div>

      <style>{`
        @keyframes gradientShift {
          0%, 100% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
        }
        .suggestion-arrow { transition: opacity 0.2s; }
        div:hover > .suggestion-arrow { opacity: 1 !important; }
      `}</style>
    </div>
  )
}

function lighten(hex) {
  const r = parseInt(hex.slice(1,3), 16)
  const g = parseInt(hex.slice(3,5), 16)
  const b = parseInt(hex.slice(5,7), 16)
  return `rgb(${Math.min(255, r + 60)}, ${Math.min(255, g + 60)}, ${Math.min(255, b + 60)})`
}
