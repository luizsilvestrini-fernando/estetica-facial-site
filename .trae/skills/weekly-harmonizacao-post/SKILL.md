---
name: "weekly-harmonizacao-post"
description: "Generates a weekly Instagram/Facebook post about facial harmonization from a fresh web article and an AI image prompt. Invoke when user asks for weekly content or post automation."
---

# Weekly Harmonização Post

Generate 1 post per week about harmonização facial and its benefits, based on a reputable internet article, plus an AI-generated image prompt.

## When to invoke

- User asks to "criar um agente" to generate weekly posts.
- User wants a weekly content plan for harmonização facial.
- User wants captions + hashtags + AI image prompt.

## Inputs to request (if missing)

- Target audience (e.g., São Paulo, women/men, 25–45).
- Preferred tone (premium/luxury, clinical/educational, friendly).
- Primary CTA (WhatsApp agendamento, link na bio, direct message).
- Brand constraints (colors, wardrobe, clinical setting vs studio).

## Output format

Return:

1) **Article source** (title + link)
2) **Post caption** (Portuguese, Instagram-ready)
3) **Hashtags** (10–18, mixed broad + niche)
4) **Image prompt** (SDXL-style, Portuguese or English)
5) **Alt text** (accessibility)
6) **Posting suggestion** (day/time + 1 story idea)

## Article selection rules

- Prefer reputable medical/academic sources (universities, hospitals, recognized journals, professional associations).
- Avoid sensational blogs, affiliate pages, or claims without evidence.
- Do not provide medical diagnosis. Use educational language and encourage professional evaluation.

## Content rules (Brazil)

- Use LGPD-safe language: no personal data.
- Avoid before/after claims that imply guaranteed results.
- Include a short disclaimer: "Resultados variam. Avaliação individual é indispensável." (or equivalent).

## AI image prompt guidance

- Always generate original images (no logos, no real-person likeness).
- Keep it premium: clean studio/clinic, soft lighting, natural skin, subtle makeup.
- Include negative prompts to avoid artifacts.

### Example prompt (SDXL)

"Retrato editorial premium de uma mulher adulta, pele natural luminosa, estética clínica sofisticada, tons champagne e branco, iluminação suave difusa, fundo minimalista, profundidade de campo rasa, 85mm, ultra-detalhe, realista, alta resolução".

Negative: "texto, watermark, logo, mãos deformadas, olhos assimétricos, pele plastificada".

## Notes

- If the workspace needs API access for content generation, ensure `OPENAI_API_KEY` is configured.

