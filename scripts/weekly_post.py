import argparse
import datetime as dt
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


def ssl_context(insecure: bool) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()
    return ssl.create_default_context()


def fetch_bytes(url: str, timeout: int = 20, *, context: ssl.SSLContext) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "weekly-post-generator/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=context) as res:
        return res.read()


def parse_rss_items(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    if channel is None:
        return []

    items: list[dict] = []
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()

        if not title or not link:
            continue

        items.append(
            {
                "title": title,
                "link": link,
                "description": strip_html(description),
                "pub_date": pub_date,
            }
        )

    return items


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def rss_url_for_query(query: str, source: str) -> str:
    return (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    )


def fetch_json(url: str, *, context: ssl.SSLContext, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "weekly-post-generator/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=context) as res:
        return json.loads(res.read().decode("utf-8"))


def fetch_pubmed_latest(term: str, *, context: ssl.SSLContext) -> dict:
    esearch_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmax=5&sort=date&term="
        + urllib.parse.quote(term)
    )
    xml_bytes = fetch_bytes(esearch_url, timeout=30, context=context)
    root = ET.fromstring(xml_bytes)
    ids = [el.text.strip() for el in root.findall(".//IdList/Id") if el.text and el.text.strip()]
    if not ids:
        raise ValueError("PubMed: nenhum ID encontrado")

    pmid = ids[0]
    esummary_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id="
        + urllib.parse.quote(pmid)
    )
    data = fetch_json(esummary_url, context=context)
    result = data.get("result", {}).get(pmid, {})
    title = (result.get("title") or "").strip().rstrip(".")
    pubdate = (result.get("pubdate") or "").strip()

    return {
        "title": title or f"PubMed PMID {pmid}",
        "link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "description": "",
        "pub_date": pubdate,
    }


def fetch_google_news_first(query: str, *, context: ssl.SSLContext) -> dict:
    rss_url = rss_url_for_query(query, "google-news")
    rss_bytes = fetch_bytes(rss_url, context=context)
    items = parse_rss_items(rss_bytes)
    if not items:
        raise ValueError("Google News RSS: nenhum item encontrado")
    return items[0]


def openai_chat_json(api_key: str, model: str, seed: dict, *, context: ssl.SSLContext) -> dict:
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Você é um redator de conteúdo para clínica premium de harmonização facial. Responda SOMENTE em JSON válido (sem markdown). Use português (pt-BR). Não faça promessas de resultado. Inclua disclaimer curto. OBRIGATÓRIO: a legenda (caption) DEVE terminar com uma chamada para ação direcionando ao WhatsApp, usando o formato: '\n\n📲 Agende sua avaliação pelo WhatsApp: (11) 99550-5765\nOu clique no link da bio!'. Campos obrigatórios: source_title, source_url, caption, hashtags, image_prompt, alt_text, posting_suggestion, story_idea, disclaimer.",
            },
            {"role": "user", "content": json.dumps(seed, ensure_ascii=False)},
        ],
        "temperature": 0.7,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60, context=context) as res:
            body = res.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            err_body = ""
        raise RuntimeError(f"OpenAI HTTP {e.code}: {err_body or e.reason}")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        snippet = body[:800]
        raise RuntimeError(f"OpenAI retornou resposta inválida (não-JSON): {snippet}")
    content = (
        parsed.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\n", "", content)
        content = re.sub(r"\n```$", "", content)
        content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        snippet = content[:1200]
        raise RuntimeError(f"Modelo não retornou JSON válido. Conteúdo: {snippet}")


def anthropic_messages_json(api_key: str, model: str, seed: dict, *, context: ssl.SSLContext) -> dict:
    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": model,
        "max_tokens": 900,
        "temperature": 0.7,
        "system": "Você é um redator de conteúdo para clínica premium de harmonização facial. Responda SOMENTE em JSON válido (sem markdown). Use português (pt-BR). Não faça promessas de resultado. Inclua disclaimer curto. OBRIGATÓRIO: a legenda (caption) DEVE terminar com uma chamada para ação direcionando ao WhatsApp, usando o formato: '\n\n📲 Agende sua avaliação pelo WhatsApp: (11) 99550-5765\nOu clique no link da bio!'. Campos obrigatórios: source_title, source_url, caption, hashtags, image_prompt, alt_text, posting_suggestion, story_idea, disclaimer.",
        "messages": [{"role": "user", "content": json.dumps(seed, ensure_ascii=False)}],
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60, context=context) as res:
            body = res.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            err_body = ""
        raise RuntimeError(f"Anthropic HTTP {e.code}: {err_body or e.reason}")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        snippet = body[:800]
        raise RuntimeError(f"Anthropic retornou resposta inválida (não-JSON): {snippet}")

    parts = parsed.get("content") or []
    text = "".join([p.get("text", "") for p in parts if isinstance(p, dict)])
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        snippet = text[:1200]
        raise RuntimeError(f"Modelo não retornou JSON válido. Conteúdo: {snippet}")


