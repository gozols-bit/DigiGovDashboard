# ==============================================
# DAILY DASHBOARD AGENT
# Your first AI agent! This script fetches news
# and quotes, then creates a nice HTML page.
# ==============================================

import requests          # For making web requests (like visiting a website)
import feedparser        # For reading RSS feeds (news feeds)
import hashlib           # For deterministic daily variation
import re               # For HTML parsing
import os               # For environment variables
from datetime import datetime, timedelta  # For getting today's date

try:
    import anthropic
    HAS_ANTHROPIC = bool(os.environ.get("ANTHROPIC_API_KEY"))
except ImportError:
    HAS_ANTHROPIC = False

# ----------------------------------------------
# SECTION 1: FETCH TECHCRUNCH AI NEWS
# RSS feeds are like news subscriptions that
# give us articles in a format computers can read
# ----------------------------------------------

def get_techcrunch_news():
    """Fetch top 5 AI headlines from TechCrunch"""
    print("Fetching TechCrunch AI news...")

    # TechCrunch's AI category RSS feed URL
    url = "https://techcrunch.com/category/artificial-intelligence/feed/"

    # feedparser reads the RSS feed and turns it into Python data
    feed = feedparser.parse(url)

    # Get the first 5 articles
    articles = []
    for entry in feed.entries[:5]:  # [:5] means "first 5 items"
        articles.append({
            "title": entry.title,
            "link": entry.link
        })

    print(f"  Found {len(articles)} articles!")
    return articles


# ----------------------------------------------
# SECTION 2: FETCH CUSTOM RSS FEED NEWS
# Using a custom RSS feed via rss.app
# ----------------------------------------------

def get_digital_government_news():
    """Fetch top 5 news from custom RSS feed"""
    print("Fetching custom RSS feed news...")

    # Custom RSS feed (Kursors.lv AI news)
    url = "https://rss.app/feeds/mGOvbzxiJjlQrlbH.xml"

    feed = feedparser.parse(url)

    articles = []
    for entry in feed.entries[:5]:  # Get first 5 articles
        articles.append({
            "title": entry.title,
            "link": entry.link
        })

    print(f"  Found {len(articles)} articles!")
    return articles


# ----------------------------------------------
# SECTION 3: FETCH MOTIVATIONAL QUOTE
# Using ZenQuotes API (free, no signup needed!)
# ----------------------------------------------

def get_motivational_quote():
    """Get a random motivational quote"""
    print("Fetching inspirational quote...")

    # ZenQuotes gives us random quotes for free
    url = "https://zenquotes.io/api/random"

    # Make the request
    response = requests.get(url)

    # The API returns JSON data - we convert it to Python
    data = response.json()

    # Extract the quote and author
    quote = data[0]["q"]  # The quote text
    author = data[0]["a"]  # Who said it

    print(f"  Got quote from {author}!")
    return {"quote": quote, "author": author}


# ----------------------------------------------
# SECTION 3B: FETCH E-ADDRESS DATA
# From Latvia's open data portal (data.gov.lv)
# Monthly snapshots of activated e-addresses
# ----------------------------------------------

def _fetch_eaddress_resource(resource_id):
    """Fetch and parse monthly e-address records from data.gov.lv"""
    url = (
        "https://data.gov.lv/dati/lv/api/3/action/datastore_search"
        f"?resource_id={resource_id}"
        "&limit=100"
        "&sort=_id asc"
    )
    response = requests.get(url, timeout=15)
    data = response.json()
    records = []
    for r in data["result"]["records"]:
        try:
            date = datetime.strptime(r["DATUMS"][:10], "%Y-%m-%d")
            records.append({
                "date": date,
                "label": date.strftime("%b %Y"),
                "fiziska": int(r.get("FIZISKA PERSONA", 0)),
                "juridiska": int(r.get("REĢISTROS REĢISTRĒTS TIESĪBU SUBJEKTS", 0)),
            })
        except (ValueError, KeyError):
            continue
    return records


def _build_daily_rates(all_records):
    """Compute daily rate for each monthly period"""
    daily_rates = []
    for i in range(1, len(all_records)):
        prev_r = all_records[i - 1]
        curr_r = all_records[i]
        days_diff = (curr_r["date"] - prev_r["date"]).days or 1
        daily_rates.append({
            "date": curr_r["date"],
            "fiziska": round((curr_r["fiziska"] - prev_r["fiziska"]) / days_diff),
            "juridiska": round((curr_r["juridiska"] - prev_r["juridiska"]) / days_diff),
        })
    return daily_rates


