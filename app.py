from flask import Flask, request, jsonify
from flask_cors import CORS
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import io
import base64
import datetime
import logging
import requests
import os
import threading
import secrets
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ============================================================
# OTP STORE (in-memory, TTL 10 minutes)
# ============================================================
OTP_STORE = {}
OTP_TTL   = 600

DEV_MODE = os.environ.get('OTP_DEV_MODE', 'true').lower() == 'true'
DEV_CODE = '1234'

# ============================================================
# RÉFÉRENTIEL YAKEEY — MARRAKECH (mars 2026)
# Colonnes : appt, villa, dar (0.85×appt), riad (1.10×appt Médina)
# liq : liquidité marché 1=faible 2=moyenne 3=élevée
# ============================================================
REFERENTIEL = {
    "Abouab Gueliz - Mabrouka":     {"appt": 6684,  "villa": 7764,  "dar": 5682,  "riad": None,  "liq": 3},
    "Abouab Mhamid":                {"appt": 5467,  "villa": 3527,  "dar": 4647,  "riad": None,  "liq": 2},
    "Agdal":                        {"appt": 16325, "villa": 9021,  "dar": 13876, "riad": None,  "liq": 3},
    "Ain Iti":                      {"appt": 8521,  "villa": 8353,  "dar": 7243,  "riad": None,  "liq": 2},
    "Al Maaden - Ain Slim":         {"appt": 5648,  "villa": 6952,  "dar": 4801,  "riad": None,  "liq": 2},
    "Alal El Fassi":                {"appt": 10595, "villa": 6664,  "dar": 9006,  "riad": None,  "liq": 3},
    "Amerchich":                    {"appt": 10795, "villa": 8320,  "dar": 9176,  "riad": None,  "liq": 2},
    "Ancienne Medina - Assouel":    {"appt": 11007, "villa": 18078, "dar": 11693, "riad": 12710, "liq": 2},
    "Ancienne Medina - Bab Aylan":  {"appt": 9928,  "villa": None,  "dar": 9410,  "riad": 11417, "liq": 2},
    "Ancienne Medina - Bab Ghmat":  {"appt": 5976,  "villa": 6276,  "dar": 5803,  "riad": 6308,  "liq": 2},
    "Ancienne Medina - Ben Chegra": {"appt": 6351,  "villa": None,  "dar": 6018,  "riad": 7304,  "liq": 2},
    "Ancienne Medina - Ben Salah":  {"appt": 5999,  "villa": None,  "dar": 5699,  "riad": 6599,  "liq": 1},
    "Ancienne Medina - Boukar":     {"appt": 10236, "villa": 11263, "dar": 10058, "riad": 10933, "liq": 2},
    "Ancienne Medina - Dar El Bacha": {"appt": 20078, "villa": 10872, "dar": 18361, "riad": 19956, "liq": 3},
    "Ancienne Medina - El Hara":    {"appt": 13748, "villa": 12442, "dar": 13441, "riad": 14610, "liq": 3},
    "Ancienne Medina - Laksour":    {"appt": 8735,  "villa": None,  "dar": 8298,  "riad": 10042, "liq": 2},
    "Ancienne Medina - Place Jemaa El Fna": {"appt": 8298, "villa": 7316, "dar": 8061, "riad": 8756, "liq": 3},
    "Ancienne Medina - Rahba Kedima": {"appt": 6752, "villa": None, "dar": 9235,  "riad": 10038, "liq": 2},
    "Ancienne Medina - Riad Laarouss": {"appt": 12375, "villa": None, "dar": 11745, "riad": 14231, "liq": 2},
    "Arset Lamaach":                {"appt": 8733,  "villa": None,  "dar": 8276,  "riad": 10043, "liq": 2},
    "Assif":                        {"appt": 8986,  "villa": 8237,  "dar": 7908,  "riad": None,  "liq": 3},
    "Azzouzia":                     {"appt": 5422,  "villa": 7139,  "dar": 4446,  "riad": None,  "liq": 2},
    "Bab Doukkala":                 {"appt": 3697,  "villa": None,  "dar": 3922,  "riad": 4252,  "liq": 1},
    "Bab Ighli":                    {"appt": 10301, "villa": 8423,  "dar": 9877,  "riad": 10737, "liq": 3},
    "Berrima":                      {"appt": 20920, "villa": None,  "dar": 18410, "riad": 23012, "liq": 2},
    "Bin Lkchali":                  {"appt": 9487,  "villa": 19356, "dar": 7779,  "riad": None,  "liq": 1},
    "Bouaakaz":                     {"appt": 5989,  "villa": 10955, "dar": 4911,  "riad": None,  "liq": 1},
    "Boulvard Moulay Abdellah - Route De Safi": {"appt": 9813, "villa": 6264, "dar": 8635, "riad": None, "liq": 2},
    "Camps El Ghoul - Victor Hugo": {"appt": 12065, "villa": 12692, "dar": 10617, "riad": None,  "liq": 3},
    "Chwiter":                      {"appt": 4333,  "villa": 5182,  "dar": 3553,  "riad": None,  "liq": 1},
    "Daoudiat":                     {"appt": 10055, "villa": 8232,  "dar": 8848,  "riad": None,  "liq": 3},
    "Diour Al Atlas":               {"appt": 5759,  "villa": None,  "dar": 4723,  "riad": None,  "liq": 1},
    "Douar Chouhada":               {"appt": 11149, "villa": None,  "dar": 9142,  "riad": None,  "liq": 1},
    "Douar Iziki":                  {"appt": 6509,  "villa": 5257,  "dar": 5337,  "riad": None,  "liq": 1},
    "Douar Laaskar":                {"appt": 6100,  "villa": 8729,  "dar": 5002,  "riad": None,  "liq": 1},
    "El Fadel":                     {"appt": 6611,  "villa": None,  "dar": 5421,  "riad": None,  "liq": 1},
    "Essaada":                      {"appt": 6594,  "villa": None,  "dar": 5407,  "riad": None,  "liq": 1},
    "Gueliz":                       {"appt": 13758, "villa": 14588, "dar": 12107, "riad": None,  "liq": 3},
    "Hay Al Massar":                {"appt": 5891,  "villa": None,  "dar": 4831,  "riad": None,  "liq": 1},
    "Hay Azli":                     {"appt": 6510,  "villa": None,  "dar": 5338,  "riad": None,  "liq": 1},
    "Hay Charaf":                   {"appt": 6762,  "villa": 10630, "dar": 5545,  "riad": None,  "liq": 2},
    "Hay El Bahja":                 {"appt": 8493,  "villa": 9278,  "dar": 6964,  "riad": None,  "liq": 2},
    "Hay Hassani":                  {"appt": 6887,  "villa": 4181,  "dar": 5648,  "riad": None,  "liq": 2},
    "Hay Inara":                    {"appt": 9687,  "villa": 3712,  "dar": 7943,  "riad": None,  "liq": 1},
    "Hay Menara":                   {"appt": 7582,  "villa": 7341,  "dar": 6217,  "riad": None,  "liq": 2},
    "Hay Nahda":                    {"appt": 7114,  "villa": None,  "dar": 5833,  "riad": None,  "liq": 1},
    "Hay Zitoun":                   {"appt": 6179,  "villa": None,  "dar": 5063,  "riad": None,  "liq": 1},
    "Hivernage":                    {"appt": 14665, "villa": 16919, "dar": 12905, "riad": None,  "liq": 3},
    "Issil":                        {"appt": 10142, "villa": 5769,  "dar": 8316,  "riad": None,  "liq": 2},
    "Izdihar":                      {"appt": 8580,  "villa": 10402, "dar": 7036,  "riad": None,  "liq": 2},
    "Jardin De La Koutoubia":       {"appt": 15546, "villa": 14024, "dar": 15004, "riad": 17252, "liq": 3},
    "Jawhar":                       {"appt": 5916,  "villa": 6195,  "dar": 4851,  "riad": None,  "liq": 1},
    "Jenan El Ghali":               {"appt": 10502, "villa": None,  "dar": 8612,  "riad": None,  "liq": 1},
    "Jnan Aourad":                  {"appt": 9612,  "villa": 10628, "dar": 7882,  "riad": None,  "liq": 2},
    "Kasbah":                       {"appt": 7131,  "villa": 8672,  "dar": 6860,  "riad": 7453,  "liq": 3},
    "Koudiat Laabid":               {"appt": 6943,  "villa": 7422,  "dar": 5694,  "riad": None,  "liq": 2},
    "Lakssour":                     {"appt": 10247, "villa": 9090,  "dar": 9867,  "riad": 10720, "liq": 3},
    "Lotissement Arafat":           {"appt": 6567,  "villa": 5810,  "dar": 5385,  "riad": None,  "liq": 2},
    "Lotissement Cherifia":         {"appt": 5931,  "villa": 7337,  "dar": 4864,  "riad": None,  "liq": 2},
    "Lotissement Les Palmiers":     {"appt": 5325,  "villa": 9221,  "dar": 4367,  "riad": None,  "liq": 2},
    "M'Hamid":                      {"appt": 5771,  "villa": 6365,  "dar": 4732,  "riad": None,  "liq": 2},
    "Massira 1":                    {"appt": 6811,  "villa": 6338,  "dar": 5585,  "riad": None,  "liq": 3},
    "Massira 2":                    {"appt": 5672,  "villa": 5775,  "dar": 4651,  "riad": None,  "liq": 3},
    "Massira 3":                    {"appt": 5921,  "villa": 7223,  "dar": 4855,  "riad": None,  "liq": 3},
    "Mellah":                       {"appt": 8389,  "villa": None,  "dar": 7958,  "riad": 9648,  "liq": 2},
    "Palmeraie":                    {"appt": 13449, "villa": 6166,  "dar": 11835, "riad": None,  "liq": 3},
    "Palmeraie Extension":          {"appt": 11935, "villa": 6038,  "dar": 10503, "riad": None,  "liq": 3},
    "Portes De Marrakech Addoha":   {"appt": 5775,  "villa": 6242,  "dar": 4736,  "riad": None,  "liq": 2},
    "Prestigia":                    {"appt": 18842, "villa": 12277, "dar": 16581, "riad": None,  "liq": 3},
    "Quartier Industriel De Sidi Ghanem": {"appt": 4864, "villa": 4669, "dar": 3989, "riad": None, "liq": 1},
    "Riad Essalam":                 {"appt": 8509,  "villa": 8387,  "dar": 6977,  "riad": None,  "liq": 2},
    "Rouidate - Majorelle":         {"appt": 9485,  "villa": 9178,  "dar": 8347,  "riad": None,  "liq": 3},
    "Route D'Amizmiz":              {"appt": 11805, "villa": None,  "dar": 9680,  "riad": None,  "liq": 1},
    "Route D'Amizmiz - Cherifia":   {"appt": 6047,  "villa": 4070,  "dar": 4959,  "riad": None,  "liq": 1},
    "Route D'Amizmiz - Douar Soultan": {"appt": 5026, "villa": 8345, "dar": 4121, "riad": None, "liq": 1},
    "Route De Casablanca":          {"appt": None,  "villa": 4724,  "dar": None,  "riad": None,  "liq": 1},
    "Route De Fes":                 {"appt": 10868, "villa": 10321, "dar": 8912,  "riad": None,  "liq": 2},
    "Route De Fes - Atlas - Amelkis": {"appt": 9611, "villa": 7170, "dar": 7881,  "riad": None,  "liq": 2},
    "Route De Fes - Douar Tamasna": {"appt": 8475,  "villa": 5517,  "dar": 6950,  "riad": None,  "liq": 1},
    "Route De Fes - Oulad Jelal":   {"appt": 7498,  "villa": 5163,  "dar": 6148,  "riad": None,  "liq": 1},
    "Route De L'Ourika - Canal Zaraba": {"appt": 11155, "villa": None, "dar": 9147, "riad": None, "liq": 1},
    "Route De L'Ourika - Douar Bouazza": {"appt": 7125, "villa": None, "dar": 5843, "riad": None, "liq": 1},
    "Route De L'Ourika - Plage Rouge": {"appt": 4190, "villa": None, "dar": 3436,  "riad": None,  "liq": 1},
    "Route De L'Ourika - Waky":     {"appt": 6012,  "villa": 7158,  "dar": 4930,  "riad": None,  "liq": 1},
    "Route De L'Ourika (Agdal)":    {"appt": 12107, "villa": 6381,  "dar": 9928,  "riad": None,  "liq": 1},
    "Route De L'Ourika (Sidi Abdellah Ghiat)": {"appt": 11155, "villa": 3084, "dar": 9147, "riad": None, "liq": 1},
    "Route De L'Ourika (Tassoultante)": {"appt": 6847, "villa": 6088, "dar": 5615, "riad": None, "liq": 1},
    "Route De Ouarzazate - Douar Ait Lahmad": {"appt": 4904, "villa": 7824, "dar": 4022, "riad": None, "liq": 1},
    "Route De Ouarzazate - Douar El Guern": {"appt": 9291, "villa": 6675, "dar": 7619, "riad": None, "liq": 1},
    "Route De Ouarzazate - Douar Laadem": {"appt": 20549, "villa": 6903, "dar": 17630, "riad": None, "liq": 1},
    "Route De Ouarzazate - Gzoula Sidi Mbarek": {"appt": 7649, "villa": 7839, "dar": 6272, "riad": None, "liq": 1},
    "Route De Tahanaout - Cherifia": {"appt": 5312, "villa": 9569, "dar": 4356,   "riad": None,  "liq": 1},
    "Route De Tahanaout - Oulad Yahya": {"appt": 3672, "villa": 6807, "dar": 3011, "riad": None, "liq": 1},
    "S.Y.B.A":                      {"appt": 6175,  "villa": 10875, "dar": 5063,  "riad": None,  "liq": 1},
    "Saada-Tissir":                 {"appt": 6222,  "villa": 5920,  "dar": 5102,  "riad": None,  "liq": 2},
    "Sanaoubar":                    {"appt": 8064,  "villa": 10551, "dar": 6612,  "riad": None,  "liq": 2},
    "Semlalia":                     {"appt": 11029, "villa": 10058, "dar": 9706,  "riad": None,  "liq": 3},
    "Sidi Abbad":                   {"appt": 8655,  "villa": 7938,  "dar": 7097,  "riad": None,  "liq": 2},
    "Sidi Abdellah Ghiat":          {"appt": 9221,  "villa": 3382,  "dar": 7561,  "riad": None,  "liq": 1},
    "Sidi Mimoun":                  {"appt": 6575,  "villa": 15222, "dar": 7607,  "riad": 8268,  "liq": 2},
    "Socoma - Lotissement Wilaya":  {"appt": 6413,  "villa": 12000, "dar": 5259,  "riad": None,  "liq": 1},
    "Sofia Targa":                  {"appt": 9881,  "villa": 6616,  "dar": 8102,  "riad": None,  "liq": 2},
    "Targa":                        {"appt": 9909,  "villa": 7999,  "dar": 8125,  "riad": None,  "liq": 2},
    "Zohor Targa - Zephyr":         {"appt": 6330,  "villa": 6507,  "dar": 5190,  "riad": None,  "liq": 2},
}

