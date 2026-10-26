import streamlit as st
import requests
from PIL import Image
from google import genai
import urllib.parse
from bs4 import BeautifulSoup
import re

# Configurazione pagina
st.set_page_config(page_title="TrovaPrezzi Italia", page_icon="⚡", layout="centered")

# --- GRAFICA MINIMALE ---
st.markdown("""
<style>
    .stApp { background-color: #F9FAFC; color: #2D3748; font-family: sans-serif; }
    h1, h2, h3 { color: #1A202C; }
    .stButton>button { background-color: #4A5568; color: white; border-radius: 8px; border: none; padding: 0.5rem 1rem; }
    .stButton>button:hover { background-color: #2D3748; }
</style>
""", unsafe_allow_html=True)

st.title("⚡ TrovaPrezzi & Usato (Filtrato & Pertinente)")
st.markdown("<p style='color: #718096;'>Filtro anti-spazzatura per risultati pertinenti e prezzi reali in Italia.</p>", unsafe_allow_html=True)

# --- CONFIGURAZIONE API ---
st.sidebar.header("🔑 Configurazione")
gemini_api_key = st.secrets.get("GEMINI_API_KEY", "") or st.sidebar.text_input("Gemini API Key", type="password")
tavily_api_key = st.secrets.get("TAVILY_API_KEY", "") or st.sidebar.text_input("Tavily API Key (Opzionale)", type="password")

MODELLO_IA = 'gemini-1.5-flash'

# --- PAROLE CHIAVE DA ESCLUDERE SEMPRE ---
BLACKLIST_TERMINI = [
    "recensione", "come scaricare", "come fare", "guida", "tutorial", 
    "trovaprezzi.it/offerte", "forum", "vs", "confronto", "scheda tecnica"
]

# --- FUNZIONI CORE ---

def estrai_prezzo_da_testo(testo):
    """Cerca pattern di prezzo in Euro all'interno del testo estratto"""
    match = re.search(r'(\d+[\.,]?\d*)\s*€|€\s*(\d+[\.,]?\d*)', testo)
    if match:
        p = match.group(1) or match.group(2)
        return f"{p} €"
    return "Vedi link"

def e_risultato_pertinente(titolo, snippet, prodotto_cercato):
    """Verifica che il risultato parli davvero del prodotto inserito e non sia un blog/guida"""
    testo_totale = f"{titolo} {snippet}".lower()
    
    # 1. Controlla Blacklist
    for bad_word in BLACKLIST_TERMINI:
        if bad_word in testo_totale:
            return False
            
    # 2. Controlla che le parole chiave principali del prodotto siano presenti
    parole_prodotto = [p.lower() for p in prodotto_cercato.split() if len(p) > 2]
    matches = sum(1 for p in parole_prodotto if p in testo_totale)
    
    # Deve contenere almeno la metà delle parole chiave del prodotto
    if parole_prodotto and (matches / len(parole_prodotto)) < 0.5:
        return False
        
    return True

def identifica_prodotto_da_foto(image_file, api_key):
    try:
        client = genai.Client(api_key=api_key)
        img = Image.open(image_file)
        response = client.models.generate_content(
            model=MODELLO_IA,
            contents=[img, "Scrivi SOLO il nome esatto del prodotto (marca e modello), senza altre parole."]
        )
        return response.text.strip()
    except Exception:
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
            res = requests.post(url, json=payload, timeout=4)
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
        query_encoded = urllib.parse.quote
