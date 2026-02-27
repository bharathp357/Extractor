import { useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, FileText } from 'lucide-react'
import MarkdownRenderer from './MarkdownRenderer'

const overlayVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1 },
}

const panelVariants = {
  hidden: { opacity: 0, scale: 0.95, y: 20 },
  visible: {
    opacity: 1, scale: 1, y: 0,
    transition: { type: 'spring', stiffness: 300, damping: 30 },
  },
  exit: { opacity: 0, scale: 0.95, y: 20, transition: { duration: 0.15 } },
}

export default function Modal({ title, content, onClose }) {
  // Escape key
  const handleKey = useCallback((e) => {
    if (e.key === 'Escape') onClose()
  }, [onClose])

  useEffect(() => {
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [handleKey])

  return (
        <motion.div
          variants={overlayVariants}
          initial="hidden"
          animate="visible"
          exit="hidden"
          onClick={onClose}
          style={{
            position: 'fixed', inset: 0, zIndex: 1000,
            background: 'rgba(0,0,0,0.6)',
            backdropFilter: 'blur(6px)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: 24,
          }}
        >
          <motion.div
            variants={panelVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            onClick={(e) => e.stopPropagation()}
            style={{
              width: '100%', maxWidth: 700, maxHeight: '80vh',
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-lg)',
              display: 'flex', flexDirection: 'column',
              overflow: 'hidden',
            }}
          >
            {/* Header */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '16px 20px',
              borderBottom: '1px solid var(--border-subtle)',
            }}>
              <FileText size={18} style={{ color: 'var(--text-muted)' }} />
              <span style={{ flex: 1, fontWeight: 600, fontSize: 14 }}>
                {title || 'Conversation History'}
              </span>
              <motion.button
                whileHover={{ scale: 1.1, background: 'var(--bg-active)' }}
                whileTap={{ scale: 0.9 }}
                onClick={onClose}
                style={{
                  width: 30, height: 30, borderRadius: 8,
                  border: 'none', background: 'transparent',
                  color: 'var(--text-muted)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer',
                }}
              >
                <X size={18} />
              </motion.button>
            </div>

            {/* Body */}
            <div style={{
              flex: 1, overflowY: 'auto', padding: '20px 24px',
            }}>
              {content ? (
                <div className="markdown-body" style={{ fontSize: 14, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                  {content}
                </div>
              ) : (
                <div style={{
                  textAlign: 'center', padding: '40px 0',
                  color: 'var(--text-faint)', fontSize: 14,
                }}>
                  No content available
                </div>
              )}
            </div>
          </motion.div>
        </motion.div>
  )
}