# ============================================================
# COEFFICIENTS
# ============================================================

COEFF_ETAT = {
    "neuf":      1.15,
    "excellent": 1.10,
    "bon":       1.00,
    "moyen":     0.90,
    "arenoveer": 0.75,
}

# Étage étendu jusqu'à 10+ (appt uniquement)
# Dernier étage avec terrasse = traité via équipements (terrasse_privative)
COEFF_ETAGE = {
    -1: 0.88,  # RDC commercial / semi-enterré
    0:  0.95,  # RDC résidentiel
    1:  1.00,
    2:  1.02,
    3:  1.05,
    4:  1.07,
    5:  1.08,
    6:  1.09,
    7:  1.10,
    8:  1.10,
    9:  1.10,
    10: 1.10,
}

# Ancienneté du bien (distinct de l'état)
COEFF_ANCIENNETE = {
    "neuf_2022_plus":  1.00,
    "recent_2015_21":  0.97,
    "moyen_2005_14":   0.93,
    "ancien_avant_05": 0.88,
}

# Nombre de pièces / chambres
COEFF_PIECES = {
    "studio": 0.92,
    "f1":     0.95,
    "f2":     1.00,
    "f3":     1.03,
    "f4":     1.06,
    "f5plus": 1.08,
}

# Implantation villa/maison
COEFF_IMPLANTATION = {
    "isolee":   1.00,  # référence
    "jumelee":  0.93,  # mur mitoyen 1 côté
    "bande":    0.86,  # murs mitoyens 2 côtés
}

