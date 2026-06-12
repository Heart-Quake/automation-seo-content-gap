import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
import base64
import json
import unicodedata
from io import BytesIO
import plotly.express as px
from collections import Counter
from urllib.parse import urlparse

from automation_seo_theme import apply_automation_seo_theme

# Classes d'exception personnalisées
class FileProcessingError(Exception):
    """Exception levée lors d'une erreur de traitement de fichier"""
    pass

class DataValidationError(Exception):
    """Exception levée lors d'une erreur de validation des données"""
    pass

class ConfigurationError(Exception):
    """Exception levée lors d'une erreur de configuration"""
    pass

class AnalysisError(Exception):
    """Exception levée lors d'une erreur d'analyse"""
    pass

st.set_page_config(
    page_title="Analyse Content Gap",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

apply_automation_seo_theme()

st.markdown(
    """
    <style>
        .filter-title,
        .section-header,
        .inline-filter-title {
            color: var(--yn-accent) !important;
            font-size: 0.82rem;
            font-weight: 800;
            letter-spacing: 0;
            margin: 0 0 0.45rem;
        }

        .subheader {
            color: var(--yn-text) !important;
            font-size: 1.12rem;
            font-weight: 800;
            margin: 1.15rem 0 0.65rem;
        }

        .stButton button[kind="secondary"] {
            background: transparent !important;
            border-color: var(--yn-border) !important;
            color: var(--yn-text) !important;
        }

        .stButton button[kind="secondary"]:hover {
            background: var(--yn-card-hover) !important;
            border-color: var(--yn-accent) !important;
            color: var(--yn-text) !important;
        }

        [data-testid="stDataFrame"] [role="gridcell"],
        [data-testid="stDataFrame"] [role="columnheader"] {
            color: var(--yn-text) !important;
        }

        .stPlotlyChart,
        [data-testid="stVegaLiteChart"] {
            background: var(--yn-card) !important;
            border-radius: 8px;
        }

        @media (max-width: 760px) {
            .tool-title {
                font-size: 2.25rem;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)

def process_content_gap_file(file):
    """Traite le fichier content gap et retourne un DataFrame nettoyé"""
    try:
        read_attempts = [
            ('utf-16', '\t'),
            ('utf-16le', '\t'),
            ('utf-8-sig', '\t'),
            ('utf-8', '\t'),
            ('utf-8-sig', ','),
            ('utf-8', ','),
            ('utf-8-sig', ';'),
            ('utf-8', ';')
        ]

        df = None
        for encoding, separator in read_attempts:
            try:
                file.seek(0)
                candidate_df = pd.read_csv(file, sep=separator, encoding=encoding)
                if len(candidate_df.columns) <= 1:
                    continue
                df = candidate_df
                break
            except Exception:
                continue

        if df is None:
            raise FileProcessingError(
                "Impossible de lire le fichier. Vérifiez l'encodage (UTF-16/UTF-8) et le séparateur (tabulation, virgule ou point-virgule)."
            )

        # Normalisation des variantes d'en-têtes selon les exports Ahrefs
        rename_map = {}
        for col in df.columns:
            normalized_col = col.replace(': Organic Position', ': Position').replace(
                ': Organic Traffic', ': Traffic'
            )
            if normalized_col != col and normalized_col not in df.columns:
                rename_map[col] = normalized_col
        if rename_map:
            df = df.rename(columns=rename_map)
        
        # Validation des colonnes requises
        required_columns = {
            'Keyword': str,
            'Volume': 'numeric',
            'KD': 'numeric',
            'CPC': 'numeric',
            'SERP features': str
        }
        
        for col, dtype in required_columns.items():
            if col not in df.columns:
                raise FileProcessingError(f"Colonne manquante : {col}")
            
            if dtype == 'numeric':
                df[col] = pd.to_numeric(
                    df[col].astype(str).replace(['', '-'], '0'), 
                    errors='coerce'
                ).fillna(0)
        
        # Validation des colonnes de position
        position_columns = [col for col in df.columns if ': Position' in col]
        if not position_columns:
            raise FileProcessingError("Aucune colonne de position trouvée")
            
        # Nettoyage des positions
        for col in position_columns:
            df[col] = pd.to_numeric(
                df[col].fillna(0).replace(['', '-'], '0'), 
                errors='coerce'
            ).fillna(0)
            
        return df

    except Exception as e:
        raise FileProcessingError(f"Erreur lors du traitement du fichier : {str(e)}")


def normalize_ahrefs_column_name(column_name):
    """Normalise les noms de colonnes Ahrefs pour détecter plusieurs formats d'export."""
    return str(column_name).strip().strip('"').strip().lower()


def extract_domain_hint_from_filename(uploaded_file):
    """Extrait un domaine probable depuis le nom du fichier importé."""
    file_name = str(getattr(uploaded_file, 'name', '')).lower()
    domain_match = re.search(r'([a-z0-9-]+(?:\.[a-z0-9-]+)+)', file_name)
    return domain_match.group(1) if domain_match else None


def detect_ahrefs_consolidation_columns(df, preferred_domain=None):
    """Détecte les colonnes keyword, volume, URL et position dans un export Ahrefs."""
    normalized_columns = {normalize_ahrefs_column_name(col): col for col in df.columns}

    keyword_col = normalized_columns.get('keyword')
    volume_col = normalized_columns.get('volume')
    if keyword_col is None or volume_col is None:
        raise FileProcessingError("Colonnes Ahrefs obligatoires introuvables : Keyword et Volume.")

    url_col = normalized_columns.get('current url')
    position_col = normalized_columns.get('current position')
    if url_col is not None and position_col is not None:
        return {
            'keyword': keyword_col,
            'volume': volume_col,
            'url': url_col,
            'position': position_col,
            'source_label': 'Current URL / Current position',
            'format_type': 'organic_keywords'
        }

    url_candidates = []
    position_map = {}
    for col in df.columns:
        normalized_col = normalize_ahrefs_column_name(col)
        if normalized_col.endswith(': url'):
            prefix = normalized_col[:-len(': url')]
            url_candidates.append((prefix, col))
        elif normalized_col.endswith(': organic position'):
            prefix = normalized_col[:-len(': organic position')]
            position_map[prefix] = col
        elif normalized_col.endswith(': position'):
            prefix = normalized_col[:-len(': position')]
            position_map[prefix] = col

    matched_candidates = []
    for prefix, candidate_url_col in url_candidates:
        candidate_position_col = position_map.get(prefix)
        if candidate_position_col is None:
            continue

        non_empty_urls = (
            df[candidate_url_col]
            .astype(str)
            .str.strip('"')
            .str.strip()
            .replace('', pd.NA)
            .notna()
            .sum()
        )
        matched_candidates.append((non_empty_urls, prefix, candidate_url_col, candidate_position_col))

    if not matched_candidates:
        raise FileProcessingError(
            "Impossible de trouver un couple URL/Position compatible. "
            "Formats supportés : Current URL/Current position ou <domaine>: URL + <domaine>: Organic Position."
        )

    selected_candidate = None
    if preferred_domain:
        normalized_hint = preferred_domain.rstrip('/').lower()
        for candidate in matched_candidates:
            candidate_prefix = candidate[1].rstrip('/').lower()
            if normalized_hint in candidate_prefix:
                selected_candidate = candidate
                break

    if selected_candidate is None:
        non_empty_candidates = [candidate for candidate in matched_candidates if candidate[0] > 0]
        selected_candidate = non_empty_candidates[0] if non_empty_candidates else matched_candidates[0]

    _, source_prefix, url_col, position_col = selected_candidate
    return {
        'keyword': keyword_col,
        'volume': volume_col,
        'url': url_col,
        'position': position_col,
        'source_label': source_prefix,
        'format_type': 'content_gap'
    }


def process_ahrefs_consolidation_file(uploaded_file):
    """Charge un export Ahrefs et prépare les colonnes nécessaires à la consolidation par URL."""
    read_attempts = [
        ('utf-16', '\t'),
        ('utf-16le', '\t'),
        ('utf-8-sig', '\t'),
        ('utf-8', '\t'),
        ('utf-8-sig', ','),
        ('utf-8', ','),
        ('utf-8-sig', ';'),
        ('utf-8', ';')
    ]

    df = None
    for encoding, separator in read_attempts:
        try:
            uploaded_file.seek(0)
            candidate_df = pd.read_csv(uploaded_file, sep=separator, encoding=encoding)
            if len(candidate_df.columns) <= 1:
                continue
            df = candidate_df
            break
        except Exception:
            continue

    if df is None:
        raise FileProcessingError(
            "Impossible de lire l'export Ahrefs. Vérifiez l'encodage et le séparateur."
        )

    domain_hint = extract_domain_hint_from_filename(uploaded_file)
    detected = detect_ahrefs_consolidation_columns(df, preferred_domain=domain_hint)
    cleaned_df = df[[
        detected['keyword'],
        detected['volume'],
        detected['position'],
        detected['url']
    ]].rename(columns={
        detected['keyword']: 'keyword',
        detected['volume']: 'volume',
        detected['position']: 'position',
        detected['url']: 'url'
    })

    for col in cleaned_df.columns:
        if cleaned_df[col].dtype == 'object':
            cleaned_df[col] = cleaned_df[col].astype(str).str.strip('"').str.strip()

    cleaned_df['volume'] = pd.to_numeric(
        cleaned_df['volume'].astype(str).str.replace(',', '', regex=False),
        errors='coerce'
    ).fillna(0)
    cleaned_df['position'] = pd.to_numeric(
        cleaned_df['position'].astype(str).str.replace(',', '.', regex=False),
        errors='coerce'
    )

    cleaned_df = cleaned_df.dropna(subset=['keyword', 'url'])
    cleaned_df = cleaned_df[
        (cleaned_df['keyword'].astype(str).str.strip() != '') &
        (cleaned_df['url'].astype(str).str.strip() != '')
    ].copy()
    cleaned_df.attrs['source_label'] = detected['source_label']
    cleaned_df.attrs['format_type'] = detected['format_type']
    return cleaned_df


def build_ahrefs_url_consolidation(df):
    """Consolide les mots-clés Ahrefs par URL avec métriques d'opportunité."""
    if df.empty:
        return pd.DataFrame(columns=[
            'URL', 'Top mot-clé', 'Volume du top mot-clé', 'Position moyenne',
            'Nb mots-clés', 'Volume total', 'Mots-clés', 'Volumes', 'Positions'
        ])

    sorted_df = df.copy()
    sorted_df['volume'] = pd.to_numeric(sorted_df['volume'], errors='coerce').fillna(0)
    sorted_df['position'] = pd.to_numeric(sorted_df['position'], errors='coerce')
    sorted_df = sorted_df.sort_values(by=['url', 'volume'], ascending=[True, False])

    top_rows = sorted_df.drop_duplicates(subset=['url'], keep='first').set_index('url')
    grouped = sorted_df.groupby('url', as_index=False).agg({
        'keyword': list,
        'position': list,
        'volume': list
    })

    grouped['Nb mots-clés'] = grouped['keyword'].apply(len)
    grouped['Volume total'] = grouped['volume'].apply(lambda values: int(pd.Series(values).fillna(0).sum()))
    grouped['Position moyenne'] = grouped['position'].apply(
        lambda values: round(pd.Series(values).dropna().mean(), 1)
        if pd.Series(values).dropna().size > 0 else pd.NA
    )
    grouped['Top mot-clé'] = grouped['url'].map(top_rows['keyword'])
    grouped['Volume du top mot-clé'] = grouped['url'].map(top_rows['volume']).fillna(0).astype(int)
    grouped['Mots-clés'] = grouped['keyword'].apply(lambda values: '\n'.join(str(value) for value in values))
    grouped['Volumes'] = grouped['volume'].apply(
        lambda values: '\n'.join(str(int(value)) for value in values if pd.notna(value))
    )
    grouped['Positions'] = grouped['position'].apply(
        lambda values: '\n'.join(str(value) for value in values if pd.notna(value))
    )

    result = grouped.rename(columns={'url': 'URL'})
    result = result[[
        'URL', 'Top mot-clé', 'Volume du top mot-clé', 'Position moyenne',
        'Nb mots-clés', 'Volume total', 'Mots-clés', 'Volumes', 'Positions'
    ]]
    return result.sort_values(by='Volume du top mot-clé', ascending=False).reset_index(drop=True)

TRANSACTION_INTENT_PATTERNS = (
    'acheter', 'achat', 'commander', 'commande', 'reservation', 'réservation',
    'reserver', 'réserver', 'louer', 'location', 'location en ligne',
    'devis', 'prix', 'tarif', 'tarifs', 'tarification', 'cout', 'coût',
    'coute', 'coûte', 'combien coute', 'combien coûte', 'frais', 'budget',
    'abonnement', 'souscrire', 'souscription', 'payer', 'paiement',
    'livraison', 'promotion', 'promo', 'code promo', 'solde', 'soldes',
    'remise', 'bon plan', 'gratuit', 'gratuite', 'free', 'pas cher',
    'moins cher', 'meilleur prix',
    'vente', 'a vendre', 'à vendre', 'vendre', 'rachat', 'reprise',
    'estimation', 'estimer', 'valeur', 'argus', 'cote', 'côte', 'cotation',
    'boutique', 'shop', 'panier', 'checkout', 'facture', 'facturation',
    'forfait', 'contrat', 'offre', 'formule', 'financement', 'credit',
    'crédit', 'sans apport', 'loa', 'lld', 'leasing', 'essai gratuit',
    'demo', 'démo', 'rendez vous', 'rendez-vous', 'rdv', 'prendre rendez vous'
)

STRONG_TRANSACTION_INTENT_PATTERNS = (
    'acheter', 'achat', 'commander', 'commande', 'reservation', 'réservation',
    'reserver', 'réserver', 'devis', 'prix', 'tarif', 'tarifs',
    'tarification', 'cout', 'coût', 'coute', 'coûte', 'combien coute',
    'combien coûte', 'abonnement', 'souscrire', 'souscription', 'payer',
    'paiement', 'livraison', 'promotion', 'promo', 'code promo', 'solde',
    'soldes', 'remise', 'bon plan', 'gratuit', 'gratuite', 'free',
    'pas cher', 'moins cher', 'meilleur prix', 'vente', 'a vendre',
    'à vendre', 'vendre', 'rachat', 'reprise', 'boutique', 'shop',
    'panier', 'checkout', 'facture', 'facturation', 'forfait', 'contrat',
    'offre', 'formule', 'financement', 'credit', 'crédit', 'sans apport',
    'essai gratuit', 'demo', 'démo', 'rendez vous', 'rendez-vous',
    'rdv', 'prendre rendez vous'
)

TRANSACTION_ACTION_PATTERNS = (
    'obtenir', 'recevoir', 'demander', 'telecharger', 'télécharger',
    'installer', 'changer', 'remplacer', 'renouveler', 'activer',
    'desactiver', 'désactiver', 'ouvrir', 'creer', 'créer'
)

TRANSACTION_CONTEXT_PATTERNS = (
    'prix', 'devis', 'tarif', 'offre', 'promotion', 'promo',
    'abonnement', 'forfait', 'contrat', 'financement', 'location',
    'credit', 'crédit', 'livraison', 'installation'
)

NAVIGATION_INTENT_PATTERNS = (
    'connexion', 'login', 'compte', 'mon compte', 'espace client',
    'se connecter', 'mot de passe', 'inscription', 'creer un compte',
    'créer un compte', 'contact', 'telephone', 'téléphone', 'adresse',
    'numero', 'numéro', 'service client', 'support', 'assistance',
    'agence', 'magasin', 'boutique proche', 'pres de moi', 'près de moi',
    'proche de moi', 'autour de moi', 'a proximite', 'à proximité',
    'localisation', 'horaire', 'horaires', 'ouverture', 'accueil',
    'plan d acces', 'plan d accès', 'site officiel', 'officiel',
    'officielle', 'portail', 'app', 'application', 'logo',
    'configurateur', 'forum'
)

COMMERCIAL_INTENT_PATTERNS = (
    'comparatif', 'comparaison', 'comparer', 'comparateur', 'vs', 'versus',
    'meilleur', 'meilleure', 'meilleurs', 'meilleures', 'top',
    'classement', 'alternative', 'alternatives', 'avis', 'test', 'essai',
    'review', 'retour', 'feedback', 'experience', 'expérience',
    'temoignage', 'témoignage', 'recommandation', 'selection', 'sélection',
    'choix', 'que choisir', 'lequel choisir', 'laquelle choisir',
    'quelle marque', 'quel produit', 'quelle solution', 'quel service',
    'quel fournisseur', 'quel operateur', 'quel opérateur',
    'quel prestataire', 'quelle entreprise', 'fiable', 'fiabilite',
    'fiabilité', 'a eviter', 'à éviter', 'modele a eviter',
    'modèle à éviter', 'rapport qualite prix', 'rapport qualité prix',
    'qualite prix', 'qualité prix'
)

INFORMATION_INTENT_PATTERNS = (
    'comment', 'pourquoi', 'quand', 'combien', 'qui', 'quoi',
    'qu est ce que', 'qu est ce', 'c est quoi', 'est ce que',
    'peut on', 'peut etre', 'peut être', 'faut il', 'doit on',
    'a quoi sert', 'à quoi sert', 'de quoi', 'pour qui', 'quel est',
    'quelle est', 'quels sont', 'quelles sont', 'que faire', 'quoi faire',
    'guide', 'guides', 'tuto', 'tutoriel', 'mode d emploi', 'pas a pas',
    'conseil', 'conseils', 'astuce', 'astuces', 'idee', 'idée',
    'idees', 'idées', 'inspiration', 'dossier', 'article', 'faq',
    'exemple', 'exemples', 'liste', 'checklist', 'definition',
    'définition', 'signification', 'explication', 'lexique', 'glossaire',
    'faire', 'preparer', 'préparer', 'cuisiner', 'cuire', 'utiliser',
    'installer', 'nettoyer', 'conserver', 'garder', 'ouvrir', 'servir',
    'accompagner', 'deguster', 'déguster', 'mariner', 'assaisonner',
    'remplacer', 'eviter', 'éviter', 'reconnaitre', 'reconnaître',
    'savoir', 'comprendre', 'apprendre', 'calculer', 'mesurer',
    'reduire', 'réduire', 'ameliorer', 'améliorer', 'recette',
    'recettes', 'ingredient', 'ingredients', 'ingrédient', 'ingrédients',
    'cuisson', 'preparation', 'préparation', 'plat', 'entree', 'entrée',
    'aperitif', 'apéritif', 'apero', 'apéro', 'sauce', 'salade',
    'cake', 'tarte', 'quiche', 'maison', 'facile', 'rapide',
    'thermomix', 'cookeo', 'accompagnement', 'menu', 'repas',
    'probleme', 'problème', 'panne', 'erreur', 'solution', 'depanner',
    'dépanner', 'reparer', 'réparer', 'ne marche pas',
    'ne fonctionne pas', 'bug', 'defaut', 'défaut', 'symptome',
    'symptôme', 'danger', 'risque', 'toxique', 'allergie',
    'intoxication', 'malade', 'fonctionnement', 'difference',
    'différence', 'difference entre', 'différence entre', 'avantage',
    'avantages', 'inconvenient', 'inconvénient', 'inconvenients',
    'inconvénients', 'bienfait', 'bienfaits', 'composition', 'origine',
    'histoire', 'saison', 'calorie', 'calories', 'nutrition',
    'nutriment', 'proteine', 'protéine', 'vitamine', 'sante', 'santé',
    'conservation', 'duree', 'durée', 'date limite', 'peremption',
    'péremption', 'utilisation', 'entretien', 'maintenance',
    'diagnostic', 'fiche technique', 'caracteristique', 'caractéristique',
    'caracteristiques', 'caractéristiques', 'dimension', 'dimensions',
    'taille', 'mesure', 'longueur', 'largeur', 'hauteur', 'poids',
    'volume', 'capacite', 'capacité', 'puissance', 'autonomie',
    'consommation', 'performance', 'performances', 'configuration',
    'configurations', 'version', 'versions', 'finition', 'finitions',
    'modele', 'modèle', 'modeles', 'modèles', 'gamme', 'type', 'types',
    'categorie', 'catégorie', 'categories', 'catégories', 'schema',
    'schéma', 'tableau', 'carte', 'norme', 'loi', 'reglementation',
    'réglementation', 'obligatoire', 'interdit', 'autorise', 'autorisé',
    'sanction', 'amende', 'condition', 'conditions', 'demarche',
    'démarche', 'aide', 'prime', 'simulation', 'calcul', 'calendrier',
    'date', 'date de sortie', 'sortie', 'planning', 'programme',
    'horaire', 'horaires', 'actualite', 'actualité', 'actualites',
    'actualités', 'news', 'resultat', 'résultat', 'resultats', 'résultats',
    'aujourd hui', 'demain'
)

INFORMATION_PRIORITY_PATTERNS = (
    'comment', 'pourquoi', 'quand', 'qu est ce que', 'qu est ce',
    'c est quoi', 'est ce que', 'peut on', 'faut il', 'doit on',
    'a quoi sert', 'à quoi sert', 'difference', 'différence',
    'difference entre', 'différence entre', 'definition', 'définition',
    'signification', 'fonctionnement', 'guide', 'tuto', 'tutoriel',
    'mode d emploi', 'que faire', 'quoi faire', 'probleme', 'problème',
    'panne', 'erreur', 'symptome', 'symptôme'
)

GENERIC_SINGLE_WORDS = (
    'voiture', 'auto', 'automobile', 'moto', 'scooter', 'camion', 'velo',
    'vélo', 'maison', 'appartement', 'assurance', 'banque', 'credit',
    'crédit', 'mutuelle', 'sante', 'santé', 'recette', 'voyage', 'hotel',
    'hôtel', 'restaurant', 'formation', 'logiciel', 'outil', 'produit',
    'service', 'chaussure', 'vetement', 'vêtement', 'telephone',
    'téléphone', 'ordinateur', 'energie', 'énergie'
)

def normalize_search_text(text: str) -> str:
    """Normalise un mot-clé pour comparer les intentions sans dépendre des accents."""
    text = unicodedata.normalize('NFD', str(text).lower())
    text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
    text = re.sub(r"['’`´-]", ' ', text)
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

KEYWORD_STOP_WORDS = {
    'l', 'le', 'la', 'les', 'de', 'du', 'des', 'd', 'un', 'une',
    'pour', 'en', 'a', 'au', 'aux'
}

DEFAULT_KEYWORD_EQUIVALENCE_PAIRS = (
    ('e commerce', 'ecommerce'),
    ('web marketing', 'webmarketing'),
    ('data base', 'database'),
    ('week end', 'weekend'),
    ('apres vente', 'apresvente'),
    ('pret a porter', 'pretaporter')
)

KEYWORD_EQUIVALENCE_PRESETS = {
    'Aucun': (),
    'SEO / Marketing': (
        ('seo', 'referencement'),
        ('seo', 'référencement'),
        ('cms', 'content management system'),
        ('crm', 'customer relationship management')
    ),
    'RH / Recrutement': (
        ('rh', 'ressources humaines'),
        ('drh', 'directeur ressources humaines'),
        ('sirh', 'systeme information ressources humaines'),
        ('sirh', 'système information ressources humaines')
    ),
    'E-commerce': (
        ('sav', 'service apres vente'),
        ('sav', 'service après vente'),
        ('pav', 'point de vente'),
        ('bopis', 'buy online pick up in store')
    ),
    'Immobilier': (
        ('dpe', 'diagnostic performance energetique'),
        ('dpe', 'diagnostic performance énergétique'),
        ('lmnp', 'location meublee non professionnelle'),
        ('lmnp', 'location meublée non professionnelle')
    ),
    'Automobile': (
        ('loa', 'location avec option achat'),
        ('lld', 'location longue duree'),
        ('lld', 'location longue durée'),
        ('adblue', 'ad blue')
    )
}

NGRAM_SIZES = (2, 3)
NGRAM_MIN_FREQUENCY = 2
NGRAM_MAX_FILTER_OPTIONS = 100
NGRAM_VISUALIZATION_LIMIT = 15
KEYWORD_AUDIT_COLUMNS = ['Keyword normalisé', 'Nb variantes regroupées', 'Variantes regroupées']
NGRAM_CLUSTER_COLUMNS = ['Cluster principal', 'Type cluster', 'Fréquence cluster']
ADDITIONAL_AUDIT_COLUMNS = KEYWORD_AUDIT_COLUMNS + NGRAM_CLUSTER_COLUMNS

FEMININE_TOKEN_REPLACEMENTS = {
    'avocate': 'avocat',
    'fiscale': 'fiscal',
    'sportive': 'sportif',
    'infirmiere': 'infirmier',
    'liberale': 'liberal',
    'consultante': 'consultant'
}

FEMININE_TOKEN_SUFFIXES = (
    ('iere', 'ier'),
    ('ive', 'if'),
    ('ale', 'al'),
    ('ante', 'ant'),
    ('ente', 'ent'),
    ('euse', 'eur')
)

def build_keyword_equivalence_map(custom_rules: str = '') -> dict:
    """Construit les équivalences de normalisation keyword à partir des règles utilisateur."""
    equivalences = {}

    def register_equivalence(canonical: str, variant: str):
        normalized_canonical = normalize_search_text(canonical)
        normalized_variant = normalize_search_text(variant)
        if normalized_canonical and normalized_variant:
            equivalences[normalized_canonical] = normalized_canonical
            equivalences[normalized_variant] = normalized_canonical

    for canonical, variant in DEFAULT_KEYWORD_EQUIVALENCE_PAIRS:
        register_equivalence(canonical, variant)

    if not isinstance(custom_rules, str):
        return equivalences

    for raw_line in custom_rules.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        canonical, variant = line.split('=', 1)
        register_equivalence(canonical.strip(), variant.strip())

    return equivalences

def merge_keyword_equivalence_rules(custom_rules: str = '', preset_name: str = 'Aucun') -> str:
    """Assemble les règles préchargées et personnalisées dans un format unique."""
    merged_rules = []
    preset_pairs = KEYWORD_EQUIVALENCE_PRESETS.get(preset_name, ())

    for canonical, variant in preset_pairs:
        merged_rules.append(f"{canonical}={variant}")

    if isinstance(custom_rules, str) and custom_rules.strip():
        merged_rules.append(custom_rules.strip())

    return '\n'.join(merged_rules)

def move_columns_to_end(df: pd.DataFrame, target_columns: list) -> pd.DataFrame:
    """Déplace certaines colonnes à la fin du DataFrame en conservant leur ordre."""
    existing_target_columns = [column for column in target_columns if column in df.columns]
    if not existing_target_columns:
        return df

    leading_columns = [column for column in df.columns if column not in existing_target_columns]
    return df[leading_columns + existing_target_columns].copy()

def apply_keyword_equivalences(normalized_text: str, equivalences: dict) -> str:
    """Remplace les variantes connues par leur forme canonique dans un texte normalisé."""
    if not normalized_text or not equivalences:
        return normalized_text

    result = f" {normalized_text} "
    ordered_equivalences = sorted(
        equivalences.items(),
        key=lambda item: len(item[0].split()),
        reverse=True
    )
    for variant, canonical in ordered_equivalences:
        result = re.sub(
            rf'(?<![a-z0-9]){re.escape(variant)}(?![a-z0-9])',
            f' {canonical} ',
            result
        )

    return re.sub(r'\s+', ' ', result).strip()

def normalize_keyword_token(token: str) -> str:
    """Ramène un token à une forme prudente pour regrouper des variantes proches."""
    if not token:
        return ''

    if token in FEMININE_TOKEN_REPLACEMENTS:
        return FEMININE_TOKEN_REPLACEMENTS[token]

    normalized_token = token
    if len(normalized_token) > 4 and normalized_token.endswith('s') and not normalized_token.endswith(('ss', 'us', 'is')):
        normalized_token = normalized_token[:-1]

    if normalized_token in FEMININE_TOKEN_REPLACEMENTS:
        return FEMININE_TOKEN_REPLACEMENTS[normalized_token]

    for suffix, replacement in FEMININE_TOKEN_SUFFIXES:
        if len(normalized_token) > len(suffix) + 2 and normalized_token.endswith(suffix):
            return normalized_token[:-len(suffix)] + replacement

    return normalized_token

def normalize_keyword_for_grouping(keyword: str, equivalences=None) -> str:
    """Construit une clé de regroupement prudente pour dédupliquer les keywords."""
    normalized_keyword = normalize_search_text(keyword)
    if not normalized_keyword:
        return ''

    active_equivalences = equivalences if equivalences is not None else build_keyword_equivalence_map()
    normalized_keyword = apply_keyword_equivalences(normalized_keyword, active_equivalences)

    normalized_tokens = []
    for token in normalized_keyword.split():
        normalized_token = normalize_keyword_token(token)
        if not normalized_token or normalized_token in KEYWORD_STOP_WORDS:
            continue
        normalized_tokens.append(normalized_token)

    if not normalized_tokens:
        normalized_tokens = [token for token in normalized_keyword.split() if token]

    return ' '.join(sorted(set(normalized_tokens)))

def normalize_keyword_for_ngrams(keyword: str, equivalences=None) -> list:
    """Normalise un keyword en conservant l'ordre utile pour générer des n-grams."""
    normalized_keyword = normalize_search_text(keyword)
    if not normalized_keyword:
        return []

    active_equivalences = equivalences if equivalences is not None else build_keyword_equivalence_map()
    normalized_keyword = apply_keyword_equivalences(normalized_keyword, active_equivalences)

    normalized_tokens = []
    for token in normalized_keyword.split():
        if not token or token in KEYWORD_STOP_WORDS:
            continue
        normalized_tokens.append(token)

    if not normalized_tokens:
        normalized_tokens = [token for token in normalized_keyword.split() if token]

    return normalized_tokens

def extract_keyword_ngrams(tokens, ngram_sizes=NGRAM_SIZES) -> list:
    """Extrait les bi-grams et tri-grams d'un keyword normalisé."""
    if isinstance(tokens, str):
        normalized_tokens = [token for token in tokens.split() if token]
    else:
        normalized_tokens = [token for token in tokens if token]

    keyword_ngrams = []
    for ngram_size in ngram_sizes:
        if len(normalized_tokens) < ngram_size:
            continue

        for start_index in range(len(normalized_tokens) - ngram_size + 1):
            ngram_tokens = normalized_tokens[start_index:start_index + ngram_size]
            observed_label = ' '.join(ngram_tokens)
            canonical_tokens = [normalize_keyword_token(token) for token in ngram_tokens]
            keyword_ngrams.append(
                {
                    'Cluster key': ' '.join(sorted(canonical_tokens)),
                    'Observed label': observed_label,
                    'Cluster size': ngram_size
                }
            )

    return keyword_ngrams

def build_ngram_cluster_catalog(df: pd.DataFrame, keyword_tokens, min_frequency: int = NGRAM_MIN_FREQUENCY) -> pd.DataFrame:
    """Agrège les n-grams fréquents sur la vue courante."""
    if df.empty or 'Keyword' not in df.columns:
        return pd.DataFrame()

    cluster_stats = {}
    volume_series = pd.to_numeric(df.get('Volume', 0), errors='coerce').fillna(0)

    for row_index, tokens in keyword_tokens.items():
        keyword_ngrams = extract_keyword_ngrams(tokens)
        if not keyword_ngrams:
            continue

        # On compte au maximum une occurrence par keyword et par cluster.
        keyword_cluster_candidates = {}
        for ngram_data in keyword_ngrams:
            cluster_key = ngram_data['Cluster key']
            current_value = keyword_cluster_candidates.get(cluster_key)
            if current_value is None:
                keyword_cluster_candidates[cluster_key] = ngram_data
                continue

            candidate_label = ngram_data['Observed label']
            current_label = current_value['Observed label']
            if (
                ngram_data['Cluster size'] > current_value['Cluster size'] or
                (
                    ngram_data['Cluster size'] == current_value['Cluster size'] and
                    candidate_label < current_label
                )
            ):
                keyword_cluster_candidates[cluster_key] = ngram_data

        row_volume = float(volume_series.loc[row_index]) if row_index in volume_series.index else 0.0
        for cluster_key, ngram_data in keyword_cluster_candidates.items():
            if cluster_key not in cluster_stats:
                cluster_stats[cluster_key] = {
                    'Fréquence cluster': 0,
                    'Volume cluster': 0.0,
                    'Cluster size': ngram_data['Cluster size'],
                    'Observed labels': Counter(),
                    'Observed label volumes': {}
                }

            cluster_stats[cluster_key]['Fréquence cluster'] += 1
            cluster_stats[cluster_key]['Volume cluster'] += row_volume
            observed_label = ngram_data['Observed label']
            cluster_stats[cluster_key]['Observed labels'][observed_label] += 1
            cluster_stats[cluster_key]['Observed label volumes'][observed_label] = (
                cluster_stats[cluster_key]['Observed label volumes'].get(observed_label, 0.0) + row_volume
            )

    cluster_records = []
    for cluster_key, cluster_data in cluster_stats.items():
        if cluster_data['Fréquence cluster'] < min_frequency:
            continue

        best_label = min(
            cluster_data['Observed labels'].keys(),
            key=lambda label: (
                -cluster_data['Observed labels'][label],
                -cluster_data['Observed label volumes'].get(label, 0.0),
                label
            )
        )
        cluster_size = int(cluster_data['Cluster size'])
        cluster_records.append(
            {
                'Cluster key': cluster_key,
                'Cluster principal': best_label,
                'Type cluster': 'Tri-gram' if cluster_size == 3 else 'Bi-gram',
                'Fréquence cluster': int(cluster_data['Fréquence cluster']),
                'Volume cluster': float(cluster_data['Volume cluster']),
                'Cluster size': cluster_size
            }
        )

    if not cluster_records:
        return pd.DataFrame()

    cluster_catalog = pd.DataFrame(cluster_records)
    return cluster_catalog.sort_values(
        by=['Fréquence cluster', 'Volume cluster', 'Cluster principal'],
        ascending=[False, False, True]
    ).reset_index(drop=True)

def assign_primary_ngram_cluster(tokens, cluster_lookup: dict) -> dict:
    """Attribue un cluster principal à un keyword à partir du catalogue n-gram."""
    if not cluster_lookup:
        return {
            'Cluster principal': '',
            'Type cluster': 'Aucun',
            'Fréquence cluster': 0
        }

    candidate_clusters = {}
    for ngram_data in extract_keyword_ngrams(tokens):
        cluster_key = ngram_data['Cluster key']
        if cluster_key in cluster_lookup:
            candidate_clusters[cluster_key] = cluster_lookup[cluster_key]

    if not candidate_clusters:
        return {
            'Cluster principal': '',
            'Type cluster': 'Aucun',
            'Fréquence cluster': 0
        }

    selected_cluster = min(
        candidate_clusters.values(),
        key=lambda cluster: (
            -cluster['Fréquence cluster'],
            -cluster['Cluster size'],
            -cluster['Volume cluster'],
            cluster['Cluster principal']
        )
    )

    return {
        'Cluster principal': selected_cluster['Cluster principal'],
        'Type cluster': selected_cluster['Type cluster'],
        'Fréquence cluster': int(selected_cluster['Fréquence cluster'])
    }

def add_ngram_clusters_to_view(
    df: pd.DataFrame,
    custom_rules: str = '',
    min_frequency: int = NGRAM_MIN_FREQUENCY,
    max_options: int = NGRAM_MAX_FILTER_OPTIONS
):
    """Ajoute temporairement les clusters n-gram à la vue affichée."""
    view_df = df.copy()
    if view_df.empty or 'Keyword' not in view_df.columns:
        view_df['Cluster principal'] = ''
        view_df['Type cluster'] = 'Aucun'
        view_df['Fréquence cluster'] = 0
        return view_df, []

    equivalences = build_keyword_equivalence_map(custom_rules)
    keyword_tokens = view_df['Keyword'].fillna('').astype(str).apply(
        lambda value: normalize_keyword_for_ngrams(value, equivalences)
    )
    cluster_catalog = build_ngram_cluster_catalog(view_df, keyword_tokens, min_frequency=min_frequency)

    if cluster_catalog.empty:
        view_df['Cluster principal'] = ''
        view_df['Type cluster'] = 'Aucun'
        view_df['Fréquence cluster'] = 0
        return view_df, []

    cluster_lookup = {
        row['Cluster key']: row
        for _, row in cluster_catalog.iterrows()
    }
    assignments = keyword_tokens.apply(lambda tokens: assign_primary_ngram_cluster(tokens, cluster_lookup))
    assignment_df = pd.DataFrame(assignments.tolist(), index=view_df.index)
    view_df[NGRAM_CLUSTER_COLUMNS] = assignment_df[NGRAM_CLUSTER_COLUMNS]
    view_df = move_columns_to_end(view_df, ADDITIONAL_AUDIT_COLUMNS)

    cluster_options_df = cluster_catalog.sort_values(
        by=['Fréquence cluster', 'Volume cluster', 'Cluster principal'],
        ascending=[False, False, True]
    ).head(max_options)
    cluster_options = cluster_options_df['Cluster principal'].tolist()

    return view_df, cluster_options

def build_ngram_visualization_summary(df: pd.DataFrame, limit: int = NGRAM_VISUALIZATION_LIMIT) -> pd.DataFrame:
    """Construit une synthèse des clusters n-gram pour la visualisation."""
    required_columns = {'Cluster principal', 'Type cluster', 'Volume'}
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame()

    cluster_df = df[df['Cluster principal'].fillna('').astype(str).str.strip() != ''].copy()
    if cluster_df.empty:
        return pd.DataFrame()

    cluster_df['Volume'] = pd.to_numeric(cluster_df['Volume'], errors='coerce').fillna(0)
    summary_df = cluster_df.groupby(['Cluster principal', 'Type cluster'], as_index=False).agg(
        **{
            'Nombre de keywords': ('Keyword', 'count'),
            'Volume total': ('Volume', 'sum')
        }
    )
    summary_df = summary_df.sort_values(
        by=['Volume total', 'Nombre de keywords', 'Cluster principal'],
        ascending=[False, False, True]
    ).head(limit)

    return summary_df

def create_ngram_cluster_bar_chart(cluster_summary_df: pd.DataFrame, graph_title_style=None, graph_layout=None):
    """Crée le graphique des clusters n-gram en conservant les labels comme catégories."""
    if cluster_summary_df.empty:
        return None

    graph_title_style = graph_title_style or {}
    graph_layout = graph_layout or {}
    chart_df = cluster_summary_df.copy()
    chart_df['Cluster principal'] = chart_df['Cluster principal'].fillna('').astype(str)
    chart_df['Type cluster'] = chart_df['Type cluster'].fillna('Aucun').astype(str)
    chart_df = chart_df.sort_values(
        by=['Volume total', 'Nombre de keywords', 'Cluster principal'],
        ascending=[True, True, False]
    )
    cluster_categories = chart_df['Cluster principal'].tolist()

    fig_clusters = px.bar(
        chart_df,
        x='Volume total',
        y='Cluster principal',
        color='Type cluster',
        orientation='h',
        hover_data={
            'Volume total': ':,.0f',
            'Nombre de keywords': True,
            'Type cluster': True,
            'Cluster principal': False
        },
        category_orders={'Cluster principal': cluster_categories},
        title='Top clusters n-gram'
    )
    fig_clusters.update_layout(
        title=dict(
            text='Top clusters n-gram',
            **graph_title_style
        ),
        xaxis_title='Volume de recherche total',
        yaxis_title='Cluster principal',
        **graph_layout
    )
    fig_clusters.update_yaxes(
        type='category',
        categoryorder='array',
        categoryarray=cluster_categories
    )

    return fig_clusters

def deduplicate_keywords_by_normalized_key(df: pd.DataFrame, client_domain: str, custom_rules: str = '') -> pd.DataFrame:
    """Conserve le meilleur keyword par groupe normalisé et ajoute les colonnes d'audit."""
    if df.empty or 'Keyword' not in df.columns:
        return df.copy()

    dedup_df = df.copy()
    equivalences = build_keyword_equivalence_map(custom_rules)
    dedup_df['Keyword normalisé'] = dedup_df['Keyword'].apply(
        lambda value: normalize_keyword_for_grouping(value, equivalences)
    )

    client_position_col = resolve_domain_metric_column(dedup_df, client_domain, ': Position')
    dedup_df['_volume_sort'] = pd.to_numeric(dedup_df['Volume'], errors='coerce').fillna(0)
    dedup_df['_kd_sort'] = pd.to_numeric(dedup_df['KD'], errors='coerce').fillna(float('inf'))
    position_numeric = pd.to_numeric(dedup_df[client_position_col], errors='coerce').fillna(0)
    dedup_df['_position_sort'] = position_numeric.where(position_numeric > 0, 9999)
    dedup_df['_keyword_length_sort'] = dedup_df['Keyword'].fillna('').astype(str).str.len()
    dedup_df['_original_order_sort'] = range(len(dedup_df))

    variant_counts = dedup_df.groupby('Keyword normalisé')['Keyword'].nunique()
    variants = dedup_df.groupby('Keyword normalisé')['Keyword'].apply(
        lambda values: ' | '.join(dict.fromkeys(values.fillna('').astype(str)))
    )

    sorted_df = dedup_df.sort_values(
        by=[
            'Keyword normalisé', '_volume_sort', '_kd_sort',
            '_position_sort', '_keyword_length_sort', '_original_order_sort'
        ],
        ascending=[True, False, True, True, True, True]
    )
    winners = sorted_df.drop_duplicates(subset=['Keyword normalisé'], keep='first').copy()
    winners['Nb variantes regroupées'] = winners['Keyword normalisé'].map(variant_counts).fillna(1).astype(int)
    winners['Variantes regroupées'] = winners['Keyword normalisé'].map(variants).fillna(winners['Keyword'])

    temp_columns = [
        '_volume_sort', '_kd_sort', '_position_sort',
        '_keyword_length_sort', '_original_order_sort'
    ]
    return winners.drop(columns=temp_columns).reset_index(drop=True)

def build_known_intent_entities(client_name: str, custom_brands: list) -> list:
    """Construit les entités connues pour mieux détecter les requêtes navigationnelles."""
    client_domain = clean_domain_name(client_name) if isinstance(client_name, str) else ''
    domain_stem = client_domain.split('.')[0] if client_domain else ''
    raw_entities = [client_domain, domain_stem] + [brand for brand in custom_brands if brand]
    normalized_entities = []

    for entity in raw_entities:
        normalized_entity = normalize_search_text(entity)
        if normalized_entity and normalized_entity not in normalized_entities:
            normalized_entities.append(normalized_entity)

    return normalized_entities

def classify_intent(keyword: str, known_entities=None) -> str:
    """
    Classifie l'intention de recherche avec des signaux génériques.
    Les règles restent volontairement transversales pour fonctionner sur toute thématique.
    """
    if not isinstance(keyword, str) or not keyword.strip():
        return 'Autre'

    normalized_keyword = normalize_search_text(keyword)
    words = re.findall(r'[a-z0-9]+', normalized_keyword)
    word_set = set(words)

    if not normalized_keyword:
        return 'Autre'

    def phrase_matches(phrase: str) -> bool:
        normalized_phrase = normalize_search_text(phrase)
        if not normalized_phrase:
            return False
        phrase_words = normalized_phrase.split()
        if len(phrase_words) == 1:
            return phrase_words[0] in word_set
        return re.search(rf'(^| ){re.escape(normalized_phrase)}( |$)', normalized_keyword) is not None

    def any_match(patterns: tuple) -> bool:
        return any(phrase_matches(pattern) for pattern in patterns)

    normalized_entities = [
        normalize_search_text(entity)
        for entity in (known_entities or [])
        if isinstance(entity, str) and normalize_search_text(entity)
    ]
    has_known_entity = any(
        re.search(rf'(^| ){re.escape(entity)}( |$)', normalized_keyword)
        for entity in normalized_entities
    )
    is_known_entity_only = normalized_keyword in normalized_entities

    has_strong_transaction = any_match(STRONG_TRANSACTION_INTENT_PATTERNS)
    has_transaction = any_match(TRANSACTION_INTENT_PATTERNS)
    has_transaction_combo = (
        any_match(TRANSACTION_ACTION_PATTERNS) and
        any_match(TRANSACTION_CONTEXT_PATTERNS)
    )
    has_commercial = any_match(COMMERCIAL_INTENT_PATTERNS)
    has_information = any_match(INFORMATION_INTENT_PATTERNS)
    has_information_priority = any_match(INFORMATION_PRIORITY_PATTERNS)

    if has_information_priority and not (has_strong_transaction or has_transaction_combo):
        return 'Informationnel'

    if has_strong_transaction or has_transaction_combo:
        return 'Transactionnel'

    if any_match(NAVIGATION_INTENT_PATTERNS) or is_known_entity_only:
        return 'Navigationnel'

    if has_commercial:
        return 'Commercial'

    if has_information:
        return 'Informationnel'

    if has_transaction:
        return 'Transactionnel'

    # Une requête courte contenant une entité connue et aucun autre signal vise souvent le site/la marque.
    if has_known_entity and len(words) <= 3:
        return 'Navigationnel'

    # Un mot-clé très court et générique n'est pas forcément navigationnel.
    if len(words) == 1 or normalized_keyword in GENERIC_SINGLE_WORDS:
        return 'Autre'

    return 'Autre'

def classify_branded(keyword: str, client_name: str, custom_brands: list) -> str:
    """Détermine si le mot-clé est de marque ou non"""
    keyword = keyword.lower()
    
    # Ajout du nom du client et des termes personnalisés à la liste des marques
    brands = [client_name.lower()] + [brand.lower() for brand in custom_brands if brand]
    
    # Vérification si le mot-clé contient une marque
    if any(brand in keyword for brand in brands if brand):
        return 'Marque'
    return 'Hors marque'

DEFAULT_TEMPLATE_MARKERS = {
    'content': (
        'blog', 'actualite', 'actualites', 'news', 'article', 'articles',
        'guide', 'guides', 'faq', 'conseil', 'conseils', 'ressource',
        'ressources', 'recette', 'recettes', 'magazine'
    ),
    'product': (
        'produit', 'produits', 'product', 'products', 'fiche-produit',
        'item', 'sku', 'reference', 'ref'
    ),
    'category': (
        'categorie', 'categories', 'category', 'catalogue', 'catalog',
        'collection', 'collections', 'boutique', 'shop', 'store',
        'univers', 'rayon', 'gamme'
    )
}

def normalize_template_marker(marker: str) -> str:
    """Nettoie un marqueur de template entré en configuration"""
    return marker.lower().strip().strip('/')

def build_template_rules(content_input: str = '', product_input: str = '', category_input: str = '') -> dict:
    """Construit les règles de classification des templates à partir des inputs"""
    def parse_markers(raw_value: str, defaults: tuple) -> set:
        if isinstance(raw_value, str) and raw_value.strip():
            markers = {
                normalize_template_marker(item)
                for item in raw_value.split(',')
                if normalize_template_marker(item)
            }
            if markers:
                return markers
        return {
            normalize_template_marker(item)
            for item in defaults
            if normalize_template_marker(item)
        }

    return {
        'content': parse_markers(content_input, DEFAULT_TEMPLATE_MARKERS['content']),
        'product': parse_markers(product_input, DEFAULT_TEMPLATE_MARKERS['product']),
        'category': parse_markers(category_input, DEFAULT_TEMPLATE_MARKERS['category'])
    }

def path_contains_marker(path: str, segments: list, marker: str) -> bool:
    """Vérifie si un marqueur est présent dans un path d'URL"""
    cleaned_marker = normalize_template_marker(marker)
    if not cleaned_marker:
        return False

    normalized_marker = cleaned_marker.replace('_', '/').replace('-', '/')
    marker_parts = [part for part in normalized_marker.split('/') if part]
    if not marker_parts:
        return False

    if len(marker_parts) == 1:
        return marker_parts[0] in segments

    normalized_path = path.replace('_', '/').replace('-', '/')
    return '/'.join(marker_parts) in normalized_path

def classify_template_from_url(url: str, template_rules=None) -> str:
    """Classifie le type de template attendu à partir d'une URL"""
    if not isinstance(url, str) or not url.strip():
        return 'Autre'

    rules = template_rules if template_rules else build_template_rules()

    try:
        path = urlparse(url.strip()).path.lower()
    except Exception:
        path = str(url).lower()

    normalized_path = path.replace('_', '/').replace('-', '/')
    segments = [segment for segment in re.split(r'/+', normalized_path) if segment]

    content_markers = rules.get('content', set())
    product_markers = rules.get('product', set())
    category_markers = rules.get('category', set())

    has_content = any(path_contains_marker(path, segments, marker) for marker in content_markers)
    has_product = any(path_contains_marker(path, segments, marker) for marker in product_markers)
    has_category = any(path_contains_marker(path, segments, marker) for marker in category_markers)

    if has_content:
        return 'Contenu'

    if re.search(r'/(p|prod|product|produit)[-_]?\d+', path):
        return 'Produit'

    if has_category and not has_product:
        return 'Catégorie'

    if has_product:
        return 'Produit'

    if has_category:
        return 'Catégorie'

    return 'Autre'

def pick_reference_urls_for_template(row, client_domain: str, max_urls: int = 3) -> list:
    """Sélectionne les meilleures URLs (top positions) pour inférer le template"""
    candidates = []

    for col in row.index:
        if not isinstance(col, str) or not col.endswith(': Position'):
            continue

        domain = col[:-len(': Position')]
        url_col = f"{domain}: URL"
        url_value = row.get(url_col, '')

        if not isinstance(url_value, str) or not url_value.strip():
            continue

        try:
            position = float(row.get(col, 0))
        except (TypeError, ValueError):
            continue

        if position > 0:
            candidates.append((position, url_value.strip()))

    if candidates:
        ordered_urls = []
        seen = set()
        for _, candidate_url in sorted(candidates, key=lambda item: item[0]):
            if candidate_url in seen:
                continue
            ordered_urls.append(candidate_url)
            seen.add(candidate_url)
            if len(ordered_urls) >= max_urls:
                break
        if ordered_urls:
            return ordered_urls

    fallback_urls = []
    client_url = row.get(f"{client_domain}: URL", '')
    if isinstance(client_url, str) and client_url.strip():
        fallback_urls.append(client_url.strip())

    if fallback_urls:
        return fallback_urls

    for col in row.index:
        if isinstance(col, str) and col.endswith(': URL'):
            candidate_url = row.get(col, '')
            if isinstance(candidate_url, str) and candidate_url.strip():
                return [candidate_url.strip()]

    return []

def define_template(row, client_domain: str, template_rules=None) -> str:
    """Détermine le template attendu (Contenu, Produit, Catégorie, Autre)"""
    try:
        reference_urls = pick_reference_urls_for_template(row, client_domain, max_urls=3)
        if not reference_urls:
            return 'Autre'

        predictions = [
            classify_template_from_url(reference_url, template_rules)
            for reference_url in reference_urls
        ]
        if not predictions:
            return 'Autre'

        vote_counts = Counter(predictions)
        max_votes = max(vote_counts.values())
        winners = [label for label, votes in vote_counts.items() if votes == max_votes]

        if len(winners) == 1:
            return winners[0]

        for prediction in predictions:
            if prediction in winners and prediction != 'Autre':
                return prediction

        return predictions[0]
    except Exception:
        return 'Autre'

def format_positions_for_output(df):
    """Formate les colonnes de position pour l'affichage/export final"""
    formatted_df = df.copy()
    position_columns = [col for col in formatted_df.columns if ': Position' in col]

    for col in position_columns:
        numeric_series = pd.to_numeric(formatted_df[col], errors='coerce').fillna(0)
        formatted_df[col] = numeric_series.apply(
            lambda value: '' if value <= 0 else int(value)
        )

    return move_columns_to_end(formatted_df, ADDITIONAL_AUDIT_COLUMNS)

def get_position_cell_style(value):
    """Retourne le style CSS d'une cellule de position SEO"""
    if value in ('', None):
        return ''

    try:
        position = float(value)
    except (TypeError, ValueError):
        return ''

    if position <= 3:
        return 'background-color: #D8F3DC; color: #1B4332; font-weight: 600;'
    if position <= 10:
        return 'background-color: rgba(76, 235, 166, 0.16); color: #4CEBA6; font-weight: 600;'
    if position <= 20:
        return 'background-color: #FFF3BF; color: #7A4E00; font-weight: 600;'
    if position <= 50:
        return 'background-color: #FFE8CC; color: #9C3D00; font-weight: 600;'
    return 'background-color: #F8D7DA; color: #842029; font-weight: 600;'

def get_volume_cell_style(value, thresholds):
    """Retourne le style CSS d'une cellule de volume"""
    if not thresholds:
        return ''

    try:
        volume = float(str(value).replace(' ', ''))
    except (TypeError, ValueError):
        return ''

    low_threshold, high_threshold = thresholds
    if volume <= low_threshold:
        return 'background-color: #F8D7DA; color: #842029; font-weight: 600;'
    if volume <= high_threshold:
        return 'background-color: #FFF3BF; color: #7A4E00; font-weight: 600;'
    return 'background-color: #D8F3DC; color: #1B4332; font-weight: 700;'

STYLER_MAX_ELEMENTS = 262144

def format_integer_display(value):
    """Formate un nombre sans décimales inutiles pour l'affichage."""
    if pd.isna(value):
        return ''

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return str(value)

    return f"{numeric_value:,.0f}".replace(',', ' ')

def get_results_dataframe_column_config(df):
    """Construit la configuration d'affichage des colonnes numériques du tableau."""
    column_config = {}

    if 'Volume' in df.columns:
        column_config['Volume'] = st.column_config.TextColumn('Volume')
    if 'KD' in df.columns:
        column_config['KD'] = st.column_config.NumberColumn('KD', format='%.1f')
    if 'CPC' in df.columns:
        column_config['CPC'] = st.column_config.NumberColumn('CPC', format='%.2f')
    if 'Concurrence' in df.columns:
        column_config['Concurrence'] = st.column_config.NumberColumn('Concurrence', format='%d')

    for column in df.columns:
        if ': Position' in column:
            column_config[column] = st.column_config.NumberColumn(column, format='%d')
        elif ': Traffic' in column:
            column_config[column] = st.column_config.NumberColumn(column, format='%d')

    return column_config

def prepare_results_dataframe_for_display(df):
    """Prépare une copie du tableau pour un affichage lisible sans modifier les données source."""
    display_df = df.copy()

    if 'Volume' in display_df.columns:
        volume_numeric = pd.to_numeric(display_df['Volume'], errors='coerce')
        display_df['Volume'] = volume_numeric.map(format_integer_display)

    for column in display_df.columns:
        if ': Position' in column:
            position_numeric = pd.to_numeric(display_df[column], errors='coerce')
            display_df[column] = position_numeric.map(format_integer_display)

    return display_df

def style_output_dataframe(df):
    """Applique un code couleur sur les volumes et positions SEO"""
    styled = df.style

    if 'Volume' in df.columns:
        volume_numeric = pd.to_numeric(df['Volume'], errors='coerce')
        valid_volume = volume_numeric.dropna()
        if not valid_volume.empty:
            if valid_volume.nunique() > 1:
                quantiles = valid_volume.quantile([0.33, 0.66]).tolist()
            else:
                single_value = float(valid_volume.iloc[0])
                quantiles = [single_value, single_value]
            styled = styled.map(
                lambda value: get_volume_cell_style(value, quantiles),
                subset=['Volume']
            )
            styled = styled.format({'Volume': format_integer_display})

    position_columns = [col for col in df.columns if ': Position' in col]
    if position_columns:
        styled = styled.map(get_position_cell_style, subset=position_columns)

    return styled

def display_results_dataframe(df):
    """Affiche le tableau avec style seulement si Pandas Styler peut le rendre."""
    display_df = prepare_results_dataframe_for_display(df)
    column_config = get_results_dataframe_column_config(display_df)
    if df.size <= STYLER_MAX_ELEMENTS:
        st.dataframe(
            style_output_dataframe(display_df),
            use_container_width=True,
            height=400,
            column_config=column_config
        )
        return

    st.info(
        "Code couleur désactivé sur ce tableau volumineux pour éviter une limite Pandas Styler. "
        "Les données restent disponibles dans le tableau, l'export et la copie."
    )
    st.dataframe(display_df, use_container_width=True, height=400, column_config=column_config)

def render_copy_to_clipboard_button(text_to_copy: str, button_label: str, key: str):
    """Affiche un bouton pour copier un texte dans le presse-papiers du navigateur"""
    safe_key = re.sub(r'[^a-zA-Z0-9_-]', '_', str(key))
    encoded_text = base64.b64encode(str(text_to_copy).encode('utf-8')).decode('ascii')

    components.html(
        f"""
        <div style="display:flex;align-items:center;gap:8px;margin-top:4px;">
            <button id="copy-btn-{safe_key}" style="
                background:#F7F8F8;
                color:#0F1011;
                border:1px solid #F7F8F8;
                border-radius:8px;
                padding:8px 12px;
                font-size:14px;
                cursor:pointer;
            ">{button_label}</button>
            <span id="copy-status-{safe_key}" style="font-size:13px;color:#49DCBC;"></span>
        </div>
        <script>
            const encoded = "{encoded_text}";
            const bytes = Uint8Array.from(atob(encoded), c => c.charCodeAt(0));
            const text = new TextDecoder().decode(bytes);
            const btn = document.getElementById("copy-btn-{safe_key}");
            const status = document.getElementById("copy-status-{safe_key}");
            btn.addEventListener("click", async () => {{
                try {{
                    await navigator.clipboard.writeText(text);
                    status.textContent = "Copié";
                    setTimeout(() => status.textContent = "", 2000);
                }} catch (error) {{
                    status.textContent = "Copie impossible";
                }}
            }});
        </script>
        """,
        height=48
    )

def dataframe_to_json_string(df: pd.DataFrame) -> str:
    """Convertit un DataFrame en JSON lisible avec des valeurs nulles valides."""
    json_ready_df = df.copy().astype(object).where(pd.notnull(df), None)
    records = json_ready_df.to_dict(orient='records')
    return json.dumps(records, ensure_ascii=False, indent=2)

def resolve_domain_metric_column(df, client_domain: str, suffix: str) -> str:
    """Résout le nom exact d'une colonne domaine (tolère les variantes avec slash)."""
    direct_column = f"{client_domain}{suffix}"
    if direct_column in df.columns:
        return direct_column

    slash_column = f"{client_domain}/{suffix}"
    if slash_column in df.columns:
        return slash_column

    matching_columns = []
    for col in df.columns:
        if not isinstance(col, str) or not col.endswith(suffix):
            continue
        domain_part = col.split(':')[0]
        if clean_domain_name(domain_part) == client_domain:
            matching_columns.append(col)

    if matching_columns:
        return matching_columns[0]

    raise DataValidationError(f"Colonne introuvable pour {client_domain}{suffix}")

def build_quick_win_by_url_view(filtered_df, client_domain: str) -> pd.DataFrame:
    """Construit la vue Quick Win avec le meilleur keyword par URL client"""
    client_url_col = resolve_domain_metric_column(filtered_df, client_domain, ': URL')
    client_position_col = resolve_domain_metric_column(filtered_df, client_domain, ': Position')

    required_columns = ['Stratégie', 'Keyword', 'Volume', 'KD', 'CPC', client_url_col, client_position_col]
    missing_columns = [col for col in required_columns if col not in filtered_df.columns]
    if missing_columns:
        raise DataValidationError(f"Colonnes manquantes pour la vue Quick Win : {', '.join(missing_columns)}")

    quick_win_df = filtered_df[filtered_df['Stratégie'] == 'Quick Win'].copy()
    if quick_win_df.empty:
        return pd.DataFrame()

    quick_win_df[client_url_col] = quick_win_df[client_url_col].fillna('').astype(str).str.strip()
    quick_win_df = quick_win_df[quick_win_df[client_url_col] != '']
    if quick_win_df.empty:
        return pd.DataFrame()

    position_numeric = pd.to_numeric(quick_win_df[client_position_col], errors='coerce').fillna(0)
    volume_numeric = pd.to_numeric(quick_win_df['Volume'], errors='coerce').fillna(0)
    kd_numeric = pd.to_numeric(quick_win_df['KD'], errors='coerce').fillna(0)

    volume_score = (volume_numeric / 1000).clip(upper=100)
    difficulty_score = 100 - kd_numeric.clip(upper=100)
    position_score = 100 - position_numeric.where(position_numeric > 0, 100).clip(upper=100)
    quick_win_df['Score opportunité'] = (volume_score * 0.4 + difficulty_score * 0.3 + position_score * 0.3).round(2)

    quick_win_df = quick_win_df.sort_values(
        by=['Score opportunité', 'Volume', 'KD', client_position_col],
        ascending=[False, False, True, True]
    )
    quick_win_df = quick_win_df.drop_duplicates(subset=[client_url_col], keep='first')

    selected_columns = [
        client_url_col, 'Keyword', client_position_col, 'Volume', 'KD', 'CPC',
        'Intention', 'Template', 'Marque', 'Score opportunité'
    ]
    existing_columns = [col for col in selected_columns if col in quick_win_df.columns]
    quick_win_df = quick_win_df[existing_columns].copy()

    rename_map = {
        client_url_col: 'URL',
        'Keyword': 'Keyword recommandé',
        client_position_col: 'Position actuelle'
    }
    quick_win_df = quick_win_df.rename(columns=rename_map)

    if 'Position actuelle' in quick_win_df.columns:
        quick_win_df['Position actuelle'] = pd.to_numeric(
            quick_win_df['Position actuelle'], errors='coerce'
        ).fillna(0).astype(int)
    if 'Volume' in quick_win_df.columns:
        quick_win_df['Volume'] = pd.to_numeric(quick_win_df['Volume'], errors='coerce').fillna(0).astype(int)
    if 'KD' in quick_win_df.columns:
        quick_win_df['KD'] = pd.to_numeric(quick_win_df['KD'], errors='coerce').fillna(0).round(1)
    if 'CPC' in quick_win_df.columns:
        quick_win_df['CPC'] = pd.to_numeric(quick_win_df['CPC'], errors='coerce').fillna(0).round(2)

    return quick_win_df.sort_values(by='Score opportunité', ascending=False)

def display_quick_win_by_url(filtered_df, client_name):
    """Affiche la vue Quick Win avec le meilleur keyword par URL"""
    try:
        client_domain = clean_domain_name(client_name)
        quick_win_view = build_quick_win_by_url_view(filtered_df, client_domain)

        st.markdown("### ⚡ Quick Win : meilleur keyword par URL")

        if quick_win_view.empty:
            st.info("Aucun Quick Win exploitable par URL avec les filtres actuels.")
            return

        metric_col1, metric_col2, metric_col3 = st.columns(3)
        with metric_col1:
            st.metric("🔗 URLs Quick Win", f"{quick_win_view['URL'].nunique():,}")
        with metric_col2:
            st.metric("📊 Volume cumulé", f"{int(quick_win_view['Volume'].sum()):,}")
        with metric_col3:
            st.metric("🎯 Score moyen", f"{quick_win_view['Score opportunité'].mean():.1f}")

        st.dataframe(
            quick_win_view,
            use_container_width=True,
            height=400,
            column_config={
                "Position actuelle": st.column_config.NumberColumn(format="%d"),
                "Volume": st.column_config.NumberColumn(format="%d"),
                "KD": st.column_config.NumberColumn(format="%.1f"),
                "CPC": st.column_config.NumberColumn(format="%.2f"),
                "Score opportunité": st.column_config.NumberColumn(format="%.2f")
            }
        )
        quick_win_export_col1, quick_win_export_col2 = st.columns(2)
        with quick_win_export_col1:
            st.download_button(
                "📥 Export Quick Win CSV",
                quick_win_view.to_csv(index=False),
                f"Quick_Win_par_URL_{client_name}.csv",
                mime="text/csv",
                help="Télécharger la vue Quick Win URL au format CSV"
            )
        with quick_win_export_col2:
            st.download_button(
                "📥 Export Quick Win JSON",
                dataframe_to_json_string(quick_win_view),
                f"Quick_Win_par_URL_{client_name}.json",
                mime="application/json",
                help="Télécharger la vue Quick Win URL au format JSON"
            )
        render_copy_to_clipboard_button(
            quick_win_view.to_csv(index=False, sep='\t'),
            "📋 Copier Quick Win (TSV)",
            f"copy_quickwin_{client_name}"
        )
    except Exception as e:
        st.error(f"❌ Erreur lors de l'affichage de la vue Quick Win : {str(e)}")

def display_filtered_results(filtered_df, client_name):
    """Affiche les résultats filtrés"""
    try:
        client_domain = clean_domain_name(client_name)
        client_position_col = f'{client_domain}: Position'
        base_filtered_df = filtered_df.copy()
        ngram_view_df = pd.DataFrame()
        cluster_options = []
        selected_clusters = []
        enable_ngram_clustering = bool(st.session_state.get('enable_ngram_clustering', False))
        keyword_equivalence_rules = merge_keyword_equivalence_rules(
            st.session_state.get('keyword_equivalence_rules', ''),
            st.session_state.get('keyword_equivalence_preset', 'Aucun')
        )

        if client_position_col not in filtered_df.columns:
            raise DataValidationError(f"Colonne introuvable : {client_position_col}")

        def coerce_int(value, fallback):
            try:
                return int(value)
            except (TypeError, ValueError):
                return int(fallback)

        volume_series = pd.to_numeric(filtered_df['Volume'], errors='coerce').fillna(0)
        position_series = pd.to_numeric(filtered_df[client_position_col], errors='coerce').fillna(0)

        vol_min_bound = int(max(0, volume_series.min()))
        vol_max_bound = int(max(vol_min_bound, volume_series.max()))
        pos_min_bound = 0
        pos_max_bound = int(max(pos_min_bound, position_series.max()))

        if 'vol_min' not in st.session_state:
            st.session_state.vol_min = vol_min_bound
        if 'vol_max' not in st.session_state:
            st.session_state.vol_max = vol_max_bound
        if 'pos_min' not in st.session_state:
            st.session_state.pos_min = pos_min_bound
        if 'pos_max' not in st.session_state:
            st.session_state.pos_max = pos_max_bound

        st.session_state.vol_min = min(
            max(coerce_int(st.session_state.vol_min, vol_min_bound), vol_min_bound),
            vol_max_bound
        )
        st.session_state.vol_max = min(
            max(coerce_int(st.session_state.vol_max, vol_max_bound), st.session_state.vol_min),
            vol_max_bound
        )
        st.session_state.pos_min = min(
            max(coerce_int(st.session_state.pos_min, pos_min_bound), pos_min_bound),
            pos_max_bound
        )
        st.session_state.pos_max = min(
            max(coerce_int(st.session_state.pos_max, pos_max_bound), st.session_state.pos_min),
            pos_max_bound
        )
        
        with st.expander("🔍 Filtres avancés", expanded=True):
            # Création de 3 colonnes pour les filtres principaux
            col1, col2, col3 = st.columns([1, 1, 1])
            
            with col1:
                # Stratégie
                st.markdown("""
                    <h6 class="inline-filter-title">
                        Stratégie
                    </h6>
                """, unsafe_allow_html=True)
                strategies = [
                    'Sauvegarde', 'Quick Win', 'Opportunité',
                    'Potentiel', 'Conquête', 'Non positionné'
                ]
                selected_strategies = st.multiselect(
                    "Filtrer par stratégie",
                    options=strategies,
                    default=strategies,
                    key='strategy_filter',
                    label_visibility="collapsed"
                )
            
            with col2:
                # Marque
                st.markdown("""
                    <h6 class="inline-filter-title">
                        Marque
                    </h6>
                """, unsafe_allow_html=True)
                brand_options = ['Marque', 'Hors marque']
                selected_brands = st.multiselect(
                    "Filtrer par marque",
                    options=brand_options,
                    default=brand_options,
                    key='brand_filter',
                    label_visibility="collapsed"
                )
            
            with col3:
                # Intention
                st.markdown("""
                    <h6 class="inline-filter-title">
                        Intention
                    </h6>
                """, unsafe_allow_html=True)
                intent_options = ['Transactionnel', 'Informationnel', 'Commercial', 'Navigationnel', 'Autre']
                selected_intentions = st.multiselect(
                    "Filtrer par intention",
                    options=intent_options,
                    default=intent_options,
                    key='intent_filter',
                    label_visibility="collapsed"
                )

            # Création de 2 colonnes pour les métriques
            metric_col1, metric_col2 = st.columns([1, 1])
            
            with metric_col1:
                # Volume
                st.markdown("""
                    <h6 class="inline-filter-title">
                        Volume
                    </h6>
                """, unsafe_allow_html=True)
                vol_col1, vol_col2 = st.columns(2)
                with vol_col1:
                    volume_min = st.number_input(
                        "Min",
                        min_value=vol_min_bound,
                        max_value=vol_max_bound,
                        step=1,
                        key='vol_min'
                    )
                with vol_col2:
                    volume_max = st.number_input(
                        "Max",
                        min_value=st.session_state.vol_min,
                        max_value=vol_max_bound,
                        step=1,
                        key='vol_max'
                    )
            
            with metric_col2:
                # Position
                st.markdown("""
                    <h6 class="inline-filter-title">
                        Position
                    </h6>
                """, unsafe_allow_html=True)
                pos_col1, pos_col2 = st.columns(2)
                with pos_col1:
                    position_min = st.number_input(
                        "Min",
                        min_value=pos_min_bound,
                        max_value=pos_max_bound,
                        step=1,
                        key='pos_min'
                    )
                with pos_col2:
                    position_max = st.number_input(
                        "Max",
                        min_value=st.session_state.pos_min,
                        max_value=pos_max_bound,
                        step=1,
                        key='pos_max'
                    )

            base_filtered_df = filtered_df[
                (filtered_df['Stratégie'].isin(selected_strategies)) &
                (filtered_df['Marque'].isin(selected_brands)) &
                (filtered_df['Intention'].isin(selected_intentions)) &
                (filtered_df['Volume'].between(volume_min, volume_max)) &
                (filtered_df[client_position_col].fillna(0).between(position_min, position_max))
            ]

            if enable_ngram_clustering:
                ngram_view_df, cluster_options = add_ngram_clusters_to_view(
                    base_filtered_df,
                    custom_rules=keyword_equivalence_rules,
                    min_frequency=NGRAM_MIN_FREQUENCY,
                    max_options=NGRAM_MAX_FILTER_OPTIONS
                )

                active_cluster_selection = st.session_state.get('ngram_cluster_filter', [])
                valid_cluster_selection = [
                    cluster_label for cluster_label in active_cluster_selection
                    if cluster_label in cluster_options
                ]
                if valid_cluster_selection != active_cluster_selection:
                    st.session_state.ngram_cluster_filter = valid_cluster_selection

                st.markdown("""
                    <h6 class="inline-filter-title">
                        Cluster n-gram
                    </h6>
                """, unsafe_allow_html=True)
                selected_clusters = st.multiselect(
                    "Filtrer par cluster n-gram",
                    options=cluster_options,
                    key='ngram_cluster_filter',
                    label_visibility="collapsed",
                    help="Filtre la vue sur le cluster principal attribué à chaque keyword."
                )

        # Application des filtres avancés
        filtered_df = base_filtered_df
        if enable_ngram_clustering:
            filtered_df = ngram_view_df
            if selected_clusters:
                filtered_df = filtered_df[filtered_df['Cluster principal'].isin(selected_clusters)]

        if filtered_df.empty:
            st.info("Aucun keyword ne correspond aux filtres actuels.")
            return

        # Affichage des métriques
        st.markdown('<p class="subheader">📈 Synthèse des mots-clés</p>', unsafe_allow_html=True)
        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
        
        with metric_col1:
            st.metric("🎯 Total mots-clés", f"{len(filtered_df):,}")
        with metric_col2:
            st.metric("📊 Volume total", f"{int(filtered_df['Volume'].sum()):,}")
        with metric_col3:
            st.metric("📈 KD moyen", f"{round(filtered_df['KD'].mean(), 1)}")
        with metric_col4:
            st.metric("💰 CPC moyen", f"${round(filtered_df['CPC'].mean(), 2)}")

        # Création des onglets
        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 Résultats filtrés",
            "📈 Répartition par stratégie",
            "🔍 Visualisations",
            "⚡ Quick Win par URL"
        ])
        output_df = format_positions_for_output(filtered_df)
        
        with tab1:
            st.markdown("""
                <h6 class="inline-filter-title">
                    Recherche par keyword
                </h6>
            """, unsafe_allow_html=True)
            keyword_query = st.text_input(
                "Rechercher dans les keywords",
                placeholder="Ex : tesla model y, assurance habitation, pompe chaleur...",
                key='keyword_search',
                label_visibility="collapsed"
            ).strip()

            searched_output_df = output_df
            normalized_keyword_query = normalize_search_text(keyword_query)
            if normalized_keyword_query:
                query_terms = normalized_keyword_query.split()
                normalized_keywords = output_df['Keyword'].fillna('').astype(str).map(normalize_search_text)
                keyword_mask = normalized_keywords.apply(
                    lambda value: all(term in value for term in query_terms)
                )
                searched_output_df = output_df[keyword_mask]

            if searched_output_df.empty:
                st.info("Aucun keyword ne correspond à cette recherche.")
            else:
                display_results_dataframe(searched_output_df)
            export_data(searched_output_df, client_name)
            render_copy_to_clipboard_button(
                searched_output_df.to_csv(index=False, sep='\t'),
                "📋 Copier les résultats (TSV)",
                f"copy_results_{client_name}"
            )

        with tab2:
            display_strategy_stats(filtered_df)

        with tab3:
            display_visualizations(filtered_df, client_name)

        with tab4:
            display_quick_win_by_url(filtered_df, client_name)

    except Exception as e:
        st.error(f"❌ Erreur lors de l'affichage des résultats : {str(e)}")
        st.info("🔄 Essayez de relancer l'analyse")

