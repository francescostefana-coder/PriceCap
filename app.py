import streamlit as st
import requests
from PIL import Image
from google import genai
import urllib.parse
from bs4 import BeautifulSoup
import re

# Configurazione pagina
st.set_page_config(page_title="TrovaPrezzi & Recensioni Italia", page_icon="⚡", layout="centered")

# --- GRAFICA MINIMALE ---
st.markdown("""
<style>
    .stApp { background-color: #F9FAFC; color: #2D3748; font-family: sans-serif; }
    h1, h2, h3 { color: #1A202C; }
    .stButton>button { background-color: #4A5568; color: white; border-radius: 8px; border: none; padding: 0.5rem 1rem; }
    .stButton>button:hover { background-color: #2D3748; }
</style>
""", unsafe_allow_html=True)

st.title("⚡ TrovaPrezzi, Usato & Recensioni")
st.markdown("<p style='color: #718096;'>Confronta prezzi e scopri cosa dicono gli utenti (pro e contro reali).</p>", unsafe_allow_html=True)

# --- CONFIGURAZIONE API ---
st.sidebar.header("🔑 Configurazione")
gemini_api_key = st.secrets.get("GEMINI_API_KEY", "") or st.sidebar.text_input("Gemini API Key", type="password")
tavily_api_key = st.secrets.get("TAVILY_API_KEY", "") or st.sidebar.text_input("Tavily API Key (Opzionale)", type="password")

MODELLI_IA = ['gemini-1.5-flash', 'gemini-1.5-pro']

# --- PAROLE CHIAVE DA ESCLUDERE SEMPRE ---
BLACKLIST_TERMINI = [
    "come scaricare", "come fare", "guida tutorial"
]

# --- FUNZIONI CORE ---

def estrai_prezzo_da_testo(testo):
    match = re.search(r'(\d+[\.,]?\d*)\s*€|€\s*(\d+[\.,]?\d*)', testo)
    if match:
        p = match.group(1) or match.group(2)
        return f"{p} €"
    return "Vedi link"

def e_risultato_pertinente(titolo, snippet, prodotto_cercato):
    testo_totale = f"{titolo} {snippet}".lower()
    for bad_word in BLACKLIST_TERMINI:
        if bad_word in testo_totale:
            return False
    parole_prodotto = [p.lower() for p in prodotto_cercato.split() if len(p) > 2]
    matches = sum(1 for p in parole_prodotto if p in testo_totale)
    if parole_prodotto and (matches / len(parole_prodotto)) < 0.5:
        return False
    return True

def identifica_prodotto_da_foto(image_file, api_key):
    if not api_key:
        return ""
    client = genai.Client(api_key=api_key)
    img = Image.open(image_file)
    for modello in MODELLI_IA:
        try:
            response = client.models.generate_content(
                model=modello,
                contents=[img, "Scrivi SOLO il nome esatto del prodotto (marca e modello), senza altre parole."]
            )
            if response and response.text:
                return response.text.strip()
        except Exception:
            continue
    return ""

def cerca_sul_web_sicura(tavily_key, query):
    risultati = []
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
            res = requests.post(url, json=payload, timeout=3)
            if res.status_code == 200:
                data = res.json().get("results", [])
                for r in data:
                    risultati.append({
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "content": r.get("content", "")
                    })
                if risultati:
                    return risultati, "Tavily API"
        except Exception:
            pass

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        query_encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={query_encoded}"
        res = requests.post(url, headers=headers, data={'q': query}, timeout=3)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for r in soup.select(".result")[:10]:
                title_elem = r.select_one(".result__title a")
                snippet_elem = r.select_one(".result__snippet")
                if title_elem:
                    risultati.append({
                        "title": title_elem.get_text(strip=True),
                        "url": title_elem.get("href"),
                        "content": snippet_elem.get_text(strip=True) if snippet_elem else ""
                    })
        if risultati:
            return risultati, "DuckDuckGo HTML"
    except Exception:
        pass

    return [], "Nessuno"

def elabora_con_gemini_o_fallback(prompt_sistema, risultati_web, prodotto_cercato, api_key):
    testo_grezzo = "\n\n".join([f"Titolo: {r['title']}\nURL: {r['url']}\nSnippet: {r['content']}" for r in risultati_web])
    
    if api_key:
        client = genai.Client(api_key=api_key)
        for modello in MODELLI_IA:
            try:
                response = client.models.generate_content(
                    model=modello,
                    contents=f"{prompt_sistema}\n\nDati dal web:\n{testo_grezzo}"
                )
                if response and response.text:
                    return response.text, f"IA ({modello})"
            except Exception:
                continue

    # Fallback diretto in assenza di IA
    tabella_diretta = "| Store / Titolo | Prezzo (€) | Recensioni / Note | Link |\n| :--- | :--- | :--- | :--- |\n