# Équipements — bonus additifs
BONUS_EQUIPEMENTS = {
    # Communs appt + villa
    "parking":            0.04,
    "ascenseur":          0.03,
    "piscine":            0.08,
    "gardien":            0.02,
    "terrasse":           0.03,
    "vue":                0.05,
    "residence_fermee":   0.05,  # NOUVEAU — résidence sécurisée (appt + villa)
    "digicode_camera":    0.02,  # NOUVEAU — sécurité électronique
    # Villa / Maison
    "jardin":             0.04,
    "terrain_sup_300":    0.03,  # terrain > 300 m² en plus du bâti
    "terrasse_privative": 0.06,  # dernier étage appt ou rooftop villa
    "double_garage":      0.03,
}

# Liquidité quartier → fourchette dynamique
FOURCHETTE_LIQ = {
    1: (0.88, 1.12),  # périphérie liq faible → ±12%
    2: (0.90, 1.10),  # standard → ±10%
    3: (0.92, 1.08),  # centre liquide → ±8%
}

# Décote liquidité sur valeur centrale
DECOTE_LIQ = {
    1: 0.97,  # liq faible → −3%
    2: 1.00,
    3: 1.00,
}

# ============================================================
# COEFFICIENTS SURFACE
# ============================================================
def coeff_surface(surface, type_bien):
    if type_bien in ("appartement", "riad"):
        if surface < 60:    return 1.05
        if surface < 100:   return 1.00
        if surface < 150:   return 0.97
        if surface < 200:   return 0.94
        return 0.90
    else:  # villa, dar
        if surface < 150:   return 1.05
        if surface < 250:   return 1.02
        if surface < 400:   return 1.00
        if surface < 600:   return 0.96
        return 0.92

