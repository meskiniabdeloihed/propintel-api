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
# En production : remplacer par Redis ou Supabase
# ============================================================
OTP_STORE = {}  # { tel: { code, expires_at, verified } }
OTP_TTL = 600   # 10 minutes

# En dev : code fixe 1234
# En prod : remplacer par appel Twilio/Vonage
DEV_MODE = os.environ.get('OTP_DEV_MODE', 'true').lower() == 'true'
DEV_CODE = '1234'

# ============================================================
# RÉFÉRENTIEL YAKEEY — MARRAKECH (mars 2026)
# ============================================================
REFERENTIEL = {
    "Abouab Gueliz - Mabrouka":     {"appt": 6684,  "villa": 7764},
    "Abouab Mhamid":                {"appt": 5467,  "villa": 3527},
    "Agdal":                        {"appt": 16325, "villa": 9021},
    "Ain Iti":                      {"appt": 8521,  "villa": 8353},
    "Al Maaden - Ain Slim":         {"appt": 5648,  "villa": 6952},
    "Alal El Fassi":                {"appt": 10595, "villa": 6664},
    "Amerchich":                    {"appt": 10795, "villa": 8320},
    "Ancienne Medina - Assouel":    {"appt": 11007, "villa": 18078},
    "Ancienne Medina - Bab Aylan":  {"appt": 9928,  "villa": None},
    "Ancienne Medina - Bab Ghmat":  {"appt": 5976,  "villa": 6276},
    "Ancienne Medina - Ben Chegra": {"appt": 6351,  "villa": None},
    "Ancienne Medina - Ben Salah":  {"appt": 5999,  "villa": None},
    "Ancienne Medina - Boukar":     {"appt": 10236, "villa": 11263},
    "Ancienne Medina - Dar El Bacha": {"appt": 20078, "villa": 10872},
    "Ancienne Medina - El Hara":    {"appt": 13748, "villa": 12442},
    "Ancienne Medina - Laksour":    {"appt": 8735,  "villa": None},
    "Ancienne Medina - Place Jemaa El Fna": {"appt": 8298, "villa": 7316},
    "Ancienne Medina - Rahba Kedima": {"appt": 6752, "villa": 22227},
    "Ancienne Medina - Riad Laarouss": {"appt": 12375, "villa": None},
    "Arset Lamaach":                {"appt": 8733,  "villa": None},
    "Assif":                        {"appt": 8986,  "villa": 8237},
    "Azzouzia":                     {"appt": 5422,  "villa": 7139},
    "Bab Doukkala":                 {"appt": 3697,  "villa": None},
    "Bab Ighli":                    {"appt": 10301, "villa": 8423},
    "Berrima":                      {"appt": 20920, "villa": None},
    "Bin Lkchali":                  {"appt": 9487,  "villa": 19356},
    "Bouaakaz":                     {"appt": 5989,  "villa": 10955},
    "Boulvard Moulay Abdellah - Route De Safi": {"appt": 9813, "villa": 6264},
    "Camps El Ghoul - Victor Hugo": {"appt": 12065, "villa": 12692},
    "Chwiter":                      {"appt": 4333,  "villa": 5182},
    "Daoudiat":                     {"appt": 10055, "villa": 8232},
    "Diour Al Atlas":               {"appt": 5759,  "villa": None},
    "Douar Chouhada":               {"appt": 11149, "villa": None},
    "Douar Iziki":                  {"appt": 6509,  "villa": 5257},
    "Douar Laaskar":                {"appt": 6100,  "villa": 8729},
    "El Fadel":                     {"appt": 6611,  "villa": None},
    "Essaada":                      {"appt": 6594,  "villa": None},
    "Gueliz":                       {"appt": 13758, "villa": 14588},
    "Hay Al Massar":                {"appt": 5891,  "villa": None},
    "Hay Azli":                     {"appt": 6510,  "villa": None},
    "Hay Charaf":                   {"appt": 6762,  "villa": 10630},
    "Hay El Bahja":                 {"appt": 8493,  "villa": 9278},
    "Hay Hassani":                  {"appt": 6887,  "villa": 4181},
    "Hay Inara":                    {"appt": 9687,  "villa": 3712},
    "Hay Menara":                   {"appt": 7582,  "villa": 7341},
    "Hay Nahda":                    {"appt": 7114,  "villa": 30245},
    "Hay Zitoun":                   {"appt": 6179,  "villa": None},
    "Hivernage":                    {"appt": 14665, "villa": 16919},
    "Issil":                        {"appt": 10142, "villa": 5769},
    "Izdihar":                      {"appt": 8580,  "villa": 10402},
    "Jardin De La Koutoubia":       {"appt": 15546, "villa": 14024},
    "Jawhar":                       {"appt": 5916,  "villa": 6195},
    "Jenan El Ghali":               {"appt": 10502, "villa": None},
    "Jnan Aourad":                  {"appt": 9612,  "villa": 10628},
    "Kasbah":                       {"appt": 7131,  "villa": 8672},
    "Koudiat Laabid":               {"appt": 6943,  "villa": 7422},
    "Lakssour":                     {"appt": 10247, "villa": 9090},
    "Lotissement Arafat":           {"appt": 6567,  "villa": 5810},
    "Lotissement Cherifia":         {"appt": 5931,  "villa": 7337},
    "Lotissement Les Palmiers":     {"appt": 5325,  "villa": 9221},
    "M'Hamid":                      {"appt": 5771,  "villa": 6365},
    "Massira 1":                    {"appt": 6811,  "villa": 6338},
    "Massira 2":                    {"appt": 5672,  "villa": 5775},
    "Massira 3":                    {"appt": 5921,  "villa": 7223},
    "Mellah":                       {"appt": 8389,  "villa": None},
    "Palmeraie":                    {"appt": 13449, "villa": 6166},
    "Palmeraie Extension":          {"appt": 11935, "villa": 6038},
    "Portes De Marrakech Addoha":   {"appt": 5775,  "villa": 6242},
    "Prestigia":                    {"appt": 18842, "villa": 12277},
    "Quartier Industriel De Sidi Ghanem": {"appt": 4864, "villa": 4669},
    "Riad Essalam":                 {"appt": 8509,  "villa": 8387},
    "Rouidate - Majorelle":         {"appt": 9485,  "villa": 9178},
    "Route D'Amizmiz":              {"appt": 11805, "villa": None},
    "Route D'Amizmiz - Cherifia":   {"appt": 6047,  "villa": 4070},
    "Route D'Amizmiz - Douar Soultan": {"appt": 5026, "villa": 8345},
    "Route De Casablanca":          {"appt": None,  "villa": 4724},
    "Route De Fes":                 {"appt": 10868, "villa": 10321},
    "Route De Fes - Atlas - Amelkis": {"appt": 9611, "villa": 7170},
    "Route De Fes - Douar Tamasna": {"appt": 8475,  "villa": 5517},
    "Route De Fes - Oulad Jelal":   {"appt": 7498,  "villa": 5163},
    "Route De L'Ourika - Canal Zaraba": {"appt": 11155, "villa": None},
    "Route De L'Ourika - Douar Bouazza": {"appt": 7125, "villa": 34457},
    "Route De L'Ourika - Plage Rouge": {"appt": 4190, "villa": 24212},
    "Route De L'Ourika - Waky":     {"appt": 6012,  "villa": 7158},
    "Route De L'Ourika (Agdal)":    {"appt": 12107, "villa": 6381},
    "Route De L'Ourika (Sidi Abdellah Ghiat)": {"appt": 11155, "villa": 3084},
    "Route De L'Ourika (Tassoultante)": {"appt": 6847, "villa": 6088},
    "Route De Ouarzazate - Douar Ait Lahmad": {"appt": 4904, "villa": 7824},
    "Route De Ouarzazate - Douar El Guern": {"appt": 9291, "villa": 6675},
    "Route De Ouarzazate - Douar Laadem": {"appt": 20549, "villa": 6903},
    "Route De Ouarzazate - Gzoula Sidi Mbarek": {"appt": 7649, "villa": 7839},
    "Route De Tahanaout - Cherifia": {"appt": 5312, "villa": 9569},
    "Route De Tahanaout - Oulad Yahya": {"appt": 3672, "villa": 6807},
    "S.Y.B.A":                      {"appt": 6175,  "villa": 10875},
    "Saada-Tissir":                 {"appt": 6222,  "villa": 5920},
    "Sanaoubar":                    {"appt": 8064,  "villa": 10551},
    "Semlalia":                     {"appt": 11029, "villa": 10058},
    "Sidi Abbad":                   {"appt": 8655,  "villa": 7938},
    "Sidi Abdellah Ghiat":          {"appt": 9221,  "villa": 3382},
    "Sidi Mimoun":                  {"appt": 6575,  "villa": 15222},
    "Socoma - Lotissement Wilaya":  {"appt": 6413,  "villa": 12000},
    "Sofia Targa":                  {"appt": 9881,  "villa": 6616},
    "Targa":                        {"appt": 9909,  "villa": 7999},
    "Zohor Targa - Zephyr":         {"appt": 6330,  "villa": 6507},
}

