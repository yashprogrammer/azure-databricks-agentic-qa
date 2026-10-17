import { useEffect, useState } from 'react'
import { api, type User } from './api'
import { go, useRoute } from './router'
import { SESSION_KEY, SessionContext } from './session'
import { TABS } from './tabs'

export default function App() {
  const route = useRoute()
  const [users, setUsers] = useState<User[]>([])
  const [userEmail, setUserEmail] = useState(
    () => localStorage.getItem(SESSION_KEY) ?? 'm.lee@contoso.example',
  )
  const [connected, setConnected] = useState(true)

  useEffect(() => {
    api.users().then(setUsers).catch(() => setConnected(false))
  }, [])

  const user = users.find((u) => u.email === userEmail) ?? null
  const active = TABS.find((t) => t.key === route.path[0]) ?? TABS[0]

  const switchUser = (email: string) => {
    localStorage.setItem(SESSION_KEY, email)
    setUserEmail(email)
    go('#/dashboard')
  }

  return (
    <div className="frame">
      <div className="banner">
        <div className="logo">
          <div className="mark">C</div>
          <div className="name">
            CONTOSO BANK
            <small>COMMERCIAL &amp; CORPORATE BANKING</small>
          </div>
        </div>
        <div className="sys">
          <b>Commercial Credit System</b>
          <br />
          Credit Portal v4.2.1
        </div>
      </div>

      <div className="userbar">
        <div>
          User:{' '}
          <select value={userEmail} onChange={(e) => switchUser(e.target.value)}>
            {users.map((u) => (
              <option key={u.email} value={u.email}>
                {u.name} ({u.email})
              </option>
            ))}
          </select>
          <span className="sep">|</span>
          Role: <b>{user?.title ?? '-'}</b>
        </div>
        <div>
          {new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
          <span className="sep">|</span>
          <a href="#/dashboard" onClick={() => alert('Contact the IT Service Desk at ext. 4357.')}>Help</a>
          <span className="sep">|</span>
          <a href="#/dashboard" onClick={() => alert('Session ended. Please close your browser.')}>Log off</a>
        </div>
      </div>

      <div className="tabs">
        {TABS.map((t) => (
          <a key={t.key} href={`#/${t.key}`} className={t.key === active.key ? 'active' : ''}>
            {t.label}
          </a>
        ))}
      </div>

      <div className="content">
        {!connected ? (
          <div className="alert alert-red">
            Unable to contact the Credit Portal server. Please try again later or call the IT Service Desk.
          </div>
        ) : user ? (
          <SessionContext.Provider value={user}>{active.render(route)}</SessionContext.Provider>
        ) : (
          <div className="muted">Loading...</div>
        )}
      </div>

      <div className="footer">
        Contoso Bank N.A. &mdash; Commercial Credit System 4.2.1 (Build 2011.03.14) &mdash; CONFIDENTIAL: for
        internal use only. All activity is monitored. Session timeout 15 minutes.
      </div>
      <div className="statusbar">
        <span>{connected ? 'Ready' : 'Disconnected'}</span>
        <span>Server: CRPRD01 &nbsp;|&nbsp; DB: CREDITDB</span>
      </div>
    </div>
  )
}
