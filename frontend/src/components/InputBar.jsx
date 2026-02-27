import { useState, useRef, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Send, Loader2 } from 'lucide-react'
import { PROVIDERS } from '../utils/constants'

export default function InputBar({ provider, disabled, onSend }) {
  const [text, setText] = useState('')
  const ref = useRef(null)
  const p = PROVIDERS[provider]

  // Auto-resize textarea
  useEffect(() => {
    if (ref.current) {
      ref.current.style.height = 'auto'
      ref.current.style.height = Math.min(ref.current.scrollHeight, 200) + 'px'
    }
  }, [text])

  // Focus on provider change
  useEffect(() => {
    ref.current?.focus()
  }, [provider])

  const handleSubmit = useCallback(() => {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
    if (ref.current) ref.current.style.height = 'auto'
  }, [text, disabled, onSend])

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }, [handleSubmit])

  return (
    <div style={{
      borderTop: '1px solid var(--border-subtle)',
      background: 'linear-gradient(to top, var(--bg-primary), transparent)',
      padding: '16px 0 24px',
    }}>
      <div style={{
        maxWidth: 'var(--chat-max-w)', margin: '0 auto',
        padding: '0 32px',
      }}>
        <motion.div
          initial={false}
          animate={{
            boxShadow: disabled
              ? `0 0 0 1px var(--border-subtle)`
              : `0 0 0 1px var(--border-subtle), 0 2px 12px ${p.dimColor}`,
          }}
          style={{
            position: 'relative',
            display: 'flex', alignItems: 'flex-end',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-lg)',
            background: 'var(--bg-card)',
            transition: 'border-color 0.2s',
          }}
          whileHover={!disabled ? { borderColor: 'var(--border-hover)' } : {}}
        >
          <textarea
            ref={ref}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder={`Ask ${p.short} anything...`}
            rows={1}
            style={{
              flex: 1, padding: '14px 16px',
              background: 'transparent', border: 'none', outline: 'none',
              color: 'var(--text-primary)',
              fontSize: 15, lineHeight: 1.5,
              fontFamily: "'Inter', sans-serif",
              resize: 'none', overflowY: 'auto',
              maxHeight: 200,
            }}
          />

          <motion.button
            onClick={handleSubmit}
            disabled={!text.trim() || disabled}
            whileHover={text.trim() && !disabled ? { scale: 1.05, y: -1 } : {}}
            whileTap={text.trim() && !disabled ? { scale: 0.92 } : {}}
            style={{
              width: 38, height: 38,
              margin: '0 8px 8px 0',
              borderRadius: 10,
              border: 'none',
              background: text.trim() && !disabled ? p.color : 'var(--bg-active)',
              color: text.trim() && !disabled ? '#fff' : 'var(--text-faint)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: text.trim() && !disabled ? 'pointer' : 'default',
              transition: 'background 0.2s, color 0.2s',
              flexShrink: 0,
            }}
          >
            {disabled ? (
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
              >
                <Loader2 size={18} />
              </motion.div>
            ) : (
              <Send size={18} style={{ transform: 'translateX(1px)' }} />
            )}
          </motion.button>
        </motion.div>

        <p style={{
          textAlign: 'center', fontSize: 11,
          color: 'var(--text-faint)', marginTop: 10,
          letterSpacing: 0.3,
        }}>
          AI Command Center · Press Enter to send, Shift+Enter for new line
        </p>
      </div>
    </div>
  )
}
