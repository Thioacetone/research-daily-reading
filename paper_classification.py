"""Evidence-backed subjects shared by the reader and the publication gate.

Search lanes are discovery hints, never reviewed classifications. Human-reviewed
DOI/title pairs take precedence; new papers need two agreeing full-text decisions.
"""
import hashlib
import html
import json
from functools import lru_cache
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote

VERSION = 'original-evidence-subject-v1'
REGISTRY = Path(__file__).with_name('reviewed_classifications.json')
EXTRA_LABELS = {
    'cheminformatics': '化学信息学与分子机器学习',
    'structural-biology': '结构生物学与生物能量学',
    'computational-structural-biology': '计算结构生物学与分子相互作用',
    'biophysical': '生物物理化学与分子凝聚',
    'cancer-biology': '肿瘤生物学与免疫治疗',
    'medical-education': '医学教育与放射安全',
    'diagnostic-imaging': '临床核医学与分子影像',
    'microbial-ecology': '微生物生态学',
    'drug-delivery': '药物递送与制剂',
    'bioactive-peptides': '生物活性肽与作用机制',
    'spatial-proteomics': '空间蛋白质组学与质谱分析',
    'radiopharmaceuticals': '放射性药物与靶向治疗',
    'digital-mental-health': '数字心理健康与心理治疗',
}
EXTRA_ENGLISH = {
    'cheminformatics':'Cheminformatics and molecular machine learning',
    'structural-biology':'Structural biology and bioenergetics',
    'computational-structural-biology':'Computational structural biology and molecular interactions',
    'biophysical':'Biophysical chemistry and biomolecular condensation',
    'cancer-biology':'Cancer biology and immunotherapy',
    'medical-education':'Medical education and radiation safety',
    'diagnostic-imaging':'Clinical nuclear medicine and molecular imaging',
    'microbial-ecology':'Microbial ecology',
    'drug-delivery':'Drug delivery and formulation',
    'bioactive-peptides':'Bioactive peptides and mechanisms of action',
    'spatial-proteomics':'Spatial proteomics and mass spectrometry',
    'radiopharmaceuticals':'Radiopharmaceuticals and targeted therapy',
    'digital-mental-health':'Digital mental health and psychotherapy',
    'other':'Subject pending review',
}


def doi_key(value):
    return re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '',
                  unquote(str(value or '')).strip().casefold())


def title_key(value):
    value = re.split(r'[†‡]|electronic supplementary information', value or '', flags=re.I)[0]
    value = re.sub(r'<[^>]+>', '', html.unescape(html.unescape(value)))
    return re.sub(r'[^\w]+', '', unicodedata.normalize('NFKC', value).casefold())


def item_title(item):
    return item.get('paper_title') or item.get('title') or ''


@lru_cache(maxsize=2)
def _registry(stamp):
    try:
        value = json.loads(REGISTRY.read_text(encoding='utf-8'))
        return value['papers'] if value.get('version') == VERSION else {}
    except (OSError, ValueError, KeyError):
        return {}


def registry():
    try:
        info=REGISTRY.stat()
        return _registry((info.st_mtime_ns,info.st_size))
    except OSError:
        return {}


def reviewed(item):
    row = registry().get(doi_key(item.get('doi')))
    if row and title_key(item_title(item)) == row.get('title_key'):
        return row
    return None


def semantic_issue(direction, title, original):
    """High-precision traps; these checks do not replace the full-text editor."""
    text = (title + '\n' + original).casefold()
    title = title.casefold()
    if direction == 'neuropharmacology' and re.search(r'psychotherapy|text messages?|email', title) and not re.search(
            r'antidepressant|drug|pharmacolog|psychoplastogen|psychedelic|receptor', title):
        return 'Digital psychotherapy without a pharmacological contribution is not drug research'
    if direction == 'catalysis' and re.search(r'variational eigenvalue|quantum processor|quantum eigensolver', title):
        return 'A quantum-computing algorithm is theoretical chemistry, not catalysis'
    if direction == 'neuropharmacology' and not re.search(
            r'antidepress|depressive disorder|depression treatment|treatment.{0,35}depression|'
            r'psychedelic|psychoplastogen|hallucinogen|neural plasticity|behavioral antidepress|behavioural antidepress', text):
        return 'No central antidepressant or neuroplasticity pharmacology evidence'
    if direction == 'protein-degradation' and not re.search(
            r'targeted (?:protein )?degradation|protein degrad(?:ation|er)|proteolysis.targeting|'
            r'protac|lytac|molecular glue|lysosome.targeting chim', text):
        return 'Protein structure or generic degradation is not targeted protein degradation'
    if direction == 'chemical-probes' and not re.search(
            r'chemical probe|chemoproteom|covalent ligand|activity.based (?:probe|protein)|'
            r'bioorthogonal|reactivity profil', text):
        return 'No chemical-probe method or biological target-profiling evidence'
    if direction == 'cadd-aidd' and not re.search(
            r'drug discover|drug design|drug development|virtual screen|pharmacokinetic|'
            r'pharmacolog|protein.ligand|binding affinit|medicinal chem', text):
        return 'Generic machine learning is not computational drug discovery'
    if re.search(r'educational evaluation|students.{0,20}learning|training module', title):
        return 'Medical education is outside substantive chemistry research'
    if re.search(r'colonization patterns of.*microbial communities', title):
        return 'Microbial community ecology is not environmental chemistry'
    return ''


