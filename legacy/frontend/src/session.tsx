import { createContext, useContext } from 'react'
import type { User } from './api'

// The signed-in user, as returned by GET /api/me (derived server-side from the token).
export const SessionContext = createContext<User | null>(null)

export function useSession(): User {
  const user = useContext(SessionContext)
  if (!user) throw new Error('No session')
  return user
}