def process_and_store_data(
    uploaded_files,
    client_name,
    nombre_sites,
    top_position,
    custom_brands,
    template_rules=None,
    enable_keyword_deduplication=False,
    keyword_equivalence_rules=''
):
    """Traitement des données avec validation améliorée"""
    try:
        if not uploaded_files:
            raise FileProcessingError("Aucun fichier n'a été téléchargé")
            
        # Traitement du fichier content gap
        for uploaded_file in uploaded_files:
            try:
                # Validation du format du fichier
                is_valid, error_msg = validate_file_format(uploaded_file.name)
                if not is_valid:
                    raise FileProcessingError(error_msg)

                # Lecture et traitement initial du fichier
                df = process_content_gap_file(uploaded_file)
                
                # Nettoyage des noms de domaines dans les en-têtes
                rename_dict = {}
                for col in df.columns:
                    if ': Position' in col or ': Traffic' in col or ': URL' in col:
                        domain = col.split(':')[0]
                        clean_domain = clean_domain_name(domain)
                        if domain != clean_domain:
                            new_col = col.replace(domain, clean_domain)
                            rename_dict[col] = new_col
                
                if rename_dict:
                    df = df.rename(columns=rename_dict)
                
                # Filtrage des résultats
                df_filtered = filter_results(df, nombre_sites, top_position)

                if enable_keyword_deduplication:
                    before_dedup_count = len(df_filtered)
                    df_filtered = deduplicate_keywords_by_normalized_key(
                        df_filtered,
                        clean_domain_name(client_name),
                        keyword_equivalence_rules
                    )
                    removed_count = before_dedup_count - len(df_filtered)
                    st.info(
                        f"🧹 Normalisation appliquée : {removed_count:,} variante(s) regroupée(s), "
                        f"{len(df_filtered):,} keyword(s) conservé(s)."
                    )
                
                # Ajout des colonnes d'analyse
                df_final = enrich_data(df_filtered, client_name, custom_brands, template_rules)
                
                # Stockage des résultats
                st.session_state.df_final = df_final
                st.session_state.analysis_done = True
                
                st.success(f"✅ Fichier traité avec succès : {uploaded_file.name}")
                return True
                
            except Exception as e:
                st.warning(f"⚠️ Erreur lors du traitement de {uploaded_file.name}: {str(e)}")
                continue

        raise AnalysisError("Aucun fichier n'a pu être traité correctement")

    except Exception as e:
        st.error(f"❌ Erreur lors de l'analyse : {str(e)}")
        return False

