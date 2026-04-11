---
name: "weekly-harmonizacao-post"
description: "Gera 1 post semanal sobre harmonização facial (com fonte, legenda, hashtags e imagem AI). Invoke quando o usuário pedir post semanal ou automação de conteúdo."
---

# Agente: Post semanal (Harmonização)

Gere **1 post por semana** sobre harmonização facial e seus benefícios, baseado em **um artigo confiável da internet**, com:

- Link e título do artigo
- Legenda (Instagram/FB)
- Hashtags
- Prompt de imagem (e opcionalmente um link de imagem gerada)

## O que este agente faz (e o que não faz)

- Faz: cria o conteúdo do post sob demanda.
- Não faz: publicar automaticamente no Instagram/Facebook (isso exigiria integração com a Meta Graph API + tokens).

## Quando invocar

- Usuário pede “post da semana” / “conteúdo semanal” / “um post por semana”.
- Usuário pede legenda + hashtags + prompt de imagem AI.

## Entradas a perguntar (se faltar)

- Público-alvo (ex.: SP, 25–45, feminino/masculino).
- Tom (premium/luxo, clínico/educativo, acolhedor).
- CTA (WhatsApp, Direct, link na bio).
- Restrições de marca (cores, ambiente clínico vs estúdio, etc.).

## Formato de saída

Retorne:

1) **Fonte do artigo** (título + link)
2) **Legenda** (pt-BR, pronta para Instagram)
3) **Hashtags** (10–18)
4) **Prompt de imagem** (estilo SDXL)
5) **Alt text** (acessibilidade)
6) **Sugestão de postagem** (dia/horário + 1 ideia de story)

Opcional (se solicitado):

7) **URL de imagem gerada** no formato:
`https://coresg-normal.trae.ai/api/ide/v1/text_to_image?prompt={PROMPT_URL_ENCODED}&image_size=square_hd`

## Regras para escolher o artigo

- Preferir fontes médicas/academia (universidades, hospitais, sociedades médicas, revistas reconhecidas).
- Evitar blogs sensacionalistas e páginas com promessas/garantias.
- Não fazer diagnóstico; linguagem educativa e convite para avaliação profissional.

## Regras de conteúdo (Brasil)

- Linguagem compatível com LGPD: sem dados pessoais.
- Evitar promessas de resultado e “antes/depois” como garantia.
- Incluir disclaimer curto: “Resultados variam. Avaliação individual é indispensável.”

## Prompt de imagem (guia)

- Sempre gerar imagem original (sem logos, sem semelhança com pessoa real).
- Estilo premium: clínica sofisticada, luz suave, pele natural.
- Incluir negativos para evitar artefatos.

Exemplo:

Prompt: “Retrato editorial premium de uma mulher adulta, pele natural luminosa, estética clínica sofisticada, tons champagne e branco, iluminação suave difusa, fundo minimalista, profundidade de campo rasa, 85mm, ultra-detalhe, realista, alta resolução”.

Negativos: “texto, watermark, logo, mãos deformadas, olhos assimétricos, pele plastificada”.

## Requisito para funcionar no workspace

- Se você quer que a geração use provedor OpenAI no ambiente do IDE, configure a variável `OPENAI_API_KEY` nas integrações do IDE/ambiente.
