import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { QuoteRef } from './aiApi'

const textCache = new Map<number, Promise<string>>()
const loadText = (filingId: number) => {
  if (!textCache.has(filingId)) textCache.set(filingId, api.filingText(filingId).then((d) => d.text))
  return textCache.get(filingId)!
}

const lineOf = (text: string, offset: number) => {
  let n = 1
  for (let i = 0; i < offset; i++) if (text.charCodeAt(i) === 10) n++
  return n
}

type Props = {
  filingId: number
  title: string
  highlight: { start: number; end: number; label: string } | null
  onQuote?: (q: QuoteRef) => void
  onClose: () => void
}

/** Shows the filing exactly as stored by the Credit Portal, scrolled to and highlighting the
 *  cited passage. Analysts can select any text and attach it to their feedback as a quote. */
export default function DocViewer({ filingId, title, highlight, onQuote, onClose }: Props) {
  const [text, setText] = useState<string | null>(null)
  const [selection, setSelection] = useState<QuoteRef | null>(null)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadText(filingId).then(setText)
  }, [filingId])

  useLayoutEffect(() => {
    if (text && highlight) boxRef.current?.querySelector('mark')?.scrollIntoView({ block: 'center' })
  }, [text, highlight])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const captureSelection = () => {
    const sel = window.getSelection()
    const box = boxRef.current
    if (!sel || sel.isCollapsed || !box || !text || !box.contains(sel.anchorNode)) return setSelection(null)
    const range = sel.getRangeAt(0)
    const pre = document.createRange()
    pre.selectNodeContents(box)
    pre.setEnd(range.startContainer, range.startOffset)
    const start = pre.toString().length
    const quoted = range.toString()
    const end = start + quoted.length
    if (quoted.trim().length < 3) return setSelection(null)
    setSelection({ text: quoted.trim(), start, end, line_start: lineOf(text, start), line_end: lineOf(text, end) })
  }

  const before = text && highlight ? text.slice(0, highlight.start) : text
  const marked = text && highlight ? text.slice(highlight.start, highlight.end) : ''
  const after = text && highlight ? text.slice(highlight.end) : ''

  return (
    <div className="ai-modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="ai-modal">
        <div className="panel-title">
          <span>Source document: {title}{highlight ? ` — ${highlight.label}` : ''}</span>
          <button onClick={onClose}>Close [Esc]</button>
        </div>
        <div className="ai-doc" ref={boxRef} onMouseUp={captureSelection}>
          {text === null ? (
            <span className="muted">Loading document from the filing store...</span>
          ) : (
            <>
              {before}
              {highlight && <mark>{marked}</mark>}
              {after}
            </>
          )}
        </div>
        {onQuote && (
          <div className="bar">
            {selection ? (
              <>
                <span className="small">
                  Selected (lines {selection.line_start}&ndash;{selection.line_end}):{' '}
                  <span className="ai-quote">&ldquo;{selection.text.slice(0, 140)}{selection.text.length > 140 ? '…' : ''}&rdquo;</span>
                </span>
                <button className="primary" onClick={() => { onQuote(selection); setSelection(null) }}>
                  Quote selection in feedback
                </button>
              </>
            ) : (
              <span className="muted small">Tip: select text in the document to quote it in your feedback to the AI.</span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