def filter_results(df, nombre_sites, top_position):
    """
    Filtre les résultats pour trouver les mots-clés où au moins X concurrents 
    sont positionnés dans le top Y des résultats Google
    
    Args:
        df: DataFrame avec les données
        nombre_sites: Nombre minimum de sites concurrents requis
        top_position: Position maximum à considérer
    """
    try:
        # Identification des colonnes de position
        position_columns = [col for col in df.columns if ': Position' in col]
        
        # Création d'une matrice booléenne pour les positions valides
        # Une position est valide si elle est > 0 ET <= top_position
        positions_valides = df[position_columns].apply(
            lambda x: (x > 0) & (x <= top_position)
        )
        
        # Compte le nombre de concurrents positionnés dans le top Y pour chaque mot-clé
        nb_concurrents_top_y = positions_valides.sum(axis=1)
        
        # Filtre les mots-clés où au moins X concurrents sont dans le top Y
        df_filtered = df[nb_concurrents_top_y >= nombre_sites]
        
        if len(df_filtered) == 0:
            raise DataValidationError(
                f"Aucun mot-clé n'a au moins {nombre_sites} "
                f"concurrent(s) dans le top {top_position}"
            )
            
        return df_filtered
        
    except Exception as e:
        raise AnalysisError(f"Erreur lors du filtrage : {str(e)}")

