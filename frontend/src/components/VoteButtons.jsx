import { useState } from 'react'
import { vote as apiVote } from '../api'

export default function VoteButtons({ questionId, initialUp = 0, initialDown = 0 }) {
  const [voteUp, setVoteUp] = useState(initialUp)
  const [voteDown, setVoteDown] = useState(initialDown)
  const [userVote, setUserVote] = useState(() => {
    return localStorage.getItem(`vote-${questionId}`) || null
  })
  const [loading, setLoading] = useState(false)

  const handleVote = async (direction) => {
    if (loading) return
    setLoading(true)

    try {
      const result = await apiVote(questionId, direction)
      setVoteUp(result.vote_up)
      setVoteDown(result.vote_down)

      if (userVote === direction) {
        localStorage.removeItem(`vote-${questionId}`)
        setUserVote(null)
      } else {
        localStorage.setItem(`vote-${questionId}`, direction)
        setUserVote(direction)
      }
    } catch (err) {
      console.error('Vote failed:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-gray-500 mr-1">Was this helpful?</span>

      <button
        onClick={() => handleVote('up')}
        disabled={loading}
        className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
          userVote === 'up'
            ? 'bg-green-100 text-green-700 ring-2 ring-green-300'
            : 'bg-gray-100 text-gray-600 hover:bg-green-50 hover:text-green-700'
        }`}
        title="Helpful answer"
      >
        <svg className="w-5 h-5" fill={userVote === 'up' ? 'currentColor' : 'none'} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
          <path strokeLinecap="round" strokeLinejoin="round" d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3H14z M4 22h0a1 1 0 01-1-1v-9a1 1 0 011-1h0" />
        </svg>
        Yes{voteUp > 0 && ` (${voteUp})`}
      </button>

      <button
        onClick={() => handleVote('down')}
        disabled={loading}
        className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
          userVote === 'down'
            ? 'bg-red-100 text-red-700 ring-2 ring-red-300'
            : 'bg-gray-100 text-gray-600 hover:bg-red-50 hover:text-red-700'
        }`}
        title="Not helpful"
      >
        <svg className="w-5 h-5" fill={userVote === 'down' ? 'currentColor' : 'none'} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
          <path strokeLinecap="round" strokeLinejoin="round" d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3H10z M20 2h0a1 1 0 011 1v9a1 1 0 01-1 1h0" />
        </svg>
        No{voteDown > 0 && ` (${voteDown})`}
      </button>
    </div>
  )
}