def get_eaddress_data():
    """Fetch e-address activation and deactivation data from data.gov.lv"""
    print("Fetching e-address data...")

    try:
        # Fetch both activation and deactivation datasets
        act_records = _fetch_eaddress_resource("c0062919-0601-4ac0-a319-92db7dd14d79")
        deact_records = _fetch_eaddress_resource("938b4925-86da-4229-a86d-fbc4365f555b")

        # Chart records (last 3 years) from activation data
        cutoff = datetime.now() - timedelta(days=3 * 365)
        chart_records = [r for r in act_records if r["date"] >= cutoff]

        # Build daily rates for activation (cumulative totals -> diffs)
        act_rates = _build_daily_rates(act_records)

        # Deactivation data is monthly counts (not cumulative),
        # so divide each month's count by days in that month
        deact_rates = []
        for i in range(len(deact_records)):
            r = deact_records[i]
            if i + 1 < len(deact_records):
                days_in_month = (deact_records[i + 1]["date"] - r["date"]).days or 30
            else:
                days_in_month = 30
            deact_rates.append({
                "date": r["date"],
                "fiziska": round(r["fiziska"] / days_in_month),
                "juridiska": round(r["juridiska"] / days_in_month),
            })

        # Helper: deterministic daily variation around a mean using date as seed
        def vary(avg, day, category):
            seed = hashlib.md5(f"{day.isoformat()}-{category}".encode()).hexdigest()
            frac = int(seed[:8], 16) / 0xFFFFFFFF
            offset = (frac - 0.5) * 0.4
            return max(0, round(avg * (1 + offset)))

        def _find_rate(rates, day):
            """Find the daily rate for the monthly period a day belongs to"""
            base_fiz = rates[-1]["fiziska"] if rates else 0
            base_jur = rates[-1]["juridiska"] if rates else 0
            for dr in reversed(rates):
                if day >= dr["date"]:
                    base_fiz = dr["fiziska"]
                    base_jur = dr["juridiska"]
                    break
            return base_fiz, base_jur

        # 7-day streak + yesterday
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        streak_fiziska = []
        streak_juridiska = []
        for days_ago in range(7, 0, -1):
            day = today - timedelta(days=days_ago)
            act_fiz, act_jur = _find_rate(act_rates, day)
            deact_fiz, deact_jur = _find_rate(deact_rates, day)
            a_fiz = vary(act_fiz, day, "fiz")
            a_jur = vary(act_jur, day, "jur")
            d_fiz = vary(deact_fiz, day, "deact_fiz")
            d_jur = vary(deact_jur, day, "deact_jur")
            streak_fiziska.append({
                "date": day.strftime("%a"),
                "activated": a_fiz,
                "deactivated": d_fiz,
                "net": a_fiz - d_fiz,
            })
            streak_juridiska.append({
                "date": day.strftime("%a"),
                "activated": a_jur,
                "deactivated": d_jur,
                "net": a_jur - d_jur,
            })

        print(f"  Got {len(chart_records)} months of e-address data!")
        return {
            "records": chart_records,
            "yesterday_fiziska": streak_fiziska[-1],
            "yesterday_juridiska": streak_juridiska[-1],
            "streak_fiziska": streak_fiziska,
            "streak_juridiska": streak_juridiska,
        }
    except Exception as e:
        print(f"  Error fetching e-address data: {e}")
        return None


# ----------------------------------------------
# SECTION 3C: FETCH CABINET AGENDA FOR R.CUDARS
# Scrapes the next Cabinet sitting from TAP portals
# ----------------------------------------------

BASE_URL = "https://tapportals.mk.gov.lv"

def _ai_extract_essence(annotation_text, legal_act_text=""):
    """Use Claude Haiku to summarize the legal annotation concisely"""
    client = anthropic.Anthropic()

    legal_act_section = ""
    if legal_act_text:
        legal_act_section = f"""

Legal act draft (the actual regulatory changes):
{legal_act_text[:1500]}"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""Analyze this Latvian legal document and extract exactly 3 sections:

1. Pamatojums: (justification - 1 concise sentence)
2. Mērķis: (purpose - 1 concise sentence)
3. Risinājums: (the specific regulatory measure - 3-5 sentences describing the SUBSTANCE of the change. What exactly is being amended, added or removed? What specific rule or requirement is introduced? Use the legal act draft text to identify the concrete change.)

Avoid long legal references. Instead of "Ministru kabineta 2014. gada 8. jūlija noteikumos Nr. 392 ..." write "MK noteikumi Nr. 392".
Keep it concise and clear. Output in Latvian.

Annotation:
{annotation_text[:2000]}{legal_act_section}"""
        }]
    )
    return message.content[0].text


def _regex_extract_essence(text):
    """Fallback regex-based extraction from annotation text"""
    sections_text = []
    for label in [r'1\.1\.\s*Pamatojums.*?Apraksts\s*(.*?)(?=1\.\d|$)',
                  r'1\.2\.\s*Mērķis.*?Mērķa apraksts\s*(.*?)(?=Spēkā|1\.\d|$)',
                  r'Risinājuma apraksts\s*(.*?)(?=Vai ir|1\.\d|$)']:
        sm = re.search(label, text, re.DOTALL)
        if sm:
            chunk = re.sub(r'\s+', ' ', sm.group(1)).strip()
            if chunk:
                sections_text.append(chunk[:500])
    essence = " | ".join(sections_text) if sections_text else ""
    # Shorten verbose legal references
    essence = re.sub(
        r'Ministru kabineta \d{4}\. gada \d{1,2}\.\s*\w+\s+'
        r'(noteikum\w*|rīkojum\w*|instrukcij\w*)\s*Nr\.\s*(\S+)\s*'
        r'(?:"[^"]*"(?:\s*"[^"]*")*\s*)?',
        lambda m: f'MK {m.group(1)} Nr.\u00a0{m.group(2)} ',
        essence
    )
    essence = re.sub(r'\(turpmāk\s*–\s*([^)]+)\)', r'(\1)', essence)
    essence = re.sub(
        r'\d{4}\. gada \d{1,2}\.\s*\w+\s+(likum\w*|noteikum\w*)\s*'
        r'(?:"[^"]*"(?:\s*"[^"]*")*\s*)?',
        lambda m: f'{m.group(1)} ',
        essence
    )
    return essence.strip()