def decision_issue(response, ids):
    if len(response.get('focus', '')) < 40:
        return 'Explain the actual main scientific contribution'
    evidence = response.get('evidence_ids', [])
    if len(set(evidence)) < 2 or not set(evidence) <= set(ids):
        return 'Use at least two supplied original paragraph IDs'
    return ''


def make_audit(item, first, second, paragraphs, abstract):
    """Called only after both decisions agree and original evidence was checked."""
    sources = {p['id']: p['text'] for p in paragraphs}
    evidence = sorted(set(first['evidence_ids']) | set(second['evidence_ids']))
    return {
        'version': VERSION, 'doi': doi_key(item['doi']),
        'title_key': title_key(item_title(item)), 'fulltext_sha256': item['fulltext_sha256'],
        'direction': first['research_direction'], 'eligible': True,
        'decisions': [{'direction': d['research_direction'],
                       'focus': d.get('focus') or d.get('assessment', ''),
                       'evidence_ids': d['evidence_ids']} for d in (first, second)],
        'evidence': [{'id': key, 'text': sources[key][:500]} for key in evidence],
        'abstract': abstract,
        'abstract_sha256': hashlib.sha256(abstract.encode()).hexdigest(),
    }


def checked_audit(item):
    a = item.get('classification_audit')
    if not isinstance(a, dict) or a.get('version') != VERSION:
        return None
    if (a.get('doi') != doi_key(item.get('doi')) or
            a.get('title_key') != title_key(item_title(item)) or
            not re.fullmatch(r'[a-f0-9]{64}', a.get('fulltext_sha256', '')) or
            a.get('fulltext_sha256') != item.get('fulltext_sha256') or a.get('eligible') is not True):
        return None
    decisions = a.get('decisions', [])
    sources = {r.get('id'): r.get('text') for r in a.get('evidence', []) if isinstance(r, dict)}
    if len(decisions) != 2 or len(sources) < 2 or not all(isinstance(t, str) and len(t) >= 30 for t in sources.values()):
        return None
    if a.get('direction') != item.get('research_direction'):
        return None
    for d in decisions:
        if (not isinstance(d, dict) or d.get('direction') != a['direction'] or
                len(d.get('focus', '')) < 40 or
                len(set(d.get('evidence_ids', []))) < 2 or not set(d['evidence_ids']) <= set(sources)):
            return None
    abstract = a.get('abstract', '')
    if hashlib.sha256(abstract.encode()).hexdigest() != a.get('abstract_sha256'):
        return None
    if semantic_issue(a['direction'], item_title(item), abstract + '\n' + '\n'.join(sources.values())):
        return None
    return a


def classification(item):
    return reviewed(item) or checked_audit(item)


def classification_ready(item):
    row = classification(item)
    return bool(row and row.get('eligible') is True and row.get('direction'))


def display_direction(item):
    row = classification(item)
    return (row.get('display_direction') or row.get('direction') or 'other') if row else 'other'


CLASSIFIER_RULES = (
    'Classify the CENTRAL contribution using ONLY the original article, never the search query, '
    'future possibilities, citations or journal prestige. Use out-of-scope for education, clinical '
    'grading or descriptive ecology without substantive chemistry. Protein structure is not targeted '
    'protein degradation; isotope-labelled metal complexes are not biological chemical probes; '
    'depression of a cell ratio is not depressive illness; neuroendocrine cancer is not depression; '
    'generic molecular ML is interdisciplinary/cheminformatics, not automatically drug discovery. '
    'Digital psychotherapy without drug development is out-of-scope, even when depression is an outcome. '
    'Quantum eigenvalue-solving algorithms belong to theoretical chemistry, not catalysis. '
    'Drug delivery/formulation belongs to drug-discovery; electrochemical reaction development to '
    'electrochemistry; chemical analysis/metabolomics to analytical. Chemical biology needs a '
    'chemical method that interrogates or perturbs biology. Assign one main direction based on the '
    'actual question, methods and results. Cite at least two original paragraph IDs. '
)
