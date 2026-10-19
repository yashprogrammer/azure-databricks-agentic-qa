import { useState, type FormEvent } from 'react'
import { signIn } from './auth'

/** Single sign-on page. Locally it signs in against the development identity provider;
 *  on Azure this page is replaced by the Microsoft Entra ID sign-in (MSAL redirect). */
export default function SignIn({ onSignedIn }: { onSignedIn: () => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await signIn(username, password)
      onSignedIn()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="frame">
      <div className="banner">
        <div className="logo">
          <div className="mark">C</div>
          <div className="name">
            CONTOSO BANK
            <small>SINGLE SIGN-ON</small>
          </div>
        </div>
        <div className="sys">
          <b>Commercial Credit System</b>
          <br />
          Credit Portal v4.2.1
        </div>
      </div>
      <div className="content" style={{ display: 'flex', justifyContent: 'center', paddingTop: 50 }}>
        <div style={{ width: 420 }}>
          <div className="alert" style={{ fontSize: 10 }}>
            <b>DEVELOPMENT IDENTITY PROVIDER</b> &mdash; stands in for Microsoft Entra ID when running locally. Test
            accounts and the development password are listed in <span className="mono">legacy/README.md</span>.
          </div>
          <div className="panel">
            <div className="panel-title">Sign in to Contoso Bank</div>
            <div className="panel-body">
              <form onSubmit={submit}>
                <table className="form">
                  <tbody>
                    <tr>
                      <td className="lbl">User ID</td>
                      <td>
                        <input type="text" style={{ width: 230 }} autoFocus autoComplete="username" placeholder="name@contoso.example"
                          value={username} onChange={(e) => setUsername(e.target.value)} />
                      </td>
                    </tr>
                    <tr>
                      <td className="lbl">Password</td>
                      <td>
                        <input type="password" style={{ width: 230, font: '11px Verdana', border: '1px solid #7f9db9', padding: '2px 3px' }}
                          autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
                      </td>
                    </tr>
                    <tr>
                      <td></td>
                      <td style={{ paddingTop: 6 }}>
                        <button className="primary" type="submit" disabled={busy || !username || !password}>
                          {busy ? 'Signing in...' : 'Sign In'}
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </form>
              {error && <div className="alert alert-red" style={{ marginTop: 8, marginBottom: 0 }}>{error}</div>}
            </div>
          </div>
          <p className="muted small">
            Authorised users only. Access is logged and monitored. Forgotten your password? Contact the IT Service
            Desk, ext. 4357.
          </p>
        </div>
      </div>
      <div className="footer">
        Contoso Bank N.A. &mdash; CONFIDENTIAL: for internal use only. All activity is monitored.
      </div>
    </div>
  )
}
