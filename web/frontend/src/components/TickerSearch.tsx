import { useState, useEffect, useRef, useCallback } from 'react'
import { searchTickers } from '../api'
import type { TickerResult } from '../types'

// ── badge colours per Yahoo quoteType ──────────────────────────────────────
const TYPE_STYLE: Record<string, string> = {
  EQUITY:         'bg-blue-500/20   text-blue-400   border-blue-500/40',
  ETF:            'bg-purple-500/20 text-purple-400 border-purple-500/40',
  MUTUALFUND:     'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
  CRYPTOCURRENCY: 'bg-orange-500/20 text-orange-400 border-orange-500/40',
  INDEX:          'bg-teal-500/20   text-teal-400   border-teal-500/40',
  CURRENCY:       'bg-yellow-500/20 text-yellow-400 border-yellow-500/40',
  FUTURE:         'bg-red-500/20    text-red-400    border-red-500/40',
}
const DEFAULT_TYPE_STYLE = 'bg-slate-600/30 text-slate-400 border-slate-600/40'

function typeBadge(type: string) {
  return (
    <span
      className={`px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider rounded border ${
        TYPE_STYLE[type] ?? DEFAULT_TYPE_STYLE
      }`}
    >
      {type || '—'}
    </span>
  )
}

interface Props {
  onSelect: (ticker: TickerResult) => void
}

export default function TickerSearch({ onSelect }: Props) {
  const [query,            setQuery]            = useState('')
  const [results,          setResults]          = useState<TickerResult[]>([])
  const [isOpen,           setIsOpen]           = useState(false)
  const [loading,          setLoading]          = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)

  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef     = useRef<HTMLInputElement>(null)
  const debounceRef  = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── close dropdown on outside click ────────────────────────────────────
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  // ── debounced search ────────────────────────────────────────────────────
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!query.trim()) {
      setResults([])
      setIsOpen(false)
      setLoading(false)
      return
    }
    setLoading(true)
    debounceRef.current = setTimeout(async () => {
      try {
        const data = await searchTickers(query)
        setResults(data)
        setIsOpen(data.length > 0)
        setHighlightedIndex(-1)
      } catch {
        setResults([])
      } finally {
        setLoading(false)
      }
    }, 280)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [query])

  // ── select a result ─────────────────────────────────────────────────────
  const select = useCallback((item: TickerResult) => {
    setQuery(item.symbol)
    setIsOpen(false)
    setResults([])
    setHighlightedIndex(-1)
    onSelect(item)
  }, [onSelect])

  // ── keyboard navigation ─────────────────────────────────────────────────
  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!isOpen) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightedIndex(i => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightedIndex(i => Math.max(i - 1, -1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (highlightedIndex >= 0 && results[highlightedIndex]) {
        select(results[highlightedIndex])
      }
    } else if (e.key === 'Escape') {
      setIsOpen(false)
      setHighlightedIndex(-1)
    }
  }

  // ── clear input ─────────────────────────────────────────────────────────
  function clear() {
    setQuery('')
    setResults([])
    setIsOpen(false)
    inputRef.current?.focus()
  }

  return (
    <div ref={containerRef} className="relative w-full">
      {/* Search input */}
      <div className="relative flex items-center">
        {/* magnifying glass */}
        <svg
          className="absolute left-4 w-5 h-5 text-slate-400 pointer-events-none"
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
        </svg>

        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => results.length > 0 && setIsOpen(true)}
          placeholder="Search ticker or company name…"
          className="
            w-full pl-12 pr-12 py-4 rounded-xl text-lg font-medium
            bg-slate-800/60 border border-slate-700 text-slate-100
            placeholder-slate-500 outline-none
            focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20
            transition-all duration-150
          "
          autoComplete="off"
          spellCheck={false}
        />

        {/* right icon: spinner or clear */}
        <div className="absolute right-4">
          {loading ? (
            <svg className="w-5 h-5 text-blue-400 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
              <path className="opacity-75" fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
            </svg>
          ) : query ? (
            <button onClick={clear} className="text-slate-500 hover:text-slate-300 transition-colors">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12"/>
              </svg>
            </button>
          ) : null}
        </div>
      </div>

      {/* Dropdown */}
      {isOpen && results.length > 0 && (
        <div className="
          absolute z-50 mt-2 w-full
          bg-slate-800 border border-slate-700
          rounded-xl shadow-2xl shadow-black/50
          overflow-hidden
        ">
          <ul>
            {results.map((item, idx) => (
              <li
                key={`${item.symbol}-${idx}`}
                onMouseDown={e => { e.preventDefault(); select(item) }}
                onMouseEnter={() => setHighlightedIndex(idx)}
                className={`
                  flex items-center gap-3 px-4 py-3 cursor-pointer
                  border-b border-slate-700/50 last:border-0
                  transition-colors duration-75
                  ${idx === highlightedIndex ? 'bg-blue-600/20' : 'hover:bg-slate-700/50'}
                `}
              >
                {/* symbol */}
                <span className="
                  font-mono font-bold text-sm min-w-[72px]
                  px-2 py-0.5 rounded
                  bg-slate-700 text-blue-300
                ">
                  {item.symbol}
                </span>

                {/* company name */}
                <span className="flex-1 text-sm text-slate-300 truncate">
                  {item.name || <span className="text-slate-500 italic">No name</span>}
                </span>

                {/* badges */}
                <div className="flex items-center gap-1.5 shrink-0">
                  {item.exchange && (
                    <span className="text-[10px] font-medium text-slate-500 uppercase tracking-wide">
                      {item.exchange}
                    </span>
                  )}
                  {typeBadge(item.type)}
                </div>
              </li>
            ))}
          </ul>

          <div className="px-4 py-2 bg-slate-900/60 text-[11px] text-slate-600 text-right">
            Powered by Yahoo Finance · use ↑↓ to navigate, Enter to select
          </div>
        </div>
      )}
    </div>
  )
}
