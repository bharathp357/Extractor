import { memo, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Copy, Check } from 'lucide-react'
import MarkdownRenderer from './MarkdownRenderer'
import { PROVIDERS } from '../utils/constants'
import { useState } from 'react'

const msgVariants = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, transition: { duration: 0.15 } },
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }, [text])

  return (
    <motion.button
      whileHover={{ scale: 1.03, borderColor: 'var(--border-default)' }}
      whileTap={{ scale: 0.95 }}
      onClick={handleCopy}
      style={{
        display: 'flex', alignItems: 'center', gap: 5,
        padding: '4px 10px', borderRadius: 6,
        border: '1px solid var(--border-subtle)',
        background: 'transparent',
        color: copied ? 'var(--success)' : 'var(--text-muted)',
        fontSize: 11, fontWeight: 500,
        transition: 'color 0.2s',
      }}
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
      {copied ? 'Copied' : 'Copy'}
    </motion.button>
  )
}

function LoadingDots() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '16px 0' }}
    >
      <div style={{ display: 'flex', gap: 4 }}>
        {[0, 1, 2].map(i => (
          <motion.span
            key={i}
            animate={{ y: [0, -8, 0] }}
            transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.15, ease: 'easeInOut' }}
            style={{
              width: 7, height: 7, borderRadius: '50%',
              background: 'var(--text-muted)',
            }}
          />
        ))}
      </div>
      <span style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 500 }}>
        Thinking...
      </span>
    </motion.div>
  )
}

const Message = memo(function Message({ msg, provider }) {
  if (msg.type === 'loading') return <LoadingDots />

  const p = PROVIDERS[provider]

  return (
    <motion.div
      variants={msgVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      layout
      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
    >
      {msg.type === 'user' && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <div style={{
              width: 26, height: 26, borderRadius: 7,
              background: 'var(--bg-active)', color: 'var(--text-secondary)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, fontWeight: 700,
            }}>Y</div>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>You</span>
          </div>
          <div style={{
            padding: '14px 18px', background: 'var(--bg-card)',
            border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)',
            fontSize: 15, lineHeight: 1.65, whiteSpace: 'pre-wrap', wordWrap: 'break-word',
          }}>
            {msg.text}
          </div>
          <div style={{ display: 'flex', gap: 4, marginTop: 8 }}>
            <CopyButton text={msg.text} />
          </div>
        </div>
      )}

      {msg.type === 'ai' && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <div style={{
              width: 26, height: 26, borderRadius: 7,
              background: p.dimColor, color: p.color,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, fontWeight: 700,
            }}>{p.initials}</div>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>{p.short}</span>
            {msg.timing && (
              <span style={{ fontSize: 11, color: 'var(--text-faint)', marginLeft: 'auto' }}>
                {msg.timing}ms
              </span>
            )}
          </div>
          <div className="markdown-body" style={{ fontSize: 15, lineHeight: 1.75 }}>
            <MarkdownRenderer content={msg.text} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
            {msg.timing && (
              <span style={{
                display: 'inline-flex', padding: '2px 9px',
                borderRadius: 'var(--radius-full)',
                background: 'rgba(255,255,255,0.04)',
                fontSize: 11, color: 'var(--text-faint)',
              }}>
                {msg.timing}ms
              </span>
            )}
            <CopyButton text={msg.text} />
          </div>
        </div>
      )}

      {msg.type === 'error' && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--error)' }}>Error</span>
          </div>
          <div style={{
            color: 'var(--error)', fontSize: 13, padding: '12px 16px',
            background: 'rgba(239,68,68,0.06)',
            border: '1px solid rgba(239,68,68,0.15)',
            borderRadius: 'var(--radius-sm)', lineHeight: 1.5,
            whiteSpace: 'pre-wrap', wordWrap: 'break-word',
          }}>
            {msg.text}
          </div>
        </div>
      )}
    </motion.div>
  )
})

export default Message
