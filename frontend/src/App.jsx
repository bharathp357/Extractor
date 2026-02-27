import { useState, useCallback, useRef, useEffect } from 'react'
import { AnimatePresence } from 'framer-motion'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import ChatPanel from './components/ChatPanel'
import Modal from './components/Modal'
import ToastContainer from './components/ToastContainer'
import { apiSend, apiNewConversation, apiReconnect, apiStatus, apiWarmup, apiHistory, apiReadHistory, apiDeleteHistory } from './utils/api'
import { PROVIDERS, PROVIDER_KEYS } from './utils/constants'

export default function App() {
  const [active, setActive] = useState('google')
  const [sidebarOpen, setSidebarOpen] = useState(() => localStorage.getItem('sidebarOpen') !== 'false')
  const [statuses, setStatuses] = useState({})
  const [history, setHistory] = useState([])
  const [messages, setMessages] = useState({ google: [], gemini: [], chatgpt: [] })
  const [sending, setSending] = useState({ google: false, gemini: false, chatgpt: false })
  const [modal, setModal] = useState(null)
  const [toasts, setToasts] = useState([])
  const msgCountRef = useRef({ google: 0, gemini: 0, chatgpt: 0 })
  const toastIdRef = useRef(0)

  // ── Toast ──
  const toast = useCallback((msg, type = '') => {
    const id = ++toastIdRef.current
    setToasts(prev => [...prev, { id, msg, type }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3500)
  }, [])

  // ── Warmup ──
  useEffect(() => {
    let cancelled = false
    async function poll() {
      try {
        const data = await apiWarmup()
        if (cancelled) return
        if (data.state === 'loading') {
          toast('Warming up providers...', '')
          setTimeout(poll, 1000)
        } else if (data.state === 'ready') {
          toast(`All providers ready — ${data.timings?.total_ms || '?'}ms`, 'success')
          pollStatus()
        } else if (data.state === 'error') {
          toast('Warmup failed', 'error')
          pollStatus()
        } else {
          setTimeout(poll, 500)
        }
      } catch { setTimeout(poll, 500) }
    }
    poll()
    return () => { cancelled = true }
  }, [])

  // ── Status polling ──
  const pollStatus = useCallback(async () => {
    try {
      const data = await apiStatus()
      setStatuses(data)
    } catch {}
  }, [])

  useEffect(() => {
    const iv = setInterval(pollStatus, 15000)
    return () => clearInterval(iv)
  }, [pollStatus])

  // ── History ──
  const loadHistory = useCallback(async () => {
    try {
      const data = await apiHistory()
      setHistory(Array.isArray(data) ? data : [])
    } catch { setHistory([]) }
  }, [])

  useEffect(() => { loadHistory() }, [loadHistory])

  // ── Send ──
  const handleSend = useCallback(async (provider, prompt) => {
    if (!prompt.trim() || sending[provider]) return
    setSending(prev => ({ ...prev, [provider]: true }))

    // Add user message
    const userMsg = { id: Date.now(), type: 'user', text: prompt.trim() }
    setMessages(prev => ({ ...prev, [provider]: [...prev[provider], userMsg] }))

    // Add loading placeholder
    const loadId = Date.now() + 1
    setMessages(prev => ({
      ...prev,
      [provider]: [...prev[provider], { id: loadId, type: 'loading' }]
    }))

    try {
      const isFollowup = provider !== 'google' && msgCountRef.current[provider] > 0
      const data = await apiSend(prompt.trim(), provider, isFollowup)

      // Remove loading
      setMessages(prev => ({
        ...prev,
        [provider]: prev[provider].filter(m => m.id !== loadId)
      }))

      if (data.success) {
        const aiMsg = {
          id: Date.now() + 2,
          type: 'ai',
          text: data.response,
          timing: data.timing?.total_ms || null,
          provider,
        }
        setMessages(prev => ({ ...prev, [provider]: [...prev[provider], aiMsg] }))
        msgCountRef.current[provider]++
      } else {
        const errMsg = {
          id: Date.now() + 2,
          type: 'error',
          text: data.response || data.error || 'Failed to get response',
        }
        setMessages(prev => ({ ...prev, [provider]: [...prev[provider], errMsg] }))
      }
    } catch (err) {
      setMessages(prev => ({
        ...prev,
        [provider]: prev[provider].filter(m => m.id !== loadId)
      }))
      const errMsg = { id: Date.now() + 3, type: 'error', text: 'Connection error: ' + err.message }
      setMessages(prev => ({ ...prev, [provider]: [...prev[provider], errMsg] }))
    }

    setSending(prev => ({ ...prev, [provider]: false }))
    if (provider === 'google') loadHistory()
  }, [sending, loadHistory])

  // ── Actions ──
  const handleNewChat = useCallback(async () => {
    try {
      await apiNewConversation(active)
      msgCountRef.current[active] = 0
      setMessages(prev => ({ ...prev, [active]: [] }))
      toast(`New ${PROVIDERS[active].short} conversation`, 'success')
    } catch { toast('Failed to start new chat', 'error') }
  }, [active, toast])

  const handleClear = useCallback(() => {
    setMessages(prev => ({ ...prev, [active]: [] }))
  }, [active])

  const handleReconnect = useCallback(async () => {
    toast(`Reconnecting ${PROVIDERS[active].short}...`, '')
    try {
      await apiReconnect(active)
      pollStatus()
      toast(`${PROVIDERS[active].short} reconnected`, 'success')
    } catch { toast('Reconnect failed', 'error') }
  }, [active, toast, pollStatus])

  const handleViewHistory = useCallback(async (filename) => {
    try {
      const data = await apiReadHistory(filename)
      setModal({
        title: filename.replace(/_/g, ' ').replace('.txt', ''),
        content: data.content,
      })
    } catch { toast('Failed to load', 'error') }
  }, [toast])

  const handleDeleteHistory = useCallback(async (filename) => {
    try {
      await apiDeleteHistory(filename)
      loadHistory()
    } catch { toast('Failed to delete', 'error') }
  }, [loadHistory, toast])

  const toggleSidebar = useCallback(() => {
    setSidebarOpen(prev => {
      localStorage.setItem('sidebarOpen', !prev)
      return !prev
    })
  }, [])

  return (
    <div style={{ display: 'flex', height: '100%', width: '100%' }}>
      <Sidebar
        open={sidebarOpen}
        active={active}
        statuses={statuses}
        history={history}
        onSwitch={setActive}
        onNewChat={handleNewChat}
        onViewHistory={handleViewHistory}
        onDeleteHistory={handleDeleteHistory}
      />
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
        <Header
          active={active}
          onSwitch={setActive}
          onToggleSidebar={toggleSidebar}
          onClear={handleClear}
          onReconnect={handleReconnect}
        />
        {PROVIDER_KEYS.map(p => (
          <ChatPanel
            key={p}
            provider={p}
            active={p === active}
            messages={messages[p]}
            sending={sending[p]}
            onSend={handleSend}
          />
        ))}
      </main>

      <AnimatePresence>
        {modal && <Modal title={modal.title} content={modal.content} onClose={() => setModal(null)} />}
      </AnimatePresence>

      <ToastContainer toasts={toasts} />
    </div>
  )
}
