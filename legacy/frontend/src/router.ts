import { useEffect, useState } from 'react'

// Minimal hash router: "#/memos/CM-2026-0101?x=1" -> { path: ["memos","CM-2026-0101"], query }.
export type Route = { path: string[]; query: URLSearchParams }

function parse(): Route {
  const raw = window.location.hash.replace(/^#\/?/, '')
  const [p, q = ''] = raw.split('?')
  return { path: p.split('/').filter(Boolean).map(decodeURIComponent), query: new URLSearchParams(q) }
}

export function useRoute(): Route {
  const [route, setRoute] = useState(parse)
  useEffect(() => {
    const onChange = () => setRoute(parse())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

export const go = (href: string) => {
  window.location.hash = href.replace(/^#/, '')
}
