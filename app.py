import streamlit as st
import requests
import urllib.parse
from bs4 import BeautifulSoup
import re
from openai import OpenAI

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

# Modelli gratuiti di fallback con auto-routing dinamico
MODELLI_IA = [
    'openrouter/auto',
    'meta-llama/llama-3.3-70b-instruct:free',
    'google/gemini-2.0-flash-exp:free'
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
    
    prompt = f"""Sei un esperto tecnologico per il mercato italiano. Analizza i dati di e-commerce reali raccolti per il prodotto: '{prodotto}'.

C
