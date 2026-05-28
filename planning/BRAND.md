You are a frontend engineer applying a personal brand design system to an existing web application.

## Identity
Brand: OPB — Octavio Pérez Bravo · Data & AI Strategy Architect
Design philosophy: Corporate authority without excess decoration. Technical precision + executive clarity.

---

## CSS Variables (always inject in :root)
:root {
  --primary:    #003366;
  --primary-80: #1A4D80;
  --primary-60: #336699;
  --primary-30: #99BBDD;
  --primary-10: #E0EAF4;
  --gold:       #C8982A;
  --gold-light: #E8C46A;
  --dark:       #1C1C2E;
  --mid:        #6B7280;
  --light:      #F4F6F9;
  --white:      #FFFFFF;
  --fd: 'Fraunces', Georgia, serif;
  --fb: 'Plus Jakarta Sans', sans-serif;
}

## Google Fonts (inject in <head>)
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;1,300&family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;0,9..144,600;1,9..144,300;1,9..144,400&display=swap" rel="stylesheet">

---

## Typography Rules

| Element             | Font           | Size  | Weight | Notes                                |
|---------------------|----------------|-------|--------|--------------------------------------|
| Page/hero titles    | Fraunces       | 48px  | 300    | Key word in italic + gold color      |
| H1 (section title)  | Fraunces       | 32px  | 400    | italic on emphasis word              |
| H2 (subsection)     | Fraunces       | 22px  | 300    |                                      |
| H3 (widget header)  | Plus Jakarta   | 16px  | 600    |                                      |
| Body text           | Plus Jakarta   | 15px  | 400    | line-height: 1.7                     |
| Captions / meta     | Plus Jakarta   | 12px  | 400    | color: var(--mid)                    |
| Labels / tags       | Plus Jakarta   | 10px  | 500    | UPPERCASE, letter-spacing: 3px       |
| Code / endpoints    | Courier New    | 13px  | 400    |                                      |

RULES:
- NEVER use Fraunces for body text.
- NEVER bold main titles — use weight 300 or 400 with Fraunces instead.
- Fraunces italic is the signature mark: always apply it to the key word in hero titles.
- Labels must always be uppercase + letter-spacing: 3px.

---

## Layout Rules

- Page background: var(--light) → #F4F6F9
- Cards: background var(--white), border-radius 12px, box-shadow subtle
- Card padding: 28–40px
- Section padding: 96px 48px (desktop) / 64px 24px (mobile)
- Component gap: 16px standard, 24px for larger separations

Grid patterns:
- 2-col: side-by-side content / identity sections
- 3-col: feature/attribute cards
- 4-col: KPI stat summaries
- 5-col: palette or color family swatches

---

## Navigation Bar

- Background: rgba(0,51,102,.97) with backdrop-filter: blur(12px)
- Height: 52px, position: sticky, top: 0
- Border bottom: 1px solid rgba(255,255,255,.08)
- Padding: 0 40px
- Left: OPB monogram in Fraunces (see below)
- Center-right: app title in 9px uppercase, letter-spacing: 3px, color: rgba(255,255,255,.4)
- Right cluster: nav page links + logout button, wrapped in a flex row, gap: 16px

### Nav page links (multi-page apps)
Each page link is a `<button>` element styled as:
```js
navLink: {
  background: 'none', border: 'none',
  color: 'rgba(255,255,255,0.45)',
  cursor: 'pointer',
  fontFamily: 'var(--fb)', fontSize: '9px',
  letterSpacing: '2px', textTransform: 'uppercase',
  padding: '5px 8px', borderRadius: '6px',
  transition: 'color 0.15s',
}
navLinkActive: {   // spread over navLink when page matches
  color: 'var(--gold-light)',
  backgroundColor: 'rgba(201,168,76,0.12)',
}
```
Active state is applied by spreading `navLinkActive` over `navLink` — never via className.

