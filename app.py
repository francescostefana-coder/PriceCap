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
                model
