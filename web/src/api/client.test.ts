import { buildUrl, parseSseChunk, snapshotQuery } from './client'

describe('buildUrl', () => {
  it('repeats array params and skips nulls', () => {
    expect(buildUrl('/meta', { window: 'last_15', punt: ['FT%', 'TO'], position: null })).toBe(
      '/api/meta?window=last_15&punt=FT%25&punt=TO',
    )
  })

  it('sends an explicit empty punt list so the server does not use its default', () => {
    expect(snapshotQuery({ window: null, punts: [] })).toEqual({ window: null, punt: [''] })
    expect(snapshotQuery({ window: null, punts: null })).toEqual({ window: null, punt: null })
  })
})

describe('parseSseChunk', () => {
  it('parses complete events and keeps the partial remainder', () => {
    const chunk =
      'event: tool\ndata: {"name":"my_roster","label":"my roster"}\n\n' +
      'event: answer\ndata: {"text":"Drop him"}\n\n' +
      'event: err'
    const { events, rest } = parseSseChunk(chunk)
    expect(events).toEqual([
      { event: 'tool', data: { name: 'my_roster', label: 'my roster' } },
      { event: 'answer', data: { text: 'Drop him' } },
    ])
    expect(rest).toBe('event: err')
  })
})
