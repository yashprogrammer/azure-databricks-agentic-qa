// Thin client for the Credit Portal API (proxied to http://localhost:8100 in dev).

export type User = { email: string; name: string; title: string; role: string }

export type Borrower = {
  borrower_id: string
  ticker: string
  name: string
  sector: string
  relationship_manager: string
  exposure_musd: number
  internal_rating: string
  next_review: string
  status: string
  restricted: boolean
}

export type Filing = {
  filing_id: number
  borrower_id: string
  ticker: string | null
  form_type: string
  accession_number: string
  filing_date: string
  blob_path: string
  size_bytes: number
  line_count: number
  downloaded_at: string
}

export type Memo = {
  memo_id: string
  borrower_id: string
  borrower_name: string | null
  ticker: string | null
  analyst_email: string
  review_year: number
  status: string
  recommendation: string
  approver_email: string | null
  created_at: string
  updated_at: string
}

export type MemoSection = {
  section_type: string
  title: string
  body: string
  updated_by: string | null
  updated_at: string | null
}

export type MemoDetail = Memo & { sections: MemoSection[] }

export type BorrowerDetail = Borrower & {
  cik: number | null
  restriction: { reason: string; effective_from: string } | null
  covering_analysts: string[]
  filings: Filing[]
  memos: Memo[]
}

export type RestrictedRow = {
  borrower_id: string
  ticker: string
  name: string
  reason: string
  added_by: string
  effective_from: string
}

export type SearchHit = {
  filing_id: number
  ticker: string
  accession_number: string
  line: number
  snippet: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* not JSON */
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

const qs = (params: Record<string, string | undefined>) => {
  const p = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => v && p.set(k, v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const api = {
  users: () => request<User[]>('/api/users'),
  dashboard: (analyst: string) =>
    request<{
      work_queue: Borrower[]
      memo_counts: Record<string, number>
      filings_on_file: number
      activity: { at: string; actor: string; action: string }[]
    }>(`/api/dashboard${qs({ analyst })}`),
  borrowers: (q?: string, analyst?: string) => request<Borrower[]>(`/api/borrowers${qs({ q, analyst })}`),
  borrower: (id: string) => request<BorrowerDetail>(`/api/borrowers/${id}`),
  filings: (borrower_id?: string) => request<Filing[]>(`/api/filings${qs({ borrower_id })}`),
  filing: (id: number) => request<Filing>(`/api/filings/${id}`),
  filingText: (id: number) => request<{ filing_id: number; text: string }>(`/api/filings/${id}/text`),
  search: (q: string, borrower_id?: string) =>
    request<{ query: string; truncated: boolean; hits: SearchHit[] }>(`/api/search${qs({ q, borrower_id })}`),
  memos: (analyst?: string, status?: string) => request<Memo[]>(`/api/memos${qs({ analyst, status })}`),
  memo: (id: string) => request<MemoDetail>(`/api/memos/${id}`),
  createMemo: (borrower_id: string, analyst_email: string) =>
    request<{ memo_id: string }>('/api/memos', {
      method: 'POST',
      body: JSON.stringify({ borrower_id, analyst_email }),
    }),
  saveSection: (memoId: string, sectionType: string, body: string, updated_by: string) =>
    request<{ ok: boolean }>(`/api/memos/${memoId}/sections/${sectionType}`, {
      method: 'PUT',
      body: JSON.stringify({ body, updated_by }),
    }),
  saveRecommendation: (memoId: string, recommendation: string, updated_by: string) =>
    request<{ ok: boolean }>(`/api/memos/${memoId}/recommendation`, {
      method: 'PUT',
      body: JSON.stringify({ recommendation, updated_by }),
    }),
  transition: (memoId: string, action: 'submit' | 'approve' | 'return', actor: string) =>
    request<{ ok: boolean; status: string }>(`/api/memos/${memoId}/${action}`, {
      method: 'POST',
      body: JSON.stringify({ actor }),
    }),
  restricted: () => request<RestrictedRow[]>('/api/restricted'),
}

export const fmtMoney = (musd: number) => `$${musd.toLocaleString('en-US', { minimumFractionDigits: 1 })}M`
