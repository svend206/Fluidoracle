import { useState, useEffect, useRef, useCallback } from 'react'
import {
  getConsultSessions,
  createConsultSession,
  getConsultSession,
  deleteConsultSession,
  sendConsultMessageStream,
  submitConsultFeedback,
  getConsultOutcomes,
  submitConsultOutcome,
  updateConsultOutcome,
  authSendCode,
  authVerifyCode,
  authLogout,
  authMe,
  authClaimSessions,
  isAuthenticated,
  setAuthToken,
  clearAuthToken,
} from '../api'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'


// ─── Phase Indicator ────────────────────────────────────────────────────────

function PhaseIndicator({ phase }) {
  if (phase === 'gathering') {
    return (
      <div className="flex items-center gap-1.5 text-xs text-amber-600 bg-amber-50 border border-amber-200 px-2.5 py-1 rounded-full">
        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        Understanding your application
      </div>
    )
  }
  if (phase === 'answering') {
    return (
      <div className="flex items-center gap-1.5 text-xs text-green-700 bg-green-50 border border-green-200 px-2.5 py-1 rounded-full">
        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        Recommendation provided
      </div>
    )
  }
  return null
}


// ─── Session Sidebar ────────────────────────────────────────────────────────

function SessionSidebar({ sessions, activeId, onSelect, onNew, onDelete, user, onSignOut, onAuthenticated }) {
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
          New Consultation
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto">
        {sessions.length === 0 && (
          <p className="p-4 text-sm text-gray-500 text-center">
            {user ? 'No consultations yet' : 'Start a consultation below'}
          </p>
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
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-xs text-gray-500">
                  {s.message_count} msg{s.message_count !== 1 ? 's' : ''}
                </span>
                {s.phase === 'gathering' && (
                  <span className="text-xs text-amber-500">diagnosing</span>
                )}
                {s.phase === 'answering' && (
                  <span className="text-xs text-green-500">answered</span>
                )}
              </div>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation()
                onDelete(s.id)
              }}
              className="opacity-0 group-hover:opacity-100 p-1 text-gray-500 hover:text-red-400 transition-all"
              title="Delete consultation"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        ))}
      </div>

      {/* Auth section at bottom */}
      <div className="border-t border-gray-700 p-3">
        {user ? (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <svg className="w-4 h-4 text-green-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
              <span className="text-xs text-gray-300 truncate">{user.email}</span>
            </div>
            <button
              onClick={onSignOut}
              className="text-xs text-gray-500 hover:text-gray-300 transition-colors flex-shrink-0"
            >
              Sign out
            </button>
          </div>
        ) : (
          <SidebarAuthPrompt onAuthenticated={onAuthenticated} />
        )}
      </div>
    </div>
  )
}

function SidebarAuthPrompt({ onAuthenticated }) {
  const [expanded, setExpanded] = useState(false)

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        className="w-full flex items-center gap-2 text-xs text-gray-400 hover:text-gray-200 transition-colors"
      >
        <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
        Sign in to save sessions
      </button>
    )
  }

  return (
    <div>
      <p className="text-xs text-gray-400 mb-2">Sign in to access your consultations from any device.</p>
      <AuthPrompt variant="inline" onAuthenticated={onAuthenticated} />
    </div>
  )
}


// ─── Chat Message ───────────────────────────────────────────────────────────

