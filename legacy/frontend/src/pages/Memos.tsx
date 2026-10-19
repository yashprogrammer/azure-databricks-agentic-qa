import { useEffect, useState } from 'react'
import { api, type Memo, type MemoDetail } from '../api'
import type { Route } from '../router'
import { useSession } from '../session'

export default function Memos({ route }: { route: Route }) {
  const id = route.path[1]
  return id ? <MemoEditor id={id} /> : <MemoList />
}

function MemoList() {
  const user = useSession()
  const [rows, setRows] = useState<Memo[]>([])
  const [status, setStatus] = useState('')
  const [mine, setMine] = useState(user.role === 'analyst')

  useEffect(() => {
    api.memos(mine, status || undefined).then(setRows)
  }, [mine, status])

  return (
    <>
      <h2>Credit Memos</h2>
      <div className="toolbar">
        Status:
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">(All)</option>
          <option>Draft</option>
          <option>Submitted</option>
          <option>Returned</option>
          <option>Approved</option>
        </select>
        <label>
          <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> My memos only
        </label>
        <span className="muted">
          To start a new memo, open the borrower from the <a href="#/borrowers">Borrowers</a> tab.
        </span>
      </div>
      <table className="grid">
        <thead>
          <tr><th>Memo ID</th><th>Borrower</th><th>Ticker</th><th>Review Year</th><th>Analyst</th><th>Status</th><th>Last Updated</th></tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.memo_id}>
              <td><a href={`#/memos/${m.memo_id}`}>{m.memo_id}</a></td>
              <td>{m.borrower_name}</td>
              <td className="mono">{m.ticker}</td>
              <td>{m.review_year}</td>
              <td>{m.analyst_email}</td>
              <td><span className={`status status-${m.status}`}>{m.status}</span></td>
              <td>{m.updated_at.replace('T', ' ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

function MemoEditor({ id }: { id: string }) {
  const user = useSession()
  const [memo, setMemo] = useState<MemoDetail | null>(null)
  const [bodies, setBodies] = useState<Record<string, string>>({})
  const [recommendation, setRecommendation] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const load = () =>
    api
      .memo(id)
      .then((m) => {
        setMemo(m)
        setBodies(Object.fromEntries(m.sections.map((s) => [s.section_type, s.body])))
        setRecommendation(m.recommendation)
      })
      .catch((e) => setError(String(e)))

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  if (error) return <div className="alert alert-red">{error}</div>
  if (!memo) return <div className="muted">Loading memo...</div>

  const editable = (memo.status === 'Draft' || memo.status === 'Returned') && user.email === memo.analyst_email
  const isOfficer = user.role === 'credit_officer'

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setError('')
    try {
      await fn()
      setMessage(`${ok} (${new Date().toLocaleTimeString()})`)
      await load()
    } catch (e) {
      setError(String(e))
    }
  }

  const saveAll = () =>
    run(async () => {
      for (const s of memo.sections) {
        if ((bodies[s.section_type] ?? '') !== s.body) {
          await api.saveSection(memo.memo_id, s.section_type, bodies[s.section_type] ?? '')
        }
      }
      if (recommendation !== memo.recommendation) {
        await api.saveRecommendation(memo.memo_id, recommendation)
      }
    }, 'Memo saved')

  return (
    <>
      <div className="breadcrumb">
        <a href="#/memos">Credit Memos</a> &raquo; {memo.memo_id}
      </div>
      <h2>
        Credit Memo {memo.memo_id} &mdash; {memo.borrower_name} ({memo.ticker})
      </h2>
      <fieldset>
        <legend>Memo Header</legend>
        <table className="form">
          <tbody>
            <tr>
              <td className="lbl">Borrower</td>
              <td><a href={`#/borrowers/${memo.borrower_id}`}>{memo.borrower_id}</a> {memo.borrower_name}</td>
              <td className="lbl">Review Year</td>
              <td>{memo.review_year}</td>
            </tr>
            <tr>
              <td className="lbl">Prepared By</td>
              <td>{memo.analyst_email}</td>
              <td className="lbl">Status</td>
              <td><span className={`status status-${memo.status}`}>{memo.status}</span></td>
            </tr>
            <tr>
              <td className="lbl">Approver</td>
              <td>{memo.approver_email ?? '-'}</td>
              <td className="lbl">Last Updated</td>
              <td>{memo.updated_at.replace('T', ' ')}</td>
            </tr>
          </tbody>
        </table>
      </fieldset>

      {message && <div className="notice" style={{ marginBottom: 8 }}>{message}</div>}
      {!editable && memo.status !== 'Approved' && (
        <div className="alert">This memo is read-only for you (status: {memo.status}).</div>
      )}

      {memo.sections.map((s) => (
        <div className="panel" key={s.section_type}>
          <div className="panel-title">
            {s.title}
            <span className="small" style={{ fontWeight: 'normal' }}>
              {s.updated_by ? `Last edited by ${s.updated_by} on ${s.updated_at?.replace('T', ' ')}` : 'Not started'}
            </span>
          </div>
          <div className="panel-body">
            <textarea
              rows={7}
              value={bodies[s.section_type] ?? ''}
              disabled={!editable}
              onChange={(e) => setBodies({ ...bodies, [s.section_type]: e.target.value })}
            />
          </div>
        </div>
      ))}

      <div className="panel">
        <div className="panel-title">7. Recommendation</div>
        <div className="panel-body">
          <textarea rows={3} value={recommendation} disabled={!editable} onChange={(e) => setRecommendation(e.target.value)} />
        </div>
      </div>

      <div className="toolbar">
        {editable && (
          <>
            <button className="primary" onClick={saveAll}>Save Memo</button>
            <button onClick={() => run(() => api.transition(memo.memo_id, 'submit'), 'Submitted for approval')}>
              Submit for Approval
            </button>
          </>
        )}
        {isOfficer && memo.status === 'Submitted' && (
          <>
            <button className="primary" onClick={() => run(() => api.transition(memo.memo_id, 'approve'), 'Memo approved')}>
              Approve
            </button>
            <button onClick={() => run(() => api.transition(memo.memo_id, 'return'), 'Memo returned to analyst')}>
              Return to Analyst
            </button>
          </>
        )}
        <button onClick={() => window.print()}>Print</button>
      </div>
    </>
  )
}
