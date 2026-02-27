import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import Welcome from './Welcome'
import Message from './Message'
import InputBar from './InputBar'

export default function ChatPanel({ provider, active, messages, sending, onSend }) {
  const scrollRef = useRef(null)
  const [showWelcome, setShowWelcome] = useState(true)

  useEffect(() => {
    setShowWelcome(messages.length === 0)
  }, [messages.length])

  // Auto-scroll
  useEffect(() => {
    if (scrollRef.current) {
      requestAnimationFrame(() => {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight
      })
    }
  }, [messages])

  const handleSend = useCallback((prompt) => {
    onSend(provider, prompt)
  }, [provider, onSend])

  const handleSuggestion = useCallback((text) => {
    onSend(provider, text)
  }, [provider, onSend])

  return (
    <div style={{
      flex: 1, display: active ? 'flex' : 'none',
      flexDirection: 'column', overflow: 'hidden',
    }}>
      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', scrollBehavior: 'smooth' }}>
        <div style={{
          maxWidth: 'var(--chat-max-w)', margin: '0 auto',
          padding: '24px 32px', minHeight: '100%',
          display: 'flex', flexDirection: 'column',
        }}>
          <AnimatePresence>
            {showWelcome && (
              <motion.div
                key="welcome"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20, transition: { duration: 0.2 } }}
                style={{ flex: 1 }}
              >
                <Welcome provider={provider} onSuggestion={handleSuggestion} />
              </motion.div>
            )}
          </AnimatePresence>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <AnimatePresence initial={false}>
              {messages.map(msg => (
                <Message key={msg.id} msg={msg} provider={provider} />
              ))}
            </AnimatePresence>
          </div>
        </div>
      </div>
      <InputBar provider={provider} disabled={sending} onSend={handleSend} />
    </div>
  )
}
