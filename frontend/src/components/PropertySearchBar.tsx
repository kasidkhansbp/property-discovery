// The search box on the Properties screen. It edits a local draft and only
// searches on submit (Enter or the Search button), like a web search engine:
// no request per keystroke. The clear (×) icon clears the box and the search.

import { Flex, Input, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

const EXAMPLES = [
  "SW1A 1BG",
  "SW1A 1",
  "1 marlborough rd SW1A 1BG",
  "baker street tipton",
  "100023336956",
];

interface PropertySearchBarProps {
  /** The submitted query; the box resets to it when it changes from outside. */
  value: string;
  onSearch: (q: string) => void;
  busy?: boolean;
}

export function PropertySearchBar({ value, onSearch, busy }: PropertySearchBarProps) {
  const [draft, setDraft] = useState(value);

  useEffect(() => setDraft(value), [value]);

  function run(q: string) {
    setDraft(q);
    onSearch(q.trim());
  }

  return (
    <div className="property-search" role="search">
      {/* Sticky on phones (see styles.css); the examples scroll away. */}
      <div className="property-search__bar">
        <Input.Search
          size="large"
          aria-label="Search properties"
          placeholder="Search by address, postcode or UPRN"
          value={draft}
          maxLength={200}
          autoComplete="off"
          spellCheck={false}
          enterKeyHint="search"
          allowClear
          enterButton="Search"
          loading={busy}
          onChange={(e) => setDraft(e.target.value)}
          // Fires on Enter, the button, and the clear icon (with an empty value).
          onSearch={(q, _e, info) => run(info?.source === "clear" ? "" : q)}
        />
      </div>
      {/* Tappable examples: on a phone, typing one is the slow part. */}
      <Flex wrap gap={6} align="center" className="property-search__examples">
        <Typography.Text type="secondary">e.g.</Typography.Text>
        {EXAMPLES.map((ex) => (
          <Tag
            key={ex}
            className="property-search__example"
            role="button"
            tabIndex={0}
            onClick={() => run(ex)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                run(ex);
              }
            }}
          >
            {ex}
          </Tag>
        ))}
      </Flex>
    </div>
  );
}
