import { useState, useEffect, useMemo } from 'react'
import { getQuestions } from '../api'
import QuestionCard from '../components/QuestionCard'
import LoadingSpinner from '../components/LoadingSpinner'

export default function BrowsePage() {
  const [questions, setQuestions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)
  const [search, setSearch] = useState('')

  const LIMIT = 20

  useEffect(() => {
    loadQuestions(1, true)
  }, [])

  async function loadQuestions(pageNum, reset = false) {
    setLoading(true)
    setError(null)

    try {
      const data = await getQuestions(pageNum, LIMIT)
      if (reset) {
        setQuestions(data.questions)
      } else {
        setQuestions(prev => [...prev, ...data.questions])
      }
      setHasMore(data.questions.length === LIMIT)
      setPage(pageNum)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function handleLoadMore() {
    loadQuestions(page + 1)
  }

  // Client-side text search (simple filter)
  const filtered = useMemo(() => {
    if (!search.trim()) return questions
    const term = search.toLowerCase()
    return questions.filter(
      q => q.question.toLowerCase().includes(term) || q.answer.toLowerCase().includes(term)
    )
  }, [questions, search])

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Recent Questions</h1>
        <span className="text-sm text-gray-500">
          {questions.length} question{questions.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Search bar */}
      <div className="mb-4">
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Filter questions..."
          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 placeholder:text-gray-400"
        />
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}

      {/* Question list */}
      {loading && questions.length === 0 ? (
        <LoadingSpinner message="Loading questions..." />
      ) : filtered.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-500">
            {search ? 'No questions match your search.' : 'No questions yet. Be the first to ask!'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(q => (
            <QuestionCard key={q.id} question={q} />
          ))}
        </div>
      )}

      {/* Load more */}
      {hasMore && !search && (
        <div className="mt-6 text-center">
          <button
            onClick={handleLoadMore}
            disabled={loading}
            className="px-5 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40 transition-colors"
          >
            {loading ? 'Loading...' : 'Load More'}
          </button>
        </div>
      )}
    </div>
  )
}
