import { Fragment, useEffect, useState } from 'react'
import { useSession } from '../session'
import { aiApi, type Citation, type DraftEvent, type DraftSection, type QuoteRef, type Version, type VersionSummary } from './aiApi'
import DocViewer from './DocViewer'

type Props = {
  memoId: string
  section: DraftSection
  filing: { filing_id: number; accession_number: string; filing_date: string } | null
  ticker: string
  canRun: boolean
  editable: boolean
  running: boolean
  onRun: (body: { analyst_email: string; feedback?: string; quotes?: QuoteRef[]; base_version?: number | null }) => Promise<void>
  reload: () => Promise<unknown>
}

type ObsTab = 'citations' | 'reasoning' | 'trace' | 'run' | 'history'

const REFUSAL_TEXT: Record<string, string> = {
  no_grounded_answer: 'The AI could not produce a draft where every statement is backed by a verified quote from the filing.',
  restricted_borrower: 'Blocked: borrower is on the Restricted List.',
  not_in_portfolio: 'Blocked: borrower is not in your portfolio.',
}

const versionLabel = (v: VersionSummary) => {
  const kind = v.origin === 'ai' ? 'AI draft' : v.origin === 'human' ? 'Analyst edit' : 'Restored'
  const why = v.feedback
    ? `regenerated from v${v.based_on} with feedback: “${v.feedback.slice(0, 60)}${v.feedback.length > 60 ? '…' : ''}”`
    : v.origin === 'human'
      ? `edited from v${v.based_on ?? '-'}`
      : 'initial agent run'
  return `v${v.version_no} · ${kind} · ${v.created_at.replace('T', ' ')} · ${why}`
}

