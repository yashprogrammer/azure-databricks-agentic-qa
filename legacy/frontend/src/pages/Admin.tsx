import { useEffect, useState } from 'react'
import { adminApi, type DirectoryEntry, type PortalUser } from '../api'
import { useSession } from '../session'

export default function Admin() {
  const me = useSession()
  const [users, setUsers] = useState<PortalUser[]>([])
  const [roles, setRoles] = useState<{ role: string; label: string }[]>([])
  const [q, setQ] = useState('')
  const [results, setResults] = useState<DirectoryEntry[] | null>(null)
  const [grantRole, setGrantRole] = useState<Record<string, string>>({})
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const load = () => adminApi.users().then(setUsers).catch((e) => setError(String(e)))
  useEffect(() => {
    load()
    adminApi.roles().then(setRoles)
  }, [])

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setError('')
    try {
      await fn()
      setMessage(`${ok} (${new Date().toLocaleTimeString()})`)
      await load()
      if (results) setResults(await adminApi.directory(q))
    } catch (e) {
      setError(String(e))
    }
  }

  const search = () => adminApi.directory(q).then(setResults).catch((e) => setError(String(e)))
  const label = (role: string) => roles.find((r) => r.role === role)?.label ?? role

  const changeRole = (u: PortalUser, role: string) => {
    if (!confirm(`Change ${u.name}'s role from "${u.role_label}" to "${label(role)}"? This takes effect immediately.`)) return
    run(() => adminApi.update(u.email, { role }), `${u.name} is now ${label(role)}`)
  }
  const setActive = (u: PortalUser, active: boolean) => {
    if (!active && !confirm(`Deactivate ${u.name}? They will lose Credit Portal access immediately.`)) return
    run(() => adminApi.update(u.email, { active }), `${u.name} ${active ? 'reactivated' : 'deactivated'}`)
  }

  return (
    <>
      <h2>Administration &mdash; Portal Users</h2>
      <div className="notice" style={{ marginBottom: 8 }}>
        Bank identities, passwords and MFA are managed by IT Identity &amp; Access Management in the corporate directory.
        Here you control <b>Credit Portal access</b>: grant access to an employee, set their role, and deactivate leavers.
        Changes take effect immediately and are recorded in the activity log.
      </div>
      {message && <div className="notice" style={{ marginBottom: 8 }}>{message}</div>}
      {error && <div className="alert alert-red">{error}</div>}

      <div className="panel">
        <div className="panel-title">
          Portal Users
          <span className="small" style={{ fontWeight: 'normal' }}>
            {users.filter((u) => u.active).length} active / {users.length} total
          </span>
        </div>
        <div className="panel-body">
          <table className="grid">
            <thead>
              <tr><th>Name</th><th>User ID</th><th>Title</th><th>Portal Role</th><th>Status</th><th>Portfolio</th><th>Open Memos</th><th></th></tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const self = u.email === me.email
                return (
                  <tr key={u.email}>
                    <td>{u.name}{self && <span className="muted"> (you)</span>}</td>
                    <td className="mono">{u.email}</td>
                    <td>{u.title}</td>
                    <td>
                      <select value={u.role} disabled={self || !u.active} onChange={(e) => changeRole(u, e.target.value)}>
                        {roles.map((r) => <option key={r.role} value={r.role}>{r.label}</option>)}
                      </select>
                    </td>
                    <td>{u.active ? <span className="status status-Approved">Active</span> : <span className="status status-Returned">Deactivated</span>}</td>
                    <td className="num">{u.portfolio_size}</td>
                    <td className="num">{u.open_memos}</td>
                    <td>
                      {u.active ? (
                        <button disabled={self} onClick={() => setActive(u, false)}>Deactivate</button>
                      ) : (
                        <button onClick={() => setActive(u, true)}>Reactivate</button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <div className="muted small" style={{ marginTop: 4 }}>
            You cannot change your own role or deactivate your own account; ask another administrator.
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Grant Portal Access</div>
        <div className="panel-body">
          <div className="toolbar">
            Find employee (name, user ID or job title):
            <input type="text" style={{ width: 240 }} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search()} />
            <button onClick={search}>Search Directory</button>
          </div>
          {results && (
            <table className="grid">
              <thead>
                <tr><th>Name</th><th>User ID</th><th>Job Title</th><th>Portal Access</th><th>Grant as</th><th></th></tr>
              </thead>
              <tbody>
                {results.map((p) => (
                  <tr key={p.email}>
                    <td>{p.name}</td>
                    <td className="mono">{p.email}</td>
                    <td>{p.job_title}</td>
                    <td>
                      {p.has_access ? (
                        <>{label(p.role!)}{p.active ? '' : ' (deactivated)'}</>
                      ) : (
                        <span className="muted">No access</span>
                      )}
                    </td>
                    <td>
                      {!p.has_access && (
                        <select value={grantRole[p.email] ?? 'analyst'} onChange={(e) => setGrantRole({ ...grantRole, [p.email]: e.target.value })}>
                          {roles.map((r) => <option key={r.role} value={r.role}>{r.label}</option>)}
                        </select>
                      )}
                    </td>
                    <td>
                      {!p.has_access && (
                        <button
                          className="primary"
                          onClick={() => run(() => adminApi.grant(p.email, grantRole[p.email] ?? 'analyst'), `Granted ${p.name} access as ${label(grantRole[p.email] ?? 'analyst')}`)}
                        >
                          Grant Access
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {results.length === 0 && <tr><td colSpan={6} className="muted">No employees found.</td></tr>}
              </tbody>
            </table>
          )}
          <div className="muted small" style={{ marginTop: 4 }}>
            New analysts start with an empty portfolio. Borrower portfolio assignment is handled by Credit Administration.
          </div>
        </div>
      </div>
    </>
  )
}
