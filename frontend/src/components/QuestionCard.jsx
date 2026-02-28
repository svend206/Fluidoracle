import { Link } from 'react-router-dom'

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

export default function QuestionCard({ question }) {
  const {
    id,
    question: text,
    answer,
    vote_up = 0,
    vote_down = 0,
    comment_count = 0,
    created_at,
  } = question

  const net = vote_up - vote_down
  const preview = answer.length > 150 ? answer.slice(0, 150) + '...' : answer

  return (
    <Link
      to={`/questions/${id}`}
      className="block bg-white border border-gray-200 rounded-lg p-4 hover:border-gray-300 hover:shadow-sm transition-all"
    >
      {/* Question text */}
      <h3 className="font-medium text-gray-900 mb-2 leading-snug">{text}</h3>

      {/* Answer preview */}
      <p className="text-sm text-gray-600 mb-3 line-clamp-3">{preview}</p>

      {/* Meta row */}
      <div className="flex items-center gap-3 text-xs text-gray-500">
        <span className={`font-medium ${
          net > 0 ? 'text-green-600' : net < 0 ? 'text-red-500' : ''
        }`}>
          {net > 0 ? '+' : ''}{net} votes
        </span>

        {comment_count > 0 && (
          <span>{comment_count} comment{comment_count !== 1 ? 's' : ''}</span>
        )}

        <span className="ml-auto">{timeAgo(created_at)}</span>
      </div>
    </Link>
  )
}