COEFF_ETAT = {
    "neuf":       1.15,
    "excellent":  1.10,
    "bon":        1.00,
    "moyen":      0.90,
    "arenoveer":  0.75,
}

COEFF_ETAGE = {
    0:  0.95,
    1:  1.00,
    2:  1.02,
    3:  1.05,
    4:  1.07,
}

BONUS_EQUIPEMENTS = {
    "parking":   0.04,
    "ascenseur": 0.03,
    "piscine":   0.08,
    "gardien":   0.02,
    "terrasse":  0.03,
    "vue":       0.05,
}

def coeff_surface(surface, type_bien):
    if type_bien == "appartement":
        if surface < 60:    return 1.05
        if surface < 100:   return 1.00
        if surface < 150:   return 0.97
        if surface < 200:   return 0.94
        return 0.90
    else:
        if surface < 200:   return 1.05
        if surface < 350:   return 1.00
        if surface < 500:   return 0.96
        return 0.92

def estimer(quartier, type_bien, surface, etat, etage=1, equipements=None):
    if equipements is None:
        equipements = []
    ref = REFERENTIEL.get(quartier)
    if not ref:
        return None, f"Quartier '{quartier}' non trouvé dans le référentiel"
    cle_type = "appt" if type_bien == "appartement" else "villa"
    prix_m2_base = ref.get(cle_type)
    if not prix_m2_base:
        autre = ref.get("villa" if cle_type == "appt" else "appt")
        if autre:
            prix_m2_base = autre * 0.90
        else:
            return None, "Aucun prix disponible pour ce type de bien dans ce quartier"
    c_etat = COEFF_ETAT.get(etat, 1.0)
    c_etage = COEFF_ETAGE.get(min(etage, 4), 1.0) if type_bien == "appartement" else 1.0
    c_surface = coeff_surface(surface, type_bien)
    bonus = sum(BONUS_EQUIPEMENTS.get(eq, 0) for eq in equipements)
    c_equipements = 1 + bonus
    prix_m2_ajuste = prix_m2_base * c_etat * c_etage * c_surface * c_equipements
    valeur_centrale = prix_m2_ajuste * surface
    valeur_min = round(valeur_centrale * 0.90 / 1000) * 1000
    valeur_max = round(valeur_centrale * 1.10 / 1000) * 1000
    valeur_mid = round(valeur_centrale / 1000) * 1000
    return {
        "prix_m2_base": round(prix_m2_base),
        "prix_m2_ajuste": round(prix_m2_ajuste),
        "valeur_min": valeur_min,
        "valeur_max": valeur_max,
        "valeur_mid": valeur_mid,
        "surface": surface,
        "quartier": quartier,
        "type_bien": type_bien,
        "etat": etat,
        "coefficients": {
            "etat": c_etat,
            "etage": c_etage,
            "surface": round(c_surface, 3),
            "equipements": round(c_equipements, 3),
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
    or_color   = colors.HexColor('#c9a84c')
    dark_color = colors.HexColor('#0d1117')
    muted_color = colors.HexColor('#6b7280')

    style_titre     = ParagraphStyle('titre', parent=styles['Normal'], fontSize=22, fontName='Helvetica-Bold', textColor=dark_color, spaceAfter=4, alignment=TA_LEFT)
    style_sous_titre= ParagraphStyle('sous_titre', parent=styles['Normal'], fontSize=11, fontName='Helvetica', textColor=muted_color, spaceAfter=16, alignment=TA_LEFT)
    style_section   = ParagraphStyle('section', parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold', textColor=or_color, spaceBefore=14, spaceAfter=6, alignment=TA_LEFT)
    style_body      = ParagraphStyle('body', parent=styles['Normal'], fontSize=10, fontName='Helvetica', textColor=dark_color, spaceAfter=4, leading=16)
    style_disclaimer= ParagraphStyle('disclaimer', parent=styles['Normal'], fontSize=8, fontName='Helvetica', textColor=muted_color, spaceAfter=4, leading=12)
    style_centre    = ParagraphStyle('centre', parent=styles['Normal'], fontSize=10, fontName='Helvetica', textColor=dark_color, alignment=TA_CENTER)

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
        ["Nom", nom_client],
        ["Téléphone", tel_client],
        ["WhatsApp", whatsapp_client],
    ], colWidths=[40*mm, 130*mm])
    client_table.setStyle(TableStyle([
        ('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'), ('FONTSIZE',(0,0),(-1,-1),9),
        ('TEXTCOLOR',(0,0),(0,-1),colors.HexColor('#374151')), ('TEXTCOLOR',(1,0),(1,-1),dark_color),
        ('ROWBACKGROUNDS',(0,0),(-1,-1),[colors.HexColor('#f9fafb'),colors.white]),
        ('TOPPADDING',(0,0),(-1,-1),6), ('BOTTOMPADDING',(0,0),(-1,-1),6), ('LEFTPADDING',(0,0),(-1,-1),8),
    ]))
    content.append(client_table)

    content.append(Paragraph("BIEN ÉVALUÉ", style_section))
    type_label = "Appartement" if estimation['type_bien'] == 'appartement' else "Villa"
    etat_labels = {"neuf":"Neuf","excellent":"Excellent","bon":"Bon état","moyen":"État moyen","arenoveer":"À rénover"}
    bien_table = Table([
        ["Type", type_label],
        ["Quartier", estimation['quartier']],
        ["Surface", f"{estimation['surface']} m²"],
        ["État général", etat_labels.get(estimation['etat'], estimation['etat'])],
        ["Prix m² référence", f"{estimation['prix_m2_base']:,} MAD/m²".replace(","," ")],
        ["Prix m² ajusté", f"{estimation['prix_m2_ajuste']:,} MAD/m²".replace(","," ")],
    ], colWidths=[40*mm, 130*mm])
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

    content.append(Paragraph("MÉTHODOLOGIE", style_section))
    content.append(Paragraph(
        "Cette estimation repose sur le référentiel de prix Yakeey (données publiques, mise à jour continue) "
        "ajusté par les coefficients terrain PropIntel : état général du bien, étage, surface et équipements. "
        "La fourchette représente un intervalle de confiance de ±10% autour de la valeur centrale.", style_body))

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
    """Envoie une notification de nouveau lead à l'agent."""
    try:
        api_key = os.environ.get('RESEND_API_KEY', '')
        valeur_mid = estimation['valeur_mid']
        quartier = estimation['quartier']
        date_str = datetime.datetime.now().strftime("%d/%m/%Y à %H:%M")

        body_html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
            <div style="background:#0d1117;padding:20px 24px;text-align:center;">
                <h1 style="color:#c9a84c;margin:0;font-size:20px;">PropIntel</h1>
                <p style="color:#aaa;margin:4px 0 0;font-size:12px;">Nouveau lead · {date_str}</p>
            </div>
            <div style="padding:28px 24px;color:#333;background:#fff;">
                <h2 style="font-size:18px;margin:0 0 20px;color:#0d1117;">🔔 Nouveau lead estimateur</h2>
                <table style="width:100%;border-collapse:collapse;">
                    <tr style="background:#f9fafb;"><td style="padding:10px;font-weight:bold;width:140px;">Nom</td><td style="padding:10px;">{nom}</td></tr>
                    <tr><td style="padding:10px;font-weight:bold;">Téléphone</td><td style="padding:10px;"><a href="tel:{tel}" style="color:#c9a84c;">{tel}</a></td></tr>
                    <tr style="background:#f9fafb;"><td style="padding:10px;font-weight:bold;">WhatsApp</td><td style="padding:10px;"><a href="https://wa.me/{whatsapp.replace('+','').replace(' ','')}" style="color:#25D366;">💬 {whatsapp}</a></td></tr>
                    <tr><td style="padding:10px;font-weight:bold;">Quartier</td><td style="padding:10px;">{quartier}</td></tr>
                    <tr style="background:#f9fafb;"><td style="padding:10px;font-weight:bold;">Type</td><td style="padding:10px;">{estimation['type_bien'].capitalize()} · {estimation['surface']} m²</td></tr>
                    <tr><td style="padding:10px;font-weight:bold;">État</td><td style="padding:10px;">{estimation['etat']}</td></tr>
                </table>
                <div style="background:#0d1117;padding:16px;margin:20px 0;text-align:center;border-radius:6px;">
                    <p style="margin:0;font-size:20px;color:#c9a84c;font-weight:bold;">{valeur_mid:,} MAD</p>
                    <p style="margin:4px 0 0;color:#aaa;font-size:12px;">Fourchette : {estimation['valeur_min']:,} – {estimation['valeur_max']:,} MAD</p>
                </div>
                <p style="font-size:12px;color:#888;">Le client a téléchargé son rapport PDF. Contactez-le rapidement.</p>
            </div>
        </div>
        """.replace(',', ' ')

        payload = {
            "from": "PropIntel Leads <contact@propintel.ma>",
            "to": ["contact@propintel.ma"],
            "subject": f"🔔 Nouveau lead — {nom} · {quartier} · {valeur_mid:,} MAD".replace(',', ' '),
            "html": body_html,
        }
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload, timeout=30
        )
        if response.status_code in (200, 201):
            logger.info(f"Notification agent envoyée pour lead : {nom} / {tel}")
        else:
            logger.error(f"Erreur Resend notification: {response.status_code} {response.text}")
    except Exception as e:
        logger.error(f"Erreur notification agent: {e}")

# ============================================================
# ENDPOINTS API
# ============================================================

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "version": "1.3.0",
        "quartiers": len(REFERENTIEL),
        "otp_dev_mode": DEV_MODE,
        "date": datetime.datetime.now().isoformat()
    })

@app.route('/api/quartiers', methods=['GET'])
def quartiers():
    liste = [{"nom": n, "prix_appt": p["appt"], "prix_villa": p["villa"]} for n, p in REFERENTIEL.items()]
    return jsonify({"quartiers": liste, "total": len(liste)})

# ============================================================
# OTP : Envoyer code
# ============================================================
@app.route('/api/send-otp', methods=['POST'])
def send_otp():
    try:
        data = request.get_json()
        tel = data.get('tel', '').strip()
        if not tel or len(tel) < 8:
            return jsonify({"error": "Numéro de téléphone invalide"}), 400

        # Nettoyage OTP expiré
        now = time.time()
        expired = [k for k, v in OTP_STORE.items() if v['expires_at'] < now]
        for k in expired:
            del OTP_STORE[k]

        if DEV_MODE:
            code = DEV_CODE
            logger.info(f"[DEV] OTP pour {tel} : {code}")
        else:
            code = str(secrets.randbelow(900000) + 100000)
            # TODO: envoyer via Twilio/Vonage
            # twilio_client.messages.create(to=tel, from_=TWILIO_FROM, body=f"PropIntel : votre code est {code}")

        OTP_STORE[tel] = {
            "code": code,
            "expires_at": now + OTP_TTL,
            "verified": False,
            "attempts": 0
        }

        return jsonify({
            "success": True,
            "message": "Code envoyé" if not DEV_MODE else "Code dev : 1234",
            "dev_mode": DEV_MODE
        })
    except Exception as e:
        logger.error(f"Erreur send_otp: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================================
# OTP : Vérifier code
# ============================================================
@app.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    try:
        data = request.get_json()
        tel = data.get('tel', '').strip()
        code = data.get('code', '').strip()

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

# ============================================================
# ESTIMATION (requiert OTP vérifié)
# ============================================================
@app.route('/api/estimate', methods=['POST'])
def estimate():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Données JSON manquantes"}), 400

        # Validation champs requis
        for champ in ["quartier", "type_bien", "surface", "etat", "nom", "tel", "whatsapp"]:
            if not data.get(champ):
                return jsonify({"error": f"Champ manquant : {champ}"}), 400

        nom      = data["nom"].strip()
        tel      = data["tel"].strip()
        whatsapp = data["whatsapp"].strip()
        quartier = data["quartier"]
        type_bien = data["type_bien"].lower()
        surface  = float(data["surface"])
        etat     = data["etat"].lower()
        etage    = int(data.get("etage", 1))
        equipements = data.get("equipements", [])

        # Vérification OTP
        entry = OTP_STORE.get(tel)
        if not entry or not entry.get('verified'):
            return jsonify({"error": "Téléphone non vérifié. Veuillez valider votre code OTP."}), 403

        if type_bien not in ["appartement", "villa"]:
            return jsonify({"error": "type_bien doit être 'appartement' ou 'villa'"}), 400
        if surface <= 0 or surface > 5000:
            return jsonify({"error": "Surface invalide"}), 400
        if etat not in COEFF_ETAT:
            return jsonify({"error": f"État invalide. Valeurs : {list(COEFF_ETAT.keys())}"}), 400

        estimation, erreur = estimer(quartier, type_bien, surface, etat, etage, equipements)
        if erreur:
            return jsonify({"error": erreur}), 400

        # Génération PDF
        pdf_b64 = generer_pdf(estimation, nom, tel, whatsapp)

        # Notification agent en arrière-plan
        thread = threading.Thread(target=notify_agent, args=(nom, tel, whatsapp, estimation))
        thread.daemon = True
        thread.start()

        # Invalider OTP après usage
        del OTP_STORE[tel]

        return jsonify({
            "success": True,
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
    return jsonify({"quartier": quartier, "prix_appt": ref["appt"], "prix_villa": ref["villa"]})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
