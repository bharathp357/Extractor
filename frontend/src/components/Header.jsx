import { useRef, useEffect, useLayoutEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Menu, Trash2, RefreshCw } from 'lucide-react'
import { PROVIDERS, PROVIDER_KEYS } from '../utils/constants'

export default function Header({ active, onSwitch, onToggleSidebar, onClear, onReconnect }) {
  const sliderRef = useRef(null)
  const pillsRef = useRef({})

  const updateSlider = useCallback(() => {
    const el = pillsRef.current[active]
    const slider = sliderRef.current
    if (!el || !slider) return
    slider.style.left = el.offsetLeft + 'px'
    slider.style.width = el.offsetWidth + 'px'
  }, [active])

  useLayoutEffect(() => { updateSlider() }, [updateSlider])
  useEffect(() => { window.addEventListener('resize', updateSlider); return () => window.removeEventListener('resize', updateSlider) }, [updateSlider])

  return (
    <header style={{
      height: 'var(--header-h)', flexShrink: 0,
      display: 'flex', alignItems: 'center', padding: '0 16px',
      borderBottom: '1px solid var(--border-subtle)',
      background: 'var(--bg-surface)', gap: 12,
    }}>
      {/* Left: menu toggle */}
      <motion.button
        whileHover={{ scale: 1.05, backgroundColor: 'var(--bg-hover)' }}
        whileTap={{ scale: 0.95 }}
        onClick={onToggleSidebar}
        style={{
          width: 38, height: 38, borderRadius: 'var(--radius-sm)',
          border: 'none', background: 'transparent', color: 'var(--text-secondary)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        <Menu size={18} />
      </motion.button>

      {/* Center: pill selector */}
      <div style={{ flex: 1, display: 'flex', justifyContent: 'center' }}>
        <div style={{
          display: 'flex', alignItems: 'center', position: 'relative',
          background: 'rgba(255,255,255,0.035)', borderRadius: 'var(--radius-md)',
          padding: 3, border: '1px solid var(--border-subtle)',
        }}>
          {/* Sliding indicator */}
          <div
            ref={sliderRef}
            style={{
              position: 'absolute', top: 3, height: 'calc(100% - 6px)',
              borderRadius: 10, background: 'rgba(255,255,255,0.08)',
              border: '1px solid var(--border-subtle)',
              transition: 'all 0.3s cubic-bezier(0.16,1,0.3,1)',
            }}
          />
          {PROVIDER_KEYS.map(p => (
            <motion.button
              key={p}
              ref={el => { pillsRef.current[p] = el }}
              whileHover={{ color: 'var(--text-secondary)' }}
              whileTap={{ scale: 0.96 }}
              onClick={() => onSwitch(p)}
              style={{
                position: 'relative', zIndex: 1,
                padding: '7px 22px', border: 'none', background: 'none',
                color: active === p ? 'var(--text-primary)' : 'var(--text-muted)',
                fontSize: 13, fontWeight: 500, borderRadius: 10,
                transition: 'color 0.2s', whiteSpace: 'nowrap',
              }}
            >
              {PROVIDERS[p].short}
            </motion.button>
          ))}
        </div>
      </div>

      {/* Right: actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <HeaderBtn icon={<Trash2 size={14} />} label="Clear" onClick={onClear} />
        <HeaderBtn icon={<RefreshCw size={14} />} label="Reconnect" onClick={onReconnect} />
      </div>
    </header>
  )
}

function HeaderBtn({ icon, label, onClick }) {
  return (
    <motion.button
      whileHover={{ scale: 1.02, borderColor: 'var(--border-hover)', backgroundColor: 'var(--bg-hover)' }}
      whileTap={{ scale: 0.97 }}
      onClick={onClick}
      style={{
        padding: '6px 14px', borderRadius: 'var(--radius-sm)',
        border: '1px solid var(--border-subtle)', background: 'transparent',
        color: 'var(--text-muted)', fontSize: 12, fontWeight: 500,
        display: 'flex', alignItems: 'center', gap: 6,
        transition: 'color 0.15s',
      }}
    >
      <span style={{ opacity: 0.7, display: 'flex' }}>{icon}</span>
      <span>{label}</span>
    </motion.button>
  )
}