export default function SectionWorkspace({ memoId, section, filing, ticker, canRun, editable, running, onRun, reload }: Props) {
  const user = useSession()
  const st = section.state
  const versions = section.versions
  const [viewingNo, setViewingNo] = useState<number | null>(st.current_version)
  const [version, setVersion] = useState<Version | null>(section.current)
  const [tab, setTab] = useState<ObsTab>('citations')
  const [selectedCite, setSelectedCite] = useState<number | null>(null)
  const [doc, setDoc] = useState<{ highlight: { start: number; end: number; label: string } | null } | null>(null)
  const [feedback, setFeedback] = useState('')
  const [quotes, setQuotes] = useState<QuoteRef[]>([])
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState('')
  const [events, setEvents] = useState<DraftEvent[]>([])
  const [error, setError] = useState('')

  // Follow the working version whenever it changes (new run, restore, approve).
  useEffect(() => {
    setViewingNo(st.current_version)
  }, [st.current_version])

  useEffect(() => {
    setSelectedCite(null)
    if (!viewingNo) return setVersion(null)
    if (section.current && section.current.version_no === viewingNo) return setVersion(section.current)
    aiApi.version(memoId, section.section_type, viewingNo).then(setVersion)
  }, [viewingNo, section.current, memoId, section.section_type])

  useEffect(() => {
    if (tab === 'history') aiApi.events(memoId).then((e) => setEvents(e.filter((x) => x.section_type === section.section_type)))
  }, [tab, memoId, section.section_type, versions.length])

  const act = async (fn: () => Promise<unknown>) => {
    setError('')
    try {
      await fn()
      await reload()
    } catch (e) {
      setError(String(e))
    }
  }

  const openCitation = (c: Citation) => {
    setSelectedCite(c.n)
    if (c.verified && c.start !== undefined && c.end !== undefined)
      setDoc({ highlight: { start: c.start, end: c.end, label: `citation [${c.n}], lines ${c.line_start}–${c.line_end}` } })
  }

  const regenerate = () =>
    act(async () => {
      await onRun({ analyst_email: user.email, feedback, quotes, base_version: viewingNo })
      setFeedback('')
      setQuotes([])
    })

  const isCurrent = viewingNo === st.current_version
  const idx = versions.findIndex((v) => v.version_no === viewingNo)
  const citeByN = new Map((version?.citations ?? []).map((c) => [c.n, c]))
  const verifiedCount = (version?.citations ?? []).filter((c) => c.verified).length

  const renderText = (text: string) =>
    text.split(/(\[\d+\])/).map((part, i) => {
      const m = part.match(/^\[(\d+)\]$/)
      if (!m) return <Fragment key={i}>{part}</Fragment>
      const c = citeByN.get(Number(m[1]))
      const cls = `ai-cite${!c?.verified ? ' bad' : ''}${selectedCite === Number(m[1]) ? ' sel' : ''}`
      return (
        <span key={i} className={cls} title={c ? `“${c.quote}”` : 'No source for this marker'} onClick={() => c && openCitation(c)}>
          {m[1]}
        </span>
      )
    })

  return (
    <div className="panel">
      <div className="panel-title">
        {section.title}
        <span className="small" style={{ fontWeight: 'normal' }}>
          {st.approved_version ? `Approved: v${st.approved_version}` : 'Not approved'}
          {st.saved_version ? ` · Saved to memo: v${st.saved_version}` : ''}
        </span>
      </div>
      <div className="panel-body">
        <div className="muted small" style={{ marginBottom: 6 }}>
          <b>Section brief:</b> {section.goal}
        </div>
        {error && <div className="alert alert-red">{error}</div>}

        {versions.length === 0 ? (
          <div className="notice">
            Not drafted yet.{' '}
            <button className="primary" disabled={!canRun || running} onClick={() => act(() => onRun({ analyst_email: user.email }))}>
              {running ? 'Drafting...' : 'Generate AI draft'}
            </button>
          </div>
        ) : (
          <>
            {/* ---------------------------------------------------------- time travel */}
            <div className="ai-versionbar">
              <b>Version</b>
              <button disabled={idx <= 0} onClick={() => setViewingNo(versions[idx - 1].version_no)} title="Older version">&laquo; Older</button>
              <select value={viewingNo ?? ''} onChange={(e) => setViewingNo(Number(e.target.value))}>
                {versions.map((v) => (
                  <option key={v.version_no} value={v.version_no}>
                    {versionLabel(v)}
                  </option>
                ))}
              </select>
              <button disabled={idx >= versions.length - 1} onClick={() => setViewingNo(versions[idx + 1].version_no)} title="Newer version">Newer &raquo;</button>
              <span className="small">({idx + 1} of {versions.length})</span>
              {isCurrent ? <span className="ai-badge run">WORKING VERSION</span> : <span className="ai-badge none">VIEWING OLDER VERSION</span>}
              {viewingNo === st.approved_version && <span className="ai-badge ok">APPROVED</span>}
              {viewingNo === st.saved_version && <span className="ai-badge saved">IN MEMO</span>}
              {!isCurrent && editable && (
                <button onClick={() => act(() => aiApi.setCurrent(memoId, section.section_type, user.email, viewingNo!))}>
                  Make v{viewingNo} the working version
                </button>
              )}
            </div>

            {/* ---------------------------------------------------------- draft */}
            {version && (
              <>
                {version.refusal_reason ? (
                  <div className="alert alert-red">
                    <b>Not grounded.</b> {REFUSAL_TEXT[version.refusal_reason] ?? version.refusal_reason} See the AI Reasoning
                    tab, or give feedback below and regenerate.
                  </div>
                ) : version.grounded ? (
                  <div className="small" style={{ marginBottom: 4 }}>
                    <span className="ai-badge ok">GROUNDED</span> {verifiedCount} of {version.citations.length} citation(s) verified
                    word-for-word against the 10-K. Click a number to see it in the filing.
                  </div>
                ) : (
                  <div className="alert" style={{ marginBottom: 4 }}>
                    <b>Review needed:</b> {version.warnings.join(' ')}
                  </div>
                )}
                {editing ? (
                  <>
                    <textarea rows={9} value={editText} onChange={(e) => setEditText(e.target.value)} />
                    <div className="toolbar" style={{ marginTop: 4 }}>
                      <button
                        className="primary"
                        onClick={() => act(async () => { await aiApi.edit(memoId, section.section_type, user.email, editText, viewingNo); setEditing(false) })}
                      >
                        Save as new version
                      </button>
                      <button onClick={() => setEditing(false)}>Cancel</button>
                      <span className="muted small">Keep the [n] markers to keep their verified sources.</span>
                    </div>
                  </>
                ) : (
                  <div className="ai-text">{version.text ? renderText(version.text) : <span className="muted">(empty draft)</span>}</div>
                )}

                {!editing && (
                  <div className="toolbar" style={{ marginTop: 6 }}>
                    <button
                      className="primary"
                      disabled={!editable || !version.text || viewingNo === st.approved_version}
                      onClick={() => act(() => aiApi.approve(memoId, section.section_type, user.email, version.version_no))}
                    >
                      Approve v{version.version_no}
                    </button>
                    <button disabled={!editable} onClick={() => { setEditText(version.text); setEditing(true) }}>Edit text</button>
                    <button disabled={!canRun || running} onClick={() => act(() => onRun({ analyst_email: user.email }))}>
                      {running ? 'Running agent...' : 'Re-run agent (no feedback)'}
                    </button>
                  </div>
                )}

                {/* ---------------------------------------------------------- observability */}
                <div className="ai-subtabs">
                  {(
                    [
                      ['citations', `Citations (${version.citations.length})`],
                      ['reasoning', 'AI Reasoning'],
                      ['trace', `Retrieval Trace (${version.trace.sources?.length ?? 0})`],
                      ['run', 'Run Details'],
                      ['history', 'History'],
                    ] as [ObsTab, string][]
                  ).map(([k, label]) => (
                    <a key={k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>{label}</a>
                  ))}
                </div>
                <div className="ai-subpanel">
                  {tab === 'citations' &&
                    (version.citations.length === 0 ? (
                      <span className="muted">No citations in this version.</span>
                    ) : (
                      <table className="grid">
                        <thead>
                          <tr><th>#</th><th>Quoted evidence</th><th>Location in 10-K</th><th>Check</th><th></th></tr>
                        </thead>
                        <tbody>
                          {version.citations.map((c) => (
                            <tr key={c.n} style={selectedCite === c.n ? { outline: '2px solid #c9a227' } : undefined}>
                              <td><span className={`ai-cite${c.verified ? '' : ' bad'}`}>{c.n}</span></td>
                              <td className="ai-quote">&ldquo;{c.quote}&rdquo;</td>
                              <td className="small">
                                {ticker} 10-K {version.trace.filing?.accession_number}
                                <br />
                                {c.verified ? `lines ${c.line_start}–${c.line_end} (source ${c.source})` : `cited ${c.source}`}
                              </td>
                              <td>{c.verified ? <span className="ai-badge ok">VERIFIED</span> : <span className="ai-badge warn">NOT FOUND</span>}</td>
                              <td style={{ whiteSpace: 'nowrap' }}>
                                {c.verified && (
                                  <>
                                    <button onClick={() => openCitation(c)}>Open in document</button>{' '}
                                    <a className="small" href={`#/filings/${c.filing_id}?line=${c.line_start}`} target="_blank" rel="noreferrer">
                                      Filing Library
                                    </a>
                                  </>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ))}

                  {tab === 'reasoning' && (
                    <>
                      <fieldset>
                        <legend>Why the AI wrote this</legend>
                        {version.reasoning || <span className="muted">No reasoning recorded.</span>}
                      </fieldset>
                      {version.feedback && (
                        <fieldset>
                          <legend>Analyst feedback this version responds to (from v{version.based_on})</legend>
                          {version.feedback}
                          {version.quotes.map((q, i) => (
                            <div key={i} className="ai-quote small">&ldquo;{q.text}&rdquo; (lines {q.line_start}&ndash;{q.line_end})</div>
                          ))}
                        </fieldset>
                      )}
                      {version.trace.queries && (
                        <fieldset>
                          <legend>Search plan (queries the agent ran against the filing)</legend>
                          <ol style={{ margin: 0, paddingLeft: 18 }}>
                            {version.trace.queries.map((q, i) => <li key={i} className="mono">{q}</li>)}
                          </ol>
                        </fieldset>
                      )}
                      {version.warnings.length > 0 && (
                        <fieldset>
                          <legend>Verification warnings</legend>
                          {version.warnings.map((w, i) => <div key={i}>{w}</div>)}
                        </fieldset>
                      )}
                    </>
                  )}

                  {tab === 'trace' &&
                    (version.trace.sources?.length ? (
                      <table className="grid">
                        <thead>
                          <tr><th>Source</th><th>Score</th><th>Lines</th><th>Passage (preview)</th><th></th></tr>
                        </thead>
                        <tbody>
                          {version.trace.sources.map((s) => (
                            <tr key={s.id}>
                              <td>
                                <b>{s.id}</b>
                                {s.pinned && <div><span className="ai-badge draft">QUOTED BY ANALYST</span></div>}
                              </td>
                              <td className="num">{s.score.toFixed(3)}</td>
                              <td className="num">{s.line_start}&ndash;{s.line_end}</td>
                              <td className="small">{s.preview}&hellip;</td>
                              <td>
                                <button onClick={() => setDoc({ highlight: { start: s.start, end: s.end, label: `source ${s.id}, lines ${s.line_start}–${s.line_end}` } })}>
                                  View
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <span className="muted">{version.trace.note ?? 'No retrieval for this version.'}</span>
                    ))}

                  {tab === 'run' && (
                    <table className="form">
                      <tbody>
                        <tr><td className="lbl">Version</td><td>v{version.version_no} ({version.origin})</td></tr>
                        <tr><td className="lbl">Created by / at</td><td>{version.created_by} &mdash; {version.created_at.replace('T', ' ')}</td></tr>
                        <tr><td className="lbl">Access check</td><td>{version.trace.guard ? `${version.trace.guard.allowed ? 'PASSED' : 'BLOCKED'}: ${version.trace.guard.detail}` : '-'}</td></tr>
                        <tr><td className="lbl">Model</td><td className="mono">{version.trace.model ?? '-'}</td></tr>
                        <tr><td className="lbl">LLM calls / latency</td><td>{version.trace.llm_calls ?? 0} call(s) / {version.trace.latency_ms ? `${(version.trace.latency_ms / 1000).toFixed(1)} s` : '-'}</td></tr>
                        <tr><td className="lbl">Source filing</td><td>{version.trace.filing ? `${version.trace.filing.accession_number} (filed ${version.trace.filing.filing_date})` : '-'}</td></tr>
                        <tr>
                          <td className="lbl">Raw model output</td>
                          <td>
                            <details>
                              <summary>show</summary>
                              <pre className="mono small" style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto' }}>{version.trace.raw_output || '-'}</pre>
                            </details>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  )}

                  {tab === 'history' && (
                    <table className="grid">
                      <thead>
                        <tr><th>When</th><th>Who</th><th>Action</th><th>Detail</th></tr>
                      </thead>
                      <tbody>
                        {events.map((e) => (
                          <tr key={e.event_id}>
                            <td style={{ whiteSpace: 'nowrap' }}>{e.at.replace('T', ' ')}</td>
                            <td>{e.actor}</td>
                            <td>{e.action}</td>
                            <td className="small">{e.detail}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </>
            )}

            {/* ---------------------------------------------------------- human feedback */}
            <fieldset style={{ marginTop: 10 }}>
              <legend>Your feedback to the AI &rarr; regenerate a new version (based on v{viewingNo})</legend>
              <textarea
                rows={3}
                placeholder="e.g. Lead with total debt and the maturity profile; mention the commercial paper program; keep it under 150 words."
                value={feedback}
                disabled={!canRun}
                onChange={(e) => setFeedback(e.target.value)}
              />
              <div style={{ margin: '4px 0' }}>
                {quotes.map((q, i) => (
                  <span key={i} className="ai-chip small">
                    <span className="ai-quote">&ldquo;{q.text.slice(0, 90)}{q.text.length > 90 ? '…' : ''}&rdquo;</span>
                    <span className="muted">L{q.line_start}</span>
                    <span className="x" title="Remove" onClick={() => setQuotes(quotes.filter((_, j) => j !== i))}>&times;</span>
                  </span>
                ))}
              </div>
              <div className="toolbar">
                <button disabled={!filing} onClick={() => setDoc({ highlight: null })}>Quote from the filing...</button>
                <button className="primary" disabled={!canRun || running || (!feedback.trim() && quotes.length === 0)} onClick={regenerate}>
                  {running ? 'Running agent...' : 'Regenerate with feedback'}
                </button>
                <span className="muted small">Quoted excerpts are pinned into the AI&rsquo;s sources for the next run.</span>
              </div>
            </fieldset>
          </>
        )}
      </div>

      {doc && filing && (
        <DocViewer
          filingId={filing.filing_id}
          title={`${ticker} Form 10-K ${filing.accession_number}`}
          highlight={doc.highlight}
          onQuote={canRun ? (q) => setQuotes((qs) => [...qs, q]) : undefined}
          onClose={() => setDoc(null)}
        />
      )}
    </div>
  )
}
