import os
import json
import urllib.request
import subprocess

def check_for_ok():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id_target = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id_target:
        print("Faltam variáveis de ambiente (Token ou Chat ID).")
        return

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read())
    except Exception as e:
        print(f"Falha ao ler telegram: {e}")
        return
        
    if not data.get("ok"):
        print("Telegram API retornou erro.")
        return
        
    messages = data.get("result", [])
    
    # Procura pelas mensagens (apenas no chat autorizado)
    found_ok = False
    highest_update_id = 0
    
    for update in messages:
        uid = update.get("update_id", 0)
        if uid > highest_update_id:
            highest_update_id = uid
            
        msg = update.get("message", {})
        chat = msg.get("chat", {})
        text = msg.get("text", "").strip().lower()
        
        # Confirma que é do chat correto
        if str(chat.get("id")) == str(chat_id_target):
            if text in ["ok", "aprovar", "aprovado", "posta", "pode postar"]:
                found_ok = True
                print(f"👍 Comando de liberação recebido! (Mensagem: {text})")

    if found_ok:
        # Se achou "OK", tenta mergiar os PRs abertos relacionados ao daily.
        print("Tentando realizar o Merge via GitHub CLI...")
        cmd = ["gh", "pr", "list", "--state", "open", "--label", "automation", "--json", "number"]
        try:
            output = subprocess.check_output(cmd, text=True)
            prs = json.loads(output)
            
            if not prs:
                print("Nenhum PR de automação aberto encontrado para merge com a label 'automation'.")
            else:
                print(f"Encontrados {len(prs)} PR(s) para processar.")
            
            for pr in prs:
                pr_num = str(pr['number'])
                print(f"Tentando realizar o merge do PR #{pr_num}...")
                merge_cmd = ["gh", "pr", "merge", pr_num, "--squash", "--delete-branch", "--admin"]
                proc = subprocess.run(merge_cmd, capture_output=True, text=True)
                
                if proc.returncode == 0:
                    print(f"✅ Merge do PR #{pr_num} realizado com sucesso!")
                    # Feedback pro usuário
                    fb_url = f"https://api.telegram.org/bot{token}/sendMessage"
                    fb_data = {"chat_id": chat_id_target, "text": f"✅ O robô obedeceu seu comando e começou a publicar o post! Sairá no Feed em instantes."}
                    urllib.request.urlopen(urllib.request.Request(fb_url, data=json.dumps(fb_data).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST"))
                else:
                    print(f"❌ Falha ao mergiar PR #{pr_num}: {proc.stderr}")
                
        except Exception as e:
            print(f"Erro crítico ao tentar aprovar automaticamente: {e}")
            
    # Marcar as mensagens como lidas
    if highest_update_id > 0:
        offset_url = f"https://api.telegram.org/bot{token}/getUpdates?offset={highest_update_id + 1}"
        try:
            urllib.request.urlopen(offset_url)
        except:
            pass

if __name__ == "__main__":
    check_for_ok()
