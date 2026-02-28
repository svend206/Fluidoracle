import { useState, useEffect, useRef, useCallback } from 'react'
import {
  inventAuth,
  setInventToken,
  clearInventToken,
  hasInventToken,
  getInventSessions,
  createInventSession,
  getInventSession,
  deleteInventSession,
  sendInventMessage,
} from '../api'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// ─── Password Gate ───────────────────────────────────────────────────────────

function PasswordGate({ onAuth }) {
  const [passphrase, setPassphrase] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await inventAuth(passphrase)
      setInventToken(passphrase)
      onAuth()
    } catch (err) {
      setError('Invalid passphrase')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="w-full max-w-sm">
        <div className="bg-gray-900 rounded-lg border border-gray-700 p-8">
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-blue-900/50 border border-blue-700 mb-3">
              <svg className="w-6 h-6 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-white">Invention Lab</h2>
            <p className="text-sm text-gray-400 mt-1">Private brainstorming sessions</p>
          </div>
          <form onSubmit={handleSubmit}>
            <input
              ref={inputRef}
              type="password"
              value={passphrase}
              onChange={(e) => setPassphrase(e.target.value)}
              placeholder="Enter passphrase"
              className="w-full px-4 py-2.5 bg-gray-800 border border-gray-600 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            {error && (
              <p className="mt-2 text-sm text-red-400">{error}</p>
            )}
            <button
              type="submit"
              disabled={loading || !passphrase}
              className="mt-4 w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-medium rounded-md transition-colors"
            >
              {loading ? 'Verifying...' : 'Enter'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}

// ─── Session Sidebar ─────────────────────────────────────────────────────────

function SessionSidebar({ sessions, activeId, onSelect, onNew, onDelete, onLogout }) {
  return (
    <div className="w-64 flex-shrink-0 bg-gray-900 border-r border-gray-700 flex flex-col h-full">
      {/* Header */}
      <div className="p-3 border-b border-gray-700">
        <button
          onClick={onNew}
          className="w-full py-2 px-3 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-md transition-colors flex items-center justify-center gap-2"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Session
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto">
        {sessions.length === 0 && (
          <p className="p-4 text-sm text-gray-500 text-center">No sessions yet</p>
        )}
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`group flex items-center gap-2 px-3 py-2.5 cursor-pointer border-b border-gray-800 transition-colors ${
              s.id === activeId
                ? 'bg-gray-800 text-white'
                : 'text-gray-400 hover:bg-gray-800/50 hover:text-gray-200'
            }`}
            onClick={() => onSelect(s.id)}
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{s.title}</p>
              <p className="text-xs text-gray-500 mt-0.5">
                {s.message_count} messages
              </p>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation()
                onDelete(s.id)
              }}
              className="opacity-0 group-hover:opacity-100 p-1 text-gray-500 hover:text-red-400 transition-all"
              title="Delete session"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        ))}
      </div>

      {/* Logout */}
      <div className="p-3 border-t border-gray-700">
        <button
          onClick={onLogout}
          className="w-full py-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
        >
          Lock &amp; Exit
        </button>
      </div>
    </div>
  )
}

// ─── Chat Message ────────────────────────────────────────────────────────────