function ChatMessage({ message }) {
  const isUser = message.role === 'user'
  const [showReport, setShowReport] = useState(false)
  const [copyFeedback, setCopyFeedback] = useState(false)

  const handleCopyReport = async () => {
    if (!message.full_report) return
    const text = `# FilterOracle — Technical Report\n# Independent AI-Powered Hydraulic Filter Consulting\n\n${message.full_report}\n\n---\n_Generated by FilterOracle • filteroracle.com • Independent & Vendor-Neutral_`
    try {
      await navigator.clipboard.writeText(text)
      setCopyFeedback(true)
      setTimeout(() => setCopyFeedback(false), 2000)
    } catch {
      console.error('Clipboard write failed')
    }
  }

  const reportRef = useRef(null)

  const handlePrintReport = () => {
    if (!message.full_report) return
    // Grab the rendered HTML from the already-mounted report element
    const reportHTML = reportRef.current?.innerHTML || ''
    const printWindow = window.open('', '_blank')
    if (!printWindow) return

    const dateStr = new Date().toLocaleDateString('en-US', {
      year: 'numeric', month: 'long', day: 'numeric',
    })

    printWindow.document.write(`<!DOCTYPE html>
<html><head><title>FilterOracle Technical Report</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 40px 24px; color: #1a1a1a; line-height: 1.6; font-size: 14px; }
  h1, h2, h3 { color: #111827; margin-top: 1.5em; }
  h1 { font-size: 1.5em; border-bottom: 2px solid #2563eb; padding-bottom: 8px; }
  h2 { font-size: 1.25em; }
  table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 13px; }
  th, td { border: 1px solid #d1d5db; padding: 6px 10px; text-align: left; }
  th { background: #f3f4f6; font-weight: 600; }
  code { background: #f3f4f6; padding: 2px 4px; border-radius: 3px; font-size: 0.9em; }
  pre { background: #f3f4f6; padding: 12px; border-radius: 6px; overflow-x: auto; }
  .header { text-align: center; margin-bottom: 2em; padding-bottom: 1em; border-bottom: 1px solid #e5e7eb; }
  .header h1 { border: none; padding: 0; margin: 0 0 4px; font-size: 1.3em; }
  .header .date { color: #6b7280; font-size: 0.9em; }
  .footer { margin-top: 3em; padding-top: 1em; border-top: 1px solid #e5e7eb; color: #9ca3af; font-size: 0.8em; text-align: center; }
  @media print { body { padding: 20px; } }
</style></head><body>
<div class="header">
  <h1>FilterOracle Technical Report</h1>
  <div class="date">${dateStr}</div>
  <div class="date">Independent AI-Powered Hydraulic Filter Consulting</div>
</div>
${reportHTML}
<div class="footer">
  <p>Generated by FilterOracle &bull; filteroracle.com &bull; Independent &amp; Vendor-Neutral</p>
  <p><em>This report is generated from knowledge base sources and should be validated against current manufacturer specifications.</em></p>
</div>
</body></html>`)
    printWindow.document.close()
    printWindow.focus()
    setTimeout(() => printWindow.print(), 300)
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-3 ${
          isUser
            ? 'bg-blue-600 text-white'
            : 'bg-gray-800 border border-gray-700 text-gray-100'
        }`}
      >
        {isUser ? (
          <div className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</div>
        ) : (
          <div className="text-sm leading-relaxed prose prose-sm prose-invert max-w-none prose-headings:text-gray-100 prose-p:text-gray-200 prose-li:text-gray-200 prose-strong:text-white prose-table:text-xs prose-a:text-blue-400">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          </div>
        )}

        {/* Expandable Full Technical Report */}
        {!isUser && message.full_report && (
          <div className="mt-3 pt-3 border-t border-gray-700">
            <button
              onClick={() => setShowReport(!showReport)}
              className="flex items-center gap-1.5 text-sm text-blue-400 hover:text-blue-300 transition-colors font-medium"
            >
              <svg
                className={`w-4 h-4 transition-transform duration-200 ${showReport ? 'rotate-90' : ''}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              {showReport ? 'Hide Full Technical Report' : 'View Full Technical Report'}
            </button>

            {showReport && (
              <div className="mt-3">
                {/* Toolbar */}
                <div className="flex items-center gap-2 mb-3">
                  <button
                    onClick={handleCopyReport}
                    className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-gray-300 bg-gray-700 hover:bg-gray-600 rounded transition-colors"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    {copyFeedback ? 'Copied!' : 'Copy'}
                  </button>
                  <button
                    onClick={handlePrintReport}
                    className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-gray-300 bg-gray-700 hover:bg-gray-600 rounded transition-colors"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
                    </svg>
                    Print
                  </button>
                </div>
                {/* Report content */}
                <div ref={reportRef} className="text-sm leading-relaxed prose prose-sm prose-invert max-w-none prose-headings:text-gray-100 prose-p:text-gray-200 prose-li:text-gray-200 prose-strong:text-white prose-table:text-xs prose-a:text-blue-400 border-l-2 border-blue-500 pl-4">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.full_report}</ReactMarkdown>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Show RAG indicator for answering-phase assistant messages */}
        {!isUser && message.rag_chunks_used?.length > 0 && (
          <div className="mt-2 pt-2 border-t border-gray-700">
            <span className="text-xs text-gray-500">
              Based on {message.rag_chunks_used.length} technical source{message.rag_chunks_used.length !== 1 ? 's' : ''}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}


// ─── Feedback Prompt ────────────────────────────────────────────────────────

function FeedbackPrompt({ sessionId, onSubmit }) {
  const [submitted, setSubmitted] = useState(false)
  const [showComment, setShowComment] = useState(false)
  const [comment, setComment] = useState('')
  const [rating, setRating] = useState(null)

  const handleRate = async (r) => {
    setRating(r)
    if (r === 'negative') {
      setShowComment(true)
    } else {
      try {
        await submitConsultFeedback(sessionId, r)
        setSubmitted(true)
        onSubmit?.()
      } catch (err) {
        console.error('Failed to submit feedback:', err)
      }
    }
  }

  const handleCommentSubmit = async () => {
    try {
      await submitConsultFeedback(sessionId, rating, comment)
      setSubmitted(true)
      onSubmit?.()
    } catch (err) {
      console.error('Failed to submit feedback:', err)
    }
  }

  if (submitted) {
    return (
      <div className="text-center py-3">
        <p className="text-sm text-gray-500">Thank you for your feedback.</p>
      </div>
    )
  }

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 mx-auto max-w-md">
      <p className="text-sm text-gray-700 text-center font-medium mb-3">
        Was this consultation helpful?
      </p>
      {!showComment ? (
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={() => handleRate('positive')}
            className="flex items-center gap-1.5 px-4 py-2 text-sm border border-gray-300 rounded-md hover:bg-green-50 hover:border-green-300 hover:text-green-700 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" />
            </svg>
            Helpful
          </button>
          <button
            onClick={() => handleRate('negative')}
            className="flex items-center gap-1.5 px-4 py-2 text-sm border border-gray-300 rounded-md hover:bg-red-50 hover:border-red-300 hover:text-red-700 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3h4.018a2 2 0 01.485.06l3.76.94m-7 10v5a2 2 0 002 2h.096c.5 0 .905-.405.905-.904 0-.715.211-1.413.608-2.008L17 13V4m-7 10h2m5-10h2a2 2 0 012 2v6a2 2 0 01-2 2h-2.5" />
            </svg>
            Not helpful
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="What was missing or incorrect? (optional)"
            rows={2}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={handleCommentSubmit}
            className="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-md transition-colors"
          >
            Submit Feedback
          </button>
        </div>
      )}
    </div>
  )
}


// ─── Auth Prompt (inline, non-blocking) ─────────────────────────────────────

function AuthPrompt({ onAuthenticated, sessionId, variant = 'inline' }) {
  const [step, setStep] = useState('email') // email | code | done
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  const handleSendCode = async (e) => {
    e.preventDefault()
    if (!email.trim()) return
    setSending(true)
    setError('')
    try {
      await authSendCode(email.trim())
      setStep('code')
    } catch (err) {
      setError(err.message || 'Failed to send code')
    } finally {
      setSending(false)
    }
  }

  const handleVerifyCode = async (e) => {
    e.preventDefault()
    if (code.length !== 6) return
    setSending(true)
    setError('')
    try {
      const result = await authVerifyCode(email.trim(), code)
      if (result.success) {
        setAuthToken(result.token)
        setStep('done')
        // Claim current session if we have one
        if (sessionId) {
          try { await authClaimSessions([sessionId]) } catch {}
        }
        onAuthenticated?.(result)
      } else {
        setError(result.message || 'Invalid code')
      }
    } catch (err) {
      setError(err.message || 'Verification failed')
    } finally {
      setSending(false)
    }
  }

  // Auto-submit when 6 digits entered
  useEffect(() => {
    if (code.length === 6 && step === 'code') {
      handleVerifyCode({ preventDefault: () => {} })
    }
  }, [code])

  if (step === 'done') {
    return (
      <div className="bg-green-50 border border-green-200 rounded-lg p-3 mx-auto max-w-md">
        <div className="flex items-center gap-2 text-sm text-green-700">
          <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>Signed in as <strong>{email}</strong> — your sessions are saved.</span>
        </div>
      </div>
    )
  }

  const isPostRecommendation = variant === 'post-recommendation'

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 mx-auto max-w-md">
      <div className="flex items-start gap-3">
        <svg className="w-5 h-5 text-blue-500 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          {isPostRecommendation ? (
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
          ) : (
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          )}
        </svg>
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-700 mb-1">
            {isPostRecommendation ? 'Save this consultation' : 'Save your consultations'}
          </p>
          <p className="text-xs text-gray-500 mb-3">
            {isPostRecommendation
              ? 'Sign in to save this session permanently. You can return anytime to review the recommendation or report how it worked out. We\'ll also notify you when we add new data relevant to your application.'
              : 'Enter your email to keep your sessions, get follow-up reminders, and receive updates when we add new data relevant to your applications.'}
          </p>

          {step === 'email' && (
            <form onSubmit={handleSendCode} className="flex gap-2">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                required
                className="flex-1 px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <button
                type="submit"
                disabled={sending || !email.trim()}
                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-300 text-white text-sm font-medium rounded-md transition-colors whitespace-nowrap"
              >
                {sending ? 'Sending...' : 'Send Code'}
              </button>
            </form>
          )}

          {step === 'code' && (
            <div>
              <p className="text-xs text-gray-600 mb-2">
                Enter the 6-digit code sent to <strong>{email}</strong>
              </p>
              <form onSubmit={handleVerifyCode} className="flex gap-2">
                <input
                  type="text"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="000000"
                  maxLength={6}
                  autoFocus
                  className="flex-1 px-3 py-1.5 border border-gray-300 rounded-md text-sm text-center tracking-widest font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
                <button
                  type="submit"
                  disabled={sending || code.length !== 6}
                  className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-300 text-white text-sm font-medium rounded-md transition-colors whitespace-nowrap"
                >
                  {sending ? 'Verifying...' : 'Verify'}
                </button>
              </form>
              <button
                onClick={() => { setStep('email'); setCode(''); setError('') }}
                className="text-xs text-blue-600 hover:text-blue-500 mt-2"
              >
                Use a different email
              </button>
            </div>
          )}

          {error && (
            <p className="text-xs text-red-500 mt-1">{error}</p>
          )}
        </div>
      </div>
    </div>
  )
}


