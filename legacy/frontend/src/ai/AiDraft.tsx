import { useCallback, useEffect, useState } from 'react'
import { api, type Memo } from '../api'
import type { Route } from '../router'
import { useSession } from '../session'
import { aiApi, memoBody, type Draft, type DraftSection } from './aiApi'
import './ai.css'
import SectionWorkspace from './SectionWorkspace'

export default function AiDraft({ route }: { route: Route }) {
  const id = route.path[1]
  return id ? <Workspace memoId={id} initialSection={route.query.get('s')} /> : <MemoPicker />
}

function MemoPicker() {
  const user = useSession()
  const [memos, setMemos] = useState<Memo[]>([])
  useEffect(() => {
    api.memos(user.role === 'analyst' ? user.email : undefined).then(setMemos)
  }, [user])
  const open = memos.filter((m) => m.status === 'Draft' || m.status === 'Returned')
  return (
    <>
      <h2>AI Credit Memo Draft</h2>
      <div className="notice" style={{ marginBottom: 8 }}>
        The AI drafts each of the six credit memo sections from the borrower&rsquo;s latest 10-K on file. Every
        statement is cited to the exact passage in the filing, and nothing reaches the credit memo until you
        review, approve and save it. Drafting is blocked for Restricted List borrowers and borrowers outside your
        portfolio.
      </div>
      <table className="grid">
        <thead>
          <tr><th>Memo ID</th><th>Borrower</th><th>Ticker</th><th>Review Year</th><th>Analyst</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>
          {open.map((m) => (
            <tr key={m.memo_id}>
              <td>{m.memo_id}</td>
              <td>{m.borrower_name}</td>
              <td className="mono">{m.ticker}</td>
              <td>{m.review_year}</td>
              <td>{m.analyst_email}</td>
              <td><span className={`status status-${m.status}`}>{m.status}</span></td>
              <td><a href={`#/ai-draft/${m.memo_id}`}>Open AI draft &raquo;</a></td>
            </tr>
          ))}
          {open.length === 0 && (
            <tr><td colSpan={7} className="muted">No Draft or Returned memos. Create one from the Borrowers tab.</td></tr>
          )}
        </tbody>
      </table>
    </>
  )
}

export function sectionBadge(s: DraftSection, running: boolean) {
  if (running) return <span className="ai-badge run">DRAFTING...</span>
  const st = s.state
  if (!st.current_version) return <span className="ai-badge none">NOT DRAFTED</span>
  if (st.saved_version && st.saved_version === st.approved_version) return <span className="ai-badge saved">SAVED v{st.saved_version}</span>
  if (st.approved_version) return <span className="ai-badge ok">APPROVED v{st.approved_version}</span>
  if (s.current && !s.current.grounded) return <span className="ai-badge warn">REVIEW v{st.current_version}</span>
  return <span className="ai-badge draft">DRAFT v{st.current_version}</span>
}

