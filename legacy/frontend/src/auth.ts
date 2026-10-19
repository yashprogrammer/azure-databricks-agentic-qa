// Sign-in session. Locally the token comes from the development identity provider
// (/dev-idp/token); on Azure it comes from Microsoft Entra ID (MSAL). The UI never decides who
// the user is: it only holds the token, and the APIs read the identity from it.

const TOKEN_KEY = 'contoso.creditportal.token'

function readExp(token: string): number {
  try {
    return JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).exp * 1000
  } catch {
    return 0
  }
}

export function getToken(): string | null {
  const token = sessionStorage.getItem(TOKEN_KEY)
  if (!token || readExp(token) < Date.now()) {
    sessionStorage.removeItem(TOKEN_KEY)
    return null
  }
  return token
}

export async function signIn(username: string, password: string): Promise<void> {
  const res = await fetch('/dev-idp/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) throw new Error(res.status === 401 ? 'Invalid user ID or password.' : `Sign-in failed (${res.status}).`)
  sessionStorage.setItem(TOKEN_KEY, (await res.json()).access_token)
}

export function signOut(): void {
  sessionStorage.removeItem(TOKEN_KEY)
  window.location.hash = '#/dashboard'
  window.dispatchEvent(new Event('auth:changed'))
}

/** Called when an API answers 401: the session expired or the token is no longer valid. */
export function sessionExpired(): void {
  sessionStorage.removeItem(TOKEN_KEY)
  window.dispatchEvent(new Event('auth:changed'))
}
