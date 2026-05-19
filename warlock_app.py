"""
🔮 TBC Warlock DPS Analyzer — Streamlit App
Kører på localhost via: streamlit run warlock_app.py

Features:
  • Boss-rankings og percentiler for din karakter
  • Spell breakdown med curse-gruppe analyse (CoR = Gruppe 1, CoE/CoA/CoD = Gruppe 2)
  • Hit cap analyse baseret på Shadow Bolt miss rate + aktive hit-buffs i gruppen
  • Gruppe-buff detektion: hvilke vigtige TBC-buffs var aktive i dit fight
  • Top 100 world sammenligning: curse-brug og DPS-benchmark for din spec
  • Spec guide med rotation, tips og typiske fejl for alle tre specs
"""

import base64
import time
from typing import Optional

import requests
import streamlit as st

# ─── Side-config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TBC Warlock DPS Analyzer",
    page_icon="🔮",
    layout="wide",
)

# ═══════════════════════════════════════════════════════════════════════════════
# VIDENSBASE
# ═══════════════════════════════════════════════════════════════════════════════

# ── Curse grupper ──────────────────────────────────────────────────────────────
CURSE_GROUP_1 = ["Curse of Recklessness"]                           # Fysisk armor-debuff
CURSE_GROUP_2 = ["Curse of the Elements", "Curse of Agony", "Curse of Doom"]  # Magic/DPS

CURSE_DESCRIPTIONS = {
    "Curse of Recklessness": "Reducerer fjendens armor med 800. Gruppe 1 – Fysisk armor-debuff. Hjælper melee og fysisk DPS.",
    "Curse of the Elements":  "+10% magic damage taget af målet. Gruppe 2 – Raid magic-buff. Kraftigst i caster-heavy raids.",
    "Curse of Agony":         "DoT-curse, 24 sekunders varighed. Gruppe 2 – Personlig DPS. Bedst på fights <24s.",
    "Curse of Doom":          "Stor enkelt hit efter 60s. Gruppe 2 – Personlig DPS. Bedst på bosses >24s.",
    "Curse of Weakness":      "Reducerer fjendens angrebskraft. Oftest ikke brugt af DPS-Warlocks.",
}

# ── Hit cap konstanter ─────────────────────────────────────────────────────────
HIT_CAP_BASE     = 202   # hit rating for 16% spell hit (standard cap mod level 73 boss)
HIT_PCT_PER_RATING = 12.62  # hit rating pr. 1% spell hit ved level 70

# Buffs der reducerer dit effektive hit cap (navn → % spell hit givet)
HIT_GIVING_BUFFS = {
    "Inspiring Presence": 1.0,   # Draenei racial — alle i party får +1% spell hit
    "Totem of Wrath":     3.0,   # Enhancement Shaman talent — +3% spell hit + 3% crit
}

# ── Vigtige raid-buffs at vise i UI ────────────────────────────────────────────
RAID_BUFF_LIST = [
    # (Navn i WCL-logs,           Emoji, Kort beskrivelse)
    ("Inspiring Presence",        "🎯", "+1% spell hit  ·  Draenei racial"),
    ("Totem of Wrath",            "🎯", "+3% spell hit + 3% spell crit  ·  Enh. Shaman"),
    ("Wrath of Air Totem",        "✨", "+101 spell damage  ·  Resto Shaman"),
    ("Arcane Brilliance",         "🧠", "+31 Int  ·  Mage"),
    ("Arcane Intellect",          "🧠", "+31 Int  ·  Mage (gruppe)"),
    ("Greater Blessing of Kings", "👑", "+10% alle stats  ·  Paladin"),
    ("Blessing of Kings",         "👑", "+10% alle stats  ·  Paladin"),
    ("Greater Blessing of Wisdom","💧", "+41 mana/5s  ·  Paladin"),
    ("Blessing of Wisdom",        "💧", "+41 mana/5s  ·  Paladin"),
    ("Prayer of Spirit",          "🕊️", "+50 Spirit  ·  Priest"),
    ("Divine Spirit",             "🕊️", "+50 Spirit  ·  Priest"),
    ("Moonkin Aura",              "🌙", "+5% spell crit  ·  Balance Druid"),
    ("Power Infusion",            "⚡", "+20% spell haste  ·  Discipline Priest"),
    ("Heroism",                   "🔥", "+30% cast speed  ·  Shaman (Horde)"),
    ("Bloodlust",                 "🔥", "+30% cast speed  ·  Shaman (Alliance)"),
    ("Demonic Pact",              "🔮", "Spell power buff  ·  Demonology Warlock"),
    ("Shadow Weaving",            "🌑", "+10% shadow dmg  ·  Shadow Priest debuff på boss"),
]

RAID_BUFF_NAMES = {b[0] for b in RAID_BUFF_LIST}

