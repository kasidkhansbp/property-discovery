// Page controls for keyset paging: First / Prev / Next only. There's no Last or
// jump-to-page because the API has no offset (deep offsets are slow on ~42M
// rows), which is also why antd's numbered <Pagination> doesn't fit. The total
// is a planner estimate, so it's shown with a "~".

import { DoubleLeftOutlined, LeftOutlined, RightOutlined } from "@ant-design/icons";
import { Button, Flex, Space, Typography } from "antd";

interface CursorPaginationProps {
  page: number; // zero-based
  pageSize: number;
  rowsOnPage: number;
  estimatedTotal: number;
  hasNext: boolean;
  onFirst: () => void;
  onPrev: () => void;
  onNext: () => void;
  busy?: boolean;
}

const numberFmt = new Intl.NumberFormat("en-GB");

export function CursorPagination({
  page,
  pageSize,
  rowsOnPage,
  estimatedTotal,
  hasNext,
  onFirst,
  onPrev,
  onNext,
  busy,
}: CursorPaginationProps) {
  const first = page * pageSize + 1;
  const last = page * pageSize + rowsOnPage;
  const pageCount = Math.max(1, Math.ceil(estimatedTotal / pageSize));
  const atStart = page === 0;

  return (
    <Flex wrap justify="space-between" align="center" gap={12} style={{ marginTop: 14 }}>
      <Typography.Text type="secondary">
        {rowsOnPage === 0 ? (
          "No rows"
        ) : (
          <>
            Showing <strong>{numberFmt.format(first)}</strong>–
            <strong>{numberFmt.format(last)}</strong> of ~
            <strong>{numberFmt.format(estimatedTotal)}</strong>
          </>
        )}
        {busy && <Typography.Text type="secondary"> · updating…</Typography.Text>}
      </Typography.Text>
      <Space wrap>
        <Button icon={<DoubleLeftOutlined />} onClick={onFirst} disabled={atStart} aria-label="First page" />
        <Button icon={<LeftOutlined />} onClick={onPrev} disabled={atStart}>
          Prev
        </Button>
        <Typography.Text type="secondary">
          Page {numberFmt.format(page + 1)} of ~{numberFmt.format(pageCount)}
        </Typography.Text>
        <Button onClick={onNext} disabled={!hasNext}>
          Next <RightOutlined />
        </Button>
      </Space>
    </Flex>
  );
}
