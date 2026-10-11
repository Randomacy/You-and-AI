# You & AI — Bubble Kin Design Handoff

## Product idea
You & AI combines live video, audio, and EEG data. Video and audio are interpreted through TRIBE v2, mapped against brain activity, and transformed into a personal generative artwork. Bloom is the desktop companion that reflects emotional states without diagnosing them.

## Design direction
**Bubble Kin**: serious ideas expressed through a warm, playful visual system. The experience should feel optimistic, emotionally fluent, soft, and credible—not childish, clinical, or stereotypically “AI.”

## Brand
- Name: You & AI
- Primary idea: human *with* AI, not human versus AI
- Mark: “You” + a sideways outlined ampersand + “AI”
- The ampersand remains a recognizable typographic glyph. Its horizontal loops only suggest a heart-like outline; never replace it with a literal heart icon.
- Voice: curious, never certain
- Prefer: “What are you noticing?”
- Avoid: “You are anxious.”

## Color tokens
```css
:root {
  --thinking-plum: #2D2250;
  --kin-pink: #FF7FAB;
  --spark-yellow: #FFE558;
  --wonder-violet: #8B79FF;
  --exhale-mint: #64E2BF;
  --soft-space: #FFF8F1;
  --warm-coral: #FF765D;
  --feeling-blue: #74B9FF;
}
```

Use Thinking Plum for text, outlines, and credibility. Use one or two candy colors per surface rather than the entire palette at once. Soft Space is the primary neutral.

## Typography
- Expressive/display: Instrument Serif, regular and italic
- UI/body: Manrope, 400–700
- Labels/data: DM Mono, 300–500
- Display headlines should use tight line-height (0.8–0.95) and slightly negative tracking.
- Data labels are uppercase, small, and widely tracked.

## Shape language
- Organic forms should be asymmetrical and feel slightly alive.
- Use soft outlines in Thinking Plum.
- Avoid perfect circles when a gently irregular form can work.
- Corners and pills are rounded, but layouts remain structured and editorial.
- Use generous negative space to stop the candy palette from feeling juvenile.

## Companion: Bloom
Bloom is a responsive digital organism made from eight gradient petals around a warm yellow center. The center contains two simple oval eyes and one fully opaque plum oval mouth. Bloom should feel expressive without imitating a human face too closely.

### Emotional states
1. **Happy**
   - Petals spin quickly: approximately 2.2 seconds per rotation.
   - The center gently bounces and expands.
   - Small radiating marks communicate excitement.
   - Suggested line: “Something good is growing.”

2. **Sad**
   - Petals detach and fall one at a time.
   - Use staggered timing across all eight petals.
   - The center settles lower and moves more slowly.
   - Mouth remains a small, fully opaque plum oval.
   - Suggested line: “We don’t have to rush this.”

3. **Sleepy**
   - Petals rotate very slowly: approximately 22 seconds per rotation.
   - Eyes become closed horizontal ovals.
   - Mouth becomes a tall, fully opaque plum oval and animates as a yawn.
   - The center softly compresses and relaxes.
   - Suggested line: “Let’s let the day soften.”

4. **Focused**
   - Petals use a precise stepped rotation rather than a smooth spin.
   - Bloom wears round plum glasses with a bridge.
   - Add angled eyebrows for determination.
   - Use a controlled attention pulse around the center.
   - Mouth remains a compact, fully opaque plum oval.
   - Suggested line: “I’ve got the thread. Keep going.”

Always honor `prefers-reduced-motion` by removing continuous movement while preserving the emotional state through pose and color.

## Generative artwork recipe
- Video controls color and light.
- Audio controls shape and rhythm.
- EEG controls motion and elasticity.
- Artworks combine layered translucent blobs, elliptical signal orbits, and a waveform.
- Every output should feel related to Bloom without literally reproducing the companion.
- Label portraits with state-oriented language such as “Bright Attention,” “Soft Focus,” or “High Energy.”

## Core interface components
- Companion message card: Bloom thumbnail, state label, one reflective sentence, low-pressure response.
- Live input pill: connection dot, modality label, signal percentage.
- Primary action: dark plum pill with white text and arrow.
- Secondary action: transparent pill with plum outline.
- Emotional state selector: numbered rows with a title, one-line behavior summary, and clear active state.
- Portrait card: generative artwork, data labels, and state caption.

## Layout principles
- Combine expressive editorial type with a visible grid.
- Use thin plum rules to divide sections.
- Pair one large conceptual statement with one precise technical explanation.
- Desktop layouts may use asymmetric 40/60 or 35/65 columns.
- Collapse to one column on mobile while keeping emotional controls directly below Bloom.

## Interaction principles
- Ask, do not diagnose.
- Reflect, do not mimic.
- Motion communicates emotion; it should never be decorative noise.
- Controls should feel calm and direct.
- Avoid Matrix green, binary-code clichés, robot imagery, and generic AI gradients.

## Accessibility
- Maintain readable contrast against candy colors.
- Do not communicate state with color alone.
- Add descriptive labels to interactive state controls.
- Support keyboard navigation and reduced motion.
- Keep body copy at a comfortable reading size and line-height.

## Suggested implementation stack
- React + TypeScript
- Tailwind CSS v4 or CSS custom properties for tokens
- CSS/SVG animation for Bloom and generative artwork
- Keep Bloom as a reusable component with a `mood` prop:

```ts
type BloomMood = "happy" | "sad" | "sleepy" | "focused";
```

## Acceptance criteria
- The experience clearly reads as You & AI / Bubble Kin.
- The sideways ampersand remains an ampersand and only suggests a heart.
- Bloom has eight petals and four visually distinct emotional states.
- Every Bloom mouth is a fully opaque plum oval.
- The generative artwork visibly relates video, audio, and EEG to different visual qualities.
- The tone remains playful and emotionally warm while treating the subject seriously.
