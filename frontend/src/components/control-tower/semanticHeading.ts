export type PanelHeadingLevel = 2 | 4;
export type HeadingTag = "h2" | "h3" | "h4" | "h5" | "h6";

export function headingTag(level: PanelHeadingLevel, offset = 0): HeadingTag {
  return `h${Math.min(6, level + offset)}` as HeadingTag;
}
