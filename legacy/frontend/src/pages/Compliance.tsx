import { useEffect, useState } from 'react'
import { api, type RestrictedRow } from '../api'

export default function Compliance() {
  const [rows, setRows] = useState<RestrictedRow[]>([])
  useEffect(() => {
    api.restricted().then(setRows)
  }, [])

  return (
    <>
      <h2>Compliance &mdash; Restricted List</h2>
      <div className="alert">
        <b>Information barrier policy (CP-114):</b> Credit analysts must not perform research on borrowers on the
        Restricted List. Analysts attest to compliance quarterly. Questions: Compliance, ext. 2210.
      </div>
      <table className="grid">
        <thead>
          <tr><th>Borrower ID</th><th>Ticker</th><th>Name</th><th>Reason</th><th>Effective From</th><th>Added By</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.borrower_id}>
              <td><a href={`#/borrowers/${r.borrower_id}`}>{r.borrower_id}</a></td>
              <td className="mono">{r.ticker}</td>
              <td>{r.name}</td>
              <td>{r.reason}</td>
              <td>{r.effective_from}</td>
              <td>{r.added_by}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        Restricted List maintenance is performed by Compliance through the Compliance Desk application.
      </p>
    </>
  )
}
