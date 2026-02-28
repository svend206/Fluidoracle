import { useState, useEffect } from 'react'
import { getComments, addComment } from '../api'

function timeAgo(dateStr) {
  const date = new Date(dateStr)
  const now = new Date()
  const seconds = Math.floor((now - date) / 1000)

  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`
  return date.toLocaleDateString()
}

export default function CommentSection({ questionId }) {
  const [comments, setComments] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [body, setBody] = useState('')
  const [isCorrection, setIsCorrection] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadComments()
  }, [questionId])

  async function loadComments() {
    try {
      const data = await getComments(questionId)
      setComments(data.comments)
    } catch (err) {
      console.error('Failed to load comments:', err)
    } finally {
      setLoading(false)
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!body.trim() || submitting) return

    setSubmitting(true)
    setError(null)

    try {
      const comment = await addComment(questionId, body.trim(), isCorrection)
      setComments(prev => [...prev, comment])
      setBody('')
      setIsCorrection(false)
      setShowForm(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mt-4">
      {/* Comment list */}
      {loading ? (
        <p className="text-sm text-gray-400">Loading comments...</p>
      ) : comments.length > 0 ? (
        <div className="space-y-3 mb-4">
          <h4 className="text-sm font-semibold text-gray-700">
            Comments ({comments.length})
          </h4>
          {comments.map(c => (
            <div key={c.id} className={`text-sm rounded-lg p-3 ${
              c.is_correction ? 'bg-amber-50 border border-amber-200' : 'bg-gray-50'
            }`}>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-medium text-gray-700">{c.author_name}</span>
                <span className="text-gray-400 text-xs">{timeAgo(c.created_at)}</span>
                {c.is_correction && (
                  <span className="text-xs bg-amber-200 text-amber-800 px-1.5 py-0.5 rounded font-medium">
                    Correction
                  </span>
                )}
              </div>
              <p className="text-gray-600 whitespace-pre-wrap">{c.body}</p>
            </div>
          ))}
        </div>
      ) : null}

      {/* Correction prompt — always visible when form is hidden */}
      {!showForm && (
        <button
          onClick={() => {
            setShowForm(true)
            setIsCorrection(true)
          }}
          className="flex items-center gap-2 text-sm text-gray-500 hover:text-amber-600 transition-colors group"
        >
          <svg className="w-4 h-4 text-gray-400 group-hover:text-amber-500 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Something wrong? Help us improve this answer
        </button>
      )}

      {/* Expanded comment form */}
      {showForm && (
        <form onSubmit={handleSubmit} className="space-y-2 mt-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
          <textarea
            value={body}
            onChange={e => setBody(e.target.value)}
            placeholder={isCorrection
              ? "What should the correct answer be? Your expertise helps us improve..."
              : "Add a comment..."
            }
            rows={3}
            autoFocus
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
          />
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
              <input
                type="checkbox"
                checked={isCorrection}
                onChange={e => setIsCorrection(e.target.checked)}
                className="rounded border-gray-300 text-amber-500 focus:ring-amber-500"
              />
              This is a correction
            </label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setShowForm(false)
                  setBody('')
                  setIsCorrection(false)
                }}
                className="px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!body.trim() || submitting}
                className="px-4 py-1.5 text-sm font-medium bg-gray-800 text-white rounded-lg hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {submitting ? 'Posting...' : 'Post'}
              </button>
            </div>
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
        </form>
      )}
    </div>
  )
}
