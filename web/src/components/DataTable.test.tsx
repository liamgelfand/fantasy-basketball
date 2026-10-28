import { fireEvent, screen, within } from '@testing-library/react'
import { renderWithTheme } from '../test/render'
import { DataTable, type Column } from './DataTable'

interface Row {
  name: string
  pts: number
}

const rows: Row[] = [
  { name: 'Alpha', pts: 10 },
  { name: 'Bravo', pts: 30 },
  { name: 'Charlie', pts: 20 },
]
const columns: Column<Row>[] = [
  { key: 'name', label: 'Name', render: (r) => r.name, sortValue: (r) => r.name },
  { key: 'pts', label: 'PTS', render: (r) => r.pts, sortValue: (r) => r.pts },
]

const names = () =>
  screen
    .getAllByRole('row')
    .slice(1)
    .map((r) => within(r).getAllByRole('cell')[0].textContent)

describe('DataTable', () => {
  it('applies the initial sort and toggles direction on header click', () => {
    renderWithTheme(<DataTable rows={rows} columns={columns} rowKey={(r) => r.name} initialSort={{ key: 'pts', desc: true }} />)
    expect(names()).toEqual(['Bravo', 'Charlie', 'Alpha'])
    fireEvent.click(screen.getByText('PTS'))
    expect(names()).toEqual(['Alpha', 'Charlie', 'Bravo'])
  })
})
