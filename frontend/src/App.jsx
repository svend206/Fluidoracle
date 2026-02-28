import { Routes, Route, Link, useLocation } from 'react-router-dom'
import SiteGate from './components/SiteGate'
import ConsultPage from './pages/ConsultPage'
import AskPage from './pages/AskPage'
import BrowsePage from './pages/BrowsePage'
import QuestionPage from './pages/QuestionPage'
import InventPage from './pages/InventPage'

function NavLink({ to, children }) {
  const location = useLocation()
  const isActive = location.pathname === to
  return (
    <Link
      to={to}
      className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
        isActive
          ? 'bg-gray-800 text-white'
          : 'text-gray-300 hover:bg-gray-700 hover:text-white'
      }`}
    >
      {children}
    </Link>
  )
}

export default function App() {
  return (
    <SiteGate>
      <div className="min-h-screen flex flex-col">
        {/* Header */}
        <header className="bg-gray-900 border-b border-gray-700">
          <div className="max-w-5xl mx-auto px-4 sm:px-6">
            <div className="flex items-center justify-between h-14">
              <Link to="/" className="flex items-center gap-2.5">
                <svg className="w-7 h-7" viewBox="0 0 32 32" fill="none">
                  <circle cx="16" cy="16" r="14" fill="#1e3a5f" stroke="#3b82f6" strokeWidth="2"/>
                  <path d="M16 6 L14 16 L12 26 M16 6 L18 16 L20 26 M16 6 L16 26 M16 6 L10 22 M16 6 L22 22"
                        stroke="#60a5fa" strokeWidth="1.5" fill="none" strokeLinecap="round" opacity="0.8"/>
                  <circle cx="16" cy="6" r="2" fill="#93c5fd"/>
                </svg>
                <span className="text-white font-semibold text-lg tracking-tight">
                  FilterOracle
                </span>
              </Link>
              <nav className="flex items-center gap-1">
                <NavLink to="/">Consult</NavLink>
                <NavLink to="/ask">Quick Ask</NavLink>
                <NavLink to="/browse">Browse</NavLink>
              </nav>
            </div>
          </div>
        </header>

        {/* Main content */}
        <main className="flex-1">
          <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6">
            <Routes>
              <Route path="/" element={<ConsultPage />} />
              <Route path="/ask" element={<AskPage />} />
              <Route path="/browse" element={<BrowsePage />} />
              <Route path="/questions/:id" element={<QuestionPage />} />
              <Route path="/invent" element={<InventPage />} />
            </Routes>
          </div>
        </main>

        {/* Footer */}
        <footer className="border-t border-gray-200 bg-white">
          <div className="max-w-5xl mx-auto px-4 sm:px-6 py-4">
            <p className="text-xs text-gray-500 text-center">
              Independent Hydraulic Filter Consulting — Not affiliated with any manufacturer. AI-powered recommendations grounded in curated technical data. Verify before use in critical applications.
            </p>
          </div>
        </footer>
      </div>
    </SiteGate>
  )
}
