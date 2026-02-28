import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getQuestion } from '../api'
import AnswerDisplay from '../components/AnswerDisplay'
import LoadingSpinner from '../components/LoadingSpinner'

export default function QuestionPage() {
  const { id } = useParams()
  const [question, setQuestion] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadQuestion()
  }, [id])

  async function loadQuestion() {
    setLoading(true)
    setError(null)

    try {
      const data = await getQuestion(id)
      setQuestion(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <LoadingSpinner message="Loading question..." />
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-red-500 mb-4">{error}</p>
        <Link to="/browse" className="text-blue-600 hover:underline text-sm">
          Back to questions
        </Link>
      </div>
    )
  }

  if (!question) return null

  return (
    <div>
      <Link to="/browse" className="text-sm text-gray-500 hover:text-gray-700 mb-4 inline-block">
        &larr; Back to questions
      </Link>

      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <h1 className="text-lg font-semibold text-gray-900 mb-4">
          {question.question}
        </h1>
        <AnswerDisplay question={question} />
      </div>
    </div>
  )
}
