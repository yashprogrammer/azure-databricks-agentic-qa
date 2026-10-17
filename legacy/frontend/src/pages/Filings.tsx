import { useEffect, useMemo, useState } from 'react'
import { api, type Filing } from '../api'
import { go, type Route } from '../router'

const LINES_PER_PAGE = 400

export default function Filings({ route }: { route: Route }) {
  const id = route.path[1]
  return id ? <FilingViewer id={Number(id)} line={Number(route.query.get('line') ?? 0)} /> : <FilingLibrary />
}

function FilingLibrary() {
  const [rows, setRows] = useState<Filing[]>([])
  useEffect(() => {
    api.filings().then(setRows)
  }, [])
  return (
    <>
      <h2>Filing Library</h2>
      <div className="notice" style={{ marginBottom: 8 }}>
        10-K annual reports are downloaded automatically from SEC EDGAR by the nightly job and stored in the
        document store. Documents are displayed as plain text.
      </div>
      <table className="grid">
        <thead>
          <tr><th>Ticker</th><th>Form</th><th>Accession No.</th><th>Filing Date</th><th>Size</th><th>Lines</th><th>Downloaded</th><th></th></tr>
        </thead>
        <tbody>
          {rows.map((f) => (
            <tr key={f.filing_id}>
              <td className="mono"><a href={`#/borrowers/${f.borrower_id}`}>{f.ticker}</a></td>
              <td>{f.form_type}</td>
              <td className="mono">{f.accession_number}</td>
              <td>{f.filing_date}</td>
              <td className="num">{(f.size_bytes / 1024).toFixed(0)} KB</td>
              <td className="num">{f.line_count.toLocaleString()}</td>
              <td>{f.downloaded_at.replace('T', ' ')}</td>
              <td><a href={`#/filings/${f.filing_id}`}>View</a></td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

function FilingViewer({ id, line }: { id: number; line: number }) {
  const [meta, setMeta] = useState<Filing | null>(null)
  const [lines, setLines] = useState<string[]>([])
  const [find, setFind] = useState('')
  const [gotoLine, setGotoLine] = useState('')
  const [page, setPage] = useState(1)

  useEffect(() => {
    api.filing(id).then(setMeta)
    api.filingText(id).then((d) => setLines(d.text.split('\n')))
  }, [id])

  const pages = Math.max(1, Math.ceil(lines.length / LINES_PER_PAGE))
  useEffect(() => {
    if (line > 0) setPage(Math.ceil(line / LINES_PER_PAGE))
  }, [line])
  useEffect(() => {
    if (line > 0) document.getElementById(`L${line}`)?.scrollIntoView({ block: 'center' })
  }, [line, page, lines])

  const start = (page - 1) * LINES_PER_PAGE
  const visible = lines.slice(start, start + LINES_PER_PAGE)
  const needle = find.trim().toLowerCase()
  const findHits = useMemo(
    () => (needle.length > 1 ? lines.flatMap((l, i) => (l.toLowerCase().includes(needle) ? [i + 1] : [])) : []),
    [needle, lines],
  )

  return (
    <>
      <div className="breadcrumb">
        <a href="#/filings">Filing Library</a> &raquo; {meta?.ticker} {meta?.form_type} {meta?.accession_number}
      </div>
      <h2>
        {meta?.ticker} &mdash; Form {meta?.form_type} filed {meta?.filing_date}
      </h2>
      <div className="toolbar">
        <button disabled={page <= 1} onClick={() => setPage(1)}>|&laquo;</button>
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>&laquo; Prev</button>
        <span>
          Page <b>{page}</b> of {pages}
        </span>
        <button disabled={page >= pages} onClick={() => setPage(page + 1)}>Next &raquo;</button>
        <button disabled={page >= pages} onClick={() => setPage(pages)}>&raquo;|</button>
        <span className="muted" style={{ marginLeft: 12 }}>Go to line:</span>
        <input type="number" style={{ width: 70 }} value={gotoLine} onChange={(e) => setGotoLine(e.target.value)} />
        <button onClick={() => gotoLine && go(`#/filings/${id}?line=${gotoLine}`)}>Go</button>
        <span className="muted" style={{ marginLeft: 12 }}>Find in document:</span>
        <input type="text" value={find} onChange={(e) => setFind(e.target.value)} />
        {needle.length > 1 && (
          <span>
            {findHits.length} line(s){' '}
            {findHits.length > 0 && (
              <button onClick={() => go(`#/filings/${id}?line=${findHits.find((h) => h > (line || 0)) ?? findHits[0]}`)}>
                Next match
              </button>
            )}
          </span>
        )}
      </div>
      <div className="viewer">
        {visible.length === 0 && <div className="muted" style={{ padding: 8 }}>Loading document...</div>}
        {visible.map((text, i) => {
          const no = start + i + 1
          return (
            <div key={no} id={`L${no}`} className={`ln${no === line ? ' hit' : ''}`}>
              <span className="no">{no}</span>
              <span className="tx">{needle.length > 1 ? highlight(text, needle) : text}</span>
            </div>
          )
        })}
      </div>
    </>
  )
}

function highlight(text: string, needle: string) {
  const idx = text.toLowerCase().indexOf(needle)
  if (idx < 0) return text
  return (
    <>
      {text.slice(0, idx)}
      <mark>{text.slice(idx, idx + needle.length)}</mark>
      {text.slice(idx + needle.length)}
    </>
  )
}