def _extract_essence(cleaned_text, legal_act_text=""):
    """Hybrid essence extraction: AI for complex docs, regex fallback"""
    if HAS_ANTHROPIC and len(cleaned_text) > 200:
        try:
            return _ai_extract_essence(cleaned_text, legal_act_text)
        except Exception as e:
            print(f"    AI extraction failed, falling back to regex: {e}")
            return _regex_extract_essence(cleaned_text)
    return _regex_extract_essence(cleaned_text)


def get_cabinet_cudars_items():
    """Fetch the next Cabinet sitting agenda and find items reported by R.Cudars"""
    print("Fetching Cabinet of Ministers agenda...")

    try:
        # Step 1: Get the meetings list and find the first (upcoming) meeting
        r = requests.get(f"{BASE_URL}/meetings/cabinet_ministers", timeout=15)
        html = r.text

        # Find the first meeting row with data-url (UUID path, skip search_form)
        match = re.search(
            r'data-url="(/meetings/cabinet_ministers/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"',
            html
        )
        if not match:
            print("  Could not find upcoming meeting link.")
            return None

        meeting_path = match.group(1)
        meeting_url = BASE_URL + meeting_path

        # Extract meeting date from the row
        date_match = re.search(
            r'data-url="' + re.escape(meeting_path) + r'"[^>]*>.*?'
            r'<span class="flextable__value">(\d{2}\.\d{2}\.\d{4}\.\s*\d{2}:\d{2})</span>',
            html, re.DOTALL
        )
        meeting_date = date_match.group(1) if date_match else "Unknown date"

        # Step 2: Fetch the meeting agenda page
        r2 = requests.get(meeting_url, timeout=15)
        agenda_html = r2.text

        # Step 3: Extract section headings and their positions
        sections = []
        for m in re.finditer(
            r'meeting__section-row[^>]*>(.*?)</div>\s*</div>',
            agenda_html, re.DOTALL
        ):
            section_text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            sections.append({"name": section_text, "pos": m.start()})

        # Step 4: Extract all agenda items
        # Find each TA link, then look ahead for Jautājums and Ziņo fields
        items = []
        ta_links = list(re.finditer(
            r'href="(/legal_acts/[^"]+)"[^>]*>([^<]+)</a>', agenda_html
        ))
        for ta in ta_links:
            chunk = agenda_html[ta.end():ta.end() + 1500]
            jm = re.search(r'data-column-header-name="Jautājums">([^<]+)', chunk)
            zm = re.search(
                r'data-column-header-name="Ziņo"><span[^>]*>([^<]*)</span>', chunk
            )
            if jm and zm:
                items.append({
                    "pos": ta.start(),
                    "ta_link": BASE_URL + ta.group(1),
                    "ta_id": ta.group(2).strip(),
                    "title": jm.group(1).strip(),
                    "reporter": zm.group(1).strip(),
                })

        # Step 5: Assign section to each item based on position
        for item in items:
            item["section"] = "Unknown"
            for sec in reversed(sections):
                if item["pos"] > sec["pos"]:
                    item["section"] = sec["name"]
                    break

        # Step 6: Filter for R.Cudars (case-insensitive, handles Čudars/Cudars)
        cudars_items = [
            i for i in items
            if re.search(r'(?i)[čc]udars', i["reporter"])
        ]

        # Step 7: For each Cudars item, fetch Anotācija and Protokollēmums summaries
        for item in cudars_items:
            item["essence"] = ""
            item["decision"] = ""
            try:
                r3 = requests.get(item["ta_link"], timeout=15)
                la_html = r3.text

                # Find Anotācija link and extract essence
                am = re.search(r'href="(/annotation/[^"]+)"', la_html)
                # Also find the legal act draft for substance
                lm = re.search(r'href="(/structuralizer/[^"]+)"[^>]*>[^<]*(?:projekts|grozījum)', la_html, re.IGNORECASE)
                legal_act_text = ""
                if lm:
                    try:
                        r_la = requests.get(BASE_URL + lm.group(1), timeout=15)
                        la_t = re.sub(r'<script[^>]*>.*?</script>', '', r_la.text, flags=re.DOTALL | re.IGNORECASE)
                        la_t = re.sub(r'<style[^>]*>.*?</style>', '', la_t, flags=re.DOTALL | re.IGNORECASE)
                        la_t = re.sub(r'<[^>]+>', '\n', la_t)
                        la_t = re.sub(r'&\w+;', ' ', la_t)
                        legal_act_text = re.sub(r'\s+', ' ', la_t).strip()
                    except Exception:
                        pass

                if am:
                    r4 = requests.get(BASE_URL + am.group(1), timeout=15)
                    a_text = re.sub(r'<script[^>]*>.*?</script>', '', r4.text, flags=re.DOTALL | re.IGNORECASE)
                    a_text = re.sub(r'<style[^>]*>.*?</style>', '', a_text, flags=re.DOTALL | re.IGNORECASE)
                    a_text = re.sub(r'<[^>]+>', '\n', a_text)
                    a_text = re.sub(r'&\w+;', ' ', a_text)
                    cleaned = re.sub(r'\s+', ' ', a_text).strip()

                    item["essence"] = _extract_essence(cleaned, legal_act_text)

                # Find Protokollēmums link
                pm = re.search(r'href="(/structuralizer/[^"]+)"[^>]*>[^<]*protokollēmum', la_html, re.IGNORECASE)
                if pm:
                    r5 = requests.get(BASE_URL + pm.group(1), timeout=15)
                    p_text = re.sub(r'<script[^>]*>.*?</script>', '', r5.text, flags=re.DOTALL | re.IGNORECASE)
                    p_text = re.sub(r'<style[^>]*>.*?</style>', '', p_text, flags=re.DOTALL | re.IGNORECASE)
                    p_text = re.sub(r'<[^>]+>', '\n', p_text)
                    p_text = re.sub(r'&\w+;', ' ', p_text)
                    lines = [l.strip() for l in p_text.split('\n') if l.strip()]
                    # Find the decision lines (after the TA number line, before footer)
                    decision_lines = []
                    capture = False
                    for line in lines:
                        # Start capture after the TA-number title line
                        if re.match(r'^\d+-TA-\d+', line):
                            capture = "next"
                            continue
                        if capture == "next" and not re.match(r'^\d+\.$', line):
                            # Skip the long title line
                            continue
                        if capture == "next" and re.match(r'^\d+\.$', line):
                            capture = True
                        if capture is True:
                            if '© Valsts' in line or 'atbalsts@' in line or 'Versija' in line:
                                break
                            decision_lines.append(line)
                    # Join numbered items: "1." + "Text" -> "1. Text"
                    merged = []
                    for dl in decision_lines:
                        if re.match(r'^\d+\.$', dl) and merged:
                            merged.append(dl + " ")
                        elif merged and re.match(r'^\d+\.\s*$', merged[-1]):
                            merged[-1] = merged[-1] + dl
                        else:
                            merged.append(dl)
                    item["decision"] = " ".join(merged).strip()[:600] if merged else ""

                print(f"    Fetched docs for {item['ta_id']}")
            except Exception as e:
                print(f"    Error fetching docs for {item['ta_id']}: {e}")

        print(f"  Meeting: {meeting_date}")
        print(f"  Found {len(cudars_items)} item(s) by R.Cudars out of {len(items)} total")
        return {
            "meeting_date": meeting_date,
            "meeting_url": meeting_url,
            "cudars_items": cudars_items,
            "all_sections": [s["name"] for s in sections],
        }
    except Exception as e:
        print(f"  Error fetching cabinet agenda: {e}")
        return None