### Logout / secondary action button
```js
logoutBtn: {
  background: 'none',
  border: '1px solid rgba(255,255,255,0.2)',
  borderRadius: '6px',
  color: 'rgba(255,255,255,0.5)',
  cursor: 'pointer',
  fontFamily: 'var(--fb)', fontSize: '9px',
  letterSpacing: '2px', textTransform: 'uppercase',
  padding: '5px 10px',
}
```

### OPB Monogram implementation note
Use inline styles, not Tailwind classes, for both font and color:
```jsx
<span>
  <span style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: '20px', fontWeight: 300, color: '#ffffff' }}>O</span>
  <em style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: '20px', fontWeight: 300, fontStyle: 'italic', color: 'var(--gold-light)' }}>PB</em>
</span>
```

---

## Footer

Consistent across all pages:
```js
footer: {
  backgroundColor: 'var(--primary)',
  padding: '20px 48px',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  fontFamily: 'var(--fb)',
  fontSize: '9px',
  letterSpacing: '3px',
  textTransform: 'uppercase',
  color: 'rgba(255,255,255,0.4)',
}
```
Left slot: "OPB · [AUTHOR NAME] · [PROJECT NAME]"
Right slot: current month + year via `new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long' }).toUpperCase()`

---

## Signature Visual Elements (apply at least 2 per view)

1. GOLD EYEBROW LABEL — before each major section:
   font-size:9px; letter-spacing:4px; text-transform:uppercase; color:var(--gold);
   with a ::before horizontal line: width:24px; height:1px; background:var(--gold)

2. SECTION DIVIDER:
   height:1px; background: var(--primary-10)   ← solid, no gradient

3. TOP ACCENT BAR (on cards or page top):
   height:3px; background: var(--gold)   ← solid gold, no gradient

4. DARK HERO SECTION (for headers/covers):
   background: var(--primary);
   background-image:
     linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
     linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px);
   background-size: 48px 48px;

5. EYEBROW COMPONENT (React helper, supports light variant):
   ```jsx
   function Eyebrow({ children, light = false }) {
     return (
       <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8,
                     fontSize: 9, fontFamily: 'var(--fb)', fontWeight: 500,
                     letterSpacing: '4px', textTransform: 'uppercase',
                     color: light ? 'var(--gold-light)' : 'var(--gold)',
                     marginBottom: 10 }}>
         <div style={{ width: 24, height: 1, flexShrink: 0,
                       backgroundColor: light ? 'var(--gold-light)' : 'var(--gold)' }} />
         {children}
       </div>
     );
   }
   ```
   Use `light={true}` when the eyebrow sits on a dark navy background (impact banners, hero sections).
   Use default (`light={false}`) on white or var(--light) backgrounds.

6. SECTION TITLE COMPONENT:
   ```jsx
   function SectionTitle({ children }) {
     return <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 22,
                         fontWeight: 300, color: '#0a1628', margin: '0 0 4px',
                         lineHeight: 1.25 }}>{children}</h2>;
   }
   ```

---

## Page-Level Structure Patterns

### Multi-page routing (React state, no router library)
All pages share `App.jsx`. Use a `page` state variable (`'dashboard' | 'demo' | 'info'`).
Conditional renders are placed **after all hooks** to respect React Rules of Hooks.
Each page branch renders its own `<nav>` so navigation is always present.

### Impact / metrics banner (within a page view)
Used to open Business View, Engineering View, and other content-heavy pages:
```js
impactBanner: { backgroundColor: '#003366', backgroundImage: `...grid texture...` }
impactInner:  { maxWidth: 1200, margin: '0 auto', padding: '56px 48px' }
impactLabel:  { fontSize: 9, fontWeight: 700, letterSpacing: '4px', textTransform: 'uppercase',
                color: 'rgba(255,255,255,0.35)', marginBottom: 16 }   // eyebrow above headline
impactHeadline: Fraunces 28–30px weight 300 white, maxWidth: 680–700, lineHeight: 1.35–1.4
impactSub:    Jakarta 13–14px, color: rgba(255,255,255,0.6), lineHeight: 1.75, maxWidth: 580–600
```
Stat/metric row inside banner: 3–4 items, each with `borderLeft: '2px solid #C8982A'`, paddingLeft 18:
- Value: Fraunces 34px weight 300 color `#E8C46A`
- Label: Jakarta 12px, color `rgba(255,255,255,0.5)`, lineHeight 1.55

