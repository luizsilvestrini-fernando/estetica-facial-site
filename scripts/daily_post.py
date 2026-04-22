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
try:
    import holidays
except ImportError:
    holidays = None

def ssl_context(insecure: bool) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()
    return ssl.create_default_context()

def fetch_bytes(url: str, timeout: int = 20, *, context: ssl.SSLContext) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "daily-post-generator/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=context) as res:
        return res.read()


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

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
            "User-Agent": "daily-post-generator/1.0",
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


def build_system_message(weekday_theme: dict) -> str:
    base = (
        "Você é o social media da clínica premium Dra. Bruna Silvestrini. "
        "O cliente NÃO QUER mais posts genéricos. Você DEVE basear seu texto EXATAMENTE no conteúdo oficial do site e NUNCA inventar informações. "
        "Responda SOMENTE em JSON válido. Use exclusivamente português (pt-BR). "
        "PROIBIDO: Não utilize nenhuma palavra em inglês nos campos 'caption', 'alt_text', 'video_script' ou 'source_title'. "
        "OBRIGATÓRIO: a legenda (caption) DEVE terminar com: '\n\n📲 Agende sua avaliação pelo WhatsApp: (11) 99550-5765\nOu clique no link da bio!'. "
        "MUITO IMPORTANTE PARA A IMAGEM: O cliente não quer mais imagens geradas por IA genérica. Você DEVE deixar o campo 'image_prompt' VAZIO (\"\") e PREENCHER o campo 'image_url' com uma destas opções do site oficial:\n"
        "- https://drabrunasilvestrini.com.br/assets/doctor_profile_updated_full_head.png (Para posts sobre a Dra Bruna, Mitos e Verdades, ou Quem Somos)\n"
        "- https://drabrunasilvestrini.com.br/assets/botox1.jpeg (Para posts sobre Toxina Botulínica, Rugas ou Prevenção)\n"
        "- https://drabrunasilvestrini.com.br/assets/preenchimento1.jpeg (Para posts sobre Preenchimento Labial ou Hidratação)\n"
        "- https://drabrunasilvestrini.com.br/assets/harmonizacao_full_face.png (Para posts sobre Harmonização Full Face, Sustentação ou Resultados)\n"
        "- https://drabrunasilvestrini.com.br/assets/hero_modern_interactive_face_1770921982241.png (Para posts institucionais, cuidados com a pele, ciência ou estética geral)\n"
        "Campos obrigatórios: source_title, source_url, caption, hashtags, image_prompt, image_url, alt_text, posting_suggestion, story_idea, disclaimer, is_video, video_script."
    )
    theme_instructions = f"\n\nINSTRUÇÕES DO TEMA DE HOJE (EM PORTUGUÊS):\n{weekday_theme['instructions']}"
    return base + theme_instructions


def call_openai(api_key: str, model: str, system_prompt: str, seed: dict, *, context: ssl.SSLContext) -> dict:
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(seed, ensure_ascii=False)},
        ],
        "temperature": 0.7,
        "response_format": { "type": "json_object" }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60, context=context) as res:
            body = res.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"OpenAI falhou: {e.read().decode('utf-8')[:200]}")
    parsed = json.loads(body)
    content = parsed.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    return json.loads(content)

def call_anthropic(api_key: str, model: str, system_prompt: str, seed: dict, *, context: ssl.SSLContext) -> dict:
    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": model,
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": [{"role": "user", "content": json.dumps(seed, ensure_ascii=False)}],
        "temperature": 0.7,
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
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60, context=context) as res:
            body = res.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Anthropic falhou: {e.read().decode('utf-8')[:200]}")
    parsed = json.loads(body)
    content_list = parsed.get("content") or []
    text = content_list[0].get("text", "") if content_list else ""
    if "```json" in text:
        text = text.split("```json")[-1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[-1].split("```")[0].strip()
    if "{" in text and "}" in text:
        text = text[text.find("{"):text.rfind("}")+1]
    return json.loads(text)

def call_deepseek(api_key: str, model: str, system_prompt: str, seed: dict, *, context: ssl.SSLContext) -> dict:
    url = "https://api.deepseek.com/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(seed, ensure_ascii=False)}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.7
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60, context=context) as res:
            body = res.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"DeepSeek falhou: {e.read().decode('utf-8')[:200]}")
    parsed = json.loads(body)
    choices = parsed.get("choices") or []
    text = (choices[0].get("message") or {}).get("content", "").strip() if choices else ""
    if "{" in text and "}" in text:
        text = text[text.find("{"):text.rfind("}")+1]
    return json.loads(text)

