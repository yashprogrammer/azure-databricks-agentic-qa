import { useEffect, useState } from 'react'
import { api, type Borrower, type SearchHit } from '../api'
import { go, type Route } from '../router'

export default function Search({ route }: { route: Route }) {
  const [q, setQ] = useState(route.query.get('q') ?? '')
  const [borrowerId, setBorrowerId] = useState(route.query.get('b') ?? '')
  const [borrowers, setBorrowers] = useState<Borrower[]>([])
  const [result, setResult] = useState<{ hits: SearchHit[]; truncated: boolean } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.borrowers().then(setBorrowers)
  }, [])

  useEffect(() => {
    const query = route.query.get('q')
    if (!query) return
    setBusy(true)
    setError('')
    api
      .search(query, route.query.get('b') || undefined)
      .then(setResult)
      .catch((e) => setError(String(e)))
      .finally(() => setBusy(false))
  }, [route.query])

  const submit = () => q.trim().length > 1 && go(`#/search?q=${encodeURIComponent(q.trim())}${borrowerId ? `&b=${borrowerId}` : ''}`)

  return (
    <>
      <h2>Keyword Search</h2>
      <fieldset>
        <legend>Search Filings</legend>
        <div className="toolbar">
          Keyword or phrase:
          <input type="text" style={{ width: 260 }} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && submit()} />
          Borrower:
          <select value={borrowerId} onChange={(e) => setBorrowerId(e.target.value)}>
            <option value="">(All borrowers)</option>
            {borrowers.map((b) => (
              <option key={b.borrower_id} value={b.borrower_id}>
                {b.ticker} - {b.name}
              </option>
            ))}
          </select>
          <button className="primary" onClick={submit}>Search</button>
        </div>
        <div className="muted small">
          Exact text match, not case sensitive. Tip: use specific terms, e.g. "covenant", "revolving credit facility".
        </div>
      </fieldset>
      {error && <div className="alert alert-red">{error}</div>}
      {busy && <div className="muted">Searching... this may take a moment.</div>}
      {result && !busy && (
        <>
          <div style={{ margin: '6px 0' }}>
            <b>{result.hits.length}</b> matching line(s){result.truncated && ' (first 200 shown)'}
          </div>
          <table className="grid">
            <thead>
              <tr><th>Ticker</th><th>Accession No.</th><th>Line</th><th>Text</th></tr>
            </thead>
            <tbody>
              {result.hits.map((h, i) => (
                <tr key={i}>
                  <td className="mono">{h.ticker}</td>
                  <td className="mono">{h.accession_number}</td>
                  <td className="num"><a href={`#/filings/${h.filing_id}?line=${h.line}`}>{h.line}</a></td>
                  <td>{h.snippet}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </>
  )
}