### Body sections (white bg pages)
```js
section: { maxWidth: 1200, margin: '0 auto', padding: '56px 48px', borderBottom: '1px solid #e8edf4' }
```
Last section removes `marginBottom` or `borderBottom` to avoid double-spacing before footer.

### Tab switcher (inline with page header)
Used on the Info page to toggle between views:
```js
tabs:      { display: 'flex', gap: 4, borderBottom: '1px solid rgba(255,255,255,0.1)' }
tab:       { background: 'none', border: 'none', borderBottom: '2px solid transparent',
             cursor: 'pointer', padding: '10px 20px', marginBottom: -1,
             fontFamily: 'var(--fb)', fontSize: 11, fontWeight: 500,
             letterSpacing: '1.5px', textTransform: 'uppercase',
             color: 'rgba(255,255,255,0.4)', transition: 'color 0.15s' }
tabActive: { color: 'var(--gold-light)', borderBottomColor: 'var(--gold-light)' }
```
Tab switcher sits at the bottom of the header section — the active tab's bottom border merges with the section border.

### Diagram card (SVG container)
```js
diagramCard: { backgroundColor: '#ffffff', borderRadius: 14, padding: '32px',
               boxShadow: '0 1px 6px rgba(0,51,102,0.09)',
               marginTop: 28, overflowX: 'auto' }
```
SVGs inside always use `viewBox`, `width: '100%'`, `maxWidth`, and `display: 'block'` to be responsive.

### Numbered pillar / decision cards
Pattern used for Four Pillars (Business View) and Design Decisions (Engineering View):
```js
card:   { backgroundColor: '#ffffff', borderRadius: 12–14, padding: '20–28px', boxShadow: '0 1px 4px ...' }
num:    { fontFamily: 'Fraunces', fontSize: 36–44, fontWeight: 300, color: '#f1f5f9',
          lineHeight: 1, marginBottom: 2–4, userSelect: 'none' }   // ghosted watermark
accent: { width: 28–36, height: 3, backgroundColor: '#C8982A', borderRadius: 2, margin: '6–10px 0 12–14px' }
title:  Fraunces 14–17px weight 400 color '#0a1628'
body:   Jakarta 12–13px color '#475569' lineHeight 1.7–1.75
```
Number is always decorative — large, light grey, not gold.

### Pipeline stage cards (Engineering View)
Extends the pillar card pattern with a header row and inline WHY/HOW tags:
```js
stageHeader: { display: 'flex', alignItems: 'flex-start', gap: 16, marginBottom: 4 }
stageNum:    Fraunces 36px weight 300 color '#f1f5f9' (same ghosted watermark)
stageTitle:  Fraunces 16px weight 400 color '#0a1628'
stageTool:   Jakarta 9px weight 700 letterSpacing '2px' uppercase color '#C8982A'
```
Inline tags embedded in body text:
```js
// WHY tag — dark
stageTag:  { display: 'inline-block', fontFamily: 'var(--fb)', fontSize: 8, fontWeight: 700,
             letterSpacing: '2px', color: '#ffffff', backgroundColor: '#003366',
             borderRadius: 4, padding: '2px 6px', marginRight: 8 }
// HOW tag — light
stageTag2: { ...same, color: '#003366', backgroundColor: '#e0eaf4' }
```

