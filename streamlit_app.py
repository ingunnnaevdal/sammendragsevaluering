import streamlit as st
import pandas as pd
import random
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv
import ast
import os

st.set_page_config(layout="wide")

load_dotenv()
password = os.getenv("MONGODB_PASSWORD")
uri = f"mongodb+srv://ingunn:{password}@samiaeval.2obnm.mongodb.net/?retryWrites=true&w=majority&tlsAllowInvalidCertificates=true"

client = MongoClient(uri, server_api=ServerApi('1'))
evaluering_kolleksjon = client['SamiaEvalDB']['personalisering_VOL2']

bruker_id = st.text_input("Skriv inn ditt navn eller ID:", key="bruker_id")
if not bruker_id:
    st.stop()

undersokelse_svart = evaluering_kolleksjon.find_one({'bruker_id': bruker_id, 'type': 'undersokelse'})

if not undersokelse_svart:
    st.title("Brukerundersøkelse")
    st.header("Før vi starter, vennligst svar på noen spørsmål:")

    svar_lengde = st.radio(
        "Hvor lange mener du at nyhetssammendrag burde være?",
        options=["1-2 setninger", "Et kort avsnitt", "En mer detaljert oppsummering (flere avsnitt)", "Varierer avhengig av sakens kompleksitet"]
    )

    svar_presentasjon = st.radio(
        "Hvordan foretrekker du at nyhetssammendrag presenteres?",
        options=[
            "Nøytralt og objektivt, uten vurderinger",
            "Kort og konsist, med kun de viktigste fakta",
            "Med en kort vurdering av saken",
            "Med forklaringer av komplekse begreper eller sammenhenger"
        ]
    )

    svar_bakgrunn = st.radio(
        "Hvor viktig er det at nyhetssammendrag gir bakgrunnsinformasjon og kontekst?",
        options=["Svært viktig", "Litt viktig", "Ikke viktig"]
    )

    svar_viktigst = st.radio(
        "Hva er viktigst for deg?",
        options=[
            "At nyhetssammendraget gir meg all relevant informasjon raskt",
            "At nyhetssammendraget forklarer hvorfor saken er viktig",
            "At nyhetssammendraget er enkelt å forstå",
            "At nyhetssammendraget har god språklig kvalitet"
        ]
    )

    svar_irriterende = st.radio(
        "Hva ville irritert deg mest med et nyhetssammendrag?",
        options=[
            "Upresis eller unøyaktig informasjon",
            "For mye tekst eller unødvendige detaljer",
            "Mangel på kontekst eller bakgrunn",
            "Et subjektivt eller vinklet språk"
        ]
    )

    if st.button("Start evaluering"):
        undersokelse = {
            'bruker_id': bruker_id,
            'type': 'undersokelse',
            'svar_lengde': svar_lengde,
            'svar_presentasjon': svar_presentasjon,
            'svar_bakgrunn': svar_bakgrunn,
            'svar_viktigst': svar_viktigst,
            'svar_irriterende': svar_irriterende
        }
        evaluering_kolleksjon.insert_one(undersokelse)
        st.success("Takk for at du svarte! Du kan nå starte evalueringen.")
        st.rerun()



def les_datasett(filsti):
    try:
        return pd.read_csv(filsti)
    except FileNotFoundError:
        st.error(f"Filen {filsti} ble ikke funnet.")
        st.stop()
    except pd.errors.ParserError:
        st.error(f"Kunne ikke lese filen {filsti}. Sjekk formatet.")
        st.stop()

def lagre_evaluering_mongodb(kolleksjon, evaluering):
    try:
        kolleksjon.insert_one(evaluering)
        st.success("Evaluering lagret!")
    except Exception as e:
        st.error(f"Feil under lagring i MongoDB: {e}")

st.title("Evaluering av sammendrag")
filsti = 'data.csv'
data = les_datasett(filsti)

if f'artikkel_indeks_{bruker_id}' not in st.session_state:
    bruker_evaluering = evaluering_kolleksjon.find_one({'bruker_id': bruker_id}, sort=[('_id', -1)])
    st.session_state[f'artikkel_indeks_{bruker_id}'] = (
        bruker_evaluering.get('artikkel_indeks', -1) + 1 if bruker_evaluering else 0
    )

start_indeks = st.session_state[f'artikkel_indeks_{bruker_id}']
if start_indeks >= len(data):
    st.success("Alle artikler er evaluert!")
    st.stop()

row = data.iloc[start_indeks]

modellene = ['gemini', 'claude', 'gpt']
if f'modell_indeks_{bruker_id}_{start_indeks}' not in st.session_state:
    st.session_state[f'modell_indeks_{bruker_id}_{start_indeks}'] = 0

modell_indeks = st.session_state[f'modell_indeks_{bruker_id}_{start_indeks}']

if modell_indeks < len(modellene):
    valgt_modell = modellene[modell_indeks]
    st.header(f"Artikkel {start_indeks + 1}/{len(data)} - Evaluering {modell_indeks + 1}/3")

