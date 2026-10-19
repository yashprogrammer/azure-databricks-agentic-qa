import { useEffect, useState } from 'react'
import { api, fmtMoney, type Borrower, type BorrowerDetail } from '../api'
import { go, type Route } from '../router'
import { useSession } from '../session'

export default function Borrowers({ route }: { route: Route }) {
  const id = route.path[1]
  return id ? <BorrowerProfile id={id} /> : <BorrowerList />
}

function BorrowerList() {
  const [rows, setRows] = useState<Borrower[]>([])
  const [q, setQ] = useState('')
  const [mine, setMine] = useState(false)

  const load = () => api.borrowers(q, mine).then(setRows)
  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mine])

  return (
    <>
      <h2>Borrower Directory</h2>
      <div className="toolbar">
        Name / Ticker / ID:
        <input type="text" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && load()} />
        <button onClick={load}>Find</button>
        <label>
          <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> My portfolio only
        </label>
        <span className="muted">{rows.length} record(s)</span>
      </div>
      <table className="grid">
        <thead>
          <tr>
            <th>Borrower ID</th>
            <th>Name</th>
            <th>Ticker</th>
            <th>Sector</th>
            <th>Relationship Mgr</th>
            <th>Exposure</th>
            <th>Internal Rating</th>
            <th>Next Review</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b) => (
            <tr key={b.borrower_id}>
              <td><a href={`#/borrowers/${b.borrower_id}`}>{b.borrower_id}</a></td>
              <td>{b.name} {b.restricted && <span className="flag-restricted">RESTRICTED</span>}</td>
              <td className="mono">{b.ticker}</td>
              <td>{b.sector}</td>
              <td>{b.relationship_manager}</td>
              <td className="num">{fmtMoney(b.exposure_musd)}</td>
              <td>{b.internal_rating}</td>
              <td>{b.next_review}</td>
              <td>{b.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

function BorrowerProfile({ id }: { id: string }) {
  const user = useSession()
  const [b, setB] = useState<BorrowerDetail | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.borrower(id).then(setB).catch((e) => setError(String(e)))
  }, [id])

  if (error) return <div className="alert alert-red">{error}</div>
  if (!b) return <div className="muted">Loading borrower...</div>

  const createMemo = async () => {
    const { memo_id } = await api.createMemo(b.borrower_id)
    go(`#/memos/${memo_id}`)
  }

  return (
    <>
      <div className="breadcrumb">
        <a href="#/borrowers">Borrowers</a> &raquo; {b.borrower_id}
      </div>
      <h2>
        {b.name} <span className="muted">({b.ticker})</span>
      </h2>
      {b.restriction && (
        <div className="alert alert-red">
          <b>RESTRICTED LIST:</b> {b.restriction.reason} (effective {b.restriction.effective_from}). Analysts
          must not perform credit research on this borrower. Contact Compliance before proceeding.
        </div>
      )}
      <div className="row">
        <div className="col">
          <fieldset>
            <legend>Borrower Profile</legend>
            <table className="form">
              <tbody>
                <tr><td className="lbl">Borrower ID</td><td>{b.borrower_id}</td></tr>
                <tr><td className="lbl">Legal Name</td><td>{b.name}</td></tr>
                <tr><td className="lbl">Ticker / CIK</td><td className="mono">{b.ticker} / {b.cik ?? 'n/a'}</td></tr>
                <tr><td className="lbl">Sector</td><td>{b.sector}</td></tr>
                <tr><td className="lbl">Relationship Manager</td><td>{b.relationship_manager}</td></tr>
                <tr><td className="lbl">Status</td><td>{b.status}</td></tr>
              </tbody>
            </table>
          </fieldset>
        </div>
        <div className="col">
          <fieldset>
            <legend>Credit Summary</legend>
            <table className="form">
              <tbody>
                <tr><td className="lbl">Total Exposure</td><td>{fmtMoney(b.exposure_musd)}</td></tr>
                <tr><td className="lbl">Internal Rating</td><td>{b.internal_rating}</td></tr>
                <tr><td className="lbl">Next Annual Review</td><td>{b.next_review}</td></tr>
                <tr><td className="lbl">Covering Analyst(s)</td><td>{b.covering_analysts.join(', ') || '-'}</td></tr>
              </tbody>
            </table>
          </fieldset>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">SEC Filings on File</div>
        <div className="panel-body">
          {b.filings.length === 0 ? (
            <div className="muted">No filings downloaded yet. The nightly job runs at 01:00 ET.</div>
          ) : (
            <table className="grid">
              <thead>
                <tr><th>Form</th><th>Accession No.</th><th>Filing Date</th><th>Lines</th><th>Downloaded</th><th></th></tr>
              </thead>
              <tbody>
                {b.filings.map((f) => (
                  <tr key={f.filing_id}>
                    <td>{f.form_type}</td>
                    <td className="mono">{f.accession_number}</td>
                    <td>{f.filing_date}</td>
                    <td className="num">{f.line_count.toLocaleString()}</td>
                    <td>{f.downloaded_at.replace('T', ' ')}</td>
                    <td><a href={`#/filings/${f.filing_id}`}>View document</a></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">
          Credit Memos
          {user.role === 'analyst' && b.covering_analysts.includes(user.email) && (
            <button onClick={createMemo}>Create Credit Memo</button>
          )}
        </div>
        <div className="panel-body">
          <table className="grid">
            <thead>
              <tr><th>Memo ID</th><th>Review Year</th><th>Analyst</th><th>Status</th><th>Last Updated</th></tr>
            </thead>
            <tbody>
              {b.memos.map((m) => (
                <tr key={m.memo_id}>
                  <td><a href={`#/memos/${m.memo_id}`}>{m.memo_id}</a></td>
                  <td>{m.review_year}</td>
                  <td>{m.analyst_email}</td>
                  <td><span className={`status status-${m.status}`}>{m.status}</span></td>
                  <td>{m.updated_at.replace('T', ' ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
