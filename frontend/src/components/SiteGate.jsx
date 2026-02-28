import { useState } from 'react'

const SITE_PASSWORD = import.meta.env.VITE_SITE_PASSWORD || ''

function hasAccess() {
  if (!SITE_PASSWORD) return true
  if (localStorage.getItem('site_gate_passed') === 'true') return true
  if (document.cookie.split('; ').some(c => c === 'site_gate=true')) return true
  return false
}

export default function SiteGate({ children }) {
  const [granted, setGranted] = useState(hasAccess)
  const [input, setInput] = useState('')
  const [error, setError] = useState('')

  if (granted) return children

  const handleSubmit = (e) => {
    e.preventDefault()
    if (input === SITE_PASSWORD) {
      localStorage.setItem('site_gate_passed', 'true')
      document.cookie = 'site_gate=true; path=/; max-age=31536000; SameSite=Lax'
      setGranted(true)
    } else {
      setError('Incorrect code')
      setInput('')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm px-6">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2.5 mb-3">
            <svg className="w-8 h-8" viewBox="0 0 32 32" fill="none">
              <circle cx="16" cy="16" r="14" fill="#1e3a5f" stroke="#3b82f6" strokeWidth="2"/>
              <path d="M16 6 L14 16 L12 26 M16 6 L18 16 L20 26 M16 6 L16 26 M16 6 L10 22 M16 6 L22 22"
                    stroke="#60a5fa" strokeWidth="1.5" fill="none" strokeLinecap="round" opacity="0.8"/>
              <circle cx="16" cy="6" r="2" fill="#93c5fd"/>
            </svg>
            <span className="text-gray-900 font-semibold text-xl tracking-tight">Fluidoracle</span>
          </div>
          <p className="text-sm text-gray-500">This site is currently in private beta.</p>
        </div>

        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="password"
            value={input}
            onChange={(e) => { setInput(e.target.value); setError('') }}
            placeholder="Enter access code"
            autoFocus
            className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <button
            type="submit"
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-md transition-colors"
          >
            Enter
          </button>
        </form>

        {error && (
          <p className="mt-2 text-sm text-red-600 text-center">{error}</p>
        )}
      </div>
    </div>
  )
}
