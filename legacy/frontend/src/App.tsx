import { useCallback, useEffect, useState } from 'react'
import { api, type User } from './api'
import { getToken, signOut } from './auth'
import { useRoute } from './router'
import { SessionContext } from './session'
import SignIn from './SignIn'
import { TABS } from './tabs'

export default function App() {
  const route = useRoute()
  const [signedIn, setSignedIn] = useState(() => getToken() !== null)
  const [user, setUser] = useState<User | null>(null)
  const [error, setError] = useState('')

  const loadUser = useCallback(() => {
    if (!getToken()) return
    setError('')
    api.me().then(setUser).catch((e) => setError(String(e)))
  }, [])

  useEffect(() => {
    const onAuthChange = () => {
      const has = getToken() !== null
      setSignedIn(has)
      if (!has) setUser(null)
    }
    window.addEventListener('auth:changed', onAuthChange)
    return () => window.removeEventListener('auth:changed', onAuthChange)
  }, [])

  useEffect(() => {
    if (signedIn) loadUser()
  }, [signedIn, loadUser])

  if (!signedIn) return <SignIn onSignedIn={() => setSignedIn(true)} />

  const tabs = TABS.filter((t) => !t.roles || (user !== null && t.roles.includes(user.role)))
  const active = tabs.find((t) => t.key === route.path[0]) ?? tabs[0]

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
          Signed in as <b>{user?.name ?? '...'}</b>
          {user && <span className="muted"> ({user.email})</span>}
          <span className="sep">|</span>
          Role: <b>{user?.title ?? '-'}</b>
        </div>
        <div>
          {new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
          <span className="sep">|</span>
          <a href="#/dashboard" onClick={() => alert('Contact the IT Service Desk at ext. 4357.')}>Help</a>
          <span className="sep">|</span>
          <a href="#/dashboard" onClick={(e) => { e.preventDefault(); signOut() }}>Sign out</a>
        </div>
      </div>

      <div className="tabs">
        {tabs.map((t) => (
          <a key={t.key} href={`#/${t.key}`} className={t.key === active.key ? 'active' : ''}>
            {t.label}
          </a>
        ))}
      </div>

      <div className="content">
        {error ? (
          <div className="alert alert-red">
            {error.startsWith('403')
              ? `Your account is not set up for the Credit Portal. Contact the IT Service Desk. (${error})`
              : `Unable to contact the Credit Portal server. Please try again later. (${error})`}
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
        <span>{error ? 'Error' : 'Ready'}</span>
        <span>Server: CRPRD01 &nbsp;|&nbsp; DB: CREDITDB</span>
      </div>
    </div>
  )
}
