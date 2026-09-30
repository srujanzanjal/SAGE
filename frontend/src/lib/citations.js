// Where a citation points: a timestamp, PDF page, file lines, or web page.
export function citationLocator(citation) {
  if (!citation) return null;
  const c = citation;
  if (c.source_type === "video" && c.video_id && c.start_time != null) {
    return {
      label: c.timestamp_label || "Timestamp",
      href: `https://www.youtube.com/watch?v=${c.video_id}&t=${Math.max(0, Math.floor(Number(c.start_time)))}s`,
    };
  }
  if (c.source_type === "github" && c.file_path && !c.file_path.startsWith("__SAGE_")) {
    const lines = c.start_line != null ? `:${c.start_line}-${c.end_line}` : "";
    return { label: `${c.file_path}${lines}`, href: c.file_url || null };
  }
  if (c.source_type === "pdf" && c.page_number) {
    return { label: `Page ${c.page_number}`, href: null };
  }
  if (c.source_type === "website" && /^https?:\/\//.test(c.source_ref || "")) {
    return { label: c.source_title || new URL(c.source_ref).pathname || c.source_ref, href: c.source_ref };
  }
  return { label: "Overview", href: null };
}