def gemini_generate_json(api_key: str, model: str, seed: dict, *, context: ssl.SSLContext) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(model)}:generateContent?key={urllib.parse.quote(api_key)}"
    system = "Você é um redator de conteúdo para clínica premium de harmonização facial. Responda SOMENTE em JSON válido (sem markdown). Use português (pt-BR). Não faça promessas de resultado. Inclua disclaimer curto. OBRIGATÓRIO: a legenda (caption) DEVE terminar com uma chamada para ação direcionando ao WhatsApp, usando o formato: '\n\n📲 Agende sua avaliação pelo WhatsApp: (11) 99550-5765\nOu clique no link da bio!'. Campos obrigatórios: source_title, source_url, caption, hashtags, image_prompt, alt_text, posting_suggestion, story_idea, disclaimer."
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": system + "\n\n" + json.dumps(seed, ensure_ascii=False)}
                ],
            }
        ],
        "generationConfig": {"temperature": 0.7},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60, context=context) as res:
            body = res.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            err_body = ""
        raise RuntimeError(f"Gemini HTTP {e.code}: {err_body or e.reason}")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        snippet = body[:800]
        raise RuntimeError(f"Gemini retornou resposta inválida (não-JSON): {snippet}")

    candidates = parsed.get("candidates") or []
    content = ((candidates[0] or {}).get("content") or {}) if candidates else {}
    parts = content.get("parts") or []
    text = "".join([p.get("text", "") for p in parts if isinstance(p, dict)]).strip()

    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        snippet = text[:1200]
        raise RuntimeError(f"Modelo não retornou JSON válido. Conteúdo: {snippet}")


def ensure_fields(obj: dict) -> dict:
    required = [
        "source_title",
        "source_url",
        "caption",
        "hashtags",
        "image_prompt",
        "alt_text",
        "posting_suggestion",
        "story_idea",
        "disclaimer",
    ]
    missing = [k for k in required if k not in obj]
    if missing:
        raise ValueError(f"JSON missing fields: {', '.join(missing)}")
    if not isinstance(obj.get("hashtags"), list):
        raise ValueError("hashtags must be an array")
    return obj


def image_url_from_prompt(prompt: str, image_size: str = "square_hd") -> str:
    encoded = urllib.parse.quote(prompt, safe="")
    return f"https://coresg-normal.trae.ai/api/ide/v1/text_to_image?prompt={encoded}&image_size={image_size}"