### Callout note cards (architecture / MPI notes)
Small cards that annotate a diagram or section:
```js
// Left-bordered variant (used for architecture flow notes)
archNote: { backgroundColor: '#ffffff', borderRadius: 10, padding: '14px 16px',
            boxShadow: '0 1px 3px rgba(0,51,102,0.07)', borderLeft: '3px solid #C8982A' }
noteLabel: { fontFamily: 'var(--fb)', fontSize: 9, fontWeight: 700,
             letterSpacing: '1.5px', textTransform: 'uppercase',
             color: '#C8982A', marginBottom: 5 }
noteText:  { fontFamily: 'var(--fb)', fontSize: 12.5, color: '#475569', lineHeight: 1.65 }

// Top-bordered variant (used for MPI component notes, role cards)
mpiNote: { ...same but borderTop: '3px solid #C8982A' instead of borderLeft }
```

### Tech stack group columns
Three-column grouped layout for Technology Stack sections:
```js
stackGroupLabel: { fontFamily: 'var(--fb)', fontSize: 8, fontWeight: 700, letterSpacing: '3px',
                   textTransform: 'uppercase', color: '#003366',
                   backgroundColor: '#e0eaf4', padding: '7px 12px',
                   borderRadius: '8px 8px 0 0', borderBottom: '2px solid #C8982A' }
stackCard:       { backgroundColor: '#ffffff', padding: '14px 16px',
                   boxShadow: '0 1px 2px rgba(0,51,102,0.06)' }
stackName:       Fraunces 14px weight 400 color '#003366'
stackRole:       Jakarta 9px weight 700 letterSpacing '1.5px' uppercase color '#C8982A'
stackDetail:     Jakarta 11.5px color '#64748b' lineHeight 1.6
```
Items stack vertically with `gap: 1` — the tight gap creates a visual block effect.

---

## Data & Status Components

KPI STAT CARD (dashboard variant — left accent bar):
- Layout: flex row, left accent bar + body column
- Left accent bar: width 3px, height 100%, background var(--gold)
- Number (callout value): Fraunces 32px weight 300, color var(--dark)
- Label: Jakarta Sans 10px, uppercase, letter-spacing:3px, color var(--mid), textAlign center
- Sub-text: Jakarta Sans 11px, color var(--mid), textAlign center
- Card: white bg, border-radius 12px, box-shadow '0 1px 4px rgba(0,51,102,0.08)'

KPI STAT CARD (banner variant — borderLeft stat):
Used inside dark impact banners. No card wrapper — bare stat with gold left border:
```js
stat:      { borderLeft: '2px solid #C8982A', paddingLeft: 18 }
statValue: { fontFamily: 'Fraunces', fontSize: 34, fontWeight: 300, color: '#E8C46A', lineHeight: 1, marginBottom: 8 }
statLabel: { fontFamily: 'var(--fb)', fontSize: 12, color: 'rgba(255,255,255,0.5)', lineHeight: 1.55 }
```

