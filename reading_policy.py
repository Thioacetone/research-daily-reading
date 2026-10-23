"""Daily chemistry selection: persistent identity, breadth, and explicit quotas."""
from collections import Counter, defaultdict
import re
import unicodedata
from urllib.parse import unquote

POLICY_VERSION='chemistry-ten-diverse-v1'
DAILY_COUNT=10
MIN_PRIORITY=5
MAX_PER_DIRECTION=3
DIRECTIONS={
 'chemical-biology':'化学生物学',
 'cadd-aidd':'CADD/AIDD 与计算药物发现',
 'drug-discovery':'药物研发与应用',
 'neuropharmacology':'抑郁症治疗与药物研发',
 'interdisciplinary':'化学与其他学科交叉',
 'organic':'有机化学', 'inorganic':'无机与配位化学',
 'physical':'物理化学', 'analytical':'分析化学',
 'polymer':'高分子化学', 'materials':'材料化学',
 'catalysis':'催化化学', 'electrochemistry':'电化学',
 'energy':'能源化学', 'environmental':'环境与绿色化学',
 'theoretical':'理论与计算化学', 'supramolecular':'超分子化学',
 'chemical-engineering':'化学工程与分离',
 'geochemistry':'地球与宇宙化学', 'nuclear':'核化学与放射化学',
}
PRIORITY=frozenset(('chemical-biology','cadd-aidd','drug-discovery','neuropharmacology','interdisciplinary'))
ALIASES={'bioorthogonal':'chemical-biology','chemical-probes':'chemical-biology',
         'protein-degradation':'chemical-biology','depression-treatment':'neuropharmacology',
         'medicinal':'drug-discovery','drug-delivery':'drug-discovery'}
QUERIES={
 'chemical-biology':'"chemical biology" OR bioorthogonal OR chemoproteomics OR "targeted protein degradation"',
 'cadd-aidd':'"virtual screening" OR "computer aided drug" OR ("deep learning" AND "drug discovery")',
 'drug-discovery':'"drug discovery" OR "drug delivery" OR "medicinal chemistry" OR "target engagement"',
 'neuropharmacology':'antidepressant OR (depression AND (drug OR receptor OR treatment))',
 'interdisciplinary':'"chemical robotics" OR "molecular computing" OR "chemical neuroscience" OR "bioelectronics"',
 'organic':'"organic synthesis" OR "enantioselective synthesis" OR "C-H functionalization"',
 'inorganic':'"inorganic chemistry" OR "coordination chemistry" OR organometallic',
 'physical':'"physical chemistry" OR "reaction dynamics" OR "ultrafast spectroscopy"',
 'analytical':'"analytical chemistry" OR "mass spectrometry" OR "chemical sensing"',
 'polymer':'"polymer chemistry" OR "controlled polymerization" OR "polymer recycling"',
 'materials':'"materials chemistry" OR "metal organic framework" OR "covalent organic framework"',
 'catalysis':'catalysis OR photocatalysis OR "catalytic mechanism"',
 'electrochemistry':'electrochemistry OR electrocatalysis OR electrosynthesis',
 'energy':'"battery chemistry" OR "solar fuel" OR "carbon dioxide conversion"',
 'environmental':'"environmental chemistry" OR "green chemistry" OR "pollutant degradation"',
 'theoretical':'"theoretical chemistry" OR "quantum chemistry" OR "molecular simulation"',
 'supramolecular':'"supramolecular chemistry" OR "molecular recognition" OR "molecular machine"',
 'chemical-engineering':'"chemical engineering" OR "membrane separation" OR "flow chemistry"',
 'geochemistry':'geochemistry OR astrochemistry OR "prebiotic chemistry"',
 'nuclear':'radiochemistry OR "nuclear chemistry" OR radiopharmaceutical',
}


class PolicyError(ValueError):
    pass


