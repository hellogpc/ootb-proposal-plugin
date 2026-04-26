# Brand assets

Drop image files into this folder using these exact names. Missing files fall back gracefully (layouts use shapes/text instead of erroring out).

| File | Used on | Suggested size | Notes |
|---|---|---|---|
| `logo.png` | top-right of content & TOC slides | ~400×200 px PNG with transparent bg | Use a dark-friendly monochrome version if possible |
| `mascot.png` | cover (bottom-left) and closing (left) | ~800×800 px PNG with transparent bg | Optional; 캐릭터 활용 브랜드일 때만 |
| `cover_bg.jpg` | full-bleed background of the cover slide | 1920×1080 JPG | Dark-tinted imagery works best (white title sits on top) |
| `section_bg.jpg` | background of section-divider slides | 1920×1080 JPG | Optional — navy solid is used if absent |

## Per-slide overrides

You can override per slide via `image:` / `background:` keys in the outline YAML — paths can be absolute or relative to the YAML file.

## Licensing

Don't commit other brands' trademarked assets here. This folder is intended for the user's own licensed creative.