def get_available_gemini_models(api_key: str, context: ssl.SSLContext) -> list[str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={urllib.parse.quote(api_key)}"
    req = urllib.request.Request(url, headers={"content-type": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30, context=context) as res:
            data = json.loads(res.read().decode("utf-8"))
            models = data.get("models", [])
            valid_models = []
            for m in models:
                name = m.get("name", "").replace("models/", "")
                methods = m.get("supportedGenerationMethods", [])
                if "gemini" in name.lower() and "generateContent" in methods:
                    valid_models.append(name)
            return valid_models
    except Exception as e:
        print(f"Aviso interno: Falha ao listar modelos do Gemini: {e}")
        return []

def call_gemini(api_key: str, model: str, system_prompt: str, seed: dict, *, context: ssl.SSLContext) -> dict:
    models_to_try = [
        model, 
        "gemini-1.5-flash", 
        "gemini-1.5-flash-002",
        "gemini-1.5-flash-001",
        "gemini-1.5-flash-8b",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro", 
        "gemini-1.5-pro-002",
        "gemini-1.5-pro-001",
        "gemini-1.0-pro",
        "gemini-pro"
    ]
    
    available = get_available_gemini_models(api_key, context)
    if available:
        print(f"🔍 Discovered Gemini models: {', '.join(available[:5])}...")
        models_to_try = available + models_to_try
    else:
        print("⚠️ Failed to dynamic list models. Relying on extensive defaults.")

    last_error = ""

    seen = set()
    unique_models = []
    for m in models_to_try:
        if m and m not in seen:
            seen.add(m)
            unique_models.append(m)

    api_versions = ["v1beta", "v1"]

    for version in api_versions:
        for m in unique_models:
            url = f"https://generativelanguage.googleapis.com/{version}/models/{urllib.parse.quote(m)}:generateContent?key={urllib.parse.quote(api_key)}"
            payload = {
                "contents": [{"role": "user", "parts": [{"text": system_prompt + "\n\n" + json.dumps(seed, ensure_ascii=False)}]}],
                "generationConfig": {"temperature": 0.7},
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"content-type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=60, context=context) as res:
                    body = res.read().decode("utf-8")
                    parsed = json.loads(body)
                    candidates = parsed.get("candidates") or []
                    content = ((candidates[0] or {}).get("content") or {}) if candidates else {}
                    parts = content.get("parts") or []
                    text = "".join([p.get("text", "") for p in parts]).strip()
                    if text.startswith("```"):
                       text = re.sub(r"^```[a-zA-Z]*\n", "", text)
                       text = re.sub(r"\n```$", "", text)
                       text = text.strip()
                    
                    try:
                        return json.loads(text)
                    except Exception as json_err:
                        raise RuntimeError(f"O modelo {m} na API {version} não retornou JSON válido.")
            except urllib.error.HTTPError as e:
                err_msg = e.read().decode("utf-8")[:200]
                last_error = err_msg
                print(f"Aviso interno: Falha ao usar {m} ({version}): {err_msg}")
                if "not found" in err_msg.lower() or "not supported" in err_msg.lower() or "Method not found" in err_msg:
                    continue # Tenta o proximo modelo/versao
                raise RuntimeError(f"Gemini falhou inesperadamente em {m} ({version}): {err_msg}")
            except Exception as ex:
                 print(f"Falha ao conectar usando {m} ({version}): {ex}")
                 continue
             
    raise RuntimeError(f"Todos os modelos do Gemini falharam em v1 e v1beta! Último erro testado: {last_error}")

def ensure_fields(obj: dict) -> dict:
    required = [
        "source_title", "source_url", "caption", "hashtags", "image_prompt",
        "image_url", "alt_text", "posting_suggestion", "story_idea", "disclaimer"
    ]
    for k in required:
        if k not in obj:
            obj[k] = ""
    if "is_video" not in obj:
        obj["is_video"] = False
    if "video_script" not in obj:
        obj["video_script"] = ""
        
    if not isinstance(obj.get("hashtags"), list):
        obj["hashtags"] = []
    # Force video flag true if script was generated
    if obj["video_script"].strip() != "":
        obj["is_video"] = True
    return obj


def get_theme_for_today() -> dict:
    today = dt.date.today()
    weekday = today.weekday()
    
    # 0=Monday, 6=Sunday
    theme = {}
    
    if weekday == 0:  # Segunda
        theme["name"] = "Antes e Depois - Procedimentos de Segunda"
        theme["instructions"] = (
            "Faça um post focado em 'Antes e Depois' (transformação) usando toxina botulínica ou preenchimento labial, com foco na naturalidade. "
            "Para o 'image_prompt', descreva uma cena HIPER-REALISTA de uma paciente mulher muito feliz e sorridente com a pele impecável, sentada em uma clínica de estética de luxo. "
            "A imagem NÃO DEVE CONTER nenhuma montagem de 'antes e depois', NENHUM TEXTO ESCRITO, apenas o retrato de excelência da paciente feliz com a pele."
        )
    elif weekday == 1: # Terça
        theme["name"] = "Ciência da Beleza e Atualizações (Terça)"
        theme["instructions"] = (
            "Faça um post educativo sobre as atualizações nos tratamentos de estética facial. Mostre como a Dra. Bruna utiliza ciência para garantir segurança. "
            "O 'image_prompt' deve ser uma fotografia de uma médica dermatologista examinando produtos premium ou a pele de uma paciente em um ambiente bem iluminado."
        )
    elif weekday == 2: # Quarta
        theme["name"] = "Curiosidades sobre Colágeno e Prevenção (Quarta)"
        theme["instructions"] = (
            "Elabore uma curiosidade super interessante sobre produção de colágeno, bioestimuladores ou prevenção do envelhecimento. "
            "Para o 'image_prompt', descreva uma fotografia macro hiper-realista da pele perfeita de um rosto feminino, transmitindo a ideia de hidratação profunda. NUNCA coloque letreiros."
        )
    elif weekday == 3: # Quinta
        theme["name"] = "Tratamentos Exclusivos e Agendamento (Quinta)"
        theme["instructions"] = (
            "Post com foco comercial elegante. Convide o usuário a conhecer a experiência exclusiva de cuidado na clínica. Fale de Harmonização Full Face. "
            "Para o 'image_prompt', descreva uma fotografia arquitetônica deslumbrante do interior de um consultório de estética luxuoso e acolhedor (sem pessoas ou textos)."
        )
    elif weekday == 4: # Sexta
        theme["name"] = "Cuidados em Casa e Skincare (Sexta)"
        theme["instructions"] = (
            "Gere conteúdo sobre Home Care (cuidados em casa): a importância de limpar a pele, hidratar e usar protetor solar para prolongar a harmonização. "
            "Para o 'image_prompt', descreva uma fotografia hiper-realista de uma mulher aplicando delicadamente um creme no rosto em um banheiro luxuoso de spa."
        )
    elif weekday == 5: # Sábado
        theme["name"] = "Resultados Avançados e Autoestima (Sábado)"
        theme["instructions"] = (
            "Faça um post narrando como os fios de sustentação ou bioestimuladores devolvem o contorno e promovem efeito lifting, elevando a autoestima. "
            "O 'image_prompt' deve descrever uma mulher madura, super elegante e sorridente em um evento social, com a pele incrivelmente firme e bem tratada."
        )
    elif weekday == 6: # Domingo
        theme["name"] = "Mitos e Verdades (Domingo)"
        theme["instructions"] = (
            "Gere um post abordando um 'Mito ou Verdade' sobre harmonização facial (ex: 'Deixa o rosto artificial? Mito!'). Explique que o foco da Dra. Bruna é a sutileza. "
            "O 'image_prompt' deve ser uma foto hiper-realista da médica sorrindo no consultório, transmitindo total confiança e empatia. Zero texto na imagem."
        )
    
    return theme


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="content/daily-posts")
    parser.add_argument("--mock-botox", action="store_true", help="Force a test post about Botox")
    parser.add_argument("--require-any-ai", action="store_true", help="Obsolete. IA is now disabled.")
    parser.add_argument("--fallback-to-draft-on-all-fail", action="store_true", help="Fallback to draft on fail")
    parser.add_argument("--fallback-on-openai-error", action="store_true", help="Try others if OpenAI fails")
    parser.add_argument("--ai-provider-order", type=str, default="", help="Obsolete. IA is now disabled.")
    parser.add_argument("--query", type=str, default="")
    args = parser.parse_args()

    # Como solicitado: Apenas gerar os posts do banco padrão do site. Nada de IA.
    print("⚠️  Modo estrito ativado: O uso de IA (OpenAI, Gemini, etc) foi DESATIVADO.")
    print("👉 Gerando post OBRIGATORIAMENTE através do Banco Oficial do Site.")
    
    fallback_posts: list[dict] = [
        {
            "source_title": "Promoção Mês das Mães - Botox Full Face",
            "source_url": "https://drabrunasilvestrini.com.br/#procedimentos",
            "caption": "✨ ESPECIAL MÊS DAS MÃES ✨\n\nPresenteie quem mais merece com o melhor da estética facial!\n\n💉 BOTOX FULL FACE\n━━━━━━━━━━━━━━━━━\n\n✅ Suaviza rugas e linhas de expressão\n✅ Previne sinais do envelhecimento\n✅ Resultado natural e rejuvenescedor\n\n💰 De R$ 1.200,00\n🔥 POR APENAS R$ 799,00\n🏷️ Em até 4x de R$ 199,75 sem juros!\n\n⏰ Promoção válida somente em Maio!\n\n📍 Unidades: Paulista | V. Madalena | V. Mariana\n🏠 Atendimento VIP à domicílio (consulte)\n\n👩‍⚕️ Dra. Bruna Silvestrini — CRO: 150190\n\n📲 Agende agora mesmo! Clique no link da bio ou pelo WhatsApp: (11) 99550-5765\n\n_Vagas limitadas!_ 💕",
            "hashtags": ["#DraBrunaSilvestrini", "#MesDasMaes", "#BotoxFullFace", "#PromocaoBotox", "#ClinicaEsteticaSP", "#PresenteDeMae"],
            "image_prompt": "",
            "image_url": "https://drabrunasilvestrini.com.br/assets/botox1.jpeg",
            "alt_text": "Promoção de Botox Full Face Mês das Mães",
            "posting_suggestion": "Postar no Feed às 12h",
            "story_idea": "Mostre os resultados rápidos do Botox para o Dia das Mães.",
            "disclaimer": "Resultados variam. Avaliação individual é indispensável.",
            "is_video": False,
            "video_script": ""
        },
        {
            "source_title": "Valor Promocional - Preenchimento Labial",
            "source_url": "https://drabrunasilvestrini.com.br/#procedimentos",
            "caption": "💋 VALOR PROMOCIONAL 💋\n\nLábios perfeitos com resultado natural e super hidratados!\n\n💉 PREENCHIMENTO LABIAL\n━━━━━━━━━━━━━━━━━━━━\n\n✅ Contorno definido e elegante\n✅ Hidratação profunda (Gloss Lips)\n✅ Volume natural e proporção perfeita\n\n💰 POR APENAS R$ 899,00\n🏷️ Em até 4x de R$ 224,75 sem juros!\n\nUtilizamos ácido hialurônico premium para entregar um resultado apaixonante e super natural.\n\n📍 Unidades: Paulista | V. Madalena | V. Mariana\n🏠 Atendimento VIP à domicílio (consulte)\n\n👩‍⚕️ Dra. Bruna Silvestrini — CRO: 150190\n\n📲 Agende sua avaliação agora! Clique no link da bio ou pelo WhatsApp: (11) 99550-5765\n\n_Agende e transforme seu sorriso!_ 💕",
            "hashtags": ["#DraBrunaSilvestrini", "#PreenchimentoLabial", "#GlossLips", "#AcidoHialuronico", "#LabiosPerfeitos", "#PromocaoEstetica"],
            "image_prompt": "",
            "image_url": "https://drabrunasilvestrini.com.br/assets/preenchimento1.jpeg",
            "alt_text": "Promoção de Preenchimento Labial",
            "posting_suggestion": "Postar no Feed às 18h",
            "story_idea": "Compartilhe um antes e depois imediato de preenchimento labial.",
            "disclaimer": "Resultados variam. Avaliação individual é indispensável.",
            "is_video": False,
            "video_script": ""
        },
        {
            "source_title": "Campanha - Harmonização Full Face",
            "source_url": "https://drabrunasilvestrini.com.br/#procedimentos",
            "caption": "🌟 HARMONIZAÇÃO FULL FACE 🌟\n\nO tratamento completo para devolver a luz ao seu rosto!\n\n💉 O QUE INCLUI:\n━━━━━━━━━━━━━━━━━\n\n✅ Preenchimento de olheiras profundas\n✅ Correção do bigode chinês\n✅ Sustentação mandibular\n✅ Harmonia facial global\n\n🪄 Resultado: aparência descansada, jovial e naturalmente linda.\n\n📍 Unidades: Paulista | V. Madalena | V. Mariana\n🏠 Atendimento VIP à domicílio (consulte)\n\n👩‍⚕️ Dra. Bruna Silvestrini — CRO: 150190\n\n📲 Solicite uma avaliação personalizada: Clique no link da bio ou pelo WhatsApp: (11) 99550-5765\n\n_Realce sua essência com excelência!_ ✨",
            "hashtags": ["#DraBrunaSilvestrini", "#HarmonizacaoFullFace", "#EsteticaFacial", "#Rejuvenescimento", "#BelezaNatural", "#Autoestima"],
            "image_prompt": "",
            "image_url": "https://drabrunasilvestrini.com.br/assets/harmonizacao_full_face.png",
            "alt_text": "Campanha Harmonização Full Face",
            "posting_suggestion": "Postar no Feed às 19h",
            "story_idea": "Explique a importância da avaliação global do rosto.",
            "disclaimer": "Resultados variam. Avaliação individual é indispensável.",
            "is_video": False,
            "video_script": ""
        },
        {
            "source_title": "Conheça a Dra. Bruna Silvestrini",
            "source_url": "https://drabrunasilvestrini.com.br/#quem-somos",
            "caption": "A clínica é um espaço pensado nos mínimos detalhes, dedicado exclusivamente a realçar a sua beleza natural através de tratamentos estéticos de excelência. 💖\n\nComo especialista reconhecida em procedimentos faciais injetáveis, uno a ciência à arte para entregar resultados que rejuvenescem e valorizam seus traços únicos. Nossa missão não é transformar quem você é, mas resgatar o seu brilho e devolver a juventude com total naturalidade, segurança e equilíbrio.\n\n📲 Agende sua avaliação pelo WhatsApp: (11) 99550-5765\nOu clique no link da bio!",
            "hashtags": ["#DraBrunaSilvestrini", "#QuemSomos", "#HarmonizacaoFacial", "#BelezaNatural", "#ClinicaEsteticaSP", "#OdontologiaEstetica"],
            "image_prompt": "",
            "image_url": "https://drabrunasilvestrini.com.br/assets/doctor_profile_updated_full_head.png",
            "alt_text": "Dra. Bruna Silvestrini",
            "posting_suggestion": "Postar no Feed às 18h",
            "story_idea": "Mostre os bastidores da clínica.",
            "disclaimer": "Resultados variam. Avaliação individual é indispensável.",
            "is_video": False,
            "video_script": ""
        },
        {
            "source_title": "Toxina Botulínica",
            "source_url": "https://drabrunasilvestrini.com.br/#procedimentos",
            "caption": "A famosa 'fórmula da juventude'! ✨\n\nA Toxina Botulínica é essencial para relaxar a musculatura, suavizar linhas de expressão e rugas, e prevenir os sinais do envelhecimento precoce. Uma prevenção inteligente que garante arqueamento de sobrancelhas e um rosto mais descansado, mantendo a naturalidade.\n\n📲 Agende sua avaliação pelo WhatsApp: (11) 99550-5765\nOu clique no link da bio!",
            "hashtags": ["#DraBrunaSilvestrini", "#ToxinaBotulinica", "#Botox", "#Prevenção", "#RejuvenescimentoFacial", "#PeleLisa"],
            "image_prompt": "",
            "image_url": "https://drabrunasilvestrini.com.br/assets/botox1.jpeg",
            "alt_text": "Aplicação de Toxina Botulínica",
            "posting_suggestion": "Postar no Feed às 12h",
            "story_idea": "Mostre como é rápido o procedimento de toxina.",
            "disclaimer": "Resultados variam. Avaliação individual é indispensável.",
            "is_video": False,
            "video_script": ""
        },
        {
            "source_title": "Preenchimento Labial",
            "source_url": "https://drabrunasilvestrini.com.br/#procedimentos",
            "caption": "Lábios desenhados sob medida para você! 👄\n\nUtilizamos ácido hialurônico para hidratar, projetar e corrigir assimetrias, entregando um volume apaixonante e super natural. Garanta um contorno definido, hidratação profunda (Gloss Lips) e a proporção perfeita que seu rosto merece.\n\n📲 Agende sua avaliação pelo WhatsApp: (11) 99550-5765\nOu clique no link da bio!",
            "hashtags": ["#DraBrunaSilvestrini", "#PreenchimentoLabial", "#LabiosPerfeitos", "#GlossLips", "#AcidoHialuronico", "#HarmonizacaoFacial"],
            "image_prompt": "",
            "image_url": "https://drabrunasilvestrini.com.br/assets/preenchimento1.jpeg",
            "alt_text": "Procedimento de Preenchimento Labial",
            "posting_suggestion": "Postar no Feed às 19h",
            "story_idea": "Compartilhe um antes e depois imediato de preenchimento labial.",
            "disclaimer": "Resultados variam. Avaliação individual é indispensável.",
            "is_video": False,
            "video_script": ""
        },
        {
            "source_title": "Harmonização Full Face",
            "source_url": "https://drabrunasilvestrini.com.br/#procedimentos",
            "caption": "Um tratamento completo para devolver a luz ao seu rosto! 🌟\n\nA Harmonização Full Face inclui preenchimento de olheiras profundas, correção do bigode chinês e sustentação mandibular. O resultado? Uma aparência descansada, sustentação dos tecidos e uma harmonia facial global incrível.\n\n📲 Agende sua avaliação pelo WhatsApp: (11) 99550-5765\nOu clique no link da bio!",
            "hashtags": ["#DraBrunaSilvestrini", "#HarmonizacaoFullFace", "#PreenchimentoDeOlheiras", "#SustentacaoFacial", "#BelezaNatural", "#Autoestima"],
            "image_prompt": "",
            "image_url": "https://drabrunasilvestrini.com.br/assets/harmonizacao_full_face.png",
            "alt_text": "Resultados de Harmonização Full Face",
            "posting_suggestion": "Postar no Feed às 18h",
            "story_idea": "Explique a importância da avaliação global do rosto.",
            "disclaimer": "Resultados variam. Avaliação individual é indispensável.",
            "is_video": False,
            "video_script": ""
        },
        {
            "source_title": "Por que nossa clínica é a escolha ideal?",
            "source_url": "https://drabrunasilvestrini.com.br/#quem-somos",
            "caption": "Por que escolher a nossa clínica para o seu cuidado facial? 💎\n\n✔️ Excelência: Compromisso com resultados impecáveis.\n✔️ Segurança: Protocolos rigorosos e a melhor tecnologia do mercado.\n✔️ Inovação: Técnicas modernas e produtos premium de última geração.\n✔️ Exclusividade: Tratamentos 100% personalizados com mapeamento individualizado do seu rosto.\n\nVenha viver essa experiência!\n\n📲 Agende sua avaliação pelo WhatsApp: (11) 99550-5765\nOu clique no link da bio!",
            "hashtags": ["#DraBrunaSilvestrini", "#ClinicaEsteticaSP", "#EsteticaPremium", "#Seguranca", "#InovacaoNaEstetica", "#AtendimentoExclusivo"],
            "image_prompt": "",
            "image_url": "https://drabrunasilvestrini.com.br/assets/hero_modern_interactive_face_1770921982241.png",
            "alt_text": "Rosto interativo e moderno representando tecnologia e exclusividade",
            "posting_suggestion": "Postar no Feed às 12h",
            "story_idea": "Mostre os produtos premium que você utiliza.",
            "disclaimer": "Resultados variam. Avaliação individual é indispensável.",
            "is_video": False,
            "video_script": ""
        }
    ]
    
    import random
    result = random.choice(fallback_posts)
    result = ensure_fields(result)

    today = dt.date.today().isoformat()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Gerar markdown bonitinho para o PR
    md_content = f"# Post Diário — {today}\n\n"
    md_content += f"**Post retirado oficialmente do Site da Clínica.**\n\n"
    if result["is_video"]:
        md_content += "🎬 **VÍDEO DETECTADO** (Este post será publicado como Reels)\n\n"
        md_content += "### Roteiro de Áudio (Locução)\n"
        md_content += f"> {result['video_script']}\n\n"
    md_content += f"## Legenda\n{result['caption']}\n\n"
    md_content += f"## Hashtags\n{' '.join(['#'+h if not h.startswith('#') else h for h in result['hashtags']])}\n\n"
    if result.get("image_prompt"):
        md_content += f"## Imagem Prompt\n{result['image_prompt']}\n\n"
    if result.get("image_url"):
        md_content += f"## Imagem Oficial do Site\n{result['image_url']}\n\n"
    
    out_file_md = out_dir / f"{today}.md"
    out_file_md.write_text(md_content, encoding="utf-8")

    out_file_json = out_dir / f"{today}.json"
    out_file_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ Rascunho gerado em {out_file_json}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
