import streamlit as st
import requests
from google import genai
import urllib.parse
from bs4 import BeautifulSoup
import re

# Configurazione pagina ottimizzata per smartphone (Mobile-First)
st.set_page_config(
    page_title="TechAdvisor & Price Finder", 
    page_icon="🛍️", 
    layout="centered"
)

# Stile grafico pulito e moderno
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

# Configurazione API sicura da Streamlit Secrets o Sidebar
st.sidebar.header("🔑 Configurazione")
gemini_api_key = st.secrets.get("GEMINI_API_KEY", "") or st.sidebar.text_input("Gemini API Key", type="password")
tavily_api_key = st.secrets.get("TAVILY_API_KEY", "") or st.sidebar.text_input("Tavily API Key (Opzionale)", type="password")

MODELLI_IA = ['gemini-1.5-flash', 'gemini-1.5-pro']

# --- FUNZIONI DI SUPPORTO E SICUREZZA ---

def pulisci_testo_markdown(testo):
    if not testo:
        return ""
    return testo.replace("|", "-").replace("[", "(").replace("]", ")").replace("\n", " ").strip()

def cerca_sul_web_sicura(tavily_key, query_prodotto):
    """
    Cerca escludendo tassativamente Trovaprezzi, Eprice, blog e forum,
    restringendo la ricerca ai principali store di elettronica in Italia.
    """
    query_reale = f'"{query_prodotto}" (site:amazon.it OR site:mediaworld.it OR site:unieuro.it OR site:euronics.it OR site:trony.it OR site:monclick.it) -site:trovaprezzi.it -site:eprice.it -site:blog.* -site:forum.*'
    
    risultati = []
    
    # 1. Tavily API (se configurata)
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

    # 2. DuckDuckGo HTML Fallback con filtri rigidi sugli store
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
    """Usa Gemini per elaborare recensione, pro/contro, alternative e top 3 prezzi con debug dell'errore."""
    testo_grezzo = "\n\n".join([f"Store/Titolo: {r['title']}\nURL: {r['url']}\nInfo: {r['content']}" for r in risultati_web])
    
    prompt = (
        f"Sei un esperto tecnologico e consumer advocate per il mercato italiano. "
        f"Analizza i dati di e-commerce reali raccolti per il prodotto: '{prodotto}'.\n\n"
        f"Crea una risposta strutturata esattamente nelle seguenti 4 sezioni in italiano:\n\n"
        f"### 📝 1. Recensione Chiara e Rielaborata\n"
        f"- Scrivi una recensione approfondita, originale e fruibile da chiunque (senza copia-incolla meccanico), basata sulle reali esperienze d'uso.\n"
        f"- **Pro (Punti di forza):** Elenco puntato chiaro.\n"
        f"- **Contro (Limiti/Difetti):** Elenco puntato chiaro.\n\n"
        f"### 🔄 2. Valide Alternative\n"
        f"- Consiglia 2 o 3 prodotti alternativi presenti sul mercato italiano della stessa categoria o fascia di prezzo, spiegando brevemente perché sceglierli.\n\n"
        f"### 📊 3. Top 3 Prezzi e Offerte\n"
        f"Crea una TABELLA Markdown ordinata dal prezzo più basso con esattamente queste colonne:\n"
        f"| E-commerce / Negozio | Prezzo (€) | Link Diretto |\n"
        f"REGOLE TABELLA:\n"
        f"- Estrai e deduci i prezzi reali in Euro dai dati forniti per gli store.\n"
        f"- Inserisci solo i **migliori 3 prezzi reali** trovati.\n"
        f"- Usa la sintassi Markdown `[Vai al Negozio](URL)` per la colonna del link.\n\n"
        f"Dati di e-commerce raccolti:\n{testo_grezzo}"
    ]

    client = genai.Client(api_key=api_key)
    ultimo_errore = ""
    
    for modello in MODELLI_IA:
        try:
            response = client.models.generate_content(model=modello, contents=prompt)
            if response and response.text:
                return response.text, f"IA ({modello})"
        except Exception as e:
            ultimo_errore = str(e)
            continue
            
    raise Exception(f"Errore tecnico da Google API: {ultimo_errore}")

# --- INTERFACCIA UTENTE ---

prodotto_input = st.text_input("🔍 Cerca un prodotto elettronico:", placeholder="Es. iPhone 15, Sony WH-1000XM5, TV LG OLED...")

col1, col2 = st.columns(2)
with col1:
    cerca_btn = st.button("🚀 Analizza e Trova Prezzi", type="primary")

if cerca_btn:
    if not prodotto_input.strip():
        st.warning("⚠️ Inserisci il nome di un prodotto elettronico.")
    elif not gemini_api_key.strip():
        st.error("⚠️ **Attenzione:** Inserisci la tua **Gemini API Key** nella barra laterale a sinistra per generare la recensione e trovare i prezzi!")
    else:
        with st.status("🔍 Scansione e-commerce italiani autorizzati...", expanded=True) as status:
            st.write("Filtro rigoroso anti-aggregatori e blog in corso...")
            risultati_web, fonte_ricerca = cerca_sul_web_sicura(tavily_api_key, prodotto_input)
            
            if not risultati_web:
                status.update(label="❌ Nessun riscontro diretto trovato sugli store.", state="error")
                st.warning("Prova a specificare meglio il modello esatto del prodotto (es. marca + modello completo).")
            else:
                st.write(f"🤖 Elaborazione recensione, pro/contro e top prezzi ({fonte_ricerca})...")
                try:
                    output_finale, modalita = genera_analisi_completa(prodotto_input, risultati_web, gemini_api_key)
                    status.update(label=f"✅ Analisi completata con successo!", state="complete")
                    st.markdown("---")
                    st.markdown(output_finale)
                except Exception as e:
                    status.update(label="❌ Errore durante l'elaborazione dell'IA.", state="error")
                    st.error(f"{e}")