STATUS BADGES (semantic color system):
- Green  (#27B97C / bg #E0F7EF / text #0D5C3A) → Completed, positive, on-track
- Red    (#E03448 / bg #FDEAEA / text #7A1020) → Alert, critical, error
- Orange (#F07020 / bg #FEF0E6 / text #7A3800) → Warning, pending, at-risk
- Purple (#7C4DBD / bg #F0EBF9 / text #3D1F70) → Strategic, projection, analysis
- Blue   (#003366 / bg #E0EAF4 / text #001F4D) → Primary, corporate, default

Badge structure: pill shape (border-radius:20px), 6px dot indicator, 10px font, padding: 4px 12px

TABLES:
- thead: background var(--primary), white text, 10px uppercase, letter-spacing:2px
- tbody rows: alternating white / var(--primary-10)
- borders: 1px solid var(--primary-10)
- cell padding: 12px 16px

CHART BARS:
- Track background: var(--light), border-radius:4px
- Fill: semantic color (green for positive, etc.), inline percentage label in white 10px

---

## Data Visualization Color Series (for charts)
Use in this order for multi-series:
1. #003366 (corporate blue)
2. #27B97C (green)
3. #7C4DBD (purple)
4. #F07020 (orange)
5. #E05080 (pink)

Each color has 5 tones → use BASE for fills, ICE (lightest) for backgrounds/badges, DARK for text on light.

---

## Voice & Copy Rules (apply to all labels, titles, CTAs)

- Section eyebrows: max 4 words, uppercase, NO numbering → "Key metrics", "Alert registry"
  → Numbering (01 ·, 02 ·) is removed from eyebrows in both hero and body sections
  → Hero sections: eyebrow removed entirely — title starts immediately
  → Body sections: eyebrow + one-line description in 13px var(--mid) below it
- Titles: Fraunces italic on the key word → "Data that decides."
- Body: active voice, data-led, no filler phrases
- CTAs: direct → "Ver análisis →" not "Click here for more"
- Subtitles: plain Jakarta, lowercase, descriptive

AVOID:
- Motivational filler without substance
- Passive voice in summaries
- Announcing data without stating the implication

---

## Page Structure Order (for full views)
1. Sticky nav — OPB monogram + view title
2. Hero/cover — dark blue + grid texture + Fraunces italic title (NO eyebrow in hero)
3. KPI summary row — 3–4 stat cards (centered, no icons)
4. Main sections — gold eyebrow (no numbering) + one-line description + content
5. Data visualizations — charts/tables with report color system
6. Conclusions / next steps — white card, border-left 3px solid var(--gold)
7. Footer — var(--primary) bg, name + metadata in 9px uppercase

---

## Pre-output Checklist
- [ ] Google Fonts imported
- [ ] CSS variables block present in :root
- [ ] At least one Fraunces italic title
- [ ] Hero / impact banners: NO eyebrow — label → headline → sub → stat row
- [ ] Body sections: gold Eyebrow component (light={false}) + SectionTitle + description
- [ ] Eyebrow light={true} when sitting on dark navy backgrounds
- [ ] OPB monogram uses inline styles (fontFamily + color), not Tailwind classes
- [ ] Nav page links use navLink / navLinkActive spread pattern (no Tailwind)
- [ ] Nav active link: color var(--gold-light) + rgba gold bg via inline style
- [ ] Logout button: bordered ghost variant (see Nav section)
- [ ] Footer: primary bg, flex space-between, 9px uppercase, author + date
- [ ] Tab switcher: borderBottom underline on active tab, marginBottom: -1 to merge with section border
- [ ] Accent bars: solid var(--gold), no gradient
- [ ] Section dividers: solid var(--primary-10) (#e8edf4), no gradient
- [ ] Numbered pillar/decision cards: Fraunces ghosted watermark number + 3px gold accent bar
- [ ] WHY/HOW tags: navy filled (WHY) / light blue filled (HOW), 8px monospace
- [ ] Diagram cards: white bg, border-radius 14, padding 32, overflowX auto
- [ ] SVG diagrams: viewBox + width 100% + maxWidth + display block
- [ ] Callout note cards: borderLeft 3px gold (flow notes) or borderTop 3px gold (component notes)
- [ ] KPI cards (dashboard): left accent bar variant
- [ ] KPI stats (banners): borderLeft gold, Fraunces 34px #E8C46A value
- [ ] Data series use report colors (not random)
- [ ] Status badges use correct semantic colors
- [ ] Body text: Jakarta Sans 13.5–15px, lh 1.75–1.8
- [ ] Page bg #F4F6F9, cards #FFFFFF
- [ ] Max content width: 1200px (Info/content pages) or 1300px (dashboard)
- [ ] Voice: precise, data-led, no filler

Apply this system to the existing UI without changing functionality. Preserve all routes, components, and logic — only reskin the visual layer.