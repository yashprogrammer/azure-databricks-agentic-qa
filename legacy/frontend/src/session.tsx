import { createContext, useContext } from 'react'
import type { User } from './api'

// The legacy portal trusts the user picked at sign-on (SSO sits in front of it in production).
export const SessionContext = createContext<User | null>(null)

export function useSession(): User {
  const user = useContext(SessionContext)
  if (!user) throw new Error('No session')
  return user
}

export const SESSION_KEY = 'contoso.creditportal.user'
