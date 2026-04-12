import sys
import json
import os
import urllib.request
import urllib.parse
import ssl
from pathlib import Path

ssl._create_default_https_context = ssl._create_unverified_context

def get_latest_post_json() -> dict:
    d = Path("content/daily-posts")
    files = sorted(d.glob("*.json"), reverse=True)
    if not files:
        return {}
    return json.loads(files[0].read_text(encoding="utf-8"))

def build_image_url(prompt: str) -> str:
    encoded = urllib.parse.quote(prompt, safe="")
    return f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1080&nologo=true"

def send_telegram():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    pr_url = os.environ.get("PR_URL", "")
    
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing")
        return

    post = get_latest_post_json()
    if not post:
         # Generic message if json fails
         url = f"https://api.telegram.org/bot{token}/sendMessage"
         data = {"chat_id": chat_id, "text": f"Novo rascunho criado, mas JSON não encontrado! Link: {pr_url}"}
    else:
         caption = post.get("caption", "...")
         hashtags = " ".join(post.get("hashtags", []))
         msg = f"📝 **Novo Rascunho Gerado!**\n\n{caption}\n\n{hashtags}\n\n"
         
         if post.get("is_video"):
             msg += "🎬 *Atenção: Este é um roteiro de VÍDEO. A imagem de fundo é enviada acima, mas a música e locução serão geradas apenas quando for pro Instagram.*\n"
             msg += f"🎙️ *Locução:* {post.get('video_script','')}\n\n"

         msg += f"👉 Para aprovar e postar agora, responda: **OK**\n"
         msg += f"Ou veja o código completo aqui: {pr_url}"

         img_url = build_image_url(post.get("image_prompt", ""))
         
         url = f"https://api.telegram.org/bot{token}/sendPhoto"
         data = {
             "chat_id": chat_id,
             "photo": img_url,
             "caption": msg,
             "parse_mode": "Markdown"
         }

    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as res:
            print("Telegram enviado com sucesso!")
    except Exception as e:
        print(f"Erro ao enviar telegram: {e}")

if __name__ == "__main__":
    send_telegram()
