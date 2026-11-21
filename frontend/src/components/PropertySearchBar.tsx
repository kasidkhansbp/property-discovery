// The search box on the Properties screen. It edits a local draft and only
// searches on submit (Enter or the Search button), like a web search engine:
// no request per keystroke. The × button clears the box and the search.

import { useEffect, useRef, useState, type FormEvent } from "react";

interface PropertySearchBarProps {
  /** The submitted query; the box resets to it when it changes from outside. */
  value: string;
  onSearch: (q: string) => void;
  busy?: boolean;
}

export function PropertySearchBar({ value, onSearch, busy }: PropertySearchBarProps) {
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => setDraft(value), [value]);

  function submit(e: FormEvent) {
    e.preventDefault();
    onSearch(draft.trim());
  }

  function clear() {
    setDraft("");
    onSearch("");
    inputRef.current?.focus();
  }

  return (
    <form className="search" role="search" onSubmit={submit}>
      <div className={`search__box${busy ? " search__box--busy" : ""}`}>
        <svg className="search__icon" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
          <path d="M20 20l-4.2-4.2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <input
          ref={inputRef}
          type="search"
          className="search__input"
          aria-label="Search properties"
          placeholder="Search by address, postcode or UPRN"
          value={draft}
          maxLength={200}
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => setDraft(e.target.value)}
        />
        {draft && (
          <button
            type="button"
            className="search__clear"
            aria-label="Clear search"
            onClick={clear}
          >
            ×
          </button>
        )}
        <button type="submit" className="search__submit" disabled={!draft.trim()}>
          Search
        </button>
      </div>
      <p className="search__hint">
        e.g. <code>SW1A 1BG</code> · <code>SW1A 1</code> ·{" "}
        <code>1 marlborough rd SW1A 1BG</code> · <code>baker street tipton</code> ·{" "}
        <code>100023336956</code>
      </p>
    </form>
  );
}
