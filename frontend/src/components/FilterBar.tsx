// The four cascading address-component dropdowns. Options come from the gateway's
// /filter-options endpoint and narrow as selections are made; changing any filter
// is reported up so the dashboard can reset to page 0.

import {
  COLUMN_LABELS,
  FILTER_COLUMNS,
  type FilterColumn,
  type Filters,
  type FilterOptions,
} from "../api/coverage";
import { MultiSelect } from "./MultiSelect";

interface FilterBarProps {
  filters: Filters;
  options?: FilterOptions;
  optionsLoading: boolean;
  onChange: (filters: Filters) => void;
}

export function FilterBar({ filters, options, optionsLoading, onChange }: FilterBarProps) {
  const activeCount = FILTER_COLUMNS.reduce(
    (sum, col) => sum + (filters[col]?.length ?? 0),
    0,
  );

  function setColumn(column: FilterColumn, values: string[]) {
    const next: Filters = { ...filters };
    if (values.length === 0) delete next[column];
    else next[column] = values;
    onChange(next);
  }

  return (
    <div className="filterbar">
      <div className="filterbar__fields">
        {FILTER_COLUMNS.map((column) => (
          <MultiSelect
            key={column}
            label={COLUMN_LABELS[column]}
            options={options?.[column] ?? []}
            selected={filters[column] ?? []}
            onChange={(values) => setColumn(column, values)}
            loading={optionsLoading && !options}
          />
        ))}
      </div>
      <button
        type="button"
        className="filterbar__reset"
        disabled={activeCount === 0}
        onClick={() => onChange({})}
      >
        Reset filters{activeCount > 0 ? ` (${activeCount})` : ""}
      </button>
    </div>
  );
}