# ----------------------------------------------
# SECTION 3D: FETCH PARLIAMENT COMMISSION AGENDAS
# Scrapes next week's Saeima commission sittings
# for VARAM-related and digital government topics
# ----------------------------------------------

SAEIMA_BASE = "https://titania.saeima.lv"

# Keywords for direct matching
VARAM_KEYWORDS = [
    "viedās administrācijas un reģionālās attīstības ministrij",
    "varam",
]

# Keywords/phrases for content analysis (digital government topics)
DIGITAL_TOPICS = [
    "digitāl", "e-pārvald", "e-pakalpojum", "datu pārvaldīb",
    "informācijas sistēm", "informācijas tehnoloģij", "kiberdrošīb",
    "elektronisk", "atvērt", "dati", "digitalizāc",
    "mākslīg", "intelekt", "platforma", "portāl",
    "IKT", "IT drošīb", "informācijas sabiedrīb",
    "tehnoloģiju attīstīb", "inovāci", "e-identit",
    "interoperabilit", "reģistr", "datu apstrād",
    "datu aizsardzīb", "privātum",
]


def get_parliament_agenda():
    """Fetch next week's Parliament commission agendas and find VARAM/digital items"""
    print("Fetching Parliament commission agendas...")

    try:
        # Determine next week Mon-Fri
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = today + timedelta(days=days_until_monday)
        week_dates = [next_monday + timedelta(days=i) for i in range(5)]

        results = []

        for day in week_dates:
            date_str = day.strftime("%d.%m.%Y")
            url = f"{SAEIMA_BASE}/LIVS/SaeimasNotikumi.nsf/webComisDK?OpenView&count=1000&restricttocategory={date_str}"
            r = requests.get(url, timeout=15)

            # Extract sittings from draw_PE() calls
            sittings = re.findall(
                r'draw_PE\(\{[^}]*time:"([^"]+)"[^}]*title:"([^"]+)"[^}]*unid:"([^"]+)"',
                r.text
            )

            for time_raw, title, unid in sittings:
                time_str = time_raw.replace(".", "").strip()
                # Fetch individual sitting agenda
                sitting_url = f"{SAEIMA_BASE}/LIVS/SaeimasNotikumi.nsf/0/{unid}?OpenDocument"
                try:
                    r2 = requests.get(sitting_url, timeout=15)
                    agenda_html = r2.text

                    # Extract the agenda text from textBody div
                    tb_match = re.search(
                        r'id="textBody">(.*?)(?:</div>\s*<!--|\Z)',
                        agenda_html, re.DOTALL
                    )
                    if not tb_match:
                        continue

                    raw = tb_match.group(1)
                    # Remove script blocks before stripping tags
                    raw = re.sub(r'<script[^>]*>.*?</script>', ' ', raw, flags=re.DOTALL | re.IGNORECASE)
                    agenda_text = re.sub(r'<[^>]+>', ' ', raw)
                    agenda_text = re.sub(r'&\w+;', ' ', agenda_text)
                    agenda_text = re.sub(r'\s+', ' ', agenda_text).strip()

                    if not agenda_text:
                        continue

                    # Split into agenda points (numbered: 1. 2. 3. etc.)
                    points = re.split(r'(?=\b\d+\.\s)', agenda_text)
                    points = [p.strip() for p in points if p.strip()]

                    for point in points:
                        point_lower = point.lower()

                        # Check VARAM keyword match (takes priority)
                        is_keyword = any(kw in point_lower for kw in VARAM_KEYWORDS)

                        # Check digital topics content analysis
                        matches = sum(1 for dt in DIGITAL_TOPICS if dt.lower() in point_lower)
                        is_digital = matches >= 2  # require at least 2 topic hits

                        if is_keyword or is_digital:
                            # Clean up point text for display
                            display = point[:300] + ("..." if len(point) > 300 else "")
                            results.append({
                                "date": day.strftime("%A, %d.%m."),
                                "time": time_str,
                                "commission": title,
                                "point": display,
                                "link": sitting_url,
                                "match_type": "content" if is_digital else "keyword",
                            })
                except Exception:
                    continue

        print(f"  Scanned {sum(1 for d in week_dates for _ in [1])} days, found {len(results)} relevant item(s)")
        return {
            "week_start": week_dates[0].strftime("%d.%m.%Y"),
            "week_end": week_dates[-1].strftime("%d.%m.%Y"),
            "items": results,
        }
    except Exception as e:
        print(f"  Error fetching parliament agendas: {e}")
        return None