# ── Spec guides ────────────────────────────────────────────────────────────────
SPECS = {
    "Affliction 💜": {
        "wcl_name": "Affliction",
        "color": "#c27be8",
        "description": "UA Lock – DoT-fokuseret, stærk sustained damage på lange fights",
        "rotation": [
            "Pre-cast Shadow Bolt inden pull",
            "Curse (Gruppe 2): CoD på boss >24s / CoA på adds og trash",
            "Unstable Affliction → refresh når <1.5s tilbage",
            "Corruption → aldrig lad det falde af",
            "Shadow Bolt som filler",
            "Dark Pact (Felhunter) / Life Tap ved <50% mana",
            "Drain Soul ved boss <25% HP  ·  bonus dmg + shard",
        ],
        "tips": [
            ("🎯 Hit Rating",          "164 hit med 3/3 Suppression (ellers 202) – tjek din effektive cap!"),
            ("💜 Corruption",          "95%+ uptime – din vigtigste DoT pr. GCD"),
            ("🌀 Unstable Affliction", "Refresh ved <1.5s – ikke for tidligt, ikke for sent"),
            ("☠️ Curse-valg",          "Gruppe 1 (CoR): kun fysisk-tunge raids uden armor debuff  ·  Gruppe 2: CoE hvis ingen anden lock dækker det, ellers CoD (>24s) / CoA (<24s)"),
            ("🔋 Dark Pact",           "Tap Felhunter for gratis mana – undgå Life Tap spam"),
            ("📣 Amplify Curse",       "Brug Amplify Curse inden du caster din curse"),
            ("🐾 Felhunter",           "Bedste pet: Spell Lock interrupt + Shadow Bite damage"),
        ],
        "mistakes": [
            "❌ Corruption falder af – din største DPS-synder",
            "❌ UA clippes for tidligt (ny UA casts med >2s tilbage af gammel)",
            "❌ Curse of Agony på boss med >24s fight time (CoD er bedre)",
            "❌ Life Tap spam til 0 mana i stedet for Dark Pact",
            "❌ Glemmer Shadow Bolt som filler",
        ],
    },
    "Destruction 🔥": {
        "wcl_name": "Destruction",
        "color": "#e85454",
        "description": "Destro / SM-Ruin – Shadow Bolt spam med ISB-stacks og DoT-support",
        "rotation": [
            "Pre-cast Shadow Bolt 1.5s inden pull-timer",
            "Immolate → hold oppe konstant (ISB-procs kræver det)",
            "Corruption (ja, selv som Destro – DPS-positivt!)",
            "Curse (Gruppe 2): CoE hvis ingen dækker det, ellers CoD/CoA",
            "Shadow Bolt spam som filler",
            "Conflagrate på cooldown (hvis specced)",
            "Life Tap / Mana Potion ved <30% mana",
        ],
        "tips": [
            ("🎯 Hit Rating",          "202 hit rating (16%) er dit cap – altid første prioritet"),
            ("⚡ ISB",                  "5-stack Improved Shadow Bolt >80% uptime på kampen"),
            ("🔥 Immolate",            "Refresh inden det udløber – ISB-procs stopper uden det"),
            ("💜 Corruption",          "Stadig DPS-positivt i Destro – brug det altid"),
            ("☠️ Curse-valg",          "Gruppe 1 (CoR): kun hvis raid mangler armor debuff  ·  Gruppe 2: CoE (+10% magic dmg) hvis ingen anden dækker det, ellers CoD/CoA for personlig DPS"),
            ("🌟 Curse of Elements",   "+10% magic damage til hele raidet – kæmpe raid-værdi"),
            ("🐾 Imp",                 "Imp i raid: Blood Pact stamina buff + fire shield"),
        ],
        "mistakes": [
            "❌ Immolate falder af – ISB-procs stopper og ticks mangler",
            "❌ ISB-stacks holder ikke – Shadow Bolt filler bliver prioriteret væk",
            "❌ Glemmer Corruption som Destro",
            "❌ Bruger ikke CoE når ingen andre dækker det",
            "❌ Stopper cast under movement (pre-position dig i stedet)",
        ],
    },
    "Demonology 🟢": {
        "wcl_name": "Demonology",
        "color": "#54c254",
        "description": "Demo / Felguard spec – stærkt pet damage + Demonic Pact raid-buff",
        "rotation": [
            "Send Felguard ind + aktiver Cleave command",
            "Corruption → hold oppe konstant",
            "Immolate → hold oppe konstant",
            "Curse (Gruppe 2): CoD på bosses >24s / CoA ellers",
            "Shadow Bolt spam",
            "Metamorphosis på cooldown – align med Bloodlust",
            "Dark Pact Felguard for gratis mana",
        ],
        "tips": [
            ("🎯 Hit Rating",  "202 hit rating – Felguard DPS skalerer også med dit spell hit"),
            ("⚔️ Felguard",    "Stor del af din DPS – hold den i live!"),
            ("🦋 Meta",        "Align Metamorphosis med Bloodlust – brug på pull"),
            ("✨ Demonic Pact", "Passive spell power buff til hele raidet"),
            ("🔋 Dark Pact",   "Dark Pact Felguard = gratis mana, intet HP-tab"),
            ("💜 Corruption",  "Skal ALTID være oppe"),
            ("☠️ Curse-valg",  "Gruppe 1 (CoR): kun ved fysisk-tunge raids  ·  Gruppe 2: CoE hvis du dækker det alene, ellers CoD/CoA"),
        ],
        "mistakes": [
            "❌ Felguard dør til AoE – repositionér den",
            "❌ Metamorphosis-cooldown glemmes",
            "❌ Life Tap i stedet for Dark Pact på Felguard",
        ],
    },
}