function Workspace({ memoId, initialSection }: { memoId: string; initialSection: string | null }) {
  const user = useSession()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState(initialSection ?? 'business_overview')
  const [running, setRunning] = useState<Set<string>>(new Set())
  const [progress, setProgress] = useState('')
  const [error, setError] = useState('')
  const [model, setModel] = useState('')

  const reload = useCallback(
    () => aiApi.draft(memoId, user.email).then(setDraft).catch((e) => setError(String(e))),
    [memoId, user.email],
  )
  useEffect(() => {
    reload()
    aiApi.health().then((h) => setModel(h.llm_configured ? h.model : `${h.model} (NOT CONFIGURED)`)).catch(() => setModel('AI service offline'))
  }, [reload])

  if (error && !draft) return <div className="alert alert-red">{error}</div>
  if (!draft) return <div className="muted">Loading AI draft workspace...</div>

  const { memo, borrower, filing, access } = draft
  const editable = (memo.status === 'Draft' || memo.status === 'Returned') && access.is_preparer
  const blocked = access.restricted || !access.in_portfolio
  const canRun = editable && !blocked && !!filing

  const runSection = async (type: string, body: Parameters<typeof aiApi.generate>[2]) => {
    setRunning((r) => new Set(r).add(type))
    try {
      await aiApi.generate(memoId, type, body)
    } finally {
      setRunning((r) => {
        const n = new Set(r)
        n.delete(type)
        return n
      })
      await reload()
    }
  }

  const draftAll = async () => {
    const todo = draft.sections.filter((s) => !s.state.current_version)
    const targets = todo.length ? todo : draft.sections
    if (!todo.length && !confirm('All six sections already have drafts. Re-run all six as new versions?')) return
    setError('')
    for (const [i, s] of targets.entries()) {
      setProgress(`Agent run ${i + 1} of ${targets.length}: ${s.title}...`)
      try {
        await runSection(s.section_type, { analyst_email: user.email })
      } catch (e) {
        setError(`${s.title}: ${String(e)}`)
      }
    }
    setProgress('')
  }

  const toSave = draft.sections.filter((s) => s.state.approved_version && s.state.approved_version !== s.state.saved_version)
  const saveApproved = async () => {
    setError('')
    for (const s of toSave) {
      const v = await aiApi.version(memoId, s.section_type, s.state.approved_version!)
      const body = memoBody(v, borrower.ticker)
      if (s.legacy_body.trim() && !confirm(`"${s.title}" already has text in the credit memo. Replace it with approved AI draft v${v.version_no}?`)) continue
      try {
        await api.saveSection(memoId, s.section_type, body, user.email) // the portal writes its own memo
        await aiApi.markSaved(memoId, s.section_type, user.email, v.version_no)
      } catch (e) {
        setError(`${s.title}: ${String(e)}`)
      }
    }
    await reload()
  }

  const current = draft.sections.find((s) => s.section_type === selected) ?? draft.sections[0]

  return (
    <>
      <div className="breadcrumb">
        <a href="#/ai-draft">AI Credit Memo Draft</a> &raquo; {memo.memo_id}
      </div>
      <h2>
        AI Draft &mdash; Credit Memo {memo.memo_id}: {memo.borrower_name} ({memo.ticker})
      </h2>
      <div className="row">
        <div className="col">
          <fieldset>
            <legend>Draft Context</legend>
            <table className="form">
              <tbody>
                <tr>
                  <td className="lbl">Borrower</td>
                  <td><a href={`#/borrowers/${borrower.borrower_id}`}>{borrower.borrower_id}</a> {borrower.name} &mdash; {borrower.sector}</td>
                </tr>
                <tr>
                  <td className="lbl">Source Filing</td>
                  <td>
                    {filing ? (
                      <>
                        Form 10-K <span className="mono">{filing.accession_number}</span> filed {filing.filing_date}{' '}
                        (<a href={`#/filings/${filing.filing_id}`}>open in Filing Library</a>)
                      </>
                    ) : (
                      <span className="muted">No 10-K on file yet</span>
                    )}
                  </td>
                </tr>
                <tr>
                  <td className="lbl">Memo Status</td>
                  <td><span className={`status status-${memo.status}`}>{memo.status}</span> &nbsp; prepared by {memo.analyst_email}</td>
                </tr>
                <tr>
                  <td className="lbl">AI Model</td>
                  <td className="mono">{model || '...'}</td>
                </tr>
              </tbody>
            </table>
          </fieldset>
        </div>
        <div className="col">
          <fieldset>
            <legend>Access Check (Compliance)</legend>
            {blocked ? (
              <div className="alert alert-red" style={{ margin: 0 }}>
                <b>AI drafting blocked.</b>{' '}
                {access.restricted
                  ? 'This borrower is on the Compliance Restricted List (information barrier).'
                  : 'This borrower is not in your portfolio.'}
              </div>
            ) : (
              <div>
                <span className="ai-badge ok">PASSED</span> Borrower is in your portfolio and is not on the Restricted
                List. Checked live against the Credit Portal on every AI run.
              </div>
            )}
            {!access.is_preparer && <div className="muted small" style={{ marginTop: 4 }}>Read-only: you are not the preparer of this memo.</div>}
            {access.is_preparer && !editable && <div className="muted small" style={{ marginTop: 4 }}>Read-only: memo is {memo.status}.</div>}
          </fieldset>
        </div>
      </div>

      <div className="toolbar">
        <button className="primary" disabled={!canRun || running.size > 0} onClick={draftAll}>
          Draft all 6 sections (6 agent runs)
        </button>
        <button disabled={!editable || toSave.length === 0} onClick={saveApproved}>
          Save approved sections to memo ({toSave.length})
        </button>
        <a href={`#/memos/${memo.memo_id}`}>View credit memo &raquo;</a>
      </div>
      {progress && <div className="ai-progress">{progress}</div>}
      {error && <div className="alert alert-red">{error}</div>}

      <div className="ai-layout">
        <div className="ai-sections">
          <div className="panel">
            <div className="panel-title">Memo Sections</div>
            <table className="grid">
              <tbody>
                {draft.sections.map((s) => (
                  <tr key={s.section_type} className={s.section_type === current.section_type ? 'sel' : ''} onClick={() => setSelected(s.section_type)}>
                    <td>
                      {s.title}
                      <div style={{ marginTop: 2 }}>{sectionBadge(s, running.has(s.section_type))}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="notice small">
            Each section is drafted by its own agent run: access check &rarr; plan &rarr; retrieve &rarr; draft &rarr;
            verify citations.
          </div>
        </div>
        <div className="ai-main">
          <SectionWorkspace
            key={current.section_type}
            memoId={memoId}
            section={current}
            filing={filing}
            ticker={borrower.ticker}
            canRun={canRun}
            editable={editable}
            running={running.has(current.section_type)}
            onRun={(body) => runSection(current.section_type, body)}
            reload={reload}
          />
        </div>
      </div>
    </>
  )
}
