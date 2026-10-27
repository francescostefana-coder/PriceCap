import streamlit as st
import requests
import urllib.parse
from bs4 import BeautifulSoup
import re
from openai import OpenAI  # Usiamo il client standard compatibile

# Configurazione pagina ottimizzata per smartphone (Mobile-First)
st.set_page_config(
    page_title="TechAdvisor & Price Finder", 
    page_icon="🛍️", 
    layout="centered"
)

st.markdown("""
<style>
    .stApp { background-color: #F8FAFC; color: #1E293B; }
    h1 { color: #0F172A; font-weight: 800; }
    .stButton>button { width: 100%; border-radius: 10px; background-color: #2563EB; color: white; font-weight: bold; }
    .stButton>button:hover { background-color: #1D4ED8; }
</style>
""", unsafe_allow_html=True)

st.title("🛍️ TechAdvisor Italia")
st.caption("Recensioni intelligenti, alternative e i 3 prezzi migliori dai reali e-commerce.")

# Configurazione API
st.sidebar.header("🔑 Configurazione")
openrouter_api_key = st.secrets.get("OPENROUTER_API_KEY", "") or st.sidebar.text_input("OpenRouter API Key (Gratis)", type="password")
tavily_api_key = st.secrets.get("TAVILY_API_KEY", "") or st.sidebar.text_input("Tavily API Key (Opzionale)", type="password")

# Modelli gratuiti e ultra-stabili su OpenRouter
MODELLI_IA = [
    'deepseek/deepseek-chat:free',
    'meta-llama/llama-3.3-70b-instruct:free',
    'mistralai/mistral-7b-instruct:free'
]

def pulisci_testo_markdown(testo):
    if not testo:
        return ""
    return testo.replace("|", "-").replace("[", "(").replace("]", ")").replace("\n", " ").strip()

def cerca_sul_web_sicura(tavily_key, query_prodotto):
    query_reale = f'"{query_prodotto}" (site:amazon.it OR site:mediaworld.it OR site:unieuro.it OR site:euronics.it OR site:trony.it OR site:monclick.it) -site:trovaprezzi.it -site:eprice.it -site:blog.* -site:forum.*'
    risultati = []
    
    if tavily_key:
        try:
            url = "https://api.tavily.com/search"
            payload = {
                "api_key": tavily_key,
                "query": query_reale,
                "search_depth": "basic",
                "max_results": 8,
                "include_answer": False
            }
            res = requests.post(url, json=payload, timeout=4)
            if res.status_code == 200:
                data = res.json().get("results", [])
                for r in data:
                    risultati.append({
                        "title": pulisci_testo_markdown(r.get("title", "")),
                        "url": r.get("url", ""),
                        "content": pulisci_testo_markdown(r.get("content", ""))
                    })
                if risultati:
                    return risultati, "Tavily (Store Filtrati)"
        except Exception:
            pass

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        query_encoded = urllib.parse.quote(query_reale)
        url = f"https://html.duckduckgo.com/html/?q={query_encoded}"
        res = requests.post(url, headers=headers, data={'q': query_reale}, timeout=4)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            blocchi = soup.select(".result") or soup.select(".web-result")
            
            for r in blocchi[:8]:
                title_elem = r.select_one(".result__title a") or r.select_one(".result__a")
                snippet_elem = r.select_one(".result__snippet")
                if title_elem:
                    url_dest = title_elem.get("href", "")
                    if not any(x in url_dest for x in ["trovaprezzi", "eprice", "blog", "forum", "wiki"]):
                        risultati.append({
                            "title": pulisci_testo_markdown(title_elem.get_text(strip=True)),
                            "url": url_dest,
                            "content": pulisci_testo_markdown(snippet_elem.get_text(strip=True)) if snippet_elem else ""
                        })
        if risultati:
            return risultati, "DuckDuckGo (Store Filtrati)"
    except Exception:
        pass

    return [], "Nessuno"

def genera_analisi_completa(prodotto, risultati_web, api_key):
    testo_grezzo = "\n\n".join([f"Store/Titolo: {r['title']}\nURL: {r['url']}\nInfo: {r['content']}" for r in risultati_web])
    
    prompt = (
        f"Sei un esperto tecnologico per il mercato italiano. "
        f"Analizza i dati di e-commerce reali raccolti per il prodotto: '{prodotto}'.\n\n"
        f"Crea una risposta strutturata esattamente nelle seguenti 4 sezioni in italiano:\n\n"
        f"### Recensione Dettagliata\n"
        f"- Scrivi una recensione approfondita e originale basata sulle reali esperienze d'uso.\n"
        f"- Pro (Punti di forza): elenco puntato.\n"
        f"- Contro (Limiti): elenco puntato.\n\n"
        f"### Valide Alternative\n"
        f"- Consiglia 2 o 3 prodotti alternativi sul mercato italiano.\n\n"
        f"### Top 3 Prezzi e Offerte\n"
        f"Crea una TABELLA Markdown ordinata dal prezzo piu basso con queste colonne:\n"
        f"| Negozio | Prezzo (€) | Link Diretto |\n"
        f"Includi i migliori 3 prezzi reali e usa la sintassi [Vai al Negozio](URL) per il link.\n\n"
        f"Dati raccolti:\n{testo_grezzo}"
    )

    # Configurazione client OpenRouter (OpenAI-compatibile)
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    
    ultimo_errore = ""
    
    for modello in MODELLI_IA:
        try:
            response = client.chat.completions.create(
                model=modello,
                messages=[{"role": "user", "content": prompt}],
                extra_headers={
                    "HTTP-Referer": "https://github.com/pricecap", # Opzionale per OpenRouter
                    "X-Title": "TechAdvisor Italia",
                }
            )
            if response and response.choices[0].message.content:
                return response.choices[0].message.content, f"OpenRouter ({modello})"
        except Exception as e:
            ultimo_errore = str(e)
            continue
            
    raise Exception(f"Errore OpenRouter: {ultimo_errore}")

# --- INTERFACCIA UTENTE ---

prodotto_input = st.text_input("Cerca un prodotto elettronico:", placeholder="Es. iPhone 15, Sony WH-1000XM5, TV LG OLED...")

col1, col2 = st.columns(2)
with col1:
    cerca_btn = st.button("Analizza e Trova Prezzi", type="primary")

if cerca_btn:
    if not prodotto_input.strip():
        st.warning("Inserisci il nome di un prodotto elettronico.")
    elif not openrouter_api_key.strip():
        st.error("Inserisci la tua OpenRouter API Key nella barra laterale a sinistra.")
    else:
        with st.status("Scansione e-commerce italiani autorizzati...", expanded=True) as status:
            st.write("Filtro anti-aggregatori e blog in corso...")
            risultati_web, fonte_ricerca = cerca_sul_web_sicura(tavily_api_key, prodotto_input)
            
            if not risultati_web:
                status.update(label="Nessun riscontro trovato.", state="error")
                st.warning("Prova a specificare meglio il modello esatto.")
            else:
                st.write(f"Elaborazione recensione e prezzi ({fonte_ricerca})...")
                try:
                    output_finale, modalita = genera_analisi_completa(prodotto_input, risultati_web, openrouter_api_key)
                    status.update(label=f"Analisi completata ({modalita})!", state="complete")
                    st.markdown("---")
                    st.markdown(output_finale)
                except Exception as e:
                    status.update(label="Errore elaborazione IA", state="error")
                    st.error(f"{e}")
