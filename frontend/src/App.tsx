import { Link, Route, Routes, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import Docket from './pages/Docket'
import DisputeDetail from './pages/DisputeDetail'
import EvaluationPage from './pages/EvaluationPage'
import ChaosLabPage from './pages/ChaosLabPage'
import ActivityTicker from './components/ActivityTicker'
import { api } from './lib/api'

export default function App() {
  const location = useLocation()
  const [llmMode, setLlmMode] = useState<string | null>(null)

  useEffect(() => {
    api.health().then((h) => setLlmMode(h.llm_mode)).catch(() => setLlmMode(null))
  }, [])

  return (
    <div className="min-h-screen bg-base">
      <header className="border-b border-line sticky top-0 z-20 bg-base/95 backdrop-blur">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex flex-col">
              <span className="font-serif font-semibold tracking-wide text-[17px] text-ink leading-tight">VERIDICT</span>
              <span className="text-dim text-[10px] font-mono uppercase tracking-widest hidden sm:block leading-tight mt-0.5">
                cross-system truth verification
              </span>
            </div>
          </div>
          
          <nav className="flex items-center gap-6 text-xs font-mono uppercase tracking-wide">
            <Link
              to="/"
              className={`transition-colors ${location.pathname === '/' ? 'text-ink' : 'text-muted hover:text-ink'}`}
            >
              Docket
            </Link>
            <Link
              to="/chaos"
              className={`transition-colors ${location.pathname === '/chaos' ? 'text-ink' : 'text-muted hover:text-ink'}`}
            >
              Chaos Lab
            </Link>
            <Link
              to="/evaluation"
              className={`transition-colors ${location.pathname === '/evaluation' ? 'text-ink' : 'text-muted hover:text-ink'}`}
            >
              Proof
            </Link>
          </nav>
          
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-cleared animate-pulse-dot" />
              <span className="text-[10px] font-mono text-cleared uppercase">Live</span>
            </div>
            {llmMode && (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded border border-line2 text-dim uppercase">
                LLM: {llmMode === 'openai' ? 'Live' : 'Demo Mode'}
              </span>
            )}
          </div>
        </div>
        <div className="border-t border-line bg-panel/30">
          <div className="max-w-7xl mx-auto px-6 py-2">
            <ActivityTicker />
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        <Routes>
          <Route path="/" element={<Docket />} />
          <Route path="/dispute/:id" element={<DisputeDetail />} />
          <Route path="/chaos" element={<ChaosLabPage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
        </Routes>
      </main>
    </div>
  )
}
