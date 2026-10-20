// Thin client for the Credit Portal API (proxied to http://localhost:8100 in dev).
// Every call carries the signed-in user's bearer token; the API takes identity from it.

import { getToken, sessionExpired } from './auth'

export type User = { email: string; name: string; title: string; role: string; roles: string[] }

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

export function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
  })
  if (res.status === 401) sessionExpired()
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

const qs = (params: Record<string, string | boolean | undefined>) => {
  const p = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => v && p.set(k, String(v)))
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const api = {
  me: () => request<User>('/api/me'),
  dashboard: () =>
    request<{
      work_queue: Borrower[]
      memo_counts: Record<string, number>
      filings_on_file: number
      activity: { at: string; actor: string; action: string }[]
    }>('/api/dashboard'),
  borrowers: (q?: string, mine?: boolean) => request<Borrower[]>(`/api/borrowers${qs({ q, mine })}`),
  borrower: (id: string) => request<BorrowerDetail>(`/api/borrowers/${id}`),
  filings: (borrower_id?: string) => request<Filing[]>(`/api/filings${qs({ borrower_id })}`),
  filing: (id: number) => request<Filing>(`/api/filings/${id}`),
  filingText: (id: number) => request<{ filing_id: number; text: string }>(`/api/filings/${id}/text`),
  search: (q: string, borrower_id?: string) =>
    request<{ query: string; truncated: boolean; hits: SearchHit[] }>(`/api/search${qs({ q, borrower_id })}`),
  memos: (mine?: boolean, status?: string) => request<Memo[]>(`/api/memos${qs({ mine, status })}`),
  memo: (id: string) => request<MemoDetail>(`/api/memos/${id}`),
  createMemo: (borrower_id: string) =>
    request<{ memo_id: string }>('/api/memos', { method: 'POST', body: JSON.stringify({ borrower_id }) }),
  saveSection: (memoId: string, sectionType: string, body: string) =>
    request<{ ok: boolean }>(`/api/memos/${memoId}/sections/${sectionType}`, {
      method: 'PUT',
      body: JSON.stringify({ body }),
    }),
  saveRecommendation: (memoId: string, recommendation: string) =>
    request<{ ok: boolean }>(`/api/memos/${memoId}/recommendation`, {
      method: 'PUT',
      body: JSON.stringify({ recommendation }),
    }),
  transition: (memoId: string, action: 'submit' | 'approve' | 'return') =>
    request<{ ok: boolean; status: string }>(`/api/memos/${memoId}/${action}`, { method: 'POST' }),
  restricted: () => request<RestrictedRow[]>('/api/restricted'),
}

export type PortalUser = {
  email: string
  name: string
  title: string
  role: string
  role_label: string
  active: boolean
  portfolio_size: number
  open_memos: number
}

export type DirectoryEntry = {
  email: string
  name: string
  job_title: string
  has_access: boolean
  role: string | null
  active: boolean | null
}

export const adminApi = {
  roles: () => request<{ role: string; label: string }[]>('/api/admin/roles'),
  users: () => request<PortalUser[]>('/api/admin/users'),
  directory: (q: string) => request<DirectoryEntry[]>(`/api/admin/directory${qs({ q })}`),
  grant: (email: string, role: string) =>
    request<PortalUser>('/api/admin/users', { method: 'POST', body: JSON.stringify({ email, role }) }),
  update: (email: string, change: { role?: string; active?: boolean }) =>
    request<PortalUser>(`/api/admin/users/${encodeURIComponent(email)}`, { method: 'PATCH', body: JSON.stringify(change) }),
}

export const fmtMoney = (musd: number) => `$${musd.toLocaleString('en-US', { minimumFractionDigits: 1 })}M`