def enrich_data(df, client_name, custom_brands, template_rules=None):
    """Enrichit les données avec des colonnes d'analyse"""
    try:
        # Nettoyage du nom de domaine client
        client_domain = clean_domain_name(client_name)
        df = df.copy()
        
        # Ajout des colonnes d'analyse dans l'ordre correct
        known_intent_entities = build_known_intent_entities(client_name, custom_brands)
        df['Sélection'] = ''
        df['Stratégie'] = df.apply(lambda row: define_strategy(row, client_domain), axis=1)
        df['Marque'] = df['Keyword'].apply(lambda x: classify_branded(x, client_domain, custom_brands))
        df['Intention'] = df['Keyword'].apply(lambda x: classify_intent(x, known_intent_entities))
        df['Template'] = df.apply(lambda row: define_template(row, client_domain, template_rules), axis=1)
        
        # Calcul de la concurrence
        position_columns = [col for col in df.columns if ': Position' in col]
        df['Concurrence'] = df[position_columns].apply(lambda x: (x > 0).sum(), axis=1)
        
        # Réorganisation des colonnes
        audit_columns = [col for col in KEYWORD_AUDIT_COLUMNS if col in df.columns]
        column_order = [
            'Keyword', 'Sélection', 'Stratégie', 'Marque', 'Intention', 'Template',
            'Concurrence', 'Volume', 'KD', 'CPC', 'SERP features'
        ]
        
        # Ajout des colonnes spécifiques aux domaines
        for suffix in [': Position', ': URL', ': Traffic']:
            client_cols = [col for col in df.columns if client_domain + suffix in col]
            other_cols = [col for col in df.columns if suffix in col and client_domain not in col]
            column_order.extend(client_cols + sorted(other_cols))

        column_order.extend(audit_columns)

        return df[column_order]
        
    except Exception as e:
        raise DataValidationError(f"Erreur lors de l'enrichissement des données : {str(e)}")