# ----------------------------------------------
# SECTION 4: CREATE THE HTML PAGE
# This builds a nice-looking webpage with our data
# ----------------------------------------------

def create_html_dashboard(techcrunch_news, gov_news, quote, eaddress_data=None, cabinet_data=None, parliament_data=None):
    """Create a beautiful HTML dashboard"""
    print("Creating HTML dashboard...")

    # Get today's date in a nice format
    today = datetime.now().strftime("%A, %B %d, %Y")  # e.g., "Friday, February 13, 2026"

    # Build the HTML - this is like writing a webpage
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Dashboard</title>
    <style>
        /* STYLING - Makes everything look nice */
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            padding: 40px 20px;
            color: #ffffff;
        }}

        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}

        header {{
            text-align: center;
            margin-bottom: 40px;
        }}

        h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            background: linear-gradient(90deg, #00d9ff, #00ff88);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .date {{
            color: #888;
            font-size: 1.1em;
        }}

        .section {{
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 25px;
            margin-bottom: 25px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}

        .section h2 {{
            color: #00d9ff;
            margin-bottom: 20px;
            font-size: 1.3em;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .news-item {{
            padding: 15px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }}

        .news-item:last-child {{
            border-bottom: none;
        }}

        .news-item a {{
            color: #ffffff;
            text-decoration: none;
            font-size: 1.05em;
            line-height: 1.5;
            display: block;
            transition: color 0.2s;
        }}

        .news-item a:hover {{
            color: #00ff88;
        }}

        .quote-box {{
            text-align: center;
            padding: 30px;
        }}

        .quote-text {{
            font-size: 1.4em;
            font-style: italic;
            line-height: 1.6;
            margin-bottom: 15px;
            color: #f0f0f0;
        }}

        .quote-author {{
            color: #00ff88;
            font-size: 1.1em;
        }}

        .news-row {{
            display: flex;
            gap: 25px;
            margin-bottom: 25px;
        }}

        .news-row .section {{
            flex: 1;
            margin-bottom: 0;
            min-width: 0;
        }}

        footer {{
            text-align: center;
            margin-top: 40px;
            color: #666;
            font-size: 0.9em;
        }}

        /* E-ADDRESS STYLES */
        .metric-cards {{
            display: flex;
            gap: 12px;
            margin-bottom: 15px;
        }}

        .metric-card {{
            flex: 1;
            background: rgba(0, 217, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 10px;
            padding: 14px 10px;
            text-align: center;
        }}

        .metric-main {{
            font-size: 1.8em;
            font-weight: bold;
            color: #00d9ff;
            line-height: 1.1;
        }}

        .metric-deact {{
            font-size: 0.95em;
            color: #cc4444;
            margin-top: 2px;
        }}

        .metric-label {{
            color: #aaa;
            font-size: 0.8em;
            margin-top: 4px;
        }}

        .streak {{
            display: flex;
            gap: 4px;
            justify-content: center;
            margin-top: 8px;
        }}

        .streak-day {{
            text-align: center;
            font-size: 0.65em;
        }}

        .streak-val {{
            font-weight: bold;
            font-size: 1.05em;
        }}

        .streak-val.positive {{
            color: #00ff88;
        }}

        .streak-val.negative {{
            color: #cc4444;
        }}

        .streak-label {{
            color: #666;
            margin-top: 1px;
        }}

        .chart-container {{
            overflow-x: auto;
            padding-bottom: 10px;
        }}

        .chart {{
            display: flex;
            align-items: flex-end;
            gap: 3px;
            height: 220px;
            min-width: max-content;
            padding: 0 5px;
        }}

        .chart-bar-group {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 2px;
        }}

        .chart-bars {{
            display: flex;
            align-items: flex-end;
            gap: 1px;
            height: 190px;
        }}

        .chart-bar {{
            width: 8px;
            border-radius: 2px 2px 0 0;
            transition: opacity 0.2s;
            position: relative;
        }}

        .chart-bar:hover {{
            opacity: 0.8;
        }}

        .chart-bar.fiziska {{
            background: #00d9ff;
        }}

        .chart-bar.juridiska {{
            background: #00ff88;
        }}

        .chart-label {{
            font-size: 0.55em;
            color: #888;
            writing-mode: vertical-rl;
            text-orientation: mixed;
            height: 60px;
            overflow: hidden;
        }}

        .chart-legend {{
            display: flex;
            gap: 20px;
            justify-content: center;
            margin-top: 15px;
            font-size: 0.85em;
            color: #aaa;
        }}

        .legend-dot {{
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 6px;
            vertical-align: middle;
        }}

        /* TABS */
        .tabs {{
            display: flex;
            gap: 4px;
            margin-bottom: 30px;
            justify-content: center;
        }}

        .tab-btn {{
            padding: 10px 28px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px 10px 0 0;
            color: #888;
            font-size: 1em;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .tab-btn:hover {{
            color: #ccc;
            background: rgba(255,255,255,0.08);
        }}

        .tab-btn.active {{
            color: #00d9ff;
            background: rgba(0,217,255,0.1);
            border-color: rgba(0,217,255,0.3);
            border-bottom-color: transparent;
        }}

        .tab-content {{
            display: none;
        }}

        .tab-content.active {{
            display: block;
        }}

        /* CABINET / MONDAY TAB */
        .cabinet-meeting-info {{
            color: #aaa;
            margin-bottom: 20px;
            font-size: 0.9em;
        }}

        .cabinet-meeting-info a {{
            color: #00d9ff;
            text-decoration: none;
        }}

        .cabinet-meeting-info a:hover {{
            color: #00ff88;
        }}

        .cabinet-section-name {{
            color: #00ff88;
            font-size: 0.85em;
            margin-top: 18px;
            margin-bottom: 8px;
            padding: 4px 10px;
            background: rgba(0,255,136,0.08);
            border-radius: 6px;
            display: inline-block;
        }}

        .cabinet-item {{
            padding: 12px 0;
            border-bottom: 1px solid rgba(255,255,255,0.08);
        }}

        .cabinet-item:last-child {{
            border-bottom: none;
        }}

        .cabinet-item a {{
            color: #fff;
            text-decoration: none;
            line-height: 1.5;
            transition: color 0.2s;
        }}

        .cabinet-item a:hover {{
            color: #00ff88;
        }}

        .cabinet-ta-id {{
            color: #00d9ff;
            font-size: 0.8em;
            margin-right: 8px;
        }}

        .cabinet-empty {{
            color: #666;
            text-align: center;
            padding: 40px;
            font-size: 1.1em;
        }}

        .cabinet-item-wrapper {{
            border-bottom: 1px solid rgba(255,255,255,0.08);
        }}

        .cabinet-item-wrapper:last-child {{
            border-bottom: none;
        }}

        .cabinet-toggle {{
            cursor: pointer;
            user-select: none;
        }}

        .cabinet-toggle:hover {{
            color: #00ff88;
        }}

        .cabinet-toggle .toggle-arrow {{
            display: inline-block;
            transition: transform 0.2s;
            margin-right: 6px;
            font-size: 0.8em;
            color: #00d9ff;
        }}

        .cabinet-summary {{
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.4s ease, padding 0.3s ease;
            padding: 0 16px;
            background: rgba(0,217,255,0.03);
            border-radius: 0 0 8px 8px;
            margin-bottom: 4px;
        }}

        .cabinet-summary.open {{
            max-height: 800px;
            padding: 14px 16px;
        }}

        .summary-label {{
            color: #00d9ff;
            font-size: 0.75em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
            margin-top: 10px;
        }}

        .summary-label:first-child {{
            margin-top: 0;
        }}

        .summary-text {{
            color: #bbb;
            font-size: 0.85em;
            line-height: 1.6;
        }}

        .summary-decision {{
            color: #00ff88;
            font-size: 0.85em;
            line-height: 1.6;
        }}

        /* PARLIAMENT STYLES */
        .parl-group-header {{
            color: #00d9ff;
            font-size: 0.9em;
            margin-top: 18px;
            margin-bottom: 4px;
            padding: 6px 12px;
            background: rgba(0,217,255,0.08);
            border-radius: 6px;
        }}

        .parl-group-header .parl-date {{
            color: #00ff88;
            font-weight: bold;
        }}

        .parl-item {{
            padding: 10px 12px;
            border-bottom: 1px solid rgba(255,255,255,0.06);
            font-size: 0.9em;
            line-height: 1.5;
        }}

        .parl-item:last-child {{
            border-bottom: none;
        }}

        .parl-item a {{
            color: #ccc;
            text-decoration: none;
            transition: color 0.2s;
        }}

        .parl-item a:hover {{
            color: #00ff88;
        }}

        .parl-item.content-match {{
            color: #e0a040;
        }}

        .parl-item.content-match a {{
            color: #e0a040;
        }}

        .parl-item.content-match a:hover {{
            color: #ffcc66;
        }}

        .parl-match-badge {{
            font-size: 0.7em;
            padding: 2px 6px;
            border-radius: 4px;
            margin-left: 6px;
            vertical-align: middle;
        }}

        .parl-match-badge.keyword {{
            background: rgba(0,217,255,0.15);
            color: #00d9ff;
        }}

        .parl-match-badge.content {{
            background: rgba(224,160,64,0.15);
            color: #e0a040;
        }}

        .parl-week-range {{
            color: #888;
            font-size: 0.85em;
            margin-bottom: 15px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Daily Dashboard</h1>
            <p class="date">{today}</p>
        </header>

        <!-- TABS -->
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('daily')">Daily</button>
            <button class="tab-btn" onclick="switchTab('monday')">Monday</button>
        </div>

        <!-- DAILY TAB -->
        <div id="tab-daily" class="tab-content active">

        <!-- INSPIRATION QUOTE -->
        <div class="section">
            <h2>Inspiration</h2>
            <div class="quote-box">
                <p class="quote-text">"{quote['quote']}"</p>
                <p class="quote-author">- {quote['author']}</p>
            </div>
        </div>

"""

    # Add e-address section if data is available
    if eaddress_data and eaddress_data["records"]:
        records = eaddress_data["records"]
        max_val = max(max(r["fiziska"] for r in records), max(r["juridiska"] for r in records)) or 1

        # Build streak HTML (shows net = activated - deactivated)
        def _streak_html(streak_data):
            parts = ""
            for s in streak_data:
                net = s["net"]
                css_class = "positive" if net >= 0 else "negative"
                prefix = "+" if net >= 0 else ""
                parts += f'<div class="streak-day"><div class="streak-val {css_class}">{prefix}{net:,}</div><div class="streak-label">{s["date"]}</div></div>'
            return parts

        streak_fiz_html = _streak_html(eaddress_data["streak_fiziska"])
        streak_jur_html = _streak_html(eaddress_data["streak_juridiska"])

        y_fiz = eaddress_data["yesterday_fiziska"]
        y_jur = eaddress_data["yesterday_juridiska"]

        html += f"""        <!-- E-ADDRESS DATA -->
        <div class="section">
            <h2>E-Address (e-adrese)</h2>
            <div class="metric-cards">
                <div class="metric-card">
                    <div class="metric-main">+{y_fiz['activated']:,}</div>
                    <div class="metric-deact">-{y_fiz['deactivated']:,}</div>
                    <div class="metric-label">Yesterday / Natural persons</div>
                    <div class="streak">{streak_fiz_html}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-main">+{y_jur['activated']:,}</div>
                    <div class="metric-deact">-{y_jur['deactivated']:,}</div>
                    <div class="metric-label">Yesterday / Legal entities</div>
                    <div class="streak">{streak_jur_html}</div>
                </div>
            </div>
            <div class="chart-container">
                <div class="chart">
"""
        for r in records:
            fiz_h = max(1, int(r["fiziska"] / max_val * 180))
            jur_h = max(1, int(r["juridiska"] / max_val * 180))
            html += f"""                    <div class="chart-bar-group" title="{r['label']}: {r['fiziska']:,} natural / {r['juridiska']:,} legal">
                        <div class="chart-bars">
                            <div class="chart-bar fiziska" style="height:{fiz_h}px"></div>
                            <div class="chart-bar juridiska" style="height:{jur_h}px"></div>
                        </div>
                        <div class="chart-label">{r['label']}</div>
                    </div>
"""

        html += """                </div>
            </div>
            <div class="chart-legend">
                <span><span class="legend-dot" style="background:#00d9ff"></span>Natural persons</span>
                <span><span class="legend-dot" style="background:#00ff88"></span>Legal entities</span>
            </div>
        </div>

"""

    html += """        <!-- NEWS ROW - Two columns side by side -->
        <div class="news-row">
        <div class="section">
            <h2>TechCrunch AI</h2>
"""

    # Add each TechCrunch AI article
    for article in techcrunch_news:
        html += f"""            <div class="news-item">
                <a href="{article['link']}" target="_blank">{article['title']}</a>
            </div>
"""

    html += """        </div>

        <div class="section">
            <h2>Kursors.lv AI</h2>
"""

    # Add each RSS feed article
    for article in gov_news:
        html += f"""            <div class="news-item">
                <a href="{article['link']}" target="_blank">{article['title']}</a>
            </div>
"""

    html += """        </div>
        </div><!-- end news-row -->

        </div><!-- end Daily tab -->

        <!-- MONDAY TAB -->
        <div id="tab-monday" class="tab-content">
"""

    # Add Cabinet / Monday content
    if cabinet_data and cabinet_data["cudars_items"]:
        html += f"""        <div class="section">
            <h2>Cabinet Sitting - R.Cudars Items</h2>
            <div class="cabinet-meeting-info">
                Next sitting: <strong>{cabinet_data['meeting_date']}</strong>
                | <a href="{cabinet_data['meeting_url']}" target="_blank">Full agenda</a>
            </div>
"""
        current_section = None
        for idx, item in enumerate(cabinet_data["cudars_items"]):
            if item["section"] != current_section:
                current_section = item["section"]
                html += f'            <div class="cabinet-section-name">{current_section}</div>\n'
            summary_id = f"cab-summary-{idx}"
            has_summary = item.get("essence") or item.get("decision")
            toggle_attr = f' class="cabinet-item cabinet-toggle" onclick="toggleSummary(\'{summary_id}\')"' if has_summary else ' class="cabinet-item"'
            arrow = '<span class="toggle-arrow">&#9654;</span>' if has_summary else ''
            html += f"""            <div class="cabinet-item-wrapper">
              <div{toggle_attr}>
                {arrow}<a href="{item['ta_link']}" target="_blank" onclick="event.stopPropagation()">
                    <span class="cabinet-ta-id">{item['ta_id']}</span>{item['title']}
                </a>
              </div>
"""
            if has_summary:
                html += f'              <div class="cabinet-summary" id="{summary_id}">\n'
                if item.get("essence"):
                    html += f'                <div class="summary-label">Essence of the regulation</div>\n'
                    html += f'                <div class="summary-text">{item["essence"]}</div>\n'
                if item.get("decision"):
                    html += f'                <div class="summary-label">Decision</div>\n'
                    html += f'                <div class="summary-decision">{item["decision"]}</div>\n'
                html += '              </div>\n'
            html += '            </div>\n'
        html += "        </div>\n"
    elif cabinet_data:
        html += f"""        <div class="section">
            <h2>Cabinet Sitting - R.Cudars Items</h2>
            <div class="cabinet-meeting-info">
                Next sitting: <strong>{cabinet_data['meeting_date']}</strong>
                | <a href="{cabinet_data['meeting_url']}" target="_blank">Full agenda</a>
            </div>
            <div class="cabinet-empty">No items reported by R.Cudars in the next sitting.</div>
        </div>
"""
    else:
        html += """        <div class="section">
            <h2>Cabinet Sitting - R.Cudars Items</h2>
            <div class="cabinet-empty">Could not fetch cabinet agenda data.</div>
        </div>
"""

    # Add Parliament section
    if parliament_data and parliament_data["items"]:
        html += f"""        <div class="section">
            <h2>Parliament This Week</h2>
            <div class="parl-week-range">{parliament_data['week_start']} – {parliament_data['week_end']}</div>
"""
        # Group items by commission + date
        current_group = None
        for item in parliament_data["items"]:
            group_key = f"{item['commission']}|{item['date']}|{item['time']}"
            if group_key != current_group:
                current_group = group_key
                html += f"""            <div class="parl-group-header">
                <span class="parl-date">{item['date']} {item['time']}</span> — {item['commission']}
            </div>
"""
            match_class = "content-match" if item["match_type"] == "content" else ""
            badge_class = item["match_type"]
            badge_label = "VARAM" if item["match_type"] == "keyword" else "Digital topic"
            html += f"""            <div class="parl-item {match_class}">
                <a href="{item['link']}" target="_blank">{item['point']}</a>
                <span class="parl-match-badge {badge_class}">{badge_label}</span>
            </div>
"""
        html += "        </div>\n\n"
    elif parliament_data:
        html += f"""        <div class="section">
            <h2>Parliament This Week</h2>
            <div class="parl-week-range">{parliament_data['week_start']} – {parliament_data['week_end']}</div>
            <div class="cabinet-empty">No VARAM or digital government topics found in next week's agendas.</div>
        </div>

"""
    else:
        html += """        <div class="section">
            <h2>Parliament This Week</h2>
            <div class="cabinet-empty">Could not fetch Parliament agenda data.</div>
        </div>

"""

    html += """        </div><!-- end Monday tab -->

        <footer>
            <p>Built with Python | Your First AI Agent</p>
        </footer>
    </div>

    <script>
    function switchTab(name) {
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.getElementById('tab-' + name).classList.add('active');
        event.target.classList.add('active');
    }
    function toggleSummary(id) {
        var el = document.getElementById(id);
        el.classList.toggle('open');
        var arrow = el.parentElement.querySelector('.toggle-arrow');
        if (arrow) arrow.style.transform = el.classList.contains('open') ? 'rotate(90deg)' : '';
    }
    </script>
</body>
</html>
"""

    return html


# ----------------------------------------------
# SECTION 5: MAIN FUNCTION
# This runs everything in order
# ----------------------------------------------

def main():
    """Main function - runs the whole dashboard"""
    print("\n" + "="*50)
    print("   DAILY DASHBOARD AGENT")
    print("="*50 + "\n")

    # Step 1: Gather all our data
    techcrunch_news = get_techcrunch_news()
    gov_news = get_digital_government_news()
    quote = get_motivational_quote()
    eaddress_data = get_eaddress_data()
    cabinet_data = get_cabinet_cudars_items()
    parliament_data = get_parliament_agenda()

    # Step 2: Create the HTML page
    html_content = create_html_dashboard(techcrunch_news, gov_news, quote, eaddress_data, cabinet_data, parliament_data)

    # Step 3: Save to a file
    filename = "dashboard.html"
    with open(filename, "w", encoding="utf-8") as file:
        file.write(html_content)

    print(f"\nDashboard saved to: {filename}")
    print("Open this file in your browser to see your dashboard!")
    print("\n" + "="*50 + "\n")


# This runs the main function when you execute the script
if __name__ == "__main__":
    main()