// ─── Outcome Report Display ─────────────────────────────────────────────────

const STAR_LABELS = ['', 'Failed', 'Poor', 'Acceptable', 'Good', 'Excellent']
const IMPL_LABELS = {
  implemented_as_recommended: 'Implemented as recommended',
  implemented_with_modifications: 'Implemented with modifications',
  partially_implemented: 'Partially implemented',
  not_implemented: 'Not implemented',
  still_evaluating: 'Still evaluating',
}
const TIMELINE_OPTIONS = [
  'Within 1 week',
  '1-4 weeks',
  '1-3 months',
  '3-6 months',
  '6+ months',
]

function OutcomeDisplay({ outcome }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 mb-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          {outcome.followup_stage === 'user_initiated' ? 'Outcome Report' : `${outcome.followup_stage.replace('_', ' ')} Follow-up`}
        </span>
        <span className="text-xs text-gray-400">
          {new Date(outcome.created_at).toLocaleDateString()}
        </span>
      </div>

      <div className="space-y-2 text-sm">
        {outcome.implementation_status && (
          <div>
            <span className="font-medium text-gray-700">Implementation: </span>
            <span className="text-gray-600">{IMPL_LABELS[outcome.implementation_status] || outcome.implementation_status}</span>
          </div>
        )}
        {outcome.performance_rating && (
          <div className="flex items-center gap-1">
            <span className="font-medium text-gray-700">Performance: </span>
            {[1,2,3,4,5].map(s => (
              <svg key={s} className={`w-4 h-4 ${s <= outcome.performance_rating ? 'text-yellow-400' : 'text-gray-300'}`} fill="currentColor" viewBox="0 0 20 20">
                <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
              </svg>
            ))}
            <span className="text-xs text-gray-500 ml-1">{STAR_LABELS[outcome.performance_rating]}</span>
          </div>
        )}
        {outcome.performance_notes && (
          <div>
            <span className="font-medium text-gray-700">Notes: </span>
            <span className="text-gray-600">{outcome.performance_notes}</span>
          </div>
        )}
        {outcome.failure_occurred && (
          <div className="bg-red-50 border border-red-200 rounded p-2">
            <span className="font-medium text-red-700">Failure reported: </span>
            <span className="text-red-600">{outcome.failure_mode}</span>
            {outcome.failure_timeline && <span className="text-red-500 text-xs ml-1">({outcome.failure_timeline})</span>}
          </div>
        )}
        {outcome.operating_conditions_matched === false && outcome.operating_conditions_notes && (
          <div>
            <span className="font-medium text-gray-700">Conditions differed: </span>
            <span className="text-gray-600">{outcome.operating_conditions_notes}</span>
          </div>
        )}
        {outcome.modifications_made && (
          <div>
            <span className="font-medium text-gray-700">Modifications: </span>
            <span className="text-gray-600">{outcome.modifications_made}</span>
          </div>
        )}
        {outcome.would_recommend_same !== null && outcome.would_recommend_same !== undefined && (
          <div>
            <span className="font-medium text-gray-700">Would choose same solution: </span>
            <span className={outcome.would_recommend_same ? 'text-green-600' : 'text-red-600'}>
              {outcome.would_recommend_same ? 'Yes' : 'No'}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}


function OutcomeForm({ sessionId, existingOutcome, onSubmitted, onCancel }) {
  const [form, setForm] = useState({
    implementation_status: existingOutcome?.implementation_status || '',
    performance_rating: existingOutcome?.performance_rating || null,
    performance_notes: existingOutcome?.performance_notes || '',
    failure_occurred: existingOutcome?.failure_occurred || false,
    failure_mode: existingOutcome?.failure_mode || '',
    failure_timeline: existingOutcome?.failure_timeline || '',
    operating_conditions_matched: existingOutcome?.operating_conditions_matched ?? null,
    operating_conditions_notes: existingOutcome?.operating_conditions_notes || '',
    modifications_made: existingOutcome?.modifications_made || '',
    would_recommend_same: existingOutcome?.would_recommend_same ?? null,
    alternative_tried: existingOutcome?.alternative_tried || '',
    additional_notes: existingOutcome?.additional_notes || '',
  })
  const [submitting, setSubmitting] = useState(false)

  const update = (key, value) => setForm(prev => ({ ...prev, [key]: value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      const payload = {
        ...form,
        followup_stage: 'user_initiated',
        operating_conditions_matched: form.operating_conditions_matched,
        would_recommend_same: form.would_recommend_same,
      }
      // Clean empty strings to null
      for (const k of Object.keys(payload)) {
        if (payload[k] === '') payload[k] = null
      }
      if (!payload.implementation_status) payload.implementation_status = null

      if (existingOutcome) {
        await updateConsultOutcome(sessionId, existingOutcome.id, payload)
      } else {
        await submitConsultOutcome(sessionId, payload)
      }
      onSubmitted()
    } catch (err) {
      console.error('Failed to submit outcome:', err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Q1: Implementation status */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Did you implement the recommendation?
        </label>
        <div className="space-y-1.5">
          {[
            ['implemented_as_recommended', 'Yes, as recommended'],
            ['implemented_with_modifications', 'Yes, with modifications'],
            ['partially_implemented', 'Partially'],
            ['not_implemented', 'No'],
            ['still_evaluating', 'Still evaluating'],
          ].map(([val, label]) => (
            <label key={val} className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
              <input
                type="radio"
                name="impl_status"
                checked={form.implementation_status === val}
                onChange={() => update('implementation_status', val)}
                className="text-blue-600"
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      {/* Q2: Performance rating */}
      {form.implementation_status && form.implementation_status !== 'not_implemented' && form.implementation_status !== 'still_evaluating' && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            How is it performing?
          </label>
          <div className="flex items-center gap-1">
            {[1,2,3,4,5].map(s => (
              <button
                type="button"
                key={s}
                onClick={() => update('performance_rating', s)}
                className="p-0.5"
                title={STAR_LABELS[s]}
              >
                <svg className={`w-7 h-7 transition-colors ${s <= (form.performance_rating || 0) ? 'text-yellow-400' : 'text-gray-300 hover:text-yellow-200'}`} fill="currentColor" viewBox="0 0 20 20">
                  <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                </svg>
              </button>
            ))}
            {form.performance_rating && (
              <span className="text-sm text-gray-500 ml-2">{STAR_LABELS[form.performance_rating]}</span>
            )}
          </div>
        </div>
      )}

      {/* Q3: Performance notes */}
      {form.implementation_status && form.implementation_status !== 'not_implemented' && form.implementation_status !== 'still_evaluating' && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Tell us more about the performance
          </label>
          <textarea
            value={form.performance_notes}
            onChange={(e) => update('performance_notes', e.target.value)}
            placeholder="What's working well? What's not? Any surprises?"
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      )}

      {/* Q4: Failure */}
      <div>
        <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
          <input
            type="checkbox"
            checked={form.failure_occurred}
            onChange={(e) => update('failure_occurred', e.target.checked)}
            className="text-red-600 rounded"
          />
          <span className="font-medium">I experienced a failure or significant issue</span>
        </label>
        {form.failure_occurred && (
          <div className="mt-2 ml-6 space-y-2">
            <textarea
              value={form.failure_mode}
              onChange={(e) => update('failure_mode', e.target.value)}
              placeholder="What failed?"
              rows={2}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <select
              value={form.failure_timeline}
              onChange={(e) => update('failure_timeline', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">When did it fail?</option>
              {TIMELINE_OPTIONS.map(opt => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Q5: Operating conditions matched */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Did the actual operating conditions match what we discussed?
        </label>
        <div className="flex gap-4">
          {[true, false].map(val => (
            <label key={String(val)} className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
              <input
                type="radio"
                name="conditions"
                checked={form.operating_conditions_matched === val}
                onChange={() => update('operating_conditions_matched', val)}
                className="text-blue-600"
              />
              {val ? 'Yes' : 'No'}
            </label>
          ))}
        </div>
        {form.operating_conditions_matched === false && (
          <textarea
            value={form.operating_conditions_notes}
            onChange={(e) => update('operating_conditions_notes', e.target.value)}
            placeholder="What was different?"
            rows={2}
            className="mt-2 w-full px-3 py-2 border border-gray-300 rounded-md text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        )}
      </div>

      {/* Q6: Modifications */}
      {form.implementation_status === 'implemented_with_modifications' && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            What did you change from the recommendation?
          </label>
          <textarea
            value={form.modifications_made}
            onChange={(e) => update('modifications_made', e.target.value)}
            placeholder="Describe the modifications and why you made them..."
            rows={2}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      )}

      {/* Q7: Would recommend same */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Knowing what you know now, would you choose the same solution?
        </label>
        <div className="flex gap-4">
          {[
            [true, 'Yes'],
            [false, 'No'],
            [null, 'Unsure'],
          ].map(([val, label]) => (
            <label key={String(val)} className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
              <input
                type="radio"
                name="recommend_same"
                checked={form.would_recommend_same === val}
                onChange={() => update('would_recommend_same', val)}
                className="text-blue-600"
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      {/* Q8: Additional notes */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Anything else you'd like to share?
        </label>
        <textarea
          value={form.additional_notes}
          onChange={(e) => update('additional_notes', e.target.value)}
          placeholder="Optional — any additional observations, tips, or context..."
          rows={2}
          className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Submit */}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="flex-1 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-300 text-white text-sm font-medium rounded-md transition-colors"
        >
          {submitting ? 'Submitting...' : existingOutcome ? 'Update Outcome Report' : 'Submit Outcome Report'}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 border border-gray-300 text-gray-600 text-sm rounded-md hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}


function OutcomeSection({ session }) {
  const [outcomes, setOutcomes] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [editingOutcome, setEditingOutcome] = useState(null)
  const [thankYou, setThankYou] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const loadOutcomes = useCallback(async () => {
    if (!session?.id) return
    try {
      const data = await getConsultOutcomes(session.id)
      setOutcomes(data.outcomes || [])
      setLoaded(true)
    } catch (err) {
      console.error('Failed to load outcomes:', err)
    }
  }, [session?.id])

  useEffect(() => {
    loadOutcomes()
  }, [loadOutcomes])

  const handleSubmitted = () => {
    setShowForm(false)
    setEditingOutcome(null)
    setThankYou(true)
    loadOutcomes()
    setTimeout(() => setThankYou(false), 5000)
  }

  // Don't render if session isn't in answering phase
  if (!session || session.phase !== 'answering') return null
  if (!loaded) return null

  return (
    <div className="border-t-2 border-blue-200 bg-blue-50/30 px-4 py-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-800">How did it go?</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Come back to this consultation anytime to report how the recommendation worked out. Your real-world feedback is the most valuable data in our system — it helps us improve recommendations for every engineer who comes after you.
          </p>
        </div>
        {!showForm && !editingOutcome && (
          <button
            onClick={() => setShowForm(true)}
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium rounded-md transition-colors"
          >
            Report Outcome
          </button>
        )}
      </div>

      {/* Thank you message */}
      {thankYou && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-3 mb-3">
          <p className="text-sm text-green-700">
            Thank you for reporting back. Your feedback helps improve recommendations for future engineers.
          </p>
        </div>
      )}

      {/* Existing outcomes */}
      {outcomes.map(o => (
        <div key={o.id}>
          <OutcomeDisplay outcome={o} />
          {!showForm && !editingOutcome && (
            <button
              onClick={() => setEditingOutcome(o)}
              className="text-xs text-blue-600 hover:text-blue-500 mb-3"
            >
              Update this report
            </button>
          )}
        </div>
      ))}

      {/* New outcome form */}
      {showForm && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <OutcomeForm
            sessionId={session.id}
            onSubmitted={handleSubmitted}
            onCancel={() => setShowForm(false)}
          />
        </div>
      )}

      {/* Edit existing outcome form */}
      {editingOutcome && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <OutcomeForm
            sessionId={session.id}
            existingOutcome={editingOutcome}
            onSubmitted={handleSubmitted}
            onCancel={() => setEditingOutcome(null)}
          />
        </div>
      )}
    </div>
  )
}


// ─── Chat Interface ─────────────────────────────────────────────────────────

function ChatInterface({ session, onMessageSent, onAuthenticated }) {
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [statusMessage, setStatusMessage] = useState('')
  // Section-aware streaming state
  const [streamingSection, setStreamingSection] = useState('summary') // 'summary' | 'full_report'
  const [streamingReport, setStreamingReport] = useState('')
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  const streamingTextRef = useRef('')
  const streamingReportRef = useRef('')
  const streamingSectionRef = useRef('summary')

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [session?.messages, streamingText, scrollToBottom])

  useEffect(() => {
    textareaRef.current?.focus()
  }, [session?.id])

  const handleSubmit = async (e, { forceTransition = false } = {}) => {
    e?.preventDefault?.()
    if (sending) return
    if (!forceTransition && !input.trim()) return

    const content = forceTransition ? '' : input.trim()
    if (!forceTransition) setInput('')
    setSending(true)
    setStreamingText('')
    setStreamingReport('')
    setStreamingSection('summary')
    setStatusMessage('')
    streamingTextRef.current = ''
    streamingReportRef.current = ''
    streamingSectionRef.current = 'summary'

    try {
      await sendConsultMessageStream(
        session.id,
        content,
        { forceTransition },
        {
          onStatus: (data) => {
            setStatusMessage(data.message || '')
          },
          onMetadata: () => {
            // Phase/domain info — we'll get full state from onMessageSent
            setStatusMessage('')
          },
          onChunk: (data) => {
            if (streamingSectionRef.current === 'full_report') {
              streamingReportRef.current += data.text
              setStreamingReport(streamingReportRef.current)
            } else {
              streamingTextRef.current += data.text
              setStreamingText(streamingTextRef.current)
            }
          },
          onSection: (data) => {
            if (data.section === 'full_report') {
              streamingSectionRef.current = 'full_report'
              setStreamingSection('full_report')
            }
          },
          onComplete: () => {
            // Stream finished — reload full session from DB
            onMessageSent()
          },
          onError: (err) => {
            console.error('Stream error:', err)
            if (!forceTransition && content) setInput(content)
          },
        },
      )
    } catch (err) {
      console.error('Failed to send message:', err)
      if (!forceTransition) setInput(content)
    } finally {
      setSending(false)
      setStreamingText('')
      setStreamingReport('')
      setStreamingSection('summary')
      setStatusMessage('')
      streamingTextRef.current = ''
      streamingReportRef.current = ''
      streamingSectionRef.current = 'summary'
    }
  }

  const handleForceTransition = (e) => {
    e.preventDefault()
    handleSubmit(e, { forceTransition: true })
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  if (!session) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">
        <div className="text-center max-w-md px-6">
          <svg className="w-16 h-16 mx-auto mb-4 text-gray-300" viewBox="0 0 32 32" fill="none">
            <circle cx="16" cy="16" r="14" fill="#f3f4f6" stroke="#d1d5db" strokeWidth="2"/>
            <path d="M16 6 L14 16 L12 26 M16 6 L18 16 L20 26 M16 6 L16 26 M16 6 L10 22 M16 6 L22 22"
                  stroke="#9ca3af" strokeWidth="1.5" fill="none" strokeLinecap="round" opacity="0.6"/>
            <circle cx="16" cy="6" r="2" fill="#9ca3af"/>
          </svg>
          <h3 className="text-lg font-semibold text-gray-700 mb-2">Hydraulic Filter Consultation</h3>
          <p className="text-sm text-gray-500">
            Start a new consultation to get expert recommendations tailored to your specific application.
          </p>
        </div>
      </div>
    )
  }

  // Determine if we should show feedback (session in answering phase with messages)
  const hasAnsweringMessages = session.messages.some(m =>
    m.role === 'assistant' && m.phase_at_time === 'answering'
  )

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Session header */}
      <div className="px-4 py-3 border-b border-gray-200 bg-white flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-semibold text-gray-900 truncate">{session.title}</h2>
        </div>
        <PhaseIndicator phase={session.phase} />
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 bg-gray-50">
        {session.messages.length === 0 && !sending && (
          <div className="flex items-center justify-center h-full text-gray-400">
            <div className="text-center max-w-sm">
              <p className="text-sm font-medium text-gray-600 mb-1">
                Describe your hydraulic filter application or problem
              </p>
              <p className="text-xs text-gray-400">
                I'll ask a few diagnostic questions to understand your needs, then provide a tailored technical recommendation.
              </p>
            </div>
          </div>
        )}
        {session.messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        {/* Streaming response or loading indicator */}
        {sending && streamingText && (
          <div className="flex justify-start mb-4">
            <div className="max-w-[80%] rounded-lg px-4 py-3 bg-gray-800 border border-gray-700 text-gray-100">
              <div className="text-sm leading-relaxed prose prose-sm prose-invert max-w-none prose-headings:text-gray-100 prose-p:text-gray-200 prose-li:text-gray-200 prose-strong:text-white prose-table:text-xs prose-a:text-blue-400">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingText}</ReactMarkdown>
              </div>
              {/* Show report generation indicator when streaming the full report */}
              {streamingSection === 'full_report' && (
                <div className="mt-3 pt-3 border-t border-gray-700">
                  <div className="flex items-center gap-2 text-sm text-blue-400">
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Generating full technical report...
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
        {sending && !streamingText && (
          <div className="flex justify-start mb-4">
            <div className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-3">
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {statusMessage
                  || (session.phase === 'gathering'
                    ? 'Thinking...'
                    : 'Searching knowledge base...'
                  )
                }
              </div>
            </div>
          </div>
        )}

        {/* Feedback prompt after answering phase */}
        {hasAnsweringMessages && !sending && (
          <div className="mt-4 mb-2">
            <FeedbackPrompt sessionId={session.id} />
          </div>
        )}

        {/* Auth prompt after recommendation (only if not authenticated) */}
        {hasAnsweringMessages && !sending && !isAuthenticated() && (
          <div className="mt-3 mb-2">
            <AuthPrompt
              variant="post-recommendation"
              sessionId={session.id}
              onAuthenticated={onAuthenticated}
            />
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Outcome reporting section */}
      <OutcomeSection session={session} />

      {/* Input */}
      <div className="p-4 border-t border-gray-200 bg-white">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              session.messages.length === 0
                ? 'Describe your hydraulic filter application or the problem you\'re trying to solve...'
                : session.phase === 'gathering'
                  ? 'Answer the questions above... (Enter to send)'
                  : 'Ask a follow-up question... (Enter to send)'
            }
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
        {/* "Skip to recommendation" shortcut — visible during gathering phase after at least one user message */}
        {session.phase === 'gathering' && session.messages.some(m => m.role === 'user') && (
          <button
            onClick={handleForceTransition}
            disabled={sending}
            className="mt-2 w-full py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-500 disabled:bg-gray-300 disabled:cursor-not-allowed rounded-md transition-colors"
          >
            Skip to Recommendation
          </button>
        )}
      </div>
    </div>
  )
}


// ─── Main Page ──────────────────────────────────────────────────────────────

export default function ConsultPage() {
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [activeSession, setActiveSession] = useState(null)
  const [loading, setLoading] = useState(false)
  const [user, setUser] = useState(null)
  const [authChecking, setAuthChecking] = useState(true)

  // Track anonymous session IDs so we can claim them after sign-in
  const anonSessionIds = useRef([])

  // Check for existing auth token on page load (returning user flow)
  useEffect(() => {
    const checkAuth = async () => {
      if (!isAuthenticated()) {
        setAuthChecking(false)
        return
      }
      try {
        const me = await authMe()
        setUser(me)
      } catch {
        // Token expired or invalid — clear it
        clearAuthToken()
      } finally {
        setAuthChecking(false)
      }
    }
    checkAuth()
  }, [])

  const loadSessions = useCallback(async () => {
    try {
      const data = await getConsultSessions()
      setSessions(data.sessions)
    } catch (err) {
      console.error('Failed to load sessions:', err)
    }
  }, [])

  const loadSession = useCallback(async (id) => {
    if (!id) {
      setActiveSession(null)
      return
    }
    setLoading(true)
    try {
      const data = await getConsultSession(id)
      setActiveSession(data)
    } catch (err) {
      console.error('Failed to load session:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  // Load sessions once auth check is complete
  useEffect(() => {
    if (!authChecking) {
      loadSessions()
    }
  }, [authChecking, loadSessions])

  useEffect(() => {
    if (activeSessionId) {
      loadSession(activeSessionId)
    } else {
      setActiveSession(null)
    }
  }, [activeSessionId, loadSession])

  const handleNewSession = async () => {
    try {
      const session = await createConsultSession()
      setSessions((prev) => [session, ...prev])
      setActiveSessionId(session.id)
      // Track for claiming later if anonymous
      if (!user) {
        anonSessionIds.current.push(session.id)
      }
    } catch (err) {
      console.error('Failed to create session:', err)
    }
  }

  const handleDeleteSession = async (id) => {
    if (!confirm('Delete this consultation and all its messages?')) return
    try {
      await deleteConsultSession(id)
      setSessions((prev) => prev.filter((s) => s.id !== id))
      if (activeSessionId === id) {
        setActiveSessionId(null)
      }
      // Remove from anonymous tracking
      anonSessionIds.current = anonSessionIds.current.filter(sid => sid !== id)
    } catch (err) {
      console.error('Failed to delete session:', err)
    }
  }

  const handleMessageSent = async () => {
    if (activeSessionId) {
      await loadSession(activeSessionId)
    }
    await loadSessions()
  }

  const handleAuthenticated = async (result) => {
    // result comes from AuthPrompt: { success, token, user }
    // Token is already set in localStorage by AuthPrompt
    setUser(result.user || { email: result.email })

    // Claim any anonymous sessions created during this visit
    const toClaim = [...anonSessionIds.current]
    if (toClaim.length > 0) {
      try {
        await authClaimSessions(toClaim)
        anonSessionIds.current = []
      } catch (err) {
        console.error('Failed to claim sessions:', err)
      }
    }

    // Refresh session list to show all user sessions
    await loadSessions()
  }

  const handleSignOut = async () => {
    try {
      await authLogout()
    } catch {
      // Ignore — token might already be invalid
    }
    clearAuthToken()
    setUser(null)
    setSessions([])
    setActiveSessionId(null)
    setActiveSession(null)
    anonSessionIds.current = []
  }

  return (
    <div className="flex h-[calc(100vh-7.5rem)] -mx-4 sm:-mx-6 -my-6 overflow-hidden">
      <SessionSidebar
        sessions={sessions}
        activeId={activeSessionId}
        onSelect={setActiveSessionId}
        onNew={handleNewSession}
        onDelete={handleDeleteSession}
        user={user}
        onSignOut={handleSignOut}
        onAuthenticated={handleAuthenticated}
      />
      <ChatInterface
        session={activeSession}
        onMessageSent={handleMessageSent}
        onAuthenticated={handleAuthenticated}
      />
      {loading && !activeSession && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-50/80">
          <div className="text-sm text-gray-500">Loading consultation...</div>
        </div>
      )}
    </div>
  )
}