def define_strategy(row, client_name):
    """Définit la stratégie SEO pour chaque mot-clé"""
    try:
        # Nettoyage du nom de domaine client
        client_domain = clean_domain_name(client_name)
        
        # Initialisation des variables
        client_position = row.get(f"{client_domain}: Position", 0)
        
        # Définition de la stratégie selon la position
        if client_position == 1:
            return "Sauvegarde"
        elif 2 <= client_position <= 5:
            return "Quick Win"
        elif 6 <= client_position <= 10:
            return "Opportunité"
        elif 11 <= client_position <= 20:
            return "Potentiel"
        elif client_position > 20:
            return "Conquête"
        else:
            return "Non positionné"
            
    except Exception as e:
        st.error(f"❌ Erreur lors de la définition de la stratégie : {str(e)}")
        return "Non défini"

def calculate_opportunity_score(volume, kd, position):
    """Calcule le score d'opportunité pour un mot-clé"""
    try:
        # Normalisation du volume (0-100)
        volume_score = min(volume / 1000, 100)
        
        # Normalisation de la difficulté (0-100)
        difficulty_score = 100 - min(kd, 100)
        
        # Normalisation de la position (0-100)
        position_score = 100 - min(position if position > 0 else 100, 100)
        
        # Calcul du score final (moyenne pondérée)
        final_score = (volume_score * 0.4) + (difficulty_score * 0.3) + (position_score * 0.3)
        
        return round(final_score, 2)
        
    except Exception as e:
        st.warning(f"⚠️ Erreur lors du calcul du score : {str(e)}")
        return 0

