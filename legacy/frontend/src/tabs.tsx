import type { ReactNode } from 'react'
import AiDraft from './ai/AiDraft'
import type { Route } from './router'
import Admin from './pages/Admin'
import Borrowers from './pages/Borrowers'
import Compliance from './pages/Compliance'
import Dashboard from './pages/Dashboard'
import Filings from './pages/Filings'
import Memos from './pages/Memos'
import Search from './pages/Search'

// `roles`: portal roles that see the tab (omitted = everyone). The API enforces the same rule.
export type Tab = { key: string; label: string; render: (route: Route) => ReactNode; roles?: string[] }

// Main navigation of the Credit Portal. Order = order of the tab strip.
export const TABS: Tab[] = [
  { key: 'dashboard', label: 'Dashboard', render: () => <Dashboard /> },
  { key: 'borrowers', label: 'Borrowers', render: (r) => <Borrowers route={r} /> },
  { key: 'filings', label: 'Filing Library', render: (r) => <Filings route={r} /> },
  { key: 'memos', label: 'Credit Memos', render: (r) => <Memos route={r} /> },
  { key: 'search', label: 'Keyword Search', render: (r) => <Search route={r} /> },
  { key: 'compliance', label: 'Compliance', render: () => <Compliance /> },
  // Integration: the only change to the legacy navigation.
  { key: 'ai-draft', label: 'AI Credit Memo Draft', render: (r) => <AiDraft route={r} />, roles: ['analyst', 'credit_officer', 'compliance'] },
  { key: 'admin', label: 'Administration', render: () => <Admin />, roles: ['admin'] },
]
