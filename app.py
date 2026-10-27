import streamlit as st
import requests
from PIL import Image
from google import genai
import urllib.parse
from bs4 import BeautifulSoup
import re

# Configurazione pagina Streamlit
st.set_page_config(
    page_title="TrovaPrezzi & Recensioni Italia", 
    page_icon="⚡", 
    layout="centered"
)

# --- INTESTAZIONE ---
st.title("⚡ TrovaPrezzi, Usato & Recensioni")
st.caption("Recensioni dettagliate, analisi Pro/Contro e confronto prezzi in tempo reale.")

# --- CONFIGURAZIONE API SIDEBAR ---
st.sidebar.header("🔑 Configurazione API")
gemini_api_key = st.secrets.get("GEMINI_API_KEY", "") or st.sidebar.text_input("Gemini API Key", type="password")
tavily_api_key = st.secrets.get("TAVILY_API_KEY", "") or st.sidebar.text_input("Tavily API Key (Opzionale)", type="password")

MODELLI_IA = ['gemini-1.5-flash', 'gemini-1.5-pro']
BLACKLIST_TERMINI = ["come scaricare", "come fare", "guida tutorial", "scarica gratis"]

# --- UTILITIES & PARSING ---

def pulisci_testo_markdown(testo):
    """Rimuove caratteri che potrebbero rompere la tabella o il layout Markdown."""
    if not testo:
        return ""
    return testo.replace("|", "-").replace("[", "(").replace("]", ")").replace("\n", " ").strip()

def estrai_prezzo_da_testo(testo):
    """Regex ottimizzato per rilevare prezzi in Euro in formati italiani ed europei."""
    match = re.search(r'(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)\s*€|€\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)', testo)
    if match:
        p = match.group(1) or match.group(2)
        return f"{p} €"
    return "Vedi link"

def e_risultato_pertinente(titolo, snippet, prodotto_cercato):
    """Filtro euristico per scartare spam e guide non inerenti."""
    testo_totale = f"{titolo} {snippet}".lower()
    
    for bad_word in BLACKLIST_TERMINI:
        if bad_word in testo_totale:
            return False
            
    parole_prodotto = [p.lower() for p in prodotto_cercato.split() if len(p) > 2]
    if not parole_prodotto:
        return True
        
    matches = sum(1 for p in parole_prodotto if p in testo_totale)
    return (matches / len(parole_prodotto)) >= 0.4

# --- AI & VISION SERVICE ---

def identifica_prodotto_da_foto(image_file, api_key):
    """Analisi visiva dell'immagine con gestione robusta delle eccezioni."""
    if not api_key:
        return ""
    try:
        client = genai.Client(api_key=api_key)
        img = Image.open(image_file)
        prompt = "Identifica il prodotto in foto. Scrivi SOLO marca e modello esatto (es. 'Dyson V15 Detect'), senza punti o spiegazioni."
        
        for modello in MODELLI_IA:
            try:
                response = client.models.generate_content(
                    model=modello,
                    contents=[img, prompt]
                )
                if response and response.text:
                    return response.text.strip()
            except Exception:
                continue
    except Exception as e:
        st.sidebar.error(f"Errore Vision: {e}")
    return ""

# --- SEARCH ENGINE SERVICE ---

def cerca_sul_web_sicura(tavily_key, query):
    """Ricerca a 2 livelli: Tavily API -> DuckDuckGo HTML Fallback."""
    risultati = []
    
    # 1. Tavily API
    if tavily_key:
        try:
            url = "https://api.tavily.com/search"
            payload = {
                "api_key": tavily_key,
                "query": query,
                "search_depth": "basic",
                "max_results": 10,
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
                    return risultati, "Tavily API"
        except Exception:
            pass

    # 2. DuckDuckGo HTML Scraping (Fallback resiliente)
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        query_encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={query_encoded}"
        res = requests.post(url, headers=headers, data={'q': query}, timeout=4)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            blocchi = soup.select(".result") or soup.select(".web-result")
            
            for r in blocchi[:10]:
                title_elem = r.select_one(".result__title a") or r.select_one(".result__a")
                snippet_elem = r.select_one(".result__snippet")
                if title_elem:
                    risultati.append({
                        "title": pulisci_testo_markdown(title_elem.get_text(strip=True)),
                        "url": title_elem.get("href", ""),
                        "content": pulisci_testo_markdown(snippet_elem.get_text(strip=True)) if snippet_elem else ""
                    })
        if risultati:
            return risultati, "DuckDuckGo HTML"
    except Exception:
        pass

    return [], "Nessuno"

# --- LLM PROCESSING & FALLBACK ENGINE ---

def elabora_con_gemini_o_fallback(prompt_sistema, risultati_web, prodotto_cercato, api_key):
    """Generazione recensione + tabella tramite LLM con Fallback automatico anti-503