def display_strategy_stats(filtered_df):
    """Affiche les statistiques par stratégie"""
    try:
        # Définir l'ordre des stratégies
        strategy_order = [
            'Sauvegarde',    # Position 1
            'Quick Win',     # Positions 2-5
            'Opportunité',   # Positions 6-10
            'Potentiel',     # Positions 11-20
            'Conquête',      # Positions > 20
            'Non positionné' # Absent du top 100
        ]
        
        # Calcul des statistiques
        stats_df = filtered_df.groupby('Stratégie').agg({
            'Keyword': 'count',
            'Volume': 'sum',
            'KD': 'mean',
            'CPC': 'mean'
        })
        
        # Réorganisation selon l'ordre défini
        stats_df = stats_df.reindex(strategy_order)
        
        # Renommage des colonnes
        stats_df.columns = ['Nombre de mots-clés', 'Volume total', 'KD moyen', 'CPC moyen']
        
        # Normalisation des types en numérique pour éviter les régressions d'affichage
        stats_df['Nombre de mots-clés'] = stats_df['Nombre de mots-clés'].fillna(0).astype(int)
        stats_df['Volume total'] = stats_df['Volume total'].fillna(0).astype(int)
        stats_df['KD moyen'] = stats_df['KD moyen'].fillna(0).astype(float).round(1)
        stats_df['CPC moyen'] = stats_df['CPC moyen'].fillna(0).astype(float).round(2)
        
        # Calcul des totaux
        totals = pd.Series({
            'Nombre de mots-clés': int(stats_df['Nombre de mots-clés'].sum()),
            'Volume total': int(stats_df['Volume total'].sum()),
            'KD moyen': round(float(stats_df['KD moyen'].mean()), 1),
            'CPC moyen': round(float(stats_df['CPC moyen'].mean()), 2)
        }, name='Total')
        
        # Ajout de la ligne des totaux
        stats_df = pd.concat([stats_df, pd.DataFrame([totals])])
        stats_df['Nombre de mots-clés'] = stats_df['Nombre de mots-clés'].astype(int)
        stats_df['Volume total'] = stats_df['Volume total'].astype(int)
        stats_df['KD moyen'] = stats_df['KD moyen'].astype(float).round(1)
        stats_df['CPC moyen'] = stats_df['CPC moyen'].astype(float).round(2)
        
        # Affichage avec style
        st.markdown("### 📊 Répartition par stratégie")
        
        # Création du style pour le tableau
        styles = [
            dict(selector="th", props=[("font-size", "1.1em"), 
                                     ("text-align", "center"),
                                    ("background-color", "#27282A"),
                                     ("color", "#49DCBC"),
                                     ("font-weight", "bold"),
                                     ("padding", "12px")]),
            dict(selector="td", props=[("text-align", "center"),
                                     ("padding", "8px")]),
            dict(selector="tr:last-child", props=[("font-weight", "bold"),
                                                ("background-color", "#27282A")])
        ]
        
        # Application du style et affichage
        st.dataframe(
            stats_df,
            use_container_width=True,
            height=250,
            column_config={
                "Nombre de mots-clés": st.column_config.NumberColumn(format="%d"),
                "Volume total": st.column_config.NumberColumn(format="%d"),
                "KD moyen": st.column_config.NumberColumn(format="%.1f"),
                "CPC moyen": st.column_config.NumberColumn(format="%.2f")
            }
        )
        
    except Exception as e:
        st.error(f"❌ Erreur lors de l'affichage des statistiques : {str(e)}")

