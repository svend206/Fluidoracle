import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import VoteButtons from './VoteButtons'
import CommentSection from './CommentSection'

export default function AnswerDisplay({ question }) {
  const {
    id,
    answer,
    vote_up = 0,
    vote_down = 0,
  } = question

  return (
    <div className="space-y-4">
      {/* Answer text — rendered as markdown */}
      <div className="answer-content prose prose-gray max-w-none prose-headings:text-gray-800 prose-p:text-gray-700 prose-li:text-gray-700 prose-strong:text-gray-900 prose-table:text-sm">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
      </div>

      {/* Vote row */}
      <div className="flex items-center justify-center pt-4 border-t border-gray-100">
        <VoteButtons questionId={id} initialUp={vote_up} initialDown={vote_down} />
      </div>

      {/* Comments */}
      <CommentSection questionId={id} />
    </div>
  )
}