def render_markdown(today: str, result: dict) -> str:
    hashtags = " ".join([h if h.startswith("#") else f"#{h}" for h in result["hashtags"]])
    img_url = image_url_from_prompt(result["image_prompt"], image_size="square_hd")
    return "\n".join(
        [
            f"# Post semanal — {today}",
            "",
            "## Fonte",
            f"- {result['source_title']}",
            f"- {result['source_url']}",
            "",
            "## Legenda", 
            result["caption"].strip(),
            "",
            "## Hashtags",
            hashtags.strip(),
            "",
            "## Prompt de imagem",
            result["image_prompt"].strip(),
            "",
            "## URL de imagem (opcional)",
            img_url,
            "",
            "## Alt text",
            result["alt_text"].strip(),
            "",
            "## Sugestão de postagem",
            result["posting_suggestion"].strip(),
            "",
            "## Ideia de story",
            result["story_idea"].strip(),
            "",
            "## Disclaimer",
            result["disclaimer"].strip(),
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--query",
        default="facial fillers aesthetic",
        help="Consulta para buscar fontes em RSS",
    )
    parser.add_argument(
        "--rss-source",
        choices=["pubmed", "google-news"],
        default="pubmed",
        help="Fonte de RSS para selecionar o artigo",
    )
    parser.add_argument(
        "--out-dir",
        default="content/weekly-posts",
        help="Diretório para salvar o markdown gerado",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        help="Modelo OpenAI (padrão via OPENAI_MODEL)",
    )
    parser.add_argument(
        "--anthropic-model",
        default=os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022"),
        help="Modelo Anthropic (padrão via ANTHROPIC_MODEL)",
    )
    parser.add_argument(
        "--gemini-model",
        default=os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"),
        help="Modelo Gemini (padrão via GEMINI_MODEL)",
    )
    parser.add_argument(
        "--insecure-ssl",
        action="store_true",
        help="Desabilita verificação SSL (use só para debug local)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Gera saída sem chamar OpenAI (para testar pipeline)",
    )
    parser.add_argument(
        "--require-openai",
        action="store_true",
        help="Falha se OPENAI_API_KEY não estiver configurada",
    )
    parser.add_argument(
        "--ai-provider-order",
        default="openai,anthropic,gemini",
        help="Ordem de provedores: openai,anthropic,gemini",
    )
    parser.add_argument(
        "--require-any-ai",
        action="store_true",
        help="Falha se nenhum provedor de IA estiver configurado",
    )
    parser.add_argument(
        "--fallback-to-draft-on-all-fail",
        action="store_true",
        help="Se todos provedores falharem, gera rascunho sem IA em vez de falhar",
    )
    parser.add_argument(
        "--fallback-on-openai-error",
        action="store_true",
        help="Em erro da OpenAI (ex.: quota), gera rascunho sem IA em vez de falhar",
    )
    args = parser.parse_args()

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    gemini_key = os.environ.get("GOOGLE_API_KEY", "").strip()

    if args.require_openai and not openai_key:
        print("OPENAI_API_KEY não configurada", file=sys.stderr)
        return 2

    if args.require_any_ai and not (openai_key or anthropic_key or gemini_key):
        print("Nenhum provedor de IA configurado (OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY)", file=sys.stderr)
        return 2

    q = args.query.strip() or "harmonização facial benefícios"
    context = ssl_context(args.insecure_ssl)

    try:
        if args.rss_source == "pubmed":
            try:
                item = fetch_pubmed_latest(q, context=context)
            except ValueError:
                fallback_terms = [
                    "orofacial harmonization",
                    "facial harmonization",
                    "hyaluronic acid filler",
                ]
                item = None
                for term in fallback_terms:
                    try:
                        item = fetch_pubmed_latest(term, context=context)
                        break
                    except ValueError:
                        item = None
                if item is None:
                    item = fetch_google_news_first(q, context=context)
        else:
            item = fetch_google_news_first(q, context=context)
    except Exception as e:
        if isinstance(e, urllib.error.URLError) and "CERTIFICATE_VERIFY_FAILED" in str(e):
            print(
                "Falha de SSL no Python local. No macOS, instale certificados do Python (Install Certificates.command) ou rode com --insecure-ssl.",
                file=sys.stderr,
            )
        raise
    today = dt.date.today().isoformat()
    seed = {
        "topic": "harmonização facial",
        "query": q,
        "article": {
            "title": item["title"],
            "url": item["link"],
            "snippet": item.get("description", ""),
            "published_at": item.get("pub_date", ""),
        },
        "brand": {
            "name": "Dra. Bruna Silvestrini",
            "tone": "premium",
            "cta": "Agende pelo WhatsApp",
        },
    }

    def draft_result(extra_disclaimer: str | None = None) -> dict:
        disclaimer = "Resultados variam. Avaliação individual é indispensável."
        if extra_disclaimer:
            disclaimer = disclaimer + " " + extra_disclaimer.strip()
        return {
            "source_title": item["title"],
            "source_url": item["link"],
            "caption": (
                f"Tema da semana: {item['title']}\n\n"
                "Na harmonização facial, pequenas estratégias podem valorizar traços com naturalidade. "
                "Se quiser entender o que faz sentido para o seu caso, a avaliação individual é o primeiro passo.\n\n"
                "📲 Agende sua avaliação pelo WhatsApp: (11) 99550-5765\n"
                "Ou clique no link da bio!"
            ),
            "hashtags": [
                "harmonizacaofacial",
                "esteticafacial",
                "saudedapele",
                "preenchimentofacial",
                "toxina",
                "beleza",
                "autocuidado",
                "odontologia",
                "orofacial",
                "saopaulo",
            ],
            "image_prompt": (
                "Retrato editorial premium de uma mulher adulta, pele natural luminosa, "
                "clínica sofisticada minimalista, tons champagne e branco, iluminação suave difusa, "
                "profundidade de campo rasa, 85mm, ultra-detalhe, realista, alta resolução; "
                "sem texto, sem logotipos"
            ),
            "alt_text": "Retrato editorial em ambiente clínico sofisticado, estética premium e iluminação suave.",
            "posting_suggestion": "Terça-feira, 12h–14h. Fixar nos destaques por 7 dias.",
            "story_idea": "Enquete: qual sua maior dúvida sobre harmonização facial? Responda e eu explico.",
            "disclaimer": disclaimer,
        }

    if args.dry_run:
        result = draft_result()
    else:
        provider_order = [p.strip().lower() for p in args.ai_provider_order.split(",") if p.strip()]

        last_error: str | None = None
        result = None

        for provider in provider_order:
            if provider == "openai":
                if not openai_key:
                    continue
                try:
                    result = openai_chat_json(api_key=openai_key, model=args.model, seed=seed, context=context)
                    result = ensure_fields(result)
                    break
                except RuntimeError as e:
                    msg = str(e)
                    last_error = msg
                    is_quota = "insufficient_quota" in msg or "HTTP 429" in msg
                    if not (args.fallback_on_openai_error and is_quota):
                        continue
                    continue

            if provider == "anthropic":
                if not anthropic_key:
                    continue
                try:
                    result = anthropic_messages_json(api_key=anthropic_key, model=args.anthropic_model, seed=seed, context=context)
                    result = ensure_fields(result)
                    break
                except RuntimeError as e:
                    last_error = str(e)
                    continue

            if provider == "gemini":
                if not gemini_key:
                    continue
                try:
                    result = gemini_generate_json(api_key=gemini_key, model=args.gemini_model, seed=seed, context=context)
                    result = ensure_fields(result)
                    break
                except RuntimeError as e:
                    last_error = str(e)
                    continue

        if result is None:
            if args.fallback_to_draft_on_all_fail:
                extra = "Rascunho gerado sem IA: nenhum provedor respondeu com sucesso."
                if last_error:
                    extra = extra + " Erro: " + last_error[:180]
                result = draft_result(extra)
            else:
                raise RuntimeError(last_error or "Nenhum provedor de IA respondeu")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{today}.md"
    out_file.write_text(render_markdown(today, result), encoding="utf-8")

    meta_file = out_dir / f"{today}.json"
    meta_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(str(out_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