# ============================================================
# FONCTION ESTIMATION PRINCIPALE
# ============================================================
def estimer(quartier, type_bien, surface, etat, etage=1,
            equipements=None, pieces=None, anciennete=None,
            implantation=None):
    if equipements is None:
        equipements = []

    ref = REFERENTIEL.get(quartier)
    if not ref:
        return None, f"Quartier '{quartier}' non trouvé dans le référentiel"

    # Clé type de bien
    cle_map = {
        "appartement": "appt",
        "villa":       "villa",
        "dar":         "dar",
        "maison":      "dar",   # alias
        "riad":        "riad",
    }
    cle_type = cle_map.get(type_bien.lower())
    if not cle_type:
        return None, f"Type de bien invalide : {type_bien}"

    prix_m2_base = ref.get(cle_type)

    # Fallback intelligent si prix absent
    if not prix_m2_base:
        if cle_type == "dar" and ref.get("appt"):
            prix_m2_base = round(ref["appt"] * 0.85)
        elif cle_type == "riad" and ref.get("appt"):
            prix_m2_base = round(ref["appt"] * 1.10)
        elif cle_type == "villa" and ref.get("appt"):
            prix_m2_base = round(ref["appt"] * 0.90)
        elif cle_type == "appt" and ref.get("villa"):
            prix_m2_base = round(ref["villa"] * 1.10)
        else:
            return None, "Aucun prix disponible pour ce type de bien dans ce quartier"

    liq = ref.get("liq", 2)

    # Coefficients de base
    c_etat       = COEFF_ETAT.get(etat, 1.0)
    c_etage      = COEFF_ETAGE.get(min(max(etage, -1), 10), 1.0) if type_bien in ("appartement",) else 1.0
    c_surface    = coeff_surface(surface, type_bien)
    c_anciennete = COEFF_ANCIENNETE.get(anciennete, 1.0) if anciennete else 1.0
    c_pieces     = COEFF_PIECES.get(pieces, 1.0) if pieces and type_bien in ("appartement",) else 1.0

    # Implantation (villa / dar uniquement)
    c_implantation = 1.0
    if type_bien in ("villa", "dar", "maison") and implantation:
        c_implantation = COEFF_IMPLANTATION.get(implantation, 1.0)

    # Équipements
    bonus = sum(BONUS_EQUIPEMENTS.get(eq, 0) for eq in equipements)
    c_equipements = 1 + bonus

    # Liquidité
    c_liq_decote = DECOTE_LIQ.get(liq, 1.0)
    fourchette_low, fourchette_high = FOURCHETTE_LIQ.get(liq, (0.90, 1.10))

    # Prix final
    ["Prix m² après application des coefficients",   f"{estimation['prix_m2_ajuste']:,}
                      * c_etat
                      * c_etage
                      * c_surface
                      * c_anciennete
                      * c_pieces
                      * c_implantation
                      * c_equipements
                      * c_liq_decote)

    valeur_centrale = prix_m2_ajuste * surface
    valeur_min = round(valeur_centrale * fourchette_low  / 1000) * 1000
    valeur_max = round(valeur_centrale * fourchette_high / 1000) * 1000
    valeur_mid = round(valeur_centrale / 1000) * 1000

    return {
        "prix_m2_base":    round(prix_m2_base),
        "prix_m2_ajuste":  round(prix_m2_ajuste),
        "valeur_min":      valeur_min,
        "valeur_max":      valeur_max,
        "valeur_mid":      valeur_mid,
        "surface":         surface,
        "quartier":        quartier,
        "type_bien":       type_bien,
        "etat":            etat,
        "liquidite":       liq,
        "coefficients": {
            "etat":          c_etat,
            "etage":         round(c_etage, 3),
            "surface":       round(c_surface, 3),
            "anciennete":    round(c_anciennete, 3),
            "pieces":        round(c_pieces, 3),
            "implantation":  round(c_implantation, 3),
            "equipements":   round(c_equipements, 3),
            "liquidite":     round(c_liq_decote, 3),
        }
    }, None

