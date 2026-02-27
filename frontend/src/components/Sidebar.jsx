import { motion, AnimatePresence } from 'framer-motion'
import { Plus, Sparkles, MessageSquare, Trash2 } from 'lucide-react'
import { PROVIDERS, PROVIDER_KEYS } from '../utils/constants'

const sidebarVariants = {
  open: { width: 280, transition: { type: 'spring', stiffness: 300, damping: 30 } },
  closed: { width: 0, transition: { type: 'spring', stiffness: 300, damping: 30 } },
}

function StatusDot({ status }) {
  const connected = status?.connected
  const needsLogin = status?.requires_login && !status?.logged_in
  const bg = connected ? (needsLogin ? 'var(--warning)' : 'var(--success)') : 'var(--text-faint)'
  const shadow = connected
    ? needsLogin
      ? '0 0 8px rgba(234,179,8,0.4)'
      : '0 0 8px rgba(34,197,94,0.5)'
    : 'none'

  return (
    <motion.span
      style={{
        width: 7, height: 7, borderRadius: '50%',
        background: bg, boxShadow: shadow, flexShrink: 0,
      }}
      animate={connected && !needsLogin ? {
        boxShadow: ['0 0 0 0 rgba(34,197,94,0.4)', '0 0 0 6px rgba(34,197,94,0)', '0 0 0 0 rgba(34,197,94,0.4)']
      } : {}}
      transition={{ duration: 2.5, repeat: Infinity }}
    />
  )
}

export default function Sidebar({ open, active, statuses, history, onSwitch, onNewChat, onViewHistory, onDeleteHistory }) {
  return (
    <motion.aside
      initial={false}
      animate={open ? 'open' : 'closed'}
      variants={sidebarVariants}
      style={{
        flexShrink: 0,
        background: 'var(--bg-surface)',
        borderRight: '1px solid var(--border-subtle)',
        overflow: 'hidden',
        position: 'relative',
        zIndex: 20,
      }}
    >
      {/* Gradient accent line */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: 2, zIndex: 1,
        background: 'linear-gradient(90deg, var(--google), var(--gemini), var(--chatgpt))',
      }} />

      <div style={{ width: 280, height: '100%', display: 'flex', flexDirection: 'column', paddingTop: 2 }}>
        {/* Brand */}
        <div style={{ padding: '20px 20px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
          <div style={{
            fontSize: 15, fontWeight: 700, letterSpacing: -0.3,
            background: 'linear-gradient(135deg, #fafafa, #71717a)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          }}>
            AI Command Center
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>
            Multi-provider interface
          </div>
        </div>

        {/* New Chat */}
        <motion.button
          whileHover={{ scale: 1.01, borderColor: 'rgba(255,255,255,0.15)' }}
          whileTap={{ scale: 0.98 }}
          onClick={onNewChat}
          style={{
            margin: '12px 12px 4px', padding: '10px 14px',
            borderRadius: 'var(--radius-sm)',
            border: '1px dashed var(--border-default)',
            background: 'transparent', color: 'var(--text-secondary)',
            fontSize: 13, fontWeight: 500,
            display: 'flex', alignItems: 'center', gap: 8,
            width: 'calc(100% - 24px)',
          }}
        >
          <Plus size={14} style={{ opacity: 0.6 }} />
          New Chat
        </motion.button>

        {/* Providers */}
        <div style={{ padding: '16px 20px 6px', fontSize: 10, fontWeight: 600, color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: 1 }}>
          Providers
        </div>
        <div style={{ padding: '4px 8px' }}>
          {PROVIDER_KEYS.map(p => {
            const isActive = p === active
            return (
              <motion.div
                key={p}
                whileHover={{ backgroundColor: 'var(--bg-hover)' }}
                whileTap={{ scale: 0.98 }}
                onClick={() => onSwitch(p)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '10px 12px', borderRadius: 'var(--radius-sm)',
                  fontSize: 13, fontWeight: 500, cursor: 'pointer',
                  color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                  background: isActive ? 'rgba(255,255,255,0.04)' : 'transparent',
                  borderLeft: isActive ? `2px solid ${PROVIDERS[p].color}` : '2px solid transparent',
                  transition: 'color 0.15s, border-color 0.15s',
                }}
              >
                <StatusDot status={statuses[p]} />
                <span>{PROVIDERS[p].name}</span>
                <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-faint)' }}>
                  {statuses[p]?.connected
                    ? statuses[p]?.requires_login && !statuses[p]?.logged_in
                      ? 'Login'
                      : 'Ready'
                    : ''}
                </span>
              </motion.div>
            )
          })}
        </div>

        <div style={{ height: 1, background: 'var(--border-subtle)', margin: '8px 16px' }} />

        {/* History */}
        <div style={{ padding: '8px 20px 6px', fontSize: 10, fontWeight: 600, color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: 1 }}>
          History
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 12px' }}>
          {!history.length ? (
            <div style={{ padding: 20, fontSize: 12, color: 'var(--text-faint)', textAlign: 'center' }}>
              No conversations yet
            </div>
          ) : (
            <AnimatePresence>
              {history.map(h => (
                <motion.div
                  key={h.filename}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -10 }}
                  whileHover={{ backgroundColor: 'var(--bg-hover)' }}
                  onClick={() => onViewHistory(h.filename)}
                  style={{
                    padding: '8px 12px', borderRadius: 'var(--radius-sm)',
                    cursor: 'pointer', position: 'relative', marginBottom: 1,
                  }}
                >
                  <div style={{
                    fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap',
                    overflow: 'hidden', textOverflow: 'ellipsis', paddingRight: 22, lineHeight: 1.4,
                  }}>
                    {h.filename.replace('.txt', '').replace(/_/g, ' ')}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', marginTop: 1 }}>
                    {h.modified}
                  </div>
                  <motion.button
                    whileHover={{ scale: 1.15, color: 'var(--error)' }}
                    onClick={e => { e.stopPropagation(); onDeleteHistory(h.filename) }}
                    style={{
                      position: 'absolute', right: 8, top: 8,
                      background: 'none', border: 'none', color: 'var(--text-faint)',
                      fontSize: 12, padding: '2px 4px', borderRadius: 4,
                    }}
                  >
                    <Trash2 size={12} />
                  </motion.button>
                </motion.div>
              ))}
            </AnimatePresence>
          )}
        </div>
      </div>
    </motion.aside>
  )
}