def display_visualizations(filtered_df, client_name):
    """Affiche les visualisations"""
    col1, col2, col3 = st.columns(3)
    
    # Configuration commune pour tous les graphiques
    graph_title_style = {
        'font': {'size': 16, 'family': 'Arial', 'color': '#F7F8F8'},
        'y': 0.95
    }
    graph_layout = {
        'title_font': graph_title_style['font'],
        'showlegend': True,
        'paper_bgcolor': '#27282A',
        'plot_bgcolor': '#27282A',
        'font': {'color': '#F7F8F8'},
        'margin': dict(t=50, b=30, l=30, r=30)
    }
    
    with col1:
        # Distribution des volumes par position
        fig_volume = create_position_volume_histogram(filtered_df, client_name)
        fig_volume.update_layout(
            title=dict(
                text='Distribution du volume de recherche par position',
                **graph_title_style
            ),
            **graph_layout
        )
        st.plotly_chart(fig_volume, use_container_width=True)
    
    with col2:
        # Répartition des stratégies
        strategy_order = ['Sauvegarde', 'Quick Win', 'Opportunité', 'Potentiel', 'Conquête', 'Non positionné']
        fig_strategies = px.pie(
            filtered_df,
            names='Stratégie',
            title='Répartition des stratégies',
            category_orders={'Stratégie': strategy_order}
        )
        fig_strategies.update_layout(
            title=dict(
                text='Répartition des stratégies',
                **graph_title_style
            ),
            **graph_layout
        )
        st.plotly_chart(fig_strategies, use_container_width=True)
    
    with col3:
        # Répartition des intentions
        fig_intentions = px.pie(
            filtered_df,
            names='Intention',
            title='Répartition des intentions de recherche'
        )
        fig_intentions.update_layout(
            title=dict(
                text='Répartition des intentions de recherche',
                **graph_title_style
            ),
            **graph_layout
        )
        st.plotly_chart(fig_intentions, use_container_width=True)

    cluster_summary_df = build_ngram_visualization_summary(filtered_df)
    if not cluster_summary_df.empty:
        st.markdown("### 🧩 Top clusters n-gram")
        fig_clusters = create_ngram_cluster_bar_chart(
            cluster_summary_df,
            graph_title_style=graph_title_style,
            graph_layout=graph_layout
        )
        st.plotly_chart(fig_clusters, use_container_width=True)

def export_data(filtered_df, client_name):
    """Export des données au format CSV"""
    export_col1, export_col2 = st.columns(2)
    with export_col1:
        st.download_button(
            "📥 Export CSV",
            filtered_df.to_csv(index=False),
            f"Analyse_Concurrentielle_{client_name}.csv",
            mime="text/csv",
            help="Télécharger les résultats au format CSV",
            type="primary"
        )
    with export_col2:
        st.download_button(
            "📥 Export JSON",
            dataframe_to_json_string(filtered_df),
            f"Analyse_Concurrentielle_{client_name}.json",
            mime="application/json",
            help="Télécharger les résultats au format JSON"
        )


def display_ahrefs_consolidation_view():
    """Affiche une vue indépendante de consolidation Ahrefs par URL."""
    st.markdown("## 🧱 Consolidation Ahrefs par URL")
    st.caption(
        "Vue isolée pour regrouper un export Ahrefs par URL : top mot-clé, volume total, "
        "position moyenne et liste des mots-clés associés."
    )

    uploaded_file = st.file_uploader(
        "Importer un export Ahrefs Organic Keywords ou Content Gap",
        type=['csv'],
        key='ahrefs_consolidation_file',
        help=(
            "Formats supportés : Current URL/Current position ou colonnes "
            "<domaine>: URL + <domaine>: Organic Position."
        )
    )

    if uploaded_file is None:
        st.info("Importez un export Ahrefs pour générer la consolidation par URL.")
        return

    try:
        cleaned_df = process_ahrefs_consolidation_file(uploaded_file)
        result_df = build_ahrefs_url_consolidation(cleaned_df)
    except Exception as error:
        st.error(f"Consolidation impossible : {error}")
        return

    if result_df.empty:
        st.warning("Aucune URL exploitable trouvée dans cet export.")
        return

    source_label = cleaned_df.attrs.get('source_label', 'Export Ahrefs')
    format_type = cleaned_df.attrs.get('format_type', 'unknown')
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("URLs consolidées", len(result_df))
    metric_col2.metric("Mots-clés analysés", len(cleaned_df))
    metric_col3.metric("Volume total", f"{int(result_df['Volume total'].sum()):,}".replace(',', ' '))
    st.caption(f"Source détectée : {source_label} · Format : {format_type}")

    st.dataframe(
        result_df,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={
            "URL": st.column_config.LinkColumn("URL", width="large"),
            "Top mot-clé": st.column_config.TextColumn("Top mot-clé", width="medium"),
            "Volume du top mot-clé": st.column_config.NumberColumn("Volume top KW", format="%d"),
            "Position moyenne": st.column_config.NumberColumn("Position moyenne", format="%.1f"),
            "Nb mots-clés": st.column_config.NumberColumn("Nb mots-clés", format="%d"),
            "Volume total": st.column_config.NumberColumn("Volume total", format="%d"),
            "Mots-clés": st.column_config.TextColumn("Mots-clés", width="large"),
        }
    )

    export_col1, export_col2 = st.columns(2)
    with export_col1:
        st.download_button(
            "📥 Télécharger CSV",
            result_df.to_csv(index=False, sep=';').encode('utf-8-sig'),
            "ahrefs_consolidation_url.csv",
            "text/csv",
            key="ahrefs_consolidation_csv"
        )
    with export_col2:
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            result_df.to_excel(writer, sheet_name='Consolidation URL', index=False)
            cleaned_df.to_excel(writer, sheet_name='Données nettoyées', index=False)
        st.download_button(
            "📥 Télécharger Excel",
            excel_buffer.getvalue(),
            "ahrefs_consolidation_url.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="ahrefs_consolidation_xlsx"
        )

def create_position_volume_histogram(filtered_df, client_name):
    """Crée un histogramme de distribution des volumes par position"""
    # Création des catégories de position
    def categorize_position(pos):
        if pd.isnull(pos) or pos == 0:
            return 'Non positionné'
        elif pos <= 3:
            return 'Top 3'
        elif pos <= 10:
            return 'Top 4-10'
        elif pos <= 20:
            return 'Top 11-20'
        else:
            return 'Top 21-100'

    # Ajout de la catégorie de position
    df_viz = filtered_df.copy()
    df_viz['Position_Category'] = df_viz[f'{client_name}: Position'].apply(categorize_position)
    
    # Calcul de la somme des volumes par catégorie avec le nom de colonne correct
    position_volume = df_viz.groupby('Position_Category')['Volume'].sum().reset_index()
    
    # Définir l'ordre personnalisé des catégories
    category_order = ['Top 3', 'Top 4-10', 'Top 11-20', 'Top 21-100', 'Non positionné']
    position_volume['Position_Category'] = pd.Categorical(
        position_volume['Position_Category'],
        categories=category_order,
        ordered=True
    )
    
    # Création du graphique
    fig_volume = px.bar(
        position_volume.sort_values('Position_Category'),
        x='Position_Category',
        y='Volume',
        title='Distribution du volume de recherche par position',
        labels={
            'Position_Category': 'Position',
            'Volume': 'Volume de recherche'
        }
    )
    
    # Personnalisation du graphique
    fig_volume.update_layout(
        title_font_size=20,
        title_font_family="Arial",
        plot_bgcolor='#27282A',
        paper_bgcolor='#27282A',
        font=dict(color='#F7F8F8'),
        bargap=0.2,
        margin=dict(t=50, b=50, l=50, r=25),
        xaxis=dict(
            title_font_size=14,
            tickfont_size=12,
            gridcolor='#37383A'
        ),
        yaxis=dict(
            title_font_size=14,
            tickfont_size=12,
            gridcolor='#37383A'
        )
    )
    
    # Couleurs personnalisées
    fig_volume.update_traces(
        marker_color=['#2ECC71', '#3498DB', '#F1C40F', '#E67E22', '#E74C3C']
    )
    
    return fig_volume