st.markdown(f"""
<div class='main-container'>
    <h1 class='article-title'>{row['title']}</h1>
    <div class='lead-text'>{row['byline']}</div>
    <div class='lead-text'>Publisert: {row['creation_date']}</div>
    <div class='lead-text'>{row['lead_text']}</div>
    <div class='article-body'>{row['artikkeltekst']}</div>
</div>
""", unsafe_allow_html=True)

if f"valgte_sammendrag_{bruker_id}_{start_indeks}_{valgt_modell}" not in st.session_state:
    faste_sammendrag = [
        (f"{valgt_modell}_prompt4", row[f"{valgt_modell}_prompt4"]),
        (f"{valgt_modell}_prompt4_age", row[f"{valgt_modell}_prompt4_age"])
    ]
    
    andre_sammendrag = [
        (col, row[col]) for col in row.index 
        if valgt_modell in col and col not in [f"{valgt_modell}_prompt4", f"{valgt_modell}_prompt4_age"]
    ]
    
    random.shuffle(andre_sammendrag)
    valgte_tilfeldige = andre_sammendrag[:2]
    
    valgte_sammendrag = faste_sammendrag + valgte_tilfeldige
    random.shuffle(valgte_sammendrag)
    
    st.session_state[f"valgte_sammendrag_{bruker_id}_{start_indeks}_{valgt_modell}"] = valgte_sammendrag

valgte_sammendrag = st.session_state[f"valgte_sammendrag_{bruker_id}_{start_indeks}_{valgt_modell}"]

st.subheader("Sammendrag:")
rankings = {}
ikke_publiserbar = {}
ranking_options = ["Best", "Nest best", "Nest dårligst", "Dårligst"]

for i, (kilde, tekst) in enumerate(valgte_sammendrag):
    with st.expander(f"Sammendrag {i + 1}"):
        try:
            tekst = ast.literal_eval(tekst)
        except (SyntaxError, ValueError):
            pass

        if isinstance(tekst, list):
            tekst = [punkt.replace("•", "").strip() for punkt in tekst]
            tekst = [f"- {punkt}" if not punkt.startswith("-") else punkt for punkt in tekst]
            st.markdown("\n".join(tekst), unsafe_allow_html=True)
        else:
            st.write(tekst)

        rankings[kilde] = st.selectbox(
            f"Ranger sammendrag {i + 1}", ranking_options, key=f"ranking_{bruker_id}_{start_indeks}_{valgt_modell}_{i}"
        )

        ikke_publiserbar[kilde] = st.checkbox(
            "Kan ikke publiseres", key=f"ikke_publiserbar_{bruker_id}_{start_indeks}_{valgt_modell}_{i}"
        )

kommentar = st.text_area("Kommentar:", key=f"kommentar_{bruker_id}_{start_indeks}_{valgt_modell}")

if st.button("Lagre evaluering", key=f"lagre_{bruker_id}_{start_indeks}_{valgt_modell}"):
    evaluering = {
        'bruker_id': bruker_id,
        'artikkel_indeks': start_indeks,
        'uuid': row['uuid'],
        'modell': valgt_modell,
        'rangeringer': rankings,
        'ikke_publiserbar': ikke_publiserbar,
        'sammendrag_kilder': [kilde for kilde, _ in valgte_sammendrag],
        'kommentar': kommentar
    }
    lagre_evaluering_mongodb(evaluering_kolleksjon, evaluering)
    
    st.session_state[f'modell_indeks_{bruker_id}_{start_indeks}'] += 1
    
    if st.session_state[f'modell_indeks_{bruker_id}_{start_indeks}'] >= len(modellene):
        st.session_state[f'artikkel_indeks_{bruker_id}'] += 1
        st.session_state.pop(f'modell_indeks_{bruker_id}_{start_indeks}')
    
    st.rerun()



st.markdown("""
    <style>
        :root {
            --primary-text-color: #333;
            --secondary-text-color: #555;
            --background-color: #f9f9f9;
        }

        @media (prefers-color-scheme: dark) {
            :root {
                --primary-text-color: #f0f0f0;
                --secondary-text-color: #bbb;
                --background-color: #222;
            }
        }
        .main-container {
            max-width: 800px;
            margin: auto;
            padding: 20px;
            background-color: var(--background-color);
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
            max-height: 800px;
            overflow-y: auto;
        }
        .article-title {
            font-size: 28px;
            font-weight: bold;
            color: var(--primary-text-color);
            margin-bottom: 10px;
        }
        .lead-text {
            font-size: 18px;
            color: var(--secondary-text-color);
            margin-bottom: 20px;
        }
        .article-body {
            font-size: 16px;
            line-height: 1.6;
            color: var(--primary-text-color);
            margin-bottom: 30px;
        }
        .summary-box {
            background: white;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        }
        .summary-header {
            font-weight: bold;
            margin-bottom: 10px;
        }
        .evaluation-section {
            background-color: #fff;
            padding: 20px;
            border: 1px solid #ddd;
            border-radius: 8px;
        }
        .evaluation-button {
            background-color: #2051b3;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
        }
        .evaluation-button:hover {
            background-color: #183c85;
        }
    </style>
""", unsafe_allow_html=True)