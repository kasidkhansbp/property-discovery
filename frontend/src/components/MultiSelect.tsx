// A small checkbox dropdown: a button showing the selection count, opening a
// scrollable, searchable list of options. No dependency — the four filter
// dropdowns in FilterBar each render one of these.

import { useEffect, useMemo, useRef, useState } from "react";

interface MultiSelectProps {
  label: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  loading?: boolean;
}

export function MultiSelect({
  label,
  options,
  selected,
  onChange,
  loading = false,
}: MultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  // Close on an outside click so dropdowns don't stack open.
  useEffect(() => {
    if (!open) return;
    function onDocClick(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return needle ? options.filter((o) => o.toLowerCase().includes(needle)) : options;
  }, [options, search]);

  const selectedSet = useMemo(() => new Set(selected), [selected]);

  function toggle(value: string) {
    onChange(
      selectedSet.has(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value],
    );
  }

  return (
    <div className="multiselect" ref={rootRef}>
      <button
        type="button"
        className="multiselect__button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="multiselect__label">{label}</span>
        <span className="multiselect__value">
          {selected.length === 0 ? "All" : `${selected.length} selected`}
        </span>
        <span className="multiselect__chevron" aria-hidden>
          ▾
        </span>
      </button>

      {open && (
        <div className="multiselect__panel" role="listbox">
          <input
            className="multiselect__search"
            type="text"
            placeholder={`Search ${label.toLowerCase()}…`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
          />
          {selected.length > 0 && (
            <button
              type="button"
              className="multiselect__clear"
              onClick={() => onChange([])}
            >
              Clear {selected.length}
            </button>
          )}
          <div className="multiselect__options">
            {loading && <div className="multiselect__empty">Loading…</div>}
            {!loading && visible.length === 0 && (
              <div className="multiselect__empty">No matches</div>
            )}
            {!loading &&
              visible.map((option) => (
                <label key={option} className="multiselect__option">
                  <input
                    type="checkbox"
                    checked={selectedSet.has(option)}
                    onChange={() => toggle(option)}
                  />
                  <span>{option}</span>
                </label>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