# ============================================================
# GÉNÉRATION PDF
# ============================================================
def generer_pdf(estimation, nom_client, tel_client, whatsapp_client):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    or_color    = colors.HexColor('#c9a84c')
    dark_color  = colors.HexColor('#0d1117')
    muted_color = colors.HexColor('#6b7280')

    style_titre      = ParagraphStyle('titre',      parent=styles['Normal'], fontSize=22, fontName='Helvetica-Bold', textColor=dark_color, spaceAfter=4,  alignment=TA_LEFT)
    style_sous_titre = ParagraphStyle('sous_titre', parent=styles['Normal'], fontSize=11, fontName='Helvetica',      textColor=muted_color, spaceAfter=16, alignment=TA_LEFT)
    style_section    = ParagraphStyle('section',    parent=styles['Normal'], fontSize=9,  fontName='Helvetica-Bold', textColor=or_color,    spaceBefore=14, spaceAfter=6, alignment=TA_LEFT)
    style_body       = ParagraphStyle('body',       parent=styles['Normal'], fontSize=10, fontName='Helvetica',      textColor=dark_color,  spaceAfter=4,  leading=16)
    style_disclaimer = ParagraphStyle('disclaimer', parent=styles['Normal'], fontSize=8,  fontName='Helvetica',      textColor=muted_color, spaceAfter=4,  leading=12)
    style_centre     = ParagraphStyle('centre',     parent=styles['Normal'], fontSize=10, fontName='Helvetica',      textColor=dark_color,  alignment=TA_CENTER)

    content = []
    date_str = datetime.datetime.now().strftime("%d/%m/%Y")

    header_data = [[
        Paragraph("<b>PropIntel</b>", ParagraphStyle('logo', parent=styles['Normal'], fontSize=18, fontName='Helvetica-Bold', textColor=or_color)),
        Paragraph(f"Rapport d'Estimation<br/><font size=9 color='grey'>{date_str}</font>",
            ParagraphStyle('right', parent=styles['Normal'], fontSize=11, fontName='Helvetica', textColor=dark_color, alignment=TA_RIGHT))
    ]]
    header_table = Table(header_data, colWidths=[85*mm, 85*mm])
    header_table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    content.append(header_table)
    content.append(HRFlowable(width="100%", thickness=1, color=or_color, spaceAfter=16))
    content.append(Paragraph("Estimation Immobilière", style_titre))
    content.append(Paragraph("Intelligence Immobilière · Marrakech · Modèle calibré sur données réelles 2024–2026", style_sous_titre))

    content.append(Paragraph("INFORMATIONS CLIENT", style_section))
    client_table = Table([
        ["Nom",       nom_client],
        ["Téléphone", tel_client],
        ["WhatsApp",  whatsapp_client],
    ], colWidths=[40*mm, 130*mm])
    client_table.setStyle(TableStyle([
        ('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'), ('FONTSIZE',(0,0),(-1,-1),9),
        ('TEXTCOLOR',(0,0),(0,-1),colors.HexColor('#374151')), ('TEXTCOLOR',(1,0),(1,-1),dark_color),
        ('ROWBACKGROUNDS',(0,0),(-1,-1),[colors.HexColor('#f9fafb'),colors.white]),
        ('TOPPADDING',(0,0),(-1,-1),6), ('BOTTOMPADDING',(0,0),(-1,-1),6), ('LEFTPADDING',(0,0),(-1,-1),8),
    ]))
    content.append(client_table)

    content.append(Paragraph("BIEN ÉVALUÉ", style_section))
    type_labels = {
        "appartement": "Appartement",
        "villa":       "Villa",
        "dar":         "Maison / Dar",
        "maison":      "Maison / Dar",
        "riad":        "Riad",
    }
    etat_labels = {"neuf":"Neuf","excellent":"Excellent","bon":"Bon état","moyen":"État moyen","arenoveer":"À rénover"}
    liq_labels  = {1:"Faible","2":"Moyenne",2:"Moyenne",3:"Élevée"}
    impl_labels = {"isolee":"Isolée","jumelee":"Jumelée","bande":"En bande"}
    niv_labels  = {"plain_pied":"Plain-pied (RDC)","r1":"R+1","r2":"R+2","r3":"R+3 et +"}
    ss_labels   = {"avec_ss":"Avec sous-sol aménagé","avec_ss_brut":"Avec sous-sol brut"}

    bien_rows = [
        ["Type",             type_labels.get(estimation['type_bien'], estimation['type_bien'])],
        ["Quartier",         estimation['quartier']],
        ["Surface bâtie",    f"{estimation['surface']} m²"],
        ["État général",     etat_labels.get(estimation['etat'], estimation['etat'])],
        ["Liquidité marché", liq_labels.get(estimation['liquidite'], "—")],
        ["Prix m² référence",f"{estimation['prix_m2_base']:,} MAD/m²".replace(","," ")],
        ["Prix m² ajusté",   f"{estimation['prix_m2_ajuste']:,} MAD/m²".replace(","," ")],
    ]
    if estimation.get('implantation'):
        bien_rows.insert(2, ["Implantation", impl_labels.get(estimation['implantation'], estimation['implantation'])])
    if estimation.get('niveaux_dar'):
        bien_rows.insert(3, ["Niveaux", niv_labels.get(estimation['niveaux_dar'], estimation['niveaux_dar'])])
    if estimation.get('sous_sol'):
        bien_rows.insert(3, ["Sous-sol", ss_labels.get(estimation['sous_sol'], estimation['sous_sol'])])

    bien_table = Table(bien_rows, colWidths=[45*mm, 125*mm])
    bien_table.setStyle(TableStyle([
        ('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'), ('FONTSIZE',(0,0),(-1,-1),9),
        ('TEXTCOLOR',(0,0),(0,-1),colors.HexColor('#374151')), ('TEXTCOLOR',(1,0),(1,-1),dark_color),
        ('ROWBACKGROUNDS',(0,0),(-1,-1),[colors.HexColor('#f9fafb'),colors.white]),
        ('TOPPADDING',(0,0),(-1,-1),6), ('BOTTOMPADDING',(0,0),(-1,-1),6), ('LEFTPADDING',(0,0),(-1,-1),8),
    ]))
    content.append(bien_table)

    content.append(Paragraph("RÉSULTAT DE L'ESTIMATION", style_section))
    content.append(Spacer(1, 6))
    fourchette_table = Table([[
        Paragraph(f"<b>{estimation['valeur_min']:,} MAD</b>".replace(","," "),
            ParagraphStyle('val', parent=styles['Normal'], fontSize=14, fontName='Helvetica-Bold', textColor=dark_color, alignment=TA_CENTER)),
        Paragraph("←  Fourchette  →",
            ParagraphStyle('sep', parent=styles['Normal'], fontSize=9, fontName='Helvetica', textColor=muted_color, alignment=TA_CENTER)),
        Paragraph(f"<b>{estimation['valeur_max']:,} MAD</b>".replace(","," "),
            ParagraphStyle('val2', parent=styles['Normal'], fontSize=14, fontName='Helvetica-Bold', textColor=dark_color, alignment=TA_CENTER)),
    ]], colWidths=[55*mm, 60*mm, 55*mm])
    fourchette_table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f9fafb')),
        ('BOX',(0,0),(-1,-1),1,colors.HexColor('#e5e7eb')),
        ('TOPPADDING',(0,0),(-1,-1),12), ('BOTTOMPADDING',(0,0),(-1,-1),12), ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
    ]))
    content.append(fourchette_table)
    content.append(Spacer(1, 8))
    mid_table = Table([[
        Paragraph(f"Valeur centrale estimée : <b>{estimation['valeur_mid']:,} MAD</b>".replace(","," "),
            ParagraphStyle('mid', parent=styles['Normal'], fontSize=12, fontName='Helvetica', textColor=or_color, alignment=TA_CENTER))
    ]], colWidths=[170*mm])
    mid_table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#0d1117')),
        ('TOPPADDING',(0,0),(-1,-1),10), ('BOTTOMPADDING',(0,0),(-1,-1),10),
    ]))
    content.append(mid_table)

    content.append(Paragraph("COEFFICIENTS APPLIQUÉS", style_section))
    coeffs = estimation['coefficients']
    coeff_rows = [["Critère", "Coefficient", "Impact"]]
    coeff_map = [
        ("État général",     coeffs['etat'],         "Qualité du bien"),
        ("Étage",            coeffs['etage'],        "Position verticale"),
        ("Surface",          coeffs['surface'],      "Dégressivité/m²"),
        ("Ancienneté",       coeffs['anciennete'],   "Année de construction"),
        ("Pièces",           coeffs['pieces'],       "Nombre de chambres"),
        ("Implantation",     coeffs['implantation'], "Bande / Jumelée / Isolée"),
        ("Équipements",      coeffs['equipements'],  "Bonus équipements"),
        ("Liquidité marché", coeffs['liquidite'],    "Facilité de revente"),
    ]
    for label, val, desc in coeff_map:
        if val != 1.0:
            sign = "+" if val > 1.0 else "−"
            pct  = abs(round((val - 1.0) * 100, 1))
            coeff_rows.append([label, f"×{val:.3f}", f"{sign}{pct}% ({desc})"])
    coeff_table = Table(coeff_rows, colWidths=[50*mm, 25*mm, 95*mm])
    coeff_table.setStyle(TableStyle([
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'), ('FONTSIZE',(0,0),(-1,-1),8),
        ('TEXTCOLOR',(0,0),(-1,0),or_color),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#f9fafb'),colors.white]),
        ('TOPPADDING',(0,0),(-1,-1),5), ('BOTTOMPADDING',(0,0),(-1,-1),5), ('LEFTPADDING',(0,0),(-1,-1),8),
    ]))
    content.append(coeff_table)

    content.append(Paragraph("MÉTHODOLOGIE", style_section))
    content.append(Paragraph(
        "Cette estimation repose sur le référentiel de prix Yakeey (données publiques, mise à jour mars 2026) "
        "ajusté par les coefficients terrain PropIntel v1.5.0 : état général, étage, surface, ancienneté, "
        "pièces, implantation (bande/jumelée/isolée), équipements et liquidité du quartier. "
        "La fourchette varie de ±8% (marchés liquides) à ±12% (périphérie), reflétant la réalité terrain.", style_body))

    content.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e5e7eb'), spaceBefore=16, spaceAfter=10))
    content.append(Paragraph(
        "Pour un accompagnement personnalisé : <b>Abdeloihed Meskini</b> · "
        "Agent Élite Yakeey · <b>contact@propintel.ma</b> · propintel.ma", style_centre))
    content.append(Spacer(1, 8))
    content.append(Paragraph(
        "Ce rapport est fourni à titre indicatif. PropIntel ne saurait être tenu responsable des décisions "
        "prises sur la base de cette estimation. Une expertise notariale reste recommandée pour toute transaction.",
        style_disclaimer))

    doc.build(content)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode('utf-8')

