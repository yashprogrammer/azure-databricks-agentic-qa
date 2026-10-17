// Client for the AI Credit Memo Draft service (FastAPI, proxied at /ai -> http://localhost:8200).

export type Citation = {
  n: number
  source: string
  quote: string
  verified: boolean
  filing_id: number
  start?: number
  end?: number
  line_start?: number
  line_end?: number
}

export type QuoteRef = { text: string; start: number; end: number; line_start: number; line_end: number }

export type TraceSource = {
  id: string
  chunk_id: string
  score: number
  start: number
  end: number
  line_start: number
  line_end: number
  pinned: boolean
  preview: string
}

export type Version = {
  version_no: number
  origin: 'ai' | 'human' | 'restore'
  text: string
  citations: Citation[]
  reasoning: string
  trace: {
    guard?: { allowed: boolean; reason: string | null; detail: string }
    queries?: string[]
    sources?: TraceSource[]
    filing?: { filing_id: number; accession_number: string; filing_date: string }
    model?: string
    llm_calls?: number
    latency_ms?: number
    raw_output?: string
    note?: string
    edited_from?: number
  }
  feedback: string
  quotes: QuoteRef[]
  based_on: number | null
  grounded: boolean
  refusal_reason: string | null
  warnings: string[]
  created_by: string
  created_at: string
}

export type VersionSummary = Pick<
  Version,
  'version_no' | 'origin' | 'grounded' | 'refusal_reason' | 'feedback' | 'based_on' | 'created_by' | 'created_at'
>

export type SectionState = {
  current_version: number | null
  approved_version: number | null
  saved_version: number | null
  saved_at: string | null
}

export type DraftSection = {
  section_type: string
  title: string
  goal: string
  state: SectionState
  versions: VersionSummary[]
  current: Version | null
  legacy_body: string
}

export type Draft = {
  memo: {
    memo_id: string
    borrower_id: string
    borrower_name: string
    ticker: string
    analyst_email: string
    review_year: number
    status: string
  }
  borrower: { borrower_id: string; name: string; ticker: string; sector: string; restricted: boolean }
  filing: { filing_id: number; accession_number: string; filing_date: string; ticker: string | null } | null
  access: { restricted: boolean; in_portfolio: boolean; is_preparer: boolean }
  sections: DraftSection[]
}

export type DraftEvent = { event_id: number; section_type: string; actor: string; action: string; detail: string; at: string }

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json' } })
  if (!res.ok) {
    let detail: unknown = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* not JSON */
    }
    const msg = typeof detail === 'object' && detail ? (detail as { detail?: string }).detail ?? JSON.stringify(detail) : String(detail)
    throw new Error(`${res.status}: ${msg}`)
  }
  return res.json() as Promise<T>
}

const post = <T,>(path: string, body: unknown) => call<T>(path, { method: 'POST', body: JSON.stringify(body) })
const sec = (memoId: string, type: string) => `/ai/drafts/${memoId}/sections/${type}`

export const aiApi = {
  health: () => call<{ env: string; model: string; llm_configured: boolean }>('/ai/health'),
  draft: (memoId: string, analyst: string) => call<Draft>(`/ai/drafts/${memoId}?analyst=${encodeURIComponent(analyst)}`),
  version: (memoId: string, type: string, no: number) => call<Version>(`${sec(memoId, type)}/versions/${no}`),
  generate: (memoId: string, type: string, body: { analyst_email: string; feedback?: string; quotes?: QuoteRef[]; base_version?: number | null }) =>
    post<Version>(`${sec(memoId, type)}/generate`, body),
  edit: (memoId: string, type: string, analyst_email: string, text: string, base_version: number | null) =>
    post<Version>(`${sec(memoId, type)}/edit`, { analyst_email, text, base_version }),
  setCurrent: (memoId: string, type: string, analyst_email: string, version_no: number) =>
    post<SectionState>(`${sec(memoId, type)}/current`, { analyst_email, version_no }),
  approve: (memoId: string, type: string, analyst_email: string, version_no: number) =>
    post<SectionState>(`${sec(memoId, type)}/approve`, { analyst_email, version_no }),
  markSaved: (memoId: string, type: string, analyst_email: string, version_no: number) =>
    post<SectionState>(`${sec(memoId, type)}/saved`, { analyst_email, version_no }),
  events: (memoId: string) => call<DraftEvent[]>(`/ai/drafts/${memoId}/events`),
}

/** Text written into the legacy memo: the approved draft plus a plain-text source list. */
export function memoBody(v: Version, ticker: string): string {
  const cited = v.citations.filter((c) => c.verified)
  if (!cited.length) return v.text
  const f = v.trace.filing
  const refs = cited
    .map((c) => `[${c.n}] ${ticker} Form 10-K${f ? ` (acc. ${f.accession_number}, filed ${f.filing_date})` : ''}, lines ${c.line_start}-${c.line_end}`)
    .join('\n')
  return `${v.text}\n\nSources:\n${refs}`
}
