import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, AlertCircle, X } from 'lucide-react'

const toastVariants = {
  initial: { opacity: 0, y: -20, x: 20, scale: 0.95 },
  animate: { opacity: 1, y: 0, x: 0, scale: 1, transition: { type: 'spring', stiffness: 400, damping: 25 } },
  exit: { opacity: 0, x: 50, scale: 0.9, transition: { duration: 0.2 } },
}

export default function ToastContainer({ toasts, onDismiss }) {
  return (
    <div style={{
      position: 'fixed', top: 16, right: 16,
      zIndex: 2000, display: 'flex', flexDirection: 'column',
      gap: 8, pointerEvents: 'none',
    }}>
      <AnimatePresence>
        {toasts.map(toast => (
          <motion.div
            key={toast.id}
            variants={toastVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            layout
            style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '10px 14px',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--bg-card)',
              border: `1px solid ${toast.type === 'error' ? 'rgba(239,68,68,0.3)' : 'rgba(34,197,94,0.3)'}`,
              boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
              pointerEvents: 'auto',
              maxWidth: 340,
            }}
          >
            {toast.type === 'error'
              ? <AlertCircle size={16} style={{ color: 'var(--error)', flexShrink: 0 }} />
              : <CheckCircle size={16} style={{ color: 'var(--success)', flexShrink: 0 }} />
            }
            <span style={{
              fontSize: 13, color: 'var(--text-secondary)',
              lineHeight: 1.4, flex: 1,
            }}>
              {toast.msg}
            </span>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
