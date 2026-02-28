import { useState, useRef, useEffect } from 'react'
import { askQuestionStream } from '../api'
import AnswerDisplay from '../components/AnswerDisplay'

const EXAMPLE_QUESTIONS = [
  'What nozzle type produces the finest droplet size at low pressure?',
  'How does spray angle change with flow rate?',
  'What is the relationship between orifice diameter and flow rate?',
  'How do I select a nozzle for FGD scrubber applications?',
]

export default function AskPage() {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Streaming state
  const [stage, setStage] = useState(null)        // 'searching' | 'generating' | null
  const [streamText, setStreamText] = useState('')  // accumulates token by token
  const [streamMeta, setStreamMeta] = useState(null) // {confidence, sources, warnings}
  const [questionId, setQuestionId] = useState(null) // set after DB save
  const [finalResult, setFinalResult] = useState(null) // set when streaming is fully done
  const [showSources, setShowSources] = useState(false) // toggle for source details

  // Auto-scroll as answer streams in
  const answerRef = useRef(null)

  useEffect(() => {
    if (streamText && answerRef.current) {
      const el = answerRef.current
      // Only auto-scroll if user is near the bottom
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150
      if (isNearBottom) {
        el.scrollTop = el.scrollHeight
      }
    }
  }, [streamText])

  async function handleSubmit(e) {
    e.preventDefault()
    if (!question.trim() || loading) return

    setLoading(true)
    setError(null)
    setStage('searching')
    setStreamText('')
    setStreamMeta(null)
    setQuestionId(null)
    setFinalResult(null)
    setShowSources(false)

    await askQuestionStream(question.trim(), {
      onStatus(data) {
        setStage(data.stage)
        if (data.stage === 'generating' && data.confidence) {
          setStreamMeta({
            confidence: data.confidence,
            sources: data.sources || [],
            warnings: data.warnings || [],
          })
        }
      },
      onChunk(data) {
        setStreamText(prev => prev + data.text)
      },
      onComplete(data) {
        // Streaming done — build the final result object
        setFinalResult({
          answer: data.answer,
          confidence: data.confidence,
          sources: data.sources || [],
          warnings: data.warnings || [],
        })
        setStage(null)
        setLoading(false)
      },
      onSaved(data) {
        setQuestionId(data.question_id)
      },
      onError(err) {
        setError(err.message)
        setStage(null)
        setLoading(false)
      },
    })
  }

  function handleExample(q) {
    setQuestion(q)
    setFinalResult(null)
    setStreamText('')
    setStreamMeta(null)
    setQuestionId(null)
    setError(null)
    setShowSources(false)
  }

  function handleAskAnother() {
    setQuestion('')
    setFinalResult(null)
    setStreamText('')
    setStreamMeta(null)
    setQuestionId(null)
    setError(null)
    setStage(null)
    setShowSources(false)
  }

  // Determine what to show
  const isStreaming = loading && stage === 'generating' && streamText
  const isSearching = loading && stage === 'searching'
  const isDone = !loading && (finalResult || streamText)

  return (
    <div>
      {/* Question input */}
      <div className="bg-white border border-gray-200 rounded-lg p-5 mb-6">
        <h1 className="text-xl font-semibold text-gray-900 mb-1">
          Ask a Hydraulic Filter Question
        </h1>
        <p className="text-sm text-gray-500 mb-4">
          Get an AI-powered expert answer backed by a curated engineering knowledge base.
        </p>

        <form onSubmit={handleSubmit}>
          <textarea
            value={question}
            onChange={e => setQuestion(e.target.value)}
            placeholder="Ask any hydraulic filter engineering question..."
            rows={4}
            maxLength={2000}
            className="w-full rounded-lg border border-gray-300 px-4 py-3 text-base focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none placeholder:text-gray-400"
          />
          <div className="flex items-center justify-between mt-3">
            <span className="text-xs text-gray-400">
              {question.length}/2000
            </span>
            <button
              type="submit"
              disabled={question.trim().length < 10 || loading}
              className="px-5 py-2.5 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Generating...' : 'Get Expert Answer'}
            </button>
          </div>
        </form>

        {/* Example questions */}
        {!isDone && !loading && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <p className="text-xs text-gray-500 mb-2">Try an example:</p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLE_QUESTIONS.map((q, i) => (
                <button
                  key={i}
                  onClick={() => handleExample(q)}
                  className="text-xs bg-gray-100 text-gray-600 px-3 py-1.5 rounded-full hover:bg-gray-200 transition-colors text-left"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Searching state */}
      {isSearching && (
        <div className="bg-white border border-gray-200 rounded-lg p-8">
          <div className="flex flex-col items-center justify-center py-8 text-gray-500">
            <div className="relative w-10 h-10 mb-4">
              <div className="absolute inset-0 border-4 border-gray-200 rounded-full"></div>
              <div className="absolute inset-0 border-4 border-blue-500 rounded-full border-t-transparent animate-spin"></div>
            </div>
            <p className="text-sm">Searching knowledge base...</p>
          </div>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-sm text-red-700 font-medium">Something went wrong</p>
          <p className="text-sm text-red-600 mt-1">{error}</p>
        </div>
      )}

      {/* Streaming answer / Final answer */}
      {(isStreaming || isDone) && (
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          {/* Header */}
          <div className="flex items-center gap-3 mb-3">
            <h2 className="text-sm font-medium text-gray-500">Expert Answer</h2>
            {isStreaming && (
              <span className="text-xs text-blue-500 animate-pulse ml-auto">
                Streaming...
              </span>
            )}
          </div>

          {/* Warnings removed — we don't surface RAG confidence/warnings to users */}

          {/* Answer body — streaming or final */}
          {isDone && questionId ? (
            // Full AnswerDisplay with voting + comments once DB save is confirmed
            <AnswerDisplay
              question={{
                id: questionId,
                answer: finalResult?.answer || streamText,
                confidence: finalResult?.confidence || streamMeta?.confidence,
                vote_up: 0,
                vote_down: 0,
              }}
            />
          ) : (
            // Streaming / pre-save display — just markdown
            <div ref={answerRef} className="answer-content prose prose-gray max-w-none prose-headings:text-gray-800 prose-p:text-gray-700 prose-li:text-gray-700 prose-strong:text-gray-900 prose-table:text-sm overflow-y-auto max-h-[70vh]">
              <StreamingMarkdown text={streamText} isStreaming={isStreaming} />
            </div>
          )}

          {/* Collapsible sources */}
          {streamMeta?.sources?.length > 0 && (isDone || isStreaming) && (
            <div className="mt-4 pt-3 border-t border-gray-100">
              <button
                onClick={() => setShowSources(prev => !prev)}
                className="text-xs text-gray-400 hover:text-gray-600 transition-colors flex items-center gap-1"
              >
                <svg
                  className={`w-3 h-3 transition-transform ${showSources ? 'rotate-90' : ''}`}
                  fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
                View sources ({streamMeta.sources.length})
              </button>
              {showSources && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {streamMeta.sources.map((s, i) => (
                    <span key={i} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Ask another button */}
          {isDone && (
            <div className="mt-4 pt-3 border-t border-gray-100 text-center">
              <button
                onClick={handleAskAnother}
                className="text-sm text-blue-600 hover:text-blue-800 transition-colors"
              >
                Ask another question
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Renders markdown text with an optional blinking cursor during streaming.
 */
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

function StreamingMarkdown({ text, isStreaming }) {
  if (!text) return null

  return (
    <>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      {isStreaming && (
        <span className="inline-block w-2 h-4 bg-blue-500 ml-0.5 animate-pulse rounded-sm" />
      )}
    </>
  )
}
