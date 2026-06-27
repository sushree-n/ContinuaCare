import React, { useState } from 'react'

/**
 * Parse an inline CSS string (kebab-case) into a React style object (camelCase).
 * Lets us port the design prototype's inline `style="..."` strings nearly verbatim.
 *
 *   css('display:flex;align-items:center;gap:10px')
 *   // => { display: 'flex', alignItems: 'center', gap: '10px' }
 */
export function css(str: string): React.CSSProperties {
  const obj: Record<string, string> = {}
  for (const rule of str.split(';')) {
    const i = rule.indexOf(':')
    if (i === -1) continue
    const rawKey = rule.slice(0, i).trim()
    const val = rule.slice(i + 1).trim()
    if (!rawKey || !val) continue
    const key = rawKey.replace(/-([a-z])/g, (_m, c: string) => c.toUpperCase())
    obj[key] = val
  }
  return obj as React.CSSProperties
}

type HProps = {
  as?: React.ElementType
  style?: React.CSSProperties
  /** Styles merged on top of `style` while the element is hovered (replaces DCLogic `style-hover`). */
  hoverStyle?: React.CSSProperties
  children?: React.ReactNode
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any
}

/** Element that merges `hoverStyle` over `style` while hovered. */
export function H({ as = 'div', style, hoverStyle, children, ...rest }: HProps) {
  const [hover, setHover] = useState(false)
  const Tag = as
  return (
    <Tag
      {...rest}
      style={{ ...style, ...(hover && hoverStyle ? hoverStyle : {}) }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      {children}
    </Tag>
  )
}
