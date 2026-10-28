import { Group, ScrollArea, Table, Text, UnstyledButton } from '@mantine/core'
import { IconChevronDown, IconChevronUp, IconSelector } from '@tabler/icons-react'
import { useMemo, useState, type ReactNode } from 'react'
import classes from './DataTable.module.css'

export interface Column<T> {
  key: string
  label: ReactNode
  render: (row: T) => ReactNode
  /** Provide to make the column sortable. */
  sortValue?: (row: T) => number | string
  align?: 'left' | 'right' | 'center'
  sticky?: boolean
  title?: string
}

interface Props<T> {
  rows: T[]
  columns: Column<T>[]
  rowKey: (row: T) => string | number
  initialSort?: { key: string; desc: boolean }
  highlight?: (row: T) => boolean
  minWidth?: number
  maxHeight?: number
}

/** Sortable, horizontally scrollable table with an optional sticky first column. */
export function DataTable<T>({ rows, columns, rowKey, initialSort, highlight, minWidth = 640, maxHeight }: Props<T>) {
  const [sort, setSort] = useState(initialSort ?? null)

  const sorted = useMemo(() => {
    const col = sort && columns.find((c) => c.key === sort.key)
    if (!col?.sortValue) return rows
    const get = col.sortValue
    return [...rows].sort((a, b) => {
      const x = get(a)
      const y = get(b)
      const cmp = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))
      return sort!.desc ? -cmp : cmp
    })
  }, [rows, columns, sort])

  const toggle = (key: string) =>
    setSort((s) => (s?.key === key ? { key, desc: !s.desc } : { key, desc: true }))

  const table = (
    <Table striped highlightOnHover verticalSpacing="xs" miw={minWidth} stickyHeader={!!maxHeight}>
      <Table.Thead>
        <Table.Tr>
          {columns.map((c) => {
            const Icon = sort?.key === c.key ? (sort.desc ? IconChevronDown : IconChevronUp) : IconSelector
            return (
              <Table.Th key={c.key} ta={c.align} className={c.sticky ? classes.sticky : undefined} title={c.title}>
                {c.sortValue ? (
                  <UnstyledButton onClick={() => toggle(c.key)} className={classes.sortButton}>
                    <Group gap={4} wrap="nowrap" justify={c.align === 'right' ? 'flex-end' : 'flex-start'}>
                      <Text fw={600} size="xs" tt="uppercase">
                        {c.label}
                      </Text>
                      <Icon size={12} />
                    </Group>
                  </UnstyledButton>
                ) : (
                  <Text fw={600} size="xs" tt="uppercase">
                    {c.label}
                  </Text>
                )}
              </Table.Th>
            )
          })}
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {sorted.map((row) => (
          <Table.Tr key={rowKey(row)} className={highlight?.(row) ? classes.highlight : undefined}>
            {columns.map((c) => (
              <Table.Td key={c.key} ta={c.align} className={c.sticky ? classes.sticky : undefined}>
                {c.render(row)}
              </Table.Td>
            ))}
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )

  return maxHeight ? (
    <ScrollArea.Autosize mah={maxHeight} type="auto">
      {table}
    </ScrollArea.Autosize>
  ) : (
    <Table.ScrollContainer minWidth={minWidth}>{table}</Table.ScrollContainer>
  )
}