GENERAL_TIPS = [
    ("🎯", "Hit Cap",        "202 hit rating er absolut MUST HAVE – under cap = miss = 0 DPS"),
    ("📜", "Pre-pot",        "Destruction Potion på pull – 120-180 spell damage i 15 sekunder"),
    ("💎", "Trinkets",       "Align on-use trinkets med Bloodlust og andre raid-cooldowns"),
    ("🧪", "Healthstone",    "Altid have Healthstone ready – sparer healerne"),
    ("💀", "Soulstone",      "Soulstone main healer PRE-PULL – standard raid-disciplin"),
    ("🔮", "Spellstone",     "Spellstone i off-hand øger spell crit"),
    ("🧠", "Positioning",    "Stå i meleerange på cleave-boss – undgå unødvendig bevægelse"),
    ("⚡", "Wand",           "Aldrig wand i TBC – Life Tap og cast videre"),
    ("🌟", "Flask",          "Flask of Supreme Power (+70 spell dmg) på progression"),
    ("🍖", "Food",           "Spicy Hot Talbuk (+23 hit) eller Blackened Basilisk (+23 spell dmg)"),
]

# ═══════════════════════════════════════════════════════════════════════════════
# WCL API
# ═══════════════════════════════════════════════════════════════════════════════

WCL_OAUTH_URL = "https://www.warcraftlogs.com/oauth/token"
WCL_API_URL   = "https://fresh.warcraftlogs.com/api/v2/client"


