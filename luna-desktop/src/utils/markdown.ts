export interface NumberedListItem {
  number: number
  text: string
}

const NUMBERED_LIST_ITEM = /^(\d+)\.\s+(.+)$/

/** Parse one Markdown list item and remove only an identical duplicated marker. */
export function parseNumberedListItem(line: string): NumberedListItem | null {
  const match = NUMBERED_LIST_ITEM.exec(line)
  if (!match) return null

  const number = Number.parseInt(match[1], 10)
  const duplicatePrefix = `${number}. `
  const text = match[2].startsWith(duplicatePrefix)
    ? match[2].slice(duplicatePrefix.length)
    : match[2]

  return { number, text }
}