def add_contextual_help():
    """Ajoute des explications contextuelles dans l'interface"""
    with st.expander("ℹ️ Comment utiliser cet outil ?", expanded=False):
        st.markdown("""
        ### Processus en 4 étapes :

        1. **Préparation des données**
           - Exportez les données de vos outils SEO
           - Assurez-vous d'avoir les fichiers pour chaque concurrent
           - Nommez les fichiers avec le domaine (ex: monsite.csv)

        2. **Import et configuration**
           - Importez tous vos fichiers en une fois
           - Sélectionnez votre domaine client
           - Ajustez les paramètres d'analyse selon vos besoins

        3. **Analyse des résultats**
           - Utilisez les filtres pour affiner votre analyse
           - Examinez les différentes visualisations
           - Identifiez les opportunités prioritaires

        4. **Export et action**
           - Exportez les résultats filtrés
           - Utilisez les données pour votre stratégie SEO
           - Suivez l'évolution des positions
        """)

def add_metric_explanations():
    """Ajoute des explications pour chaque métrique"""
    with st.expander("📊 Comprendre les métriques", expanded=False):
        st.markdown("""
        ### Métriques principales

        #### 🎯 Stratégie
        - **Sauvegarde** : Mots-clés en position 1 - Focus sur la défense
        - **Quick Win** : Positions 2-5 - Potentiel de gain rapide
        - **Opportunité** : Positions 6-10 - Progression possible
        - **Potentiel** : Positions 11-20 - Travail à moyen terme
        - **Conquête** : Positions > 20 - Objectif long terme

        #### 📈 Métriques SEO
        - **Volume** : Nombre moyen de recherches mensuelles
        - **KD** : Score de difficulté (0-100)
        - **Position** : Position actuelle dans les résultats
        - **CPC** : Coût par clic moyen
        """)

def initialize_session_state():
    """Initialise les variables de session"""
    if 'df_final' not in st.session_state:
        st.session_state.df_final = None
    if 'analysis_done' not in st.session_state:
        st.session_state.analysis_done = False
    if 'enable_ngram_clustering' not in st.session_state:
        st.session_state.enable_ngram_clustering = False
    if 'ngram_cluster_filter' not in st.session_state:
        st.session_state.ngram_cluster_filter = []
    if 'keyword_equivalence_rules' not in st.session_state:
        st.session_state.keyword_equivalence_rules = ''
    if 'keyword_equivalence_preset' not in st.session_state:
        st.session_state.keyword_equivalence_preset = 'Aucun'

def clean_domain_name(domain: str) -> str:
    """Nettoie le nom de domaine en retirant www. et les slashes"""
    domain = domain.lower().strip()
    # Suppression du protocole (http:// ou https://)
    if '://' in domain:
        domain = domain.split('://')[-1]
    # Suppression du www.
    if domain.startswith('www.'):
        domain = domain[4:]
    # Suppression des slashes
    domain = domain.rstrip('/')
    return domain

def extract_domains_from_files(uploaded_files):
    """Extrait les domaines des fichiers téléchargés"""
    try:
        if not uploaded_files:
            return [], None
            
        # Lecture et traitement du fichier
        df = process_content_gap_file(uploaded_files[0])
        
        # Extraction des domaines depuis les colonnes de position
        domains = set()
        for col in df.columns:
            if ': Position' in col:
                domain = col.split(':')[0]
                clean_domain = clean_domain_name(domain)
                domains.add(clean_domain)
                
        return sorted(list(domains)), df
                
    except Exception as e:
        st.error(f"❌ Erreur lors de l'extraction des domaines : {str(e)}")
        return [], None

def validate_file_format(file_name: str) -> tuple[bool, str]:
    """Valide le format du fichier"""
    # Nettoyer le nom du fichier en retirant les tirets au début
    clean_name = file_name.lstrip('-')
    
    if not clean_name.endswith('.csv'):
        return False, "Le fichier doit être au format CSV"
    if "content-gap" not in clean_name:
        return False, "Le fichier doit être un export content gap"
    return True, ""

def main():
    """Fonction principale de l'application"""
    try:
        initialize_session_state()
        
        st.markdown(
            """
            <section class="tool-hero">
                <div class="tool-kicker">Content gap</div>
                <h1 class="tool-title">Analyse Content Gap</h1>
                <p class="tool-lead">
                    Priorise les opportunités SEO depuis des exports Ahrefs ou Semrush,
                    filtre les requêtes et consolide les quick wins par URL.
                </p>
            </section>
            """,
            unsafe_allow_html=True,
        )
        
        # Guide d'utilisation en dropdown dans la zone principale
        with st.expander("Guide d'utilisation", expanded=False):
            st.markdown("""
            ## 1. Import des données
            ### Formats acceptés :
            - **Ahrefs** : exports Content Gap / Organic Keywords
               - Encodage recommandé : UTF-16
               - Séparateur : tabulation
            - **Semrush** : exports Organic Research > Positions
               - Encodage recommandé : UTF-8
               - Séparateur : tabulation, virgule ou point-virgule

            ### Contraintes de fichier :
            - Extension `.csv`
            - Le nom du fichier doit contenir `content-gap`
            - Colonnes obligatoires : `Keyword`, `Volume`, `KD`, `CPC`, `SERP features`

            ## 2. Configuration
            - Sélectionnez le domaine client
            - Ajoutez vos termes de marque ou entités connues (optionnel)
            - Ajustez les règles `Template` via **Règles Template (URLs)** si besoin
            - Activez la **Normalisation des keywords** si vous souhaitez regrouper les variantes proches et garder le meilleur volume

            ## 3. Comprendre la colonne Intention
            - Le moteur d'intention utilise des signaux transversaux : achat/devis/prix, comparaison/avis, questions/aide, navigation vers une marque ou un service
            - Il n'est pas limité à une verticale : automobile, food, finance, santé, voyage, SaaS, local ou e-commerce
            - Les termes de marque ajoutés dans la configuration aident aussi à classer les requêtes exactes en `Navigationnel`

            ## 4. Comprendre la normalisation des keywords
            - La déduplication est optionnelle et désactivée par défaut
            - Elle regroupe les variantes prudentes : accents, singulier/pluriel, féminin/masculin simple, articles, tirets et ordre des mots
            - Un préchargement thématique facultatif permet d'ajouter quelques équivalences sûres par univers métier
            - Les équivalences personnalisées permettent de gérer abréviations, concaténations et fautes fréquentes
            - Les colonnes `Keyword normalisé`, `Nb variantes regroupées` et `Variantes regroupées` auditent les regroupements

            ## 5. Comprendre les clusters n-gram
            - La catégorisation n-gram est optionnelle et désactivée par défaut
            - Elle calcule des bi-grams et tri-grams sur la vue déjà filtrée pour repérer les clusters de contenu connexes
            - Le filtre `Cluster n-gram` s'appuie sur le `Cluster principal` et n'impacte pas la recherche keyword au-dessus du tableau
            - Les colonnes `Cluster principal`, `Type cluster` et `Fréquence cluster` n'apparaissent que si la fonctionnalité est active
            - L'onglet `Visualisations` affiche aussi les clusters les plus fréquents quand la fonctionnalité est active

            ## 6. Comprendre la colonne Template
            - Le template est estimé automatiquement à partir des **3 meilleures URLs** (vote majoritaire)
            - Valeurs possibles : `Contenu`, `Produit`, `Catégorie`, `Autre`
            - Exemple `Contenu` : URLs contenant `/blog/`, `/actualite/`, `/actualites/`

            ## 7. Lancer et exploiter l'analyse
            - Cliquez sur **Lancer l'analyse**
            - Filtrez les opportunités par stratégie, marque, intention, volume, position, cluster n-gram ou recherche par keyword
            - Exportez le CSV final
            """)

        with st.expander("Consolidation Ahrefs par URL", expanded=False):
            display_ahrefs_consolidation_view()
        
        # Configuration dans la sidebar
        with st.sidebar:
            st.header("Configuration")
            
            uploaded_files = st.file_uploader(
                "Importer les fichiers CSV",
                accept_multiple_files=True,
                type=['csv'],
                help="Supporte Ahrefs/Semrush avec UTF-16 ou UTF-8 (séparateur tabulation, virgule ou point-virgule)"
            )

            if uploaded_files:
                try:
                    domains, df = extract_domains_from_files(uploaded_files)
                    if df is None:
                        st.warning("⚠️ Aucun domaine n'a pu être extrait des noms de fichiers")
                    else:
                        client_name = st.selectbox(
                            "🎯 Sélectionner le client",
                            options=domains,
                            help="Sélectionnez le domaine correspondant au client"
                        )
                        
                        # Termes de marque
                        brand_terms = st.text_input(
                            "🔤 Termes de marque / entités connues (séparés par des virgules)",
                            help="Ajoutez les variations de marque, produits, sites ou entités clés. Elles servent à la colonne Marque et aux requêtes navigationnelles exactes."
                        )
                        custom_brands = [t.strip() for t in brand_terms.split(',')] if brand_terms else []

                        with st.expander("🧩 Règles Template (URLs)", expanded=False):
                            content_markers_input = st.text_input(
                                "Marqueurs Contenu",
                                value=", ".join(DEFAULT_TEMPLATE_MARKERS['content']),
                                help="Ex: blog, actualite, actualites, guide"
                            )
                            product_markers_input = st.text_input(
                                "Marqueurs Produit",
                                value=", ".join(DEFAULT_TEMPLATE_MARKERS['product']),
                                help="Ex: produit, product, item, fiche-produit"
                            )
                            category_markers_input = st.text_input(
                                "Marqueurs Catégorie",
                                value=", ".join(DEFAULT_TEMPLATE_MARKERS['category']),
                                help="Ex: categorie, collection, boutique, shop"
                            )
                        template_rules = build_template_rules(
                            content_markers_input,
                            product_markers_input,
                            category_markers_input
                        )

                        with st.expander("🧹 Normalisation des keywords", expanded=False):
                            enable_keyword_deduplication = st.checkbox(
                                "Activer la normalisation/déduplication",
                                value=False,
                                key='enable_keyword_deduplication',
                                help=(
                                    "Regroupe les variantes proches et conserve le keyword avec le plus fort volume. "
                                    "La fonctionnalité est désactivée par défaut pour préserver les analyses historiques."
                                )
                            )
                            st.selectbox(
                                "Préchargement thématique",
                                options=list(KEYWORD_EQUIVALENCE_PRESETS.keys()),
                                key='keyword_equivalence_preset',
                                help=(
                                    "Ajoute un petit socle d'équivalences sûres par thématique. "
                                    "Optionnel et sans effet tant que la normalisation ou les clusters n-gram "
                                    "ne sont pas activés."
                                )
                            )
                            keyword_equivalence_rules = st.text_area(
                                "Équivalences personnalisées",
                                value="",
                                key='keyword_equivalence_rules',
                                placeholder="rh=ressources humaines\nsav=service après-vente\nreferencement=référencement",
                                help=(
                                    "Une règle par ligne, au format forme canonique=variante. "
                                    "Exemple : rh=ressources humaines."
                                ),
                                height=120,
                                disabled=not (
                                    enable_keyword_deduplication or
                                    st.session_state.get('enable_ngram_clustering', False)
                                )
                            )

                        with st.expander("🧩 Clusters n-gram", expanded=False):
                            st.checkbox(
                                "Activer la catégorisation n-gram",
                                value=False,
                                key='enable_ngram_clustering',
                                help=(
                                    "Calcule des bi-grams et tri-grams sur la vue filtrée courante pour identifier "
                                    "les clusters de contenu connexes. La fonctionnalité reste désactivée par défaut "
                                    "pour éviter toute régression sur les analyses existantes."
                                )
                            )

                        effective_keyword_equivalence_rules = merge_keyword_equivalence_rules(
                            keyword_equivalence_rules,
                            st.session_state.get('keyword_equivalence_preset', 'Aucun')
                        )
                        
                        # Paramètres avancés
                        st.subheader("📊 Paramètres d'analyse")
                        nombre_sites = st.number_input(
                            "Nombre minimum de sites", 
                            min_value=1, 
                            value=1,
                            help="Nombre minimum de sites concurrents positionnés"
                        )
                        top_position = st.number_input(
                            "Position maximum", 
                            min_value=1, 
                            value=20,
                            help="Position maximum à prendre en compte"
                        )

                        # Bouton d'action
                        st.markdown("---")
                        if client_name:
                            if st.button("Lancer l'analyse", type="primary"):
                                process_and_store_data(
                                    uploaded_files,
                                    client_name,
                                    nombre_sites,
                                    top_position,
                                    custom_brands,
                                    template_rules,
                                    enable_keyword_deduplication,
                                    effective_keyword_equivalence_rules
                                )
                except Exception as e:
                    st.error(f"❌ Erreur lors de la configuration : {str(e)}")
            else:
                st.info("ℹ️ Commencez par importer vos fichiers d'analyse")

        # Affichage des résultats si disponibles
        if st.session_state.analysis_done and st.session_state.df_final is not None:
            try:
                display_filtered_results(st.session_state.df_final, client_name)
            except Exception as e:
                st.error(f"❌ Erreur lors de l'affichage des résultats : {str(e)}")
                st.info("🔄 Essayez de relancer l'analyse")

    except Exception as e:
        st.error(f"❌ Erreur système critique : {str(e)}")
        st.info("""
        🔧 Solutions possibles :
        1. Rafraîchissez la page
        2. Vérifiez vos fichiers d'entrée
        3. Contactez le support technique si l'erreur persiste
        """)

if __name__ == "__main__":
    main() 