@st.cache_data(ttl=600, show_spinner=False)
def get_token(client_id: str, client_secret: str) -> str:
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    r = requests.post(
        WCL_OAUTH_URL,
        headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def wcl(token: str, gql: str, variables: dict = None) -> dict:
    r = requests.post(
        WCL_API_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": gql, "variables": variables or {}},
        timeout=25,
    )
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(data["errors"][0].get("message", "GraphQL fejl"))
    return data.get("data", {})


# ── GraphQL Queries ────────────────────────────────────────────────────────────

Q_ZONES = "query { worldData { zones { id name expansion { name } } } }"

Q_ZONE_RANKINGS = """
query($name:String!, $server:String!, $region:String!, $zoneID:Int!) {
  characterData {
    character(name:$name, serverSlug:$server, serverRegion:$region) {
      zoneRankings(zoneID:$zoneID, metric:dps) {
        bestPerformanceAverage
        medianPerformanceAverage
        rankings {
          encounter { id name }
          rankPercent bestAmount medianPercent totalKills spec
        }
      }
    }
  }
}"""

Q_RECENT_REPORTS = """
query($name:String!, $server:String!, $region:String!) {
  characterData {
    character(name:$name, serverSlug:$server, serverRegion:$region) {
      recentReports(limit:5) {
        data {
          code title startTime
          zone { name }
          fights { id name startTime endTime difficulty kill encounterID }
        }
      }
    }
  }
}"""

Q_DAMAGE_TABLE = """
query($code:String!, $start:Float!, $end:Float!) {
  reportData {
    report(code:$code) {
      table(dataType:DamageDone, startTime:$start, endTime:$end, sourceID:-1)
    }
  }
}"""

Q_BUFF_TABLE = """
query($code:String!, $start:Float!, $end:Float!, $targetID:Int!) {
  reportData {
    report(code:$code) {
      table(dataType:Buffs, startTime:$start, endTime:$end, targetID:$targetID)
    }
  }
}"""

Q_ENCOUNTER_TOP100 = """
query($encounterID:Int!, $specName:String!) {
  worldData {
    encounter(id:$encounterID) {
      characterRankings(
        className:"Warlock"
        specName:$specName
        metric:dps
        limit:100
      ) {
        count
        rankings {
          name amount duration
          report { code startTime }
          startTime
        }
      }
    }
  }
}"""


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSE-FUNKTIONER
# ═══════════════════════════════════════════════════════════════════════════════

def detect_spec(abilities: list) -> str:
    names = {a.get("name", "") for a in abilities}
    if "Unstable Affliction" in names:
        return "Affliction 💜"
    if "Conflagrate" in names or "Incinerate" in names:
        return "Destruction 🔥"
    m = {a.get("name", ""): a.get("total", 0) for a in abilities}
    if m.get("Immolate", 0) > m.get("Corruption", 0) * 0.8:
        return "Destruction 🔥"
    return "Affliction 💜"


def analyze_curses(spell_map: dict) -> dict:
    """Returnerer fuld curse-analyse med gruppe-klassifikation."""
    g1 = [c for c in CURSE_GROUP_1 if c in spell_map]
    g2 = [c for c in CURSE_GROUP_2 if c in spell_map]
    none_used = not g1 and not g2 and not any(
        c in spell_map for c in ["Curse of Weakness", "Curse of Exhaustion"]
    )
    return {"group1": g1, "group2": g2, "none": none_used}


def analyze_hit_cap(spell_map: dict, active_hit_buffs: list, spec: str) -> dict:
    """
    Beregner effektiv hit cap og sammenligner med observeret miss rate.
    Returnerer dict med talværdier og vurdering.
    """
    hit_pct_from_buffs = sum(HIT_GIVING_BUFFS.get(b, 0) for b in active_hit_buffs)
    effective_cap = round(HIT_CAP_BASE - hit_pct_from_buffs * HIT_PCT_PER_RATING)

    # Affliction Suppression: -3% hit behov for DoTs (vises som info, ikke ændrer Shadow Bolt cap)
    affliction_suppression_cap = round(effective_cap - 3 * HIT_PCT_PER_RATING) if "Affliction" in spec else None

    # Miss rate fra Shadow Bolt
    sb = spell_map.get("Shadow Bolt", {})
    casts  = sb.get("casts", 0)
    misses = sb.get("misses", 0)
    miss_rate = (misses / casts * 100) if casts > 5 else None
    at_cap = (miss_rate is not None and miss_rate < 1.0)

    return {
        "hit_pct_from_buffs":      hit_pct_from_buffs,
        "effective_cap":           effective_cap,
        "affliction_cap":          affliction_suppression_cap,
        "sb_casts":                casts,
        "sb_misses":               misses,
        "miss_rate":               miss_rate,
        "at_cap":                  at_cap,
    }


def extract_active_buffs(buff_table_data: dict) -> dict:
    """
    Parser buff-tabel fra WCL og returnerer:
      active_hit_buffs: liste af hit-giving buffs
      raid_buffs: dict {navn: uptime_pct} for kendte raid-buffs
    """
    entries = buff_table_data.get("auras", []) or buff_table_data.get("data", {}).get("auras", []) or []
    # Forsøg alle mulige nøgler
    if not entries and isinstance(buff_table_data, dict):
        for key in ("auras", "entries", "data"):
            val = buff_table_data.get(key)
            if isinstance(val, list):
                entries = val
                break
            if isinstance(val, dict):
                entries = val.get("auras", []) or val.get("entries", [])
                if entries:
                    break

    names_present = {e.get("name", ""): e for e in entries}

    active_hit_buffs = [n for n in HIT_GIVING_BUFFS if n in names_present]
    raid_buffs = {}
    for name, emoji, desc in RAID_BUFF_LIST:
        if name in names_present:
            uptime = names_present[name].get("totalUptime", names_present[name].get("uptime", 0))
            raid_buffs[name] = {"emoji": emoji, "desc": desc, "uptime": uptime}

    return {"active_hit_buffs": active_hit_buffs, "raid_buffs": raid_buffs}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_top100_curse_analysis(token: str, encounter_id: int, spec_wcl: str) -> dict:
    """
    Henter top 100 rankings for encounter+spec og analyserer
    curse-gruppefordelingen hos de bedste spillere (sample af top 15).
    Returnerer DPS-liste og curse-stats.
    """
    try:
        data = wcl(token, Q_ENCOUNTER_TOP100, {"encounterID": encounter_id, "specName": spec_wcl})
        rankings_raw = (data.get("worldData", {})
                        .get("encounter", {})
                        .get("characterRankings", {})
                        .get("rankings", []))
    except Exception:
        return {"error": "Kunne ikke hente top 100 rankings."}

    if not rankings_raw:
        return {"error": "Ingen rankings fundet for dette encounter og denne spec."}

    dps_list = [r.get("amount", 0) for r in rankings_raw]

    # Sample top 15 for curse-analyse
    sample = rankings_raw[:15]
    curse_counts = {"Gruppe 1 (CoR)": 0, "Gruppe 2 – CoE": 0, "Gruppe 2 – CoA/CoD": 0, "Ingen curse": 0}
    analysed = 0

    for entry in sample:
        report = entry.get("report", {})
        code   = report.get("code", "")
        start  = entry.get("startTime", 0)
        dur    = entry.get("duration", 0)
        end    = start + dur if dur else start + 600000  # fallback 10 min
        name   = entry.get("name", "")
        if not code:
            continue
        try:
            tdata = wcl(token, Q_DAMAGE_TABLE, {"code": code, "start": float(start), "end": float(end)})
            entries_list = (tdata.get("reportData", {}).get("report", {})
                            .get("table", {}).get("data", {}).get("entries", []))
            player = next((e for e in entries_list if e.get("name", "").lower() == name.lower()), None)
            if player:
                abilities = player.get("abilities", []) or []
                ab_names  = {a.get("name", "") for a in abilities}
                has_g1    = any(c in ab_names for c in CURSE_GROUP_1)
                has_coe   = "Curse of the Elements" in ab_names
                has_coad  = any(c in ab_names for c in ["Curse of Agony", "Curse of Doom"])

                if has_g1:
                    curse_counts["Gruppe 1 (CoR)"] += 1
                elif has_coe:
                    curse_counts["Gruppe 2 – CoE"] += 1
                elif has_coad:
                    curse_counts["Gruppe 2 – CoA/CoD"] += 1
                else:
                    curse_counts["Ingen curse"] += 1
                analysed += 1
        except Exception:
            continue

    return {
        "dps_list":     dps_list,
        "curse_counts": curse_counts,
        "analysed":     analysed,
        "total":        len(rankings_raw),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# UI HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def pct_badge(pct: float) -> str:
    if pct >= 95: return "🟡"
    if pct >= 75: return "🟣"
    if pct >= 50: return "🔵"
    if pct >= 25: return "🟢"
    return "⚪"

def pct_label(pct: float) -> str:
    if pct >= 95: return "Legendary"
    if pct >= 75: return "Epic"
    if pct >= 50: return "Rare"
    if pct >= 25: return "Uncommon"
    return "Common"


def render_curse_analysis(curse_result: dict, spell_map: dict):
    """Renderer curse-gruppe analyse i UI."""
    g1 = curse_result["group1"]
    g2 = curse_result["group2"]

    st.markdown("##### ☠️ Curse Gruppe Analyse")

    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.markdown("**Gruppe 1 – Fysisk (CoR)**")
        if g1:
            for c in g1:
                st.success(f"✅ **{c}** aktiv")
                st.caption(CURSE_DESCRIPTIONS.get(c, ""))
        else:
            st.info("Ikke brugt i dette fight")
        st.caption("Bruges i fysisk-tunge raids for armor reduction. Koster personlig DPS vs CoA.")

    with col_g2:
        st.markdown("**Gruppe 2 – Magic/DPS (CoE, CoA, CoD)**")
        if g2:
            for c in g2:
                st.success(f"✅ **{c}** aktiv")
                st.caption(CURSE_DESCRIPTIONS.get(c, ""))
                if c == "Curse of Agony":
                    st.caption("💡 Overvej CoD på fights >24s – det giver mere total damage")
        else:
            st.info("Ikke brugt i dette fight")
        st.caption("CoE = raid magic-buff (+10%). CoA/CoD = personlig DPS.")

    if curse_result["none"]:
        st.error("❌ **Ingen curse registreret!** Du skal altid have en aktiv curse på boss.")
    elif g1 and g2:
        st.warning("⚠️ **Begge grupper brugt i samme fight.** Kan være bevidst (f.eks. CoR på adds, CoE på boss) – men vær sikker på at det var intentionelt.")


def render_hit_cap(hit_result: dict, active_hit_buffs: list, spec: str):
    """Renderer hit cap analyse i UI."""
    st.markdown("##### 🎯 Hit Cap Analyse")

    cap = hit_result["effective_cap"]
    buffs_pct = hit_result["hit_pct_from_buffs"]
    miss_rate  = hit_result["miss_rate"]
    at_cap     = hit_result["at_cap"]
    aff_cap    = hit_result.get("affliction_cap")

    col1, col2, col3 = st.columns(3)
    col1.metric("Basis hit cap", f"{HIT_CAP_BASE} hit rating", "16% spell hit")
    col2.metric(
        "Effektiv hit cap (med buffs)",
        f"{cap} hit rating",
        f"-{buffs_pct:.0f}% fra gruppe-buffs" if buffs_pct > 0 else "Ingen hit-buffs aktive",
        delta_color="inverse",
    )
    if miss_rate is not None:
        col3.metric(
            "Shadow Bolt miss rate",
            f"{miss_rate:.1f}%",
            "✅ Hit cap ramt" if at_cap else "⚠️ Under hit cap",
            delta_color="normal" if at_cap else "inverse",
        )
    else:
        col3.metric("Shadow Bolt miss rate", "–", "For få casts til analyse")

    if active_hit_buffs:
        st.success(f"**Aktive hit-buffs i dit fight:** {', '.join(active_hit_buffs)}")
        for b in active_hit_buffs:
            pct = HIT_GIVING_BUFFS[b]
            reduction = round(pct * HIT_PCT_PER_RATING)
            st.caption(f"  • **{b}**: +{pct:.0f}% spell hit → reducerer dit cap med {reduction} hit rating")
    else:
        st.warning("⚠️ **Ingen hit-givende buffs detekteret** (Inspiring Presence / Totem of Wrath). Dit hit cap er standard **202 hit rating**.")

    if aff_cap and "Affliction" in spec:
        st.info(f"📜 **Affliction note:** Med 3/3 Suppression er dit effektive cap for DoTs **{aff_cap} hit rating** (Shadow Bolt kræver stadig {cap}).")

    if miss_rate is not None and not at_cap:
        estimated_missing = round((miss_rate / 100) * HIT_PCT_PER_RATING * 100)
        st.error(
            f"⚠️ **{miss_rate:.1f}% miss rate på Shadow Bolt** – du er under hit cap! "
            f"Du misser ca. {hit_result['sb_misses']} ud af {hit_result['sb_casts']} casts. "
            f"Prioritér hit rating gear – du mangler ca. **{estimated_missing} hit rating**."
        )


def render_raid_buffs(raid_buffs: dict):
    """Renderer aktive raid-buffs i UI."""
    st.markdown("##### 🛡️ Gruppe-buffs i dit Fight")

    if not raid_buffs:
        st.info("Ingen kendte raid-buffs detekteret – enten mangler du dem, eller bufftype-query returnerede intet.")
        return

    cols = st.columns(2)
    for i, (name, info) in enumerate(raid_buffs.items()):
        with cols[i % 2]:
            uptime = info.get("uptime", 0)
            uptime_str = f" · {uptime:.0f}% uptime" if uptime and uptime > 1 else ""
            st.success(f"{info['emoji']} **{name}**{uptime_str}")
            st.caption(info["desc"])


def render_top100(top100: dict, player_best_dps: float, spec_label: str, boss_name: str):
    """Renderer top 100 sammenligning i UI."""
    st.subheader(f"🌍 Top 100 Sammenligning – {spec_label} på {boss_name}")

    if "error" in top100:
        st.warning(top100["error"])
        return

    import pandas as pd

    dps_list    = sorted(top100["dps_list"], reverse=True)
    total_count = top100["total"]
    analysed    = top100["analysed"]
    curse_counts = top100["curse_counts"]

    # DPS benchmark
    col1, col2, col3 = st.columns(3)
    if dps_list:
        top1_dps = dps_list[0]
        avg_dps  = sum(dps_list) / len(dps_list)
        rank     = next((i + 1 for i, d in enumerate(dps_list) if d <= player_best_dps), len(dps_list))
        pct_rank = 100 - (rank / total_count * 100)

        col1.metric("🥇 Top 1 DPS",       f"{top1_dps:,.0f}", f"{spec_label}")
        col2.metric("📊 Gennemsnit top 100", f"{avg_dps:,.0f}",  f"{len(dps_list)} spillere")
        col3.metric("📍 Din placering",    f"~{rank}. / {total_count}", f"{pct_rank:.0f}. percentil")

        # DPS distribution
        buckets = {}
        step = 500
        for d in dps_list:
            bucket = (int(d / step)) * step
            buckets[bucket] = buckets.get(bucket, 0) + 1

        df_hist = pd.DataFrame(
            [{"DPS interval": f"{k:,}–{k+step:,}", "Antal spillere": v}
             for k, v in sorted(buckets.items())]
        )
        with st.expander("📈 DPS fordeling (top 100)"):
            st.bar_chart(df_hist.set_index("DPS interval"))

    # Curse fordeling
    st.markdown(f"**☠️ Curse-gruppe fordeling (sample: top {analysed} spillere)**")

    if analysed > 0:
        curse_df_rows = []
        for label, count in curse_counts.items():
            pct = count / analysed * 100
            curse_df_rows.append({
                "Curse gruppe":  label,
                "Antal":         count,
                "% af sample":   f"{pct:.0f}%",
                "Bar":           "█" * int(pct / 5),
            })
        st.dataframe(pd.DataFrame(curse_df_rows), use_container_width=True, hide_index=True)

        # Konkret anbefaling
        dominant = max(curse_counts, key=curse_counts.get)
        dom_pct  = curse_counts[dominant] / analysed * 100
        if dom_pct >= 50:
            st.success(
                f"✅ **{dom_pct:.0f}% af top {analysed} Warlocks** bruger **{dominant}**. "
                "Det er det mest optimale curse-valg for dette encounter."
            )
    else:
        st.info("Kunne ikke hente spell-data fra top-spillernes logs til curse-analyse.")


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("🔮 Warlock DPS Analyzer")
    st.caption("TBC Fresh — WarcraftLogs analyse")

    st.subheader("👤 Din Karakter")
    char   = st.text_input("Karakternavn", value="dprsxd")
    server = st.text_input("Server",       value="spineshatter")
    region = st.selectbox("Region", ["eu", "us", "kr", "tw"], index=0)

    st.subheader("🧙 Din Spec")
    spec_choice = st.selectbox("Spec", list(SPECS.keys()), index=1)

    st.divider()
    st.subheader("🔑 WarcraftLogs API")
    st.caption("Kræves for at hente dine logs og top 100 data.")
    with st.expander("Hvad er dette?"):
        st.markdown(
            "1. Gå til [warcraftlogs.com/api/clients](https://www.warcraftlogs.com/api/clients)\n"
            "2. Klik **Create Client**\n"
            "3. Redirect URI: `http://localhost`\n"
            "4. Kopier **Client ID** og **Client Secret** herunder"
        )
    client_id     = st.text_input("Client ID",     placeholder="abc123...")
    client_secret = st.text_input("Client Secret", type="password", placeholder="••••••••")
    analyze_btn   = st.button("🔍 Analysér", type="primary", use_container_width=True)

    st.divider()
    st.caption(f"[Se dine logs på WCL →](https://fresh.warcraftlogs.com/character/{region}/{server}/{char})")


# ═══════════════════════════════════════════════════════════════════════════════
# HOVED LAYOUT
# ═══════════════════════════════════════════════════════════════════════════════

st.title("🔮 TBC Warlock DPS Analyzer")
st.caption(
    "Analyse af din Warlock-performance via WarcraftLogs · "
    "Curse-gruppe analyse (CoR = Gruppe 1 · CoE/CoA/CoD = Gruppe 2) · "
    "Hit cap via gruppe-buffs · Top 100 world sammenligning"
)

# ── API-analyse blok ───────────────────────────────────────────────────────────
if analyze_btn:
    if not client_id or not client_secret:
        st.warning("Udfyld Client ID og Client Secret i sidebaren. Scroll ned for spec-guide.")
    else:
        try:
            with st.spinner("Forbinder til WarcraftLogs..."):
                token = get_token(client_id, client_secret)
            st.success("✅ API forbundet!")

            # Zoner
            with st.spinner("Henter raid-zones..."):
                zones_raw = wcl(token, Q_ZONES)
            all_zones = zones_raw.get("worldData", {}).get("zones", [])
            tbc_zones = [z for z in all_zones if "Burning Crusade" in (z.get("expansion") or {}).get("name", "")]
            zone_list = tbc_zones if tbc_zones else all_zones[:15]
            zone_map  = {z["name"]: z["id"] for z in zone_list}

            selected_zone = st.selectbox("Vælg raid-zone", list(zone_map.keys()))
            zone_id = zone_map[selected_zone]

            # ── 1. Boss Rankings ───────────────────────────────────────────────
            with st.spinner(f"Henter rankings for {char}..."):
                rdata = wcl(token, Q_ZONE_RANKINGS, {
                    "name": char, "server": server, "region": region, "zoneID": zone_id
                })

            char_info = rdata.get("characterData", {}).get("character")
            if not char_info:
                st.error(f"Karakter '{char}' ikke fundet på {server}-{region}.")
                st.stop()

            zr       = char_info.get("zoneRankings", {})
            best_avg = zr.get("bestPerformanceAverage") or 0
            med_avg  = zr.get("medianPerformanceAverage") or 0

            st.subheader(f"📊 {char} — {selected_zone}")
            c1, c2, c3 = st.columns(3)
            c1.metric("⭐ Bedste gennemsnit",  f"{best_avg:.1f}%",  pct_label(best_avg))
            c2.metric("📈 Median gennemsnit",  f"{med_avg:.1f}%",   pct_label(med_avg))
            c3.metric("🎯 Niveau",             pct_label(best_avg), pct_badge(best_avg))

            rankings = zr.get("rankings", [])
            if rankings:
                import pandas as pd
                rows = []
                for r in rankings:
                    p = r.get("rankPercent") or 0
                    m = r.get("medianPercent") or 0
                    rows.append({
                        "Boss":       r.get("encounter", {}).get("name", "?"),
                        "Bedste %":   f"{pct_badge(p)} {p:.1f}%",
                        "Bedste DPS": f"{r.get('bestAmount', 0):,.0f}",
                        "Median %":   f"{pct_badge(m)} {m:.1f}%",
                        "Kills":      r.get("totalKills", 0),
                        "Niveau":     pct_label(p),
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            # ── 2. Spell Breakdown + Curse + Hit Cap + Buffs ───────────────────
            st.divider()
            st.subheader("🔬 Din Analyse")

            with st.spinner("Henter nyligste log..."):
                rep_raw = wcl(token, Q_RECENT_REPORTS, {
                    "name": char, "server": server, "region": region
                })
            reports = (rep_raw.get("characterData", {}).get("character", {})
                       .get("recentReports", {}).get("data", [])) or []

            if not reports:
                st.info("Ingen nylige rapporter fundet.")
            else:
                latest      = reports[0]
                fights      = latest.get("fights", []) or []
                boss_fights = [f for f in fights if f.get("difficulty") and f.get("endTime")]

                if not boss_fights:
                    st.info("Ingen boss-fights i den nyligste rapport.")
                else:
                    fight      = boss_fights[0]
                    boss_name  = fight.get("name", "?")
                    enc_id     = fight.get("encounterID")
                    zone_name  = (latest.get("zone") or {}).get("name", "?")
                    kill_str   = "✅ Kill" if fight.get("kill") else "❌ Wipe"
                    code       = latest["code"]
                    f_start    = float(fight.get("startTime", 0))
                    f_end      = float(fight.get("endTime", 9999999))

                    st.caption(f"Analyserer: **{boss_name}** i {zone_name} — {kill_str}")

                    # Hent damage table
                    with st.spinner("Henter spell breakdown..."):
                        tdata = wcl(token, Q_DAMAGE_TABLE, {"code": code, "start": f_start, "end": f_end})
                    entries_list = (tdata.get("reportData", {}).get("report", {})
                                    .get("table", {}).get("data", {}).get("entries", [])) or []
                    me = next((e for e in entries_list if e.get("name", "").lower() == char.lower()), None)
                    actor_id = me.get("id") if me else None

                    if not me:
                        st.warning(f"Kunne ikke finde '{char}' i log-data.")
                    else:
                        abilities = me.get("abilities", []) or []
                        spell_map = {a.get("name", ""): a for a in abilities}
                        total_dmg = sum(a.get("total", 0) for a in abilities)
                        detected  = detect_spec(abilities)

                        st.info(f"Detekteret spec fra logs: **{detected}**")

                        # Tab-layout for analyse
                        t_spells, t_curse, t_hit, t_buffs = st.tabs([
                            "💥 Spell Breakdown",
                            "☠️ Curse Grupper",
                            "🎯 Hit Cap",
                            "🛡️ Gruppe Buffs",
                        ])

                        # ── Spell Breakdown ────────────────────────────────────
                        with t_spells:
                            import pandas as pd
                            spell_rows = []
                            for a in sorted(abilities, key=lambda x: x.get("total", 0), reverse=True)[:15]:
                                pct = (a.get("total", 0) / total_dmg * 100) if total_dmg else 0
                                spell_rows.append({
                                    "Spell":           a.get("name", "?"),
                                    "% af total dmg":  f"{pct:.1f}%",
                                    "Total damage":    f"{a.get('total', 0):,}",
                                    "Casts":           a.get("casts", "–"),
                                    "Misses":          a.get("misses", "–"),
                                    "Uptime %":        f"{a.get('uptime', 0):.0f}%" if a.get("uptime") else "–",
                                })
                            st.dataframe(pd.DataFrame(spell_rows), use_container_width=True, hide_index=True)

                            # Specifikke advarsler
                            issues = []
                            if "Corruption" not in spell_map:
                                issues.append(("❌", "Corruption", "Ikke registreret – bør altid være øverst i prioriteten!"))
                            else:
                                up = spell_map["Corruption"].get("uptime", 0)
                                if up and up < 90:
                                    issues.append(("⚠️", "Corruption", f"{up:.0f}% uptime – mål er 95%+"))

                            if "Destruction" in detected:
                                if "Immolate" not in spell_map:
                                    issues.append(("⚠️", "Immolate", "Ikke registreret – essentielt for ISB-procs"))
                                else:
                                    up = spell_map["Immolate"].get("uptime", 0)
                                    if up and up < 85:
                                        issues.append(("⚠️", "Immolate", f"{up:.0f}% uptime – mål er 90%+"))

                            if "Affliction" in detected and "Unstable Affliction" not in spell_map:
                                issues.append(("❌", "Unstable Affliction", "Ikke registreret – næstvigtigste DoT!"))

                            if issues:
                                st.markdown("**Observationer:**")
                                for icon, topic, msg in issues:
                                    st.warning(f"**{icon} {topic}:** {msg}")
                            else:
                                st.success("✅ Spell breakdown ser fornuftigt ud!")

                        # ── Curse Grupper ──────────────────────────────────────
                        with t_curse:
                            curse_result = analyze_curses(spell_map)
                            render_curse_analysis(curse_result, spell_map)

                        # ── Hit Cap ────────────────────────────────────────────
                        with t_hit:
                            # Hent buff-tabel for hit-buff detektion
                            active_hit_buffs = []
                            buff_data_raw = {}
                            if actor_id:
                                try:
                                    with st.spinner("Henter buff-data..."):
                                        bdata = wcl(token, Q_BUFF_TABLE, {
                                            "code": code, "start": f_start,
                                            "end": f_end, "targetID": actor_id
                                        })
                                    buff_table = (bdata.get("reportData", {}).get("report", {})
                                                  .get("table", {}).get("data", {}))
                                    buff_parsed   = extract_active_buffs(buff_table)
                                    active_hit_buffs = buff_parsed["active_hit_buffs"]
                                    buff_data_raw    = buff_parsed["raid_buffs"]
                                except Exception:
                                    pass

                            hit_result = analyze_hit_cap(spell_map, active_hit_buffs, detected)
                            render_hit_cap(hit_result, active_hit_buffs, detected)

                        # ── Gruppe Buffs ───────────────────────────────────────
                        with t_buffs:
                            if buff_data_raw:
                                render_raid_buffs(buff_data_raw)
                            else:
                                st.info(
                                    "Buff-data ikke tilgængeligt. "
                                    "WCL returnerer kun buffs for rapporter der inkluderer fuld buff-tracking."
                                )
                                st.markdown("**Buffs der ville forbedre dit play hvis de mangler:**")
                                for name, emoji, desc in RAID_BUFF_LIST[:8]:
                                    st.caption(f"{emoji} **{name}** – {desc}")

                    # ── 3. Top 100 Sammenligning ───────────────────────────────
                    if enc_id:
                        st.divider()
                        spec_wcl = SPECS[spec_choice]["wcl_name"]

                        with st.spinner(f"Henter top 100 {spec_wcl} Warlocks på {boss_name}..."):
                            top100 = fetch_top100_curse_analysis(token, enc_id, spec_wcl)

                        player_best = me.get("total", 0) / max((f_end - f_start) / 1000, 1) if me else 0
                        render_top100(top100, player_best, spec_choice, boss_name)
                    else:
                        st.info("Encounter ID ikke tilgængeligt – top 100 analyse kræver dette.")

        except requests.HTTPError as e:
            st.error(f"❌ API-fejl: {e} — Tjek dine credentials.")
        except Exception as e:
            st.error(f"❌ Fejl: {e}")

elif not analyze_btn:
    st.info("👈 Udfyld oplysninger i sidebaren og tryk **Analysér**. Scroll ned for spec-guide.")

# ═══════════════════════════════════════════════════════════════════════════════
# SPEC GUIDE (altid synlig)
# ═══════════════════════════════════════════════════════════════════════════════

st.divider()
spec = SPECS[spec_choice]
st.subheader(f"📖 Spec Guide: {spec_choice}")
st.caption(spec["description"])

tab_rot, tab_tips, tab_err = st.tabs(["🔄 Rotation", "💡 Tips", "⚡ Typiske Fejl"])

with tab_rot:
    for i, step in enumerate(spec["rotation"], 1):
        st.markdown(f"**{i}.** {step}")

with tab_tips:
    import pandas as pd
    tips_df = pd.DataFrame(spec["tips"], columns=["Emne", "Tip"])
    st.dataframe(tips_df, use_container_width=True, hide_index=True)

with tab_err:
    for m in spec["mistakes"]:
        st.markdown(m)

# ═══════════════════════════════════════════════════════════════════════════════
# GENERELLE TIPS (altid synlig)
# ═══════════════════════════════════════════════════════════════════════════════

st.divider()
st.subheader("🌟 Generelle TBC Warlock Tips")

cols = st.columns(2)
for i, (emoji, topic, tip) in enumerate(GENERAL_TIPS):
    with cols[i % 2]:
        st.markdown(f"**{emoji} {topic}**")
        st.caption(tip)
        st.write("")
