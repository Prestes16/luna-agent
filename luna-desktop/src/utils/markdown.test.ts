import { describe, expect, it } from 'vitest'
import { parseNumberedListItem } from './markdown'

describe('parseNumberedListItem', () => {
  it('preserves declared list numbers', () => {
    expect(['1. Alfa', '2. Beta', '3. Gama'].map(parseNumberedListItem)).toEqual([
      { number: 1, text: 'Alfa' },
      { number: 2, text: 'Beta' },
      { number: 3, text: 'Gama' },
    ])
  })

  it('removes only a duplicated matching marker at the item boundary', () => {
    expect(parseNumberedListItem('1. 1. Abra o Network')).toEqual({
      number: 1,
      text: 'Abra o Network',
    })
    expect(parseNumberedListItem('2. 3. Este número faz parte do conteúdo')).toEqual({
      number: 2,
      text: '3. Este número faz parte do conteúdo',
    })
  })

  it('rejects ordinary paragraphs', () => {
    expect(parseNumberedListItem('HTTP/1.1 200 OK')).toBeNull()
  })
})
