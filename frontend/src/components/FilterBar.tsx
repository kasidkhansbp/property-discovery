// A row of cascading multi-select dropdowns, one per filter column. Options come
// from the gateway's /filter-options endpoint for the view and narrow as
// selections are made; changing any filter is reported up so the dashboard can
// reset to page 0. Generic over the column set, so the sales -> UPRN view
// (four address columns) and the EPC UPRN -> sales view (six attribute columns)
// share it.

import { MultiSelect } from "./MultiSelect";

interface FilterBarProps<C extends string> {
  columns: readonly C[];
  labels: Record<C, string>;
  filters: Partial<Record<C, string[]>>;
  options?: Record<C, string[]>;
  optionsLoading: boolean;
  onChange: (filters: Partial<Record<C, string[]>>) => void;
}

export function FilterBar<C extends string>({
  columns,
  labels,
  filters,
  options,
  optionsLoading,
  onChange,
}: FilterBarProps<C>) {
  const activeCount = columns.reduce((sum, col) => sum + (filters[col]?.length ?? 0), 0);

  function setColumn(column: C, values: string[]) {
    const next = { ...filters };
    if (values.length === 0) delete next[column];
    else next[column] = values;
    onChange(next);
  }

  return (
    <div className="filterbar">
      <div className="filterbar__fields">
        {columns.map((column) => (
          <MultiSelect
            key={column}
            label={labels[column]}
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
