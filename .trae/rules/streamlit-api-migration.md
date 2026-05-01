---
alwaysApply: true
scene: streamlit
---
# Streamlit API Migration Rules

## Deprecated APIs

### `st.components.v1.html` → `st.html`

**Status**: Deprecated since Streamlit 1.45, removal after 2026-06-01.

| Old (deprecated) | New |
|---|---|
| `import streamlit.components.v1 as components` | Remove the import entirely |
| `components.html(html_str, height=0)` | `st.html(html_str, unsafe_allow_javascript=True)` |

Key differences when migrating:

1. **No iframe wrapper**: `st.html` renders directly into the page DOM, not inside an iframe. This means:
   - JS can access `document` directly — do NOT use `window.parent.document`
   - CSS selectors target the main document — no iframe boundary
2. **No `height` / `width` / `scrolling` params**: `st.html` has no iframe sizing parameters. Use CSS within the HTML for layout.
3. **No f-string brace escaping**: Since `st.html` is not used inside f-strings, JS curly braces `{}` are written as-is, NOT doubled as `{{}}`.
4. **JavaScript is disabled by default**: `st.html` ignores `<script>` tags unless `unsafe_allow_javascript=True` is set. **Always add this parameter when the HTML contains `<script>` tags**, otherwise JS will silently not execute.

### Migration checklist

- [ ] Remove `import streamlit.components.v1 as components`
- [ ] Replace `components.html(...)` with `st.html(..., unsafe_allow_javascript=True)` (if HTML contains scripts)
- [ ] Remove `height`, `width`, `scrolling` keyword arguments
- [ ] Change `window.parent.document` → `document` in embedded JS
- [ ] Remove f-string `{{` / `}}` escaping in embedded JS/CSS (use raw `{` / `}`)
- [ ] Add `unsafe_allow_javascript=True` when HTML contains `<script>` tags

## General Principle

When modifying Streamlit code, always prefer the top-level `st.*` API over `st.components.v1.*`. If Streamlit emits a deprecation warning in the console, treat it as a bug and fix it immediately.