# ============================================================
# NOTIFICATION EMAIL AGENT (Resend)
# ============================================================
def notify_agent(nom, tel, whatsapp, estimation):
    try:
        api_key  = os.environ.get('RESEND_API_KEY', '')
        valeur_mid = estimation['valeur_mid']
        quartier   = estimation['quartier']
        date_str   = datetime.datetime.now().strftime("%d/%m/%Y à %H:%M")

        type_labels = {"appartement":"Appartement","villa":"Villa","dar":"Maison/Dar","maison":"Maison/Dar","riad":"Riad"}
        liq_labels  = {1:"Faible",2:"Moyenne",3:"Élevée"}

        body_html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
            <div style="background:#0d1117;padding:20px 24px;text-align:center;">
                <h1 style="color:#c9a84c;margin:0;font-size:20px;">PropIntel</h1>
                <p style="color:#aaa;margin:4px 0 0;font-size:12px;">Nouveau lead · {date_str}</p>
            </div>
            <div style="padding:28px 24px;color:#333;background:#fff;">
                <h2 style="font-size:18px;margin:0 0 20px;color:#0d1117;">Nouveau lead estimateur</h2>
                <table style="width:100%;border-collapse:collapse;">
                    <tr style="background:#f9fafb;"><td style="padding:10px;font-weight:bold;width:140px;">Nom</td><td style="padding:10px;">{nom}</td></tr>
                    <tr><td style="padding:10px;font-weight:bold;">Téléphone</td><td style="padding:10px;"><a href="tel:{tel}" style="color:#c9a84c;">{tel}</a></td></tr>
                    <tr style="background:#f9fafb;"><td style="padding:10px;font-weight:bold;">WhatsApp</td><td style="padding:10px;"><a href="https://wa.me/{whatsapp.replace('+','').replace(' ','')}" style="color:#25D366;">💬 {whatsapp}</a></td></tr>
                    <tr><td style="padding:10px;font-weight:bold;">Quartier</td><td style="padding:10px;">{quartier}</td></tr>
                    <tr style="background:#f9fafb;"><td style="padding:10px;font-weight:bold;">Type</td><td style="padding:10px;">{type_labels.get(estimation['type_bien'], estimation['type_bien'])} · {estimation['surface']} m²</td></tr>
                    <tr><td style="padding:10px;font-weight:bold;">État</td><td style="padding:10px;">{estimation['etat']}</td></tr>
                    <tr style="background:#f9fafb;"><td style="padding:10px;font-weight:bold;">Liquidité</td><td style="padding:10px;">{liq_labels.get(estimation['liquidite'],'—')}</td></tr>
                </table>
                <div style="background:#0d1117;padding:16px;margin:20px 0;text-align:center;border-radius:6px;">
                    <p style="margin:0;font-size:20px;color:#c9a84c;font-weight:bold;">{valeur_mid:,} MAD</p>
                    <p style="margin:4px 0 0;color:#aaa;font-size:12px;">Fourchette : {estimation['valeur_min']:,} – {estimation['valeur_max']:,} MAD</p>
                </div>
                <p style="font-size:12px;color:#888;">Le client a téléchargé son rapport PDF. Règle des 48h : contactez-le rapidement.</p>
            </div>
        </div>
        """.replace(',', ' ')

        payload = {
            "from":    "PropIntel Leads <contact@propintel.ma>",
            "to":      ["contact@propintel.ma"],
            "subject": f"Nouveau lead — {nom} · {quartier} · {valeur_mid:,} MAD".replace(',', ' '),
            "html":    body_html,
        }
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload, timeout=30
        )
        if response.status_code in (200, 201):
            logger.info(f"Notification agent envoyée : {nom} / {tel}")
        else:
            logger.error(f"Erreur Resend: {response.status_code} {response.text}")
    except Exception as e:
        logger.error(f"Erreur notification agent: {e}")

# ============================================================
# TWILIO OTP
# ============================================================
def send_sms_otp(phone, code):
    from twilio.rest import Client
    client = Client(os.environ.get("TWILIO_SID"), os.environ.get("TWILIO_TOKEN"))
    client.messages.create(
        body=f"PropIntel - Votre code de vérification : {code}",
        from_=os.environ.get("TWILIO_FROM"),
        to=phone
    )

# ============================================================
# ENDPOINTS API
# ============================================================

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        "status":       "ok",
        "version":      "1.5.0",
        "quartiers":    len(REFERENTIEL),
        "otp_dev_mode": DEV_MODE,
        "date":         datetime.datetime.now().isoformat()
    })

@app.route('/api/quartiers', methods=['GET'])
def quartiers():
    liste = [{
        "nom":        n,
        "prix_appt":  p["appt"],
        "prix_villa": p["villa"],
        "prix_dar":   p["dar"],
        "prix_riad":  p["riad"],
        "liquidite":  p["liq"],
    } for n, p in REFERENTIEL.items()]
    return jsonify({"quartiers": liste, "total": len(liste)})

@app.route('/api/send-otp', methods=['POST'])
def send_otp():
    try:
        data = request.get_json()
        tel  = data.get('tel', '').strip()
        if not tel:
            return jsonify({"error": "Numéro de téléphone requis"}), 400

        now     = time.time()
        expired = [k for k, v in OTP_STORE.items() if v['expires_at'] < now]
        for k in expired:
            del OTP_STORE[k]

        if DEV_MODE:
            code = DEV_CODE
            logger.info(f"[DEV] OTP pour {tel} : {code}")
        else:
            code = str(secrets.randbelow(900000) + 100000)
            try:
                send_sms_otp(tel, code)
                logger.info(f"[PROD] OTP Twilio envoyé à {tel}")
            except Exception as e:
                logger.error(f"Erreur Twilio: {e}")
                return jsonify({"error": "Échec envoi SMS. Vérifiez votre numéro."}), 500

        OTP_STORE[tel] = {
            "code":       code,
            "expires_at": now + OTP_TTL,
            "verified":   False,
            "attempts":   0
        }
        return jsonify({
            "success":  True,
            "message":  "Code envoyé" if not DEV_MODE else "Code dev : 1234",
            "dev_mode": DEV_MODE
        })
    except Exception as e:
        logger.error(f"Erreur send_otp: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    try:
        data  = request.get_json()
        tel   = data.get('tel', '').strip()
        code  = data.get('code', '').strip()
        if not tel or not code:
            return jsonify({"error": "Données manquantes"}), 400

        entry = OTP_STORE.get(tel)
        if not entry:
            return jsonify({"error": "Code expiré ou numéro non trouvé"}), 400
        if time.time() > entry['expires_at']:
            del OTP_STORE[tel]
            return jsonify({"error": "Code expiré"}), 400

        entry['attempts'] = entry.get('attempts', 0) + 1
        if entry['attempts'] > 5:
            del OTP_STORE[tel]
            return jsonify({"error": "Trop de tentatives"}), 429
        if code != entry['code']:
            return jsonify({"error": "Code incorrect", "attempts_left": 5 - entry['attempts']}), 400

        entry['verified'] = True
        return jsonify({"success": True, "verified": True})
    except Exception as e:
        logger.error(f"Erreur verify_otp: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/estimate', methods=['POST'])
def estimate():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Données JSON manquantes"}), 400

        for champ in ["quartier", "type_bien", "surface", "etat", "nom", "tel", "whatsapp"]:
            if not data.get(champ):
                return jsonify({"error": f"Champ manquant : {champ}"}), 400

        nom         = data["nom"].strip()
        tel         = data["tel"].strip()
        whatsapp    = data["whatsapp"].strip()
        quartier    = data["quartier"]
        type_bien   = data["type_bien"].lower()
        surface     = float(data["surface"])
        etat        = data["etat"].lower()
        etage       = int(data.get("etage", 1))
        equipements = data.get("equipements", [])
        pieces      = data.get("pieces", None)
        anciennete  = data.get("anciennete", None)
        implantation= data.get("implantation", None)
        niveaux_dar = data.get("niveaux_dar", None)
        sous_sol    = data.get("sous_sol", None)

        # Vérification OTP
        entry = OTP_STORE.get(tel)
        if not entry or not entry.get('verified'):
            return jsonify({"error": "Téléphone non vérifié. Veuillez valider votre code OTP."}), 403

        # Validations
        types_valides = ["appartement", "villa", "dar", "maison", "riad"]
        if type_bien not in types_valides:
            return jsonify({"error": f"type_bien doit être parmi : {types_valides}"}), 400
        if surface <= 0 or surface > 5000:
            return jsonify({"error": "Surface invalide"}), 400
        if etat not in COEFF_ETAT:
            return jsonify({"error": f"État invalide. Valeurs : {list(COEFF_ETAT.keys())}"}), 400
        if implantation and implantation not in COEFF_IMPLANTATION:
            return jsonify({"error": f"Implantation invalide. Valeurs : {list(COEFF_IMPLANTATION.keys())}"}), 400
        if pieces and pieces not in COEFF_PIECES:
            return jsonify({"error": f"Pièces invalide. Valeurs : {list(COEFF_PIECES.keys())}"}), 400
        if anciennete and anciennete not in COEFF_ANCIENNETE:
            return jsonify({"error": f"Ancienneté invalide. Valeurs : {list(COEFF_ANCIENNETE.keys())}"}), 400

        estimation, erreur = estimer(
            quartier, type_bien, surface, etat, etage,
            equipements, pieces, anciennete, implantation
        )
        if erreur:
            return jsonify({"error": erreur}), 400

        # Stocker implantation pour le PDF
        estimation['implantation'] = implantation
        estimation['niveaux_dar']  = niveaux_dar
        estimation['sous_sol']     = sous_sol

        pdf_b64 = generer_pdf(estimation, nom, tel, whatsapp)

        thread = threading.Thread(target=notify_agent, args=(nom, tel, whatsapp, estimation))
        thread.daemon = True
        thread.start()

        del OTP_STORE[tel]

        return jsonify({
            "success":    True,
            "estimation": estimation,
            "pdf_base64": pdf_b64,
        })

    except Exception as e:
        logger.error(f"Erreur estimate: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/prix/<quartier>', methods=['GET'])
def prix_quartier(quartier):
    ref = REFERENTIEL.get(quartier)
    if not ref:
        return jsonify({"error": "Quartier non trouvé"}), 404
    return jsonify({
        "quartier":    quartier,
        "prix_appt":   ref["appt"],
        "prix_villa":  ref["villa"],
        "prix_dar":    ref["dar"],
        "prix_riad":   ref["riad"],
        "liquidite":   ref["liq"],
    })

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