function ChatMessage({ message }) {
  const [showSources, setShowSources] = useState(false)
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-3 ${
          isUser
            ? 'bg-blue-600 text-white'
            : 'bg-gray-800 border border-gray-700 text-gray-100'
        }`}
      >
        {/* Message content */}
        {isUser ? (
          <div className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</div>
        ) : (
          <div className="text-sm leading-relaxed prose prose-sm prose-invert max-w-none prose-headings:text-gray-100 prose-p:text-gray-200 prose-li:text-gray-200 prose-strong:text-white prose-table:text-xs prose-a:text-blue-400">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          </div>
        )}

        {/* Assistant metadata */}
        {!isUser && message.sources?.length > 0 && (
          <div className="mt-3 pt-2 border-t border-gray-700">
            <div className="flex items-center gap-2 flex-wrap">
              {message.sources?.length > 0 && (
                <button
                  onClick={() => setShowSources(!showSources)}
                  className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
                >
                  {showSources ? 'Hide' : 'Show'} {message.sources.length} source{message.sources.length !== 1 ? 's' : ''}
                </button>
              )}
            </div>
            {showSources && message.sources?.length > 0 && (
              <ul className="mt-2 space-y-1">
                {message.sources.map((src, i) => (
                  <li key={i} className="text-xs text-gray-400 truncate">
                    [{i + 1}] {src}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Chat Interface ──────────────────────────────────────────────────────────

function ChatInterface({ session, onMessageSent }) {
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [session?.messages, scrollToBottom])

  useEffect(() => {
    textareaRef.current?.focus()
  }, [session?.id])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!input.trim() || sending) return

    const content = input.trim()
    setInput('')
    setSending(true)

    try {
      await sendInventMessage(session.id, content)
      onMessageSent()
    } catch (err) {
      console.error('Failed to send message:', err)
      // Put the message back if it failed
      setInput(content)
    } finally {
      setSending(false)
    }
  }

  const handleKeyDown = (e) => {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  if (!session) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">
        <div className="text-center">
          <svg className="w-12 h-12 mx-auto mb-3 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          <p className="text-sm">Select a session or start a new one</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Session header */}
      <div className="px-4 py-3 border-b border-gray-200 bg-white">
        <h2 className="font-semibold text-gray-900 truncate">{session.title}</h2>
        <p className="text-xs text-gray-500 mt-0.5">
          {session.messages.length} messages
        </p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 bg-gray-50">
        {session.messages.length === 0 && !sending && (
          <div className="flex items-center justify-center h-full text-gray-400">
            <div className="text-center">
              <p className="text-sm">Start brainstorming. What are you working on?</p>
              <p className="text-xs mt-1 text-gray-400">
                Full knowledge base access. Multi-turn conversation. Private.
              </p>
            </div>
          </div>
        )}
        {session.messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        {sending && (
          <div className="flex justify-start mb-4">
            <div className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-3">
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Searching knowledge base and thinking...
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-gray-200 bg-white">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your message... (Enter to send, Shift+Enter for newline)"
            rows={2}
            disabled={sending}
            className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:text-gray-500"
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="self-end px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-300 disabled:cursor-not-allowed text-white text-sm font-medium rounded-md transition-colors"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  )
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function InventPage() {
  const [authenticated, setAuthenticated] = useState(hasInventToken())
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [activeSession, setActiveSession] = useState(null)
  const [loading, setLoading] = useState(false)

  // Load sessions on auth
  const loadSessions = useCallback(async () => {
    try {
      const data = await getInventSessions()
      setSessions(data.sessions)
    } catch (err) {
      console.error('Failed to load sessions:', err)
      if (err.message?.includes('401') || err.message?.includes('Invalid')) {
        clearInventToken()
        setAuthenticated(false)
      }
    }
  }, [])

  // Load a specific session
  const loadSession = useCallback(async (id) => {
    if (!id) {
      setActiveSession(null)
      return
    }
    setLoading(true)
    try {
      const data = await getInventSession(id)
      setActiveSession(data)
    } catch (err) {
      console.error('Failed to load session:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (authenticated) {
      loadSessions()
    }
  }, [authenticated, loadSessions])

  useEffect(() => {
    if (activeSessionId) {
      loadSession(activeSessionId)
    } else {
      setActiveSession(null)
    }
  }, [activeSessionId, loadSession])

  const handleAuth = () => {
    setAuthenticated(true)
  }

  const handleNewSession = async () => {
    try {
      const session = await createInventSession()
      setSessions((prev) => [session, ...prev])
      setActiveSessionId(session.id)
    } catch (err) {
      console.error('Failed to create session:', err)
    }
  }

  const handleDeleteSession = async (id) => {
    if (!confirm('Delete this session and all its messages?')) return
    try {
      await deleteInventSession(id)
      setSessions((prev) => prev.filter((s) => s.id !== id))
      if (activeSessionId === id) {
        setActiveSessionId(null)
      }
    } catch (err) {
      console.error('Failed to delete session:', err)
    }
  }

  const handleMessageSent = async () => {
    // Reload the active session to get the new messages
    if (activeSessionId) {
      await loadSession(activeSessionId)
    }
    // Refresh session list (title may have auto-updated)
    await loadSessions()
  }

  const handleLogout = () => {
    clearInventToken()
    setAuthenticated(false)
    setSessions([])
    setActiveSessionId(null)
    setActiveSession(null)
  }

  if (!authenticated) {
    return <PasswordGate onAuth={handleAuth} />
  }

  return (
    <div className="flex h-[calc(100vh-7.5rem)] -mx-4 sm:-mx-6 -my-6 overflow-hidden">
      <SessionSidebar
        sessions={sessions}
        activeId={activeSessionId}
        onSelect={setActiveSessionId}
        onNew={handleNewSession}
        onDelete={handleDeleteSession}
        onLogout={handleLogout}
      />
      <ChatInterface
        session={activeSession}
        onMessageSent={handleMessageSent}
      />
      {loading && !activeSession && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-50/80">
          <div className="text-sm text-gray-500">Loading session...</div>
        </div>
      )}
    </div>
  )
}
