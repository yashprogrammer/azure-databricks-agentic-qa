import { useEffect, useState } from 'react'
import { api, fmtMoney } from '../api'
import { useSession } from '../session'

type Data = Awaited<ReturnType<typeof api.dashboard>>

export default function Dashboard() {
  const user = useSession()
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setData(null)
    api.dashboard().then(setData).catch((e) => setError(String(e)))
  }, [user.email])

  if (error) return <div className="alert alert-red">{error}</div>
  if (!data) return <div className="muted">Loading dashboard...</div>

  const statuses = ['Draft', 'Submitted', 'Returned', 'Approved']

  return (
    <>
      <h2>Welcome, {user.name}</h2>
      <div className="alert">
        <b>System notice:</b> Scheduled maintenance this Saturday 22:00&ndash;02:00 ET. The Credit Portal will be
        unavailable. Filing downloads run nightly at 01:00 ET.
      </div>
      <div className="row">
        <div className="col" style={{ flex: 2 }}>
          <div className="panel">
            <div className="panel-title">My Annual Review Queue</div>
            <div className="panel-body">
              {data.work_queue.length === 0 ? (
                <div className="muted">No borrowers assigned to your portfolio.</div>
              ) : (
                <table className="grid">
                  <thead>
                    <tr>
                      <th>Borrower ID</th>
                      <th>Name</th>
                      <th>Ticker</th>
                      <th>Rating</th>
                      <th>Exposure</th>
                      <th>Next Review</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.work_queue.map((b) => (
                      <tr key={b.borrower_id}>
                        <td><a href={`#/borrowers/${b.borrower_id}`}>{b.borrower_id}</a></td>
                        <td>{b.name}</td>
                        <td className="mono">{b.ticker}</td>
                        <td>{b.internal_rating}</td>
                        <td className="num">{fmtMoney(b.exposure_musd)}</td>
                        <td>{b.next_review}</td>
                        <td>{b.restricted && <span className="flag-restricted">RESTRICTED</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
        <div className="col">
          <div className="panel">
            <div className="panel-title">My Credit Memos</div>
            <div className="panel-body">
              <table className="grid">
                <tbody>
                  {statuses.map((s) => (
                    <tr key={s}>
                      <td><span className={`status status-${s}`}>{s}</span></td>
                      <td className="num">{data.memo_counts[s] ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ marginTop: 6 }}>
                <a href="#/memos">Go to Credit Memos &raquo;</a>
              </div>
            </div>
          </div>
          <div className="panel">
            <div className="panel-title">Filing Library</div>
            <div className="panel-body">
              <b>{data.filings_on_file}</b> 10-K filings on file. <a href="#/filings">Browse &raquo;</a>
            </div>
          </div>
          <div className="panel">
            <div className="panel-title">Recent Activity</div>
            <div className="panel-body small">
              {data.activity.map((a, i) => (
                <div key={i} style={{ borderBottom: '1px dotted #c5cdd8', padding: '2px 0' }}>
                  <span className="muted">{a.at.replace('T', ' ')}</span> &mdash; <b>{a.actor}</b>: {a.action}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
