import { formatStat, pct, probColor, signed, titleCase } from './format'

describe('format', () => {
  it('formats ratio and counting stats', () => {
    expect(formatStat('FG%', 0.4567)).toBe('.457')
    expect(formatStat('PTS', 12.34)).toBe('12.3')
    expect(formatStat('PTS', 1234.5)).toBe('1,235')
  })

  it('clamps extreme probabilities', () => {
    expect(pct(0.999)).toBe('>99%')
    expect(pct(0.001)).toBe('<1%')
    expect(pct(0.42)).toBe('42%')
  })

  it('signs numbers', () => {
    expect(signed(1.234)).toBe('+1.2')
    expect(signed(-0.5, 2)).toBe('-0.50')
    expect(signed(0)).toBe('0.0')
  })

  it('maps probability to color bands', () => {
    expect(probColor(0.9)).toBe('teal')
    expect(probColor(0.5)).toBe('yellow')
    expect(probColor(0.1)).toBe('red')
  })

  it('title-cases enum strings', () => {
    expect(titleCase('H2H_CATEGORY')).toBe('H2h Category')
    expect(titleCase('DAY_TO_DAY')).toBe('Day To Day')
  })
})
