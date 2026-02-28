import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getPlatformConfig } from '../api'

export default function PlatformLanding() {
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    getPlatformConfig()
      .then(setConfig)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    )
  }

  if (!config) {
    return (
      <div className="text-center py-24 text-gray-500">
        Failed to load platform configuration.
      </div>
    )
  }

  const verticals = Object.entries(config.verticals || {})

  // If only one vertical, go directly to it
  if (verticals.length === 1) {
    const [verticalId] = verticals[0]
    navigate(`/consult/${verticalId}`, { replace: true })
    return null
  }

  return (
    <div className="max-w-3xl mx-auto py-12">
      <div className="text-center mb-10">
        <h1 className="text-3xl font-bold text-gray-900 mb-3">
          {config.platform_name}
        </h1>
        <p className="text-gray-600 text-lg">
          Select a consulting area to start a conversation with an expert AI engineer.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {verticals.map(([verticalId, vertical]) => (
          <button
            key={verticalId}
            onClick={() => navigate(`/consult/${verticalId}`)}
            className="text-left p-6 bg-white rounded-xl border border-gray-200 
                       hover:border-blue-400 hover:shadow-lg transition-all duration-200
                       group cursor-pointer"
          >
            <h2 className="text-xl font-semibold text-gray-900 group-hover:text-blue-600 mb-2">
              {vertical.display_name}
            </h2>
            <p className="text-gray-600 text-sm mb-4">
              {vertical.description}
            </p>
            {vertical.example_questions?.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                  Example questions
                </p>
                {vertical.example_questions.slice(0, 2).map((q, i) => (
                  <p key={i} className="text-xs text-gray-500 italic leading-relaxed">
                    "{q}"
                  </p>
                ))}
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