def identity_keys(item):
    keys=set()
    doi=unquote(str(item.get('doi') or '')).strip().casefold()
    doi=re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)','',doi)
    if doi:keys.add('doi:'+doi)
    title=item.get('paper_title') or item.get('title') or item.get('title_zh') or ''
    title=re.sub(r'[^\w]+','',unicodedata.normalize('NFKC',title).casefold())
    if title:keys.add('title:'+title)
    if not keys:raise PolicyError('Paper has no stable identity')
    return keys


def direction(item):
    from paper_classification import classification
    verified=classification(item)
    if verified is not None:
        return verified.get('direction','') if verified.get('eligible') else ''
    # This fallback routes discoveries only. Publication must also call quality,
    # which rejects every unreviewed subject, including old cached editorials.
    declared=item.get('research_direction','')
    result=ALIASES.get(declared,declared)
    return result if result in DIRECTIONS else ''


def history_identities(reports, except_day=None):
    used=set()
    for report in reports:
        day=report.get('recommendation_date') or report.get('date')
        if except_day is not None and day==except_day:continue
        for section in report.get('sections',{}).values():
            for item in section.get('items',[]):used.update(identity_keys(item))
    return used


def validate_daily(items, used=(), quality_check=None):
    if len(items)!=DAILY_COUNT:raise PolicyError('Daily reading must contain exactly 10 papers')
    seen=set(used);counts=Counter();priority=0
    for item in items:
        keys=identity_keys(item)
        if keys & seen:raise PolicyError('Paper has already been recommended or is duplicated within the issue')
        seen.update(keys)
        main=direction(item)
        if not main:raise PolicyError('A verified main research direction is required')
        counts[main]+=1
        priority+=main in PRIORITY
        if quality_check is not None and not quality_check(item):raise PolicyError('Full-text editorial quality check failed')
    if max(counts.values())>MAX_PER_DIRECTION:raise PolicyError('A main direction exceeds three papers')
    if priority<MIN_PRIORITY:raise PolicyError('At least five papers must belong to priority areas')
    return {'papers':len(items),'priority_papers':priority,'directions':dict(counts),'policy_version':POLICY_VERSION}


def choose_daily(candidates, used=(), fixed=(), quality_check=None):
    """Select whole groups with DP; a failed early choice cannot monopolize a day."""
    used=set(used);seen=set(used);groups=defaultdict(list)
    fixed=list(fixed)
    fixed_counts=Counter();base_priority=0
    for item in fixed:
        keys=identity_keys(item);main=direction(item)
        if keys & seen or not main:raise PolicyError('Reserved selection conflicts with persistent history')
        seen.update(keys);fixed_counts[main]+=1;base_priority+=main in PRIORITY
        if quality_check and not quality_check(item):raise PolicyError('Reserved paper is incomplete')
    if len(fixed)>DAILY_COUNT or any(n>MAX_PER_DIRECTION for n in fixed_counts.values()):
        raise PolicyError('Reserved selection exceeds a daily quota')
    for item in candidates:
        keys=identity_keys(item);main=direction(item)
        if keys & seen or not main or (quality_check and not quality_check(item)):continue
        seen.update(keys);groups[main].append(item)
    # Within a direction, retain the editorial/candidate ranking, never invent scores.
    states={(len(fixed),min(MIN_PRIORITY,base_priority)):(len(fixed_counts),list(fixed))}
    for main in DIRECTIONS:
        lane=groups.get(main,[])[:MAX_PER_DIRECTION-fixed_counts[main]]
        new={}
        for (n,p),(breadth,chosen) in states.items():
            for count in range(min(len(lane),DAILY_COUNT-n)+1):
                key=(n+count,min(MIN_PRIORITY,p+(count if main in PRIORITY else 0)))
                value=(breadth+int(count>0 and not fixed_counts[main]),chosen+lane[:count])
                if key not in new or value[0]>new[key][0]:new[key]=value
        states=new
    result=states.get((DAILY_COUNT,MIN_PRIORITY))
    if not result:raise PolicyError('Insufficient new qualified papers for the 10/5/3 quotas; no repeat fallback allowed')
    validate_daily(result[1],used,quality_check)
    return result[1]
