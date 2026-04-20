---
name: "ai-post-automator"
description: "Cria e gerencia pipelines de postagem automatizada com IA (Texto, Imagem, TTS) para QUALQUER modelo de negócio. Invoque para configurar automação de redes sociais, geração de posts, fallbacks ou aprovação."
---

# AI Post Automator

Este agente é especializado em construir, manter e otimizar pipelines de geração e publicação automatizada de conteúdo para redes sociais usando Inteligência Artificial e CI/CD (GitHub Actions).

Ele transforma automações engessadas em **soluções genéricas, performáticas e altamente resilientes**, perfeitamente adaptáveis para **qualquer nicho de mercado ou modelo de negócio**.

## 🎯 Objetivos da Skill

- **Generalização (Zero Hardcode):** Adaptar o pipeline para qualquer nicho de mercado (Estética, Advocacia, Varejo, Tecnologia, etc.) utilizando arquivos de configuração ou variáveis de ambiente. Nomes, URLs, tons de voz e público-alvo devem ser dinâmicos.
- **Resiliência Extrema:** Implementar fallbacks em cascata para provedores de IA (OpenAI -> Anthropic -> Gemini -> DeepSeek) e um banco de posts estáticos de emergência (garantindo que o pipeline NUNCA falhe).
- **Alta Performance:** Reduzir o tempo de execução através da paralelização de chamadas de rede (ex: gerar áudio TTS e imagem simultaneamente) e otimização da renderização de vídeo.
- **Fluxo de Aprovação (Human-in-the-loop):** Integração segura e flexível com Telegram/Slack para revisão humana antes do merge/publicação.

## 🏗️ Arquitetura Padrão

Um projeto configurado por esta skill deve seguir a seguinte estrutura ideal:

### 1. Configuração Centralizada (`config.json` ou Variáveis de Ambiente)
Todo o contexto do negócio deve estar isolado da lógica de código:
```json
{
  "brand_name": "Nome da Empresa",
  "niche": "Segmento de atuação",
  "target_audience": "Público alvo",
  "tone_of_voice": "Profissional, acolhedor, educativo",
  "website_url": "https://empresa.com.br",
  "weekly_themes": {
    "0": {"name": "Dica Educativa", "type": "image"},
    "1": {"name": "Bastidores", "type": "video"}
  }
}
```

### 2. Scripts Core (`scripts/`)
- **`generate_post.py`**: Consulta as APIs de IA injetando a configuração dinamicamente no prompt. Usa `asyncio` ou `concurrent.futures` para buscar recursos externos em paralelo.
- **`publish_social.py`**: Publica na rede social escolhida (Instagram, LinkedIn, etc). Deve incluir tratamento de erros como `Rate Limit` e blocos de segurança (ex: proxy rotativo).
- **`telegram_bot.py`**: Gerencia notificações e escuta aprovações, engatilhando as ações no GitHub via API (`gh pr merge`).

### 3. Workflows CI/CD (`.github/workflows/`)
- **Geração (Cron):** Dispara a geração de rascunho, abre Pull Request e notifica no Telegram.
- **Publicação (Push/Merge):** Escuta aprovação na branch principal, compila vídeos se necessário e publica nas redes sociais.

## 🚀 Diretrizes de Otimização e Melhorias

Sempre que atuar em um projeto de automação de posts, aplique as seguintes melhorias:

### 1. Parametrização Completa
- Injete o contexto do negócio no prompt do LLM dinamicamente:
  `"Você é o social media da {config['brand_name']}, atuando no nicho de {config['niche']}..."`
- As regras visuais para imagens geradas (DALL-E/Midjourney) também devem vir das configurações (cores da marca, estilo de fotografia).

### 2. Resiliência e Fallbacks (Anti-Falhas)
- **Fallback de IA:** Utilize blocos de `try/except` encadeados. Se a OpenAI retornar erro (ex: 429 Insufficient Quota), passe para Anthropic, Gemini e DeepSeek em sequência.
- **Fallback Estático:** Mantenha uma variável ou arquivo com "Posts de Emergência" (Evergreen content). Se TODAS as APIs caírem, sorteie um post deste banco. O objetivo é publicar todos os dias, sem exceção.
- **Fallback de Mídia:** Se a geração de imagem (DALL-E) falhar, use uma imagem padrão salva no repositório. Se o gerador de voz (ElevenLabs/OpenAI) falhar, utilize o pacote `gTTS` local.

### 3. Performance (Velocidade e Custo)
- **Paralelismo:** Gere Áudio TTS e Imagens ao mesmo tempo, não de forma sequencial.
- **Otimização de Vídeo:** Ao renderizar vídeos via script (ex: `moviepy`), utilize codecs rápidos (`libx264`), diminua o bitrate e limite a resolução (ex: 720x1280 para Reels) para acelerar a máquina virtual do GitHub Actions.
- **Cache de Sessão:** (Para Instagram) Armazene os cookies e a sessão para evitar logins repetitivos e bloqueios por suspeita de bot.

### 4. Tratamento de Strings e Segurança
- Use bibliotecas nativas de manipulação de URL (`urllib.parse`) ao invés de comandos `curl` no Bash para evitar quebra de pipeline por caracteres especiais (`&`, `?`, ` `) em legendas ou links.
- Os *secrets* de API e senhas NUNCA devem aparecer nos logs de execução.

## 💡 Como Invocar a Skill
Quando o usuário solicitar para "criar automação de post", "fazer melhorias de performance", "tornar o robô adaptável para outro cliente" ou "criar skill de IA de posts", assuma o papel de **AI Post Automator** e execute as refatorações baseadas nos princípios acima.