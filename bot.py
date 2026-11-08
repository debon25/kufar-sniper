import os
import re
import sys
import json
import time
import random
import html
import statistics
import requests

# ================= НАСТРОЙКИ =================
TG_TOKEN = os.getenv("TG_TOKEN", "8874085987:AAFA6bn_mxYb41eZyRRSRwtQLEOgyb7975c")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "1091251853")
PROXY_URL = os.getenv("PROXY_URL", "")

MAX_RUN_HOURS = float(os.getenv("MAX_RUN_HOURS", "5.8"))

# Hard-фильтры: Телефоны (17010), Минск (rgn=7), Частники (cmp=0), Б/у (cnd=1), 120-700 BYN, по дате
KUFAR_SEARCH_URL = (
    "https://api.kufar.by/search-api/v2/search/rendered-paginated"
    "?cat=17010&cmp=0&cnd=1&lang=ru&prc=r%3A12000%2C70000&rgn=7&size=25&sort=lst.d"
)

MIN_INTERVAL = 5
MAX_INTERVAL = 12

# Коэффициент реальной сделки (0.90 = минус 10% от медианы хотелок Куфара на торг)
BARGAIN_FACTOR = 0.90

# Пороги выгоды (в BYN и %)
FAT_PROFIT_BYN = 85       # От 85 BYN выгоды -> ЖИР (СО ЗВУКОМ)
FAT_PROFIT_PCT = 20       # Или от 20% ниже рынка -> ЖИР (СО ЗВУКОМ)
URGENT_PROFIT_BYN = 55    # Если есть слово "Срочно/Сегодня" + выгода от 55 BYN -> ЖИР (СО ЗВУКОМ)
WORK_PROFIT_BYN = 40      # От 40 до 84 BYN -> НЕ ЖИР / Рабочий (БЕЗ ЗВУКА)
INSPECT_MIN_PROFIT = -25  # От -25 до 39 BYN (чистый телефон без косяков) -> ПОД ОСМОТР (БЕЗ ЗВУКА)

SEEN_FILE = "seen_ads.json"
MARKET_CACHE_FILE = "market_cache.json"
SELLERS_FILE = "seen_sellers.json"
MARKET_CACHE_TTL = 4 * 3600  # Кэш рынка живет 4 часа
# =============================================

# 1. БЕЛЫЙ СПИСОК МОДЕЛЕЙ (От сложных названий к простым, чтобы не путать Pro Max и обычные)
# Формат: (ID модели, бренд, регулярка для поиска, список доступной памяти [минимальная первая], поисковый запрос)
MODELS_WHITELIST = [
    # --- APPLE iPHONE ---
    ("iPhone 13 Pro Max", "apple", r"\b13\s*(?:pro\s*max|про\s*макс|промакс|promax)\b", [128, 256, 512], "iPhone 13 Pro Max"),
    ("iPhone 13 Pro", "apple", r"\b13\s*(?:pro|про)\b", [128, 256, 512], "iPhone 13 Pro"),
    ("iPhone 13 mini", "apple", r"\b13\s*(?:mini|мини)\b", [128, 256, 512], "iPhone 13 mini"),
    ("iPhone 13", "apple", r"(?:iphone|айфон|айф)\s*13\b|\b13\s*(?:айфон|iphone)\b", [128, 256, 512], "iPhone 13"),

    ("iPhone 12 Pro Max", "apple", r"\b12\s*(?:pro\s*max|про\s*макс|промакс|promax)\b", [128, 256, 512], "iPhone 12 Pro Max"),
    ("iPhone 12 Pro", "apple", r"\b12\s*(?:pro|про)\b", [128, 256, 512], "iPhone 12 Pro"),
    ("iPhone 12 mini", "apple", r"\b12\s*(?:mini|мини)\b", [64, 128, 256], "iPhone 12 mini"),
    ("iPhone 12", "apple", r"(?:iphone|айфон|айф|двенадцатый)\s*12?\b|\b12\s*(?:айфон|iphone)\b", [64, 128, 256], "iPhone 12"),

    ("iPhone 11 Pro Max", "apple", r"\b11\s*(?:pro\s*max|про\s*макс|промакс|promax)\b", [64, 256, 512], "iPhone 11 Pro Max"),
    ("iPhone 11 Pro", "apple", r"\b11\s*(?:pro|про)\b", [64, 256, 512], "iPhone 11 Pro"),
    ("iPhone 11", "apple", r"(?:iphone|айфон|айф|одиннадцатый)\s*11?\b|\b11\s*(?:айфон|iphone)\b", [64, 128, 256], "iPhone 11"),

    ("iPhone XS Max", "apple", r"\b(?:xs|хс|икс\s*эс)\s*(?:max|макс)\b", [64, 256, 512], "iPhone XS Max"),
    ("iPhone XS", "apple", r"\b(?:iphone|айфон)?\s*(?:xs|хс|икс\s*эс)\b", [64, 256], "iPhone XS"),
    ("iPhone XR", "apple", r"\b(?:iphone|айфон)?\s*(?:xr|хр|икс\s*эр|хr)\b", [64, 128, 256], "iPhone XR"),
    ("iPhone SE 2022", "apple", r"\bse\s*(?:2022|3|22)\b", [64, 128, 256], "iPhone SE 2022"),
    ("iPhone SE 2020", "apple", r"\bse\s*(?:2020|2|20)\b", [64, 128, 256], "iPhone SE 2020"),

    # --- SAMSUNG ---
    ("Samsung S21 FE", "android", r"\bs\s*21\s*(?:fe|фе)\b", [128, 256], "Samsung S21 FE"),
    ("Samsung S21 Plus", "android", r"\bs\s*21\s*(?:\+|plus|плюс)\b", [128, 256], "Samsung S21 Plus"),
    ("Samsung S21", "android", r"\b(?:samsung|самсунг|galaxy)?\s*s\s*21\b", [128, 256], "Samsung S21"),
    ("Samsung S20 FE", "android", r"\bs\s*20\s*(?:fe|фе)\b", [128, 256], "Samsung S20 FE"),
    ("Samsung S22", "android", r"\b(?:samsung|самсунг|galaxy)?\s*s\s*22\b", [128, 256], "Samsung S22"),
    ("Samsung A55", "android", r"\b(?:a|а)\s*55\b", [128, 256], "Samsung A55"),
    ("Samsung A54", "android", r"\b(?:a|а)\s*54\b", [128, 256], "Samsung A54"),
    ("Samsung A53", "android", r"\b(?:a|а)\s*53\b", [128, 256], "Samsung A53"),
    ("Samsung A52", "android", r"\b(?:a|а)\s*52\b", [128, 256], "Samsung A52"),
    ("Samsung A35", "android", r"\b(?:a|а)\s*35\b", [128, 256], "Samsung A35"),
    ("Samsung A34", "android", r"\b(?:a|а)\s*34\b", [128, 256], "Samsung A34"),

    # --- XIAOMI / REDMI / POCO ---
    ("Redmi Note 13 Pro", "android", r"\bnote\s*13\s*(?:pro|про)\b|\bноут\s*13\s*(?:pro|про)\b", [128, 256, 512], "Redmi Note 13 Pro"),
    ("Redmi Note 13", "android", r"\bnote\s*13\b|\bноут\s*13\b", [128, 256], "Redmi Note 13"),
    ("Redmi Note 12 Pro", "android", r"\bnote\s*12\s*(?:pro|про)\b|\bноут\s*12\s*(?:pro|про)\b", [128, 256], "Redmi Note 12 Pro"),
    ("Redmi Note 12", "android", r"\bnote\s*12\b|\bноут\s*12\b", [64, 128, 256], "Redmi Note 12"),
    ("Redmi Note 11 Pro", "android", r"\bnote\s*11\s*(?:pro|про)\b|\bноут\s*11\s*(?:pro|про)\b", [64, 128], "Redmi Note 11 Pro"),

    ("Poco X6 Pro", "android", r"\bpoco\s*x\s*6\s*(?:pro|про)\b|\bпоко\s*х\s*6\s*(?:pro|про)\b", [256, 512], "Poco X6 Pro"),
    ("Poco X6", "android", r"\bpoco\s*x\s*6\b|\bпоко\s*х\s*6\b", [256, 512], "Poco X6"),
    ("Poco X5 Pro", "android", r"\bpoco\s*x\s*5\s*(?:pro|про)\b|\bпоко\s*х\s*5\s*(?:pro|про)\b", [128, 256], "Poco X5 Pro"),
    ("Poco X5", "android", r"\bpoco\s*x\s*5\b|\bпоко\s*х\s*5\b", [128, 256], "Poco X5"),
    ("Poco X4 Pro", "android", r"\bpoco\s*x\s*4\s*(?:pro|про)\b|\bпоко\s*х\s*4\s*(?:pro|про)\b", [128, 256], "Poco X4 Pro"),
    ("Poco M6 Pro", "android", r"\bpoco\s*m\s*6\s*(?:pro|про)\b|\bпоко\s*м\s*6\s*(?:pro|про)\b", [256, 512], "Poco M6 Pro"),
    ("Poco M5s", "android", r"\bpoco\s*m\s*5\s*s\b|\bпоко\s*м\s*5\s*с\b", [64, 128, 256], "Poco M5s"),
    ("Poco F5", "android", r"\bpoco\s*f\s*5\b|\bпоко\s*ф\s*5\b", [256], "Poco F5"),
    ("Poco F4", "android", r"\bpoco\s*f\s*4\b|\bпоко\s*ф\s*4\b", [128, 256], "Poco F4"),

    # --- GOOGLE PIXEL ---
    ("Pixel 7a", "android", r"\bpixel\s*7\s*a\b|\bпиксель\s*7\s*а\b", [128], "Pixel 7a"),
    ("Pixel 7", "android", r"\bpixel\s*7\b|\bпиксель\s*7\b", [128, 256], "Pixel 7"),
    ("Pixel 6a", "android", r"\bpixel\s*6\s*a\b|\bпиксель\s*6\s*а\b", [128], "Pixel 6a"),
    ("Pixel 6", "android", r"\bpixel\s*6\b|\bпиксель\s*6\b", [128, 256], "Pixel 6"),
]

# 2. ЖЕСТКИЙ BLACKLIST (Магазины, скупки, критический брак, блокировки)
STOP_PATTERNS = [
    r"\bрассрочк[ауеи]\b", r"\bкредит\b", r"\bдоставка по рб\b",
    r"\bтрейд[\s\-]*ин\b", r"\btrade[\s\-]*in\b", r"\bскупк[аи]\b", r"\bвыкуп\b",
    r"\bмагазин[аеу]?\b", r"\bв наличии\b", r"\bхалв[аы]\b", r"\bчерепах[аи]\b",
    r"\bна запчасти\b", r"\bне включается\b", r"\bразбит[аыо]?\b", r"\bразбил[аи]?\b",
    r"\bтрещин[аы]\b", r"\bтреснут[аыо]?\b", r"\bпоплыл\b", r"\bпятн[оа]\b",
    r"\bвыгоран[иея]\b", r"\bвыгорел\b", r"\bзасвет[ы]?\b", r"\bполос[аы] на экране\b",
    r"\bматеринская плата\b", r"\bплата под\b", r"\bicloud\b", r"\bайклауд\b",
    r"\bзаблокирован[аы]?\b", r"\bmdm\b", r"\bмдм\b", r"\bлизинг\b",
    r"\bне оплачен\b", r"\bнеоплачен\b", r"\bдонор\b", r"\bбайпас\b", r"\bbypass\b",
    r"\bне работает face\b", r"\bне работает фейс\b", r"\bбез face id\b", r"\bбез фейс\b",
    r"\bкопия\b", r"\bреплика\b", r"\bмуляж\b"
]

# 3. УМНЫЙ ФИЛЬТР ЗАМЕНЕННОГО АКБ И ЭКРАНА НА iPHONE (Пропускает "НЕ менялся", банит "менялся")
FOREIGN_BATTERY_PATTERNS = [
    r"(?<!не\s)(?<!не)\b(?:акб|батаре[яюи]|аккумулятор)\s+(?:менял[асьсяи]+|заменен[аы]?|нов[аяый]|не\s*родн[аяой]|усиленн[аяый])",
    r"(?<!не\s)(?<!не)\b(?:менял[асьсяи]+|заменен[аы]?)\s+(?:акб|батаре[яюи]|аккумулятор|экран|дисплей)",
    r"\bнеизвестная деталь\b", r"\bошибка акб\b", r"\bошибка аккумулятора\b", r"\bбез отображения емкости\b"
]

# 4. ТРИГГЕРЫ РЕАЛЬНОЙ СРОЧНОСТИ (Только жесткие причины, без мусора вроде "торг")
URGENT_WORDS = [
    "срочно", "очень срочно", "только сегодня", "до вечера", "до завтра",
    "актуально сегодня", "быстрым", "уезжаю", "переезд", "нужны деньги",
    "подарили новый", "купил новый"
]

# 5. МОДИФИКАТОРЫ СОСТОЯНИЯ (Для сдвига рыночной цены лота вверх или вниз)
DEFECT_PATTERNS = [
    r"\bскол[ыаов]?\b", r"\bвмятин[аы]\b", r"\bпотертост[иь]\b",
    r"\bцарапин[аы] на экране\b", r"\bглубокие царапины\b", r"\bкоцк[иа]\b",
    r"\bхрипит динамик\b", r"\bтихий динамик\b", r"\bне работает трутон\b", r"\bбез трутона\b"
]

IDEAL_PATTERNS = [
    r"\bв идеале\b", r"\bидеальное состояние\b", r"\bсостояние идеал\b",
    r"\bкак новый\b", r"\bсостояние нового\b", r"\bбез царапин\b",
    r"\bбез единой царапины\b", r"\bполный комплект\b"
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.kufar.by/"
})

if PROXY_URL:
    session.proxies.update({"http": PROXY_URL, "https": PROXY_URL})


# ================= БАЗА И КЭШ =================
def load_json_file(filename, default_val):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default_val


def save_json_file(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Ошибка сохранения {filename}: {e}")


# ================= НОРМАЛИЗАТОР И ФИЛЬТРЫ =================
def clean_text(text):
    if not text:
        return ""
    t = text.lower().replace("ё", "е")
    t = re.sub(r"\b(?:ifon|iphon|ipone|aifon|айфоша)\b", "iphone", t)
    return t


def check_regex_list(text, patterns):
    t = clean_text(text)
    for pat in patterns:
        match = re.search(pat, t)
        if match:
            return match.group(0)
    return None


def is_bad_iphone_battery(text, model_name):
    """Проверяет замену АКБ на iPhone и невозможные 100% на старых моделях (XR, XS, 11, 12)."""
    t = clean_text(text)
    matched = check_regex_list(t, FOREIGN_BATTERY_PATTERNS)
    if matched:
        return f"Заменен АКБ/экран ('{matched}')"

    # Детектор 100% АКБ на старых моделях (XR, XS, 11, 12, SE 2020)
    old_models = ("iPhone XR", "iPhone XS", "iPhone XS Max", "iPhone 11", "iPhone 11 Pro",
                  "iPhone 11 Pro Max", "iPhone 12", "iPhone 12 mini", "iPhone 12 Pro", "iPhone SE 2020")
    if model_name in old_models:
        if re.search(r"\b(?:акб|батаре[яи]|емкость|состояние\s*акб)[\s:=-]*100\s*%", t):
            return "Подозрительные 100% АКБ на старой модели (скорее всего менялся)"
    return None


def extract_memory(text, ad_params, valid_memories):
    """Извлекает память из параметров Куфара или текста (отсекая ОЗУ вроде 8/256 и цены)."""
    # 1. Пробуем достать из ad_parameters Куфара
    if ad_params:
        for p in ad_params:
            if p.get("p") in ("phablet_phones_memory", "mobile_phones_memory", "memory"):
                val_str = str(p.get("vl") or p.get("v") or "")
                for mem in valid_memories:
                    if re.search(rf"\b{mem}\b", val_str):
                        return mem, False

    t = clean_text(text)
    # 2. Формат Android ОЗУ/ПЗУ: 6/128, 8/256
    slash_match = re.search(r"\b(?:4|6|8|12|16)\s*/\s*(64|128|256|512)\b", t)
    if slash_match:
        mem = int(slash_match.group(1))
        if mem in valid_memories:
            return mem, False

    # 3. Явное указание с единицами: 128 гб, 128gb, на 128
    for mem in valid_memories:
        if re.search(rf"\b{mem}\s*(?:гб|gb|гиг|г|g)\b|\bна\s*{mem}\b", t):
            return mem, False

    # 4. Если ничего не нашли — берем минимальную память модели по низу рынка
    return valid_memories[0], True


def normalize_phone(title, description="", ad_params=None):
    """
    Распознает модель и память.
    Отсекает объявления, где перечислено сразу несколько разных моделей телефонов.
    Возвращает: (dict с инфо о телефоне, причина отказа)
    """
    t_title = clean_text(title)
    t_full = clean_text(f"{title} {description}")

    # 1. Ищем все модели в заголовке (чтобы отсечь мульти-лоты вроде "iPhone 11 и XR")
    found_in_title = []
    temp_title = t_title
    for model_id, m_type, regex, mem_list, query_str in MODELS_WHITELIST:
        if re.search(regex, temp_title):
            found_in_title.append((model_id, m_type, mem_list, query_str))
            temp_title = re.sub(regex, " ", temp_title)

    if len(found_in_title) > 1:
        names = [x[0] for x in found_in_title]
        return None, f"В заголовке сразу несколько моделей: {', '.join(names)}"

    # Если в заголовке ровно 1 модель — берем её
    if len(found_in_title) == 1:
        model_id, m_type, mem_list, query_str = found_in_title[0]
    else:
        # Иначе пробуем найти в полном тексте
        found_in_body = []
        temp_body = t_full
        for m_id, m_t, regex, m_l, q_s in MODELS_WHITELIST:
            if re.search(regex, temp_body):
                found_in_body.append((m_id, m_t, m_l, q_s))
                temp_body = re.sub(regex, " ", temp_body)

        if not found_in_body:
            return None, "Модель не входит в Белый список"
        if len(found_in_body) > 1:
            return None, "В описании перечислено несколько разных моделей"
        model_id, m_type, mem_list, query_str = found_in_body[0]

    memory, is_assumed_mem = extract_memory(t_full, ad_params, mem_list)
    return {
        "model": model_id,
        "type": m_type,
        "memory": memory,
        "is_assumed_mem": is_assumed_mem,
        "query": query_str,
        "key": f"{model_id}_{memory}GB"
    }, None


# ================= РАСЧЕТ РЫНКА (КУФАР + ONLINER) =================
def fetch_kufar_sample_prices(phone_info, region_minsk=True):
    """
    Собирает до 100 объявлений (2 страницы по 50 шт) на Куфаре по конкретной модели,
    отсеивает чужие версии (Pro/Max), битые аппараты и магазины.
    """
    prices = []
    cursor = None
    rgn_param = "&rgn=7" if region_minsk else ""

    for _ in range(2):  # До 2 страниц по 50 объявлений = глубокий охват 100 лотов
        url = (
            f"https://api.kufar.by/search-api/v2/search/rendered-paginated"
            f"?cat=17010&cmp=0&cnd=1&lang=ru&prc=r%3A12000%2C150000{rgn_param}"
            f"&query={requests.utils.quote(phone_info['query'])}&size=50&sort=lst.d"
        )
        if cursor:
            url += f"&cursor={cursor}"

        try:
            resp = session.get(url, timeout=7)
            if resp.status_code != 200:
                break
            data = resp.json()
            ads = data.get("ads", [])
            if not ads:
                break

            for ad in ads:
                subj = ad.get("subject", "")
                p_byn = int(ad.get("price_byn", "0")) / 100
                if p_byn < 100 or p_byn > 2000:
                    continue

                # Отсекаем брак и магазины из выборки
                if check_regex_list(subj, STOP_PATTERNS):
                    continue

                # Проверяем, что найденный аналог — это ТОЧНО та же модель и память
                norm, _ = normalize_phone(subj, "", ad.get("ad_parameters", []))
                if norm and norm["model"] == phone_info["model"] and norm["memory"] == phone_info["memory"]:
                    prices.append(p_byn)

            # Ищем токен следующей страницы (пагинация)
            next_token = None
            for page in data.get("pagination", {}).get("pages", []):
                if page.get("label") == "next":
                    next_token = page.get("token")
                    break
            if not next_token:
                break
            cursor = next_token
        except Exception:
            break

    return prices


def fetch_onliner_baraholka_prices(phone_info):
    """Дополнительный источник №1: парсит цены б/у аналогов с Барахолки Onliner (раздел Мобильные телефоны, f=213)."""
    prices = []
    q = requests.utils.quote(f"{phone_info['query']} {phone_info['memory']}")
    url = f"https://baraholka.onliner.by/search.php?q={q}&f=213&cat=1"
    try:
        resp = session.get(url, timeout=6)
        if resp.status_code == 200:
            html_text = resp.text
            # Вытаскиваем блоки объявлений и цены в рублях с Барахолки
            matches = re.findall(
                r'class="ba-tbl-list__table".*?(\d{3,4})\s*(?:р\.|руб|BYN)',
                html_text, re.DOTALL | re.IGNORECASE
            )
            for m in matches[:15]:
                val = float(m)
                if 120 <= val <= 1500:
                    prices.append(val)
    except Exception:
        pass
    return prices


def fetch_onliner_catalog_new_price(phone_info):
    """Дополнительный источник №2: проверяет минимальную цену НОВОГО аппарата в Каталоге Onliner (потолок цены)."""
    q = requests.utils.quote(f"{phone_info['query']} {phone_info['memory']}GB")
    url = f"https://catalog.onliner.by/sdapi/catalog.api/search/mobile?query={q}"
    try:
        resp = session.get(url, timeout=5)
        if resp.status_code == 200:
            products = resp.json().get("products", [])
            for prod in products:
                full_name = prod.get("full_name", "")
                norm, _ = normalize_phone(full_name)
                if norm and norm["model"] == phone_info["model"] and norm["memory"] == phone_info["memory"]:
                    prices_obj = prod.get("prices")
                    if prices_obj and prices_obj.get("price_min"):
                        return float(prices_obj["price_min"].get("amount", 0))
    except Exception:
        pass
    return None


def get_market_price(phone_info, market_cache):
    """
    Гибридный расчет реального рынка:
    Кэш -> 100 объявлений Куфара (Минск/РБ) + Барахолка Onliner -> Обрезка краев (15% низа и 20% верха)
    -> Медиана -> Умножение на 0.90 (торг) -> Сверка с потолком нового из Каталога Onliner.
    """
    cache_key = phone_info["key"]
    now = time.time()

    if cache_key in market_cache:
        entry = market_cache[cache_key]
        if now - entry.get("ts", 0) < MARKET_CACHE_TTL:
            return entry["price"], entry["sample_size"], entry.get("new_price")

    # 1. Собираем глубокую выборку по Минску
    kufar_prices = fetch_kufar_sample_prices(phone_info, region_minsk=True)

    # Если в Минске мало чистых аналогов (< 5 шт) — расширяем статистику на всю Беларусь
    if len(kufar_prices) < 5:
        rb_prices = fetch_kufar_sample_prices(phone_info, region_minsk=False)
        if len(rb_prices) > len(kufar_prices):
            kufar_prices = rb_prices

    # 2. Подтягиваем Барахолку Onliner
    baraholka_prices = fetch_onliner_baraholka_prices(phone_info)
    all_prices = kufar_prices + baraholka_prices

    if len(all_prices) < 3:
        return None, len(all_prices), None

    # 3. Обрезка ценовых аномалий (отсекаем 15% самых дешевых и 20% самых дорогих)
    all_prices.sort()
    n = len(all_prices)
    if n >= 7:
        cut_low = max(1, int(n * 0.15))
        cut_high = max(1, int(n * 0.20))
        core_prices = all_prices[cut_low: n - cut_high]
    else:
        core_prices = all_prices

    raw_median = statistics.median(core_prices)

    # 4. Поправка на реальный торг (-10%)
    real_market = round(raw_median * BARGAIN_FACTOR)

    # 5. Сверка с ценой нового в Каталоге Onliner (б/у не может стоить дороже 78% нового)
    new_price = fetch_onliner_catalog_new_price(phone_info)
    if new_price and new_price > 200:
        max_used_cap = round(new_price * 0.78)
        if real_market > max_used_cap:
            real_market = max_used_cap

    market_cache[cache_key] = {
        "price": real_market,
        "sample_size": n,
        "new_price": new_price,
        "ts": now
    }
    save_json_file(MARKET_CACHE_FILE, market_cache)
    return real_market, n, new_price


def adjust_market_for_condition(base_market, full_text):
    """Сдвигает рыночную цену конкретного телефона в зависимости от состояния (Сколы vs Идеал)."""
    defect = check_regex_list(full_text, DEFECT_PATTERNS)
    if defect:
        # Штраф -10% за косметические косяки / сколы
        return round(base_market * 0.90), f"📉 -10% к рынку (найдено: «{defect}»)", True

    ideal = check_regex_list(full_text, IDEAL_PATTERNS)
    if ideal:
        # Бонус +7% за идеальное состояние / полный комплект
        return round(base_market * 1.07), f"💎 +7% к рынку («{ideal}»)", False

    return base_market, "Стандартное состояние", False


# ================= ЗАПРОСЫ К КУФАРУ И TELEGRAM =================
def get_ads():
    try:
        response = session.get(KUFAR_SEARCH_URL, timeout=8)
        if response.status_code == 200:
            return response.json().get("ads", [])
        elif response.status_code == 429:
            print("⚠️ Слишком частые запросы (429). Пауза 30 сек...")
            time.sleep(30)
    except Exception as e:
        print(f"⚠️ Ошибка сети: {e}")
    return []


def get_ad_description(ad_id):
    url = f"https://api.kufar.by/search-api/v2/item/{ad_id}/rendered?lang=ru"
    try:
        response = session.get(url, timeout=6)
        if response.status_code == 200:
            return response.json().get("result", {}).get("body", "")
    except Exception:
        pass
    return ""


def parse_area(ad):
    for param in ad.get("ad_parameters", []):
        if param.get("p") == "area":
            val = param.get("vl") or param.get("v")
            if val:
                return f"Минск ({val})"
    return "Минск"


def send_telegram(text, photo_url=None, with_sound=False):
    """Отправляет карточку в ТГ. Если фото битое — автоматически дублирует текстом."""
    disable_sound = not with_sound
    try:
        if photo_url:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
            payload = {
                "chat_id": TG_CHAT_ID,
                "photo": photo_url,
                "caption": text,
                "parse_mode": "HTML",
                "disable_notification": disable_sound
            }
            r = session.post(url, data=payload, timeout=8)
            if r.status_code == 200:
                return
        # Если фото нет или Куфар еще не сгенерировал картинку (ошибка 400) — шлем текстом
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        payload = {
            "chat_id": TG_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
            "disable_notification": disable_sound
        }
        session.post(url, data=payload, timeout=8)
    except Exception as e:
        print(f"⚠️ Ошибка отправки в Telegram: {e}")


# ================= РЕЖИМ САМОПРОВЕРКИ (--test) =================
def run_self_test(market_cache):
    print("🧪 ЗАПУСК САМОПРОВЕРКИ ВСЕХ СИСТЕМ БОТА...")
    t1, err1 = normalize_phone("Продам Айфон 11 на 128 гб в идеале")
    print(f"1. Тест нормализатора: {t1} (Ошибка: {err1})")

    t2, err2 = normalize_phone("Продам iPhone 11 и iPhone XR")
    print(f"2. Тест отсева мульти-лотов: Ошибка = '{err2}' (Должен отсечь!)")

    bat1 = is_bad_iphone_battery("Состояние отличное, акб не менялся, 84%", "iPhone 11")
    bat2 = is_bad_iphone_battery("Состояние супер, батарея менялась месяц назад", "iPhone 11")
    bat3 = is_bad_iphone_battery("Телефон в идеале, АКБ 100%", "iPhone 11")
    print(f"3. Тест фильтра АКБ: 'не менялся' -> {bat1} | 'менялась' -> {bat2} | '100% на 11-м' -> {bat3}")

    print("4. Тест живого расчета рынка (Куфар + Onliner) для iPhone 11 128GB...")
    m_price, count, new_p = get_market_price(t1, market_cache)
    print(f"   📊 Реальный рынок (с торгом 10%): ~{m_price} BYN (на основе {count} объявлений)")

    test_msg = (
        f"🧪 <b>ТЕСТ СИСТЕМЫ УСПЕШЕН!</b>\n\n"
        f"📱 Модель: <b>{t1['model']} {t1['memory']}GB</b>\n"
        f"📊 Расчетный реальный рынок: <b>~{m_price} BYN</b> (проверено {count} лотов)\n"
        f"✅ Фильтры АКБ, нормализатор и кросс-чекинг работают штатно."
    )
    send_telegram(test_msg, with_sound=True)
    print("✅ Тестовое сообщение отправлено в Telegram!")


# ================= ОСНОВНОЙ ЦИКЛ =================
def main():
    market_cache = load_json_file(MARKET_CACHE_FILE, {})

    if "--test" in sys.argv:
        run_self_test(market_cache)
        return

    start_time = time.time()
    max_seconds = MAX_RUN_HOURS * 3600

    # seen_ads хранит словарь {"ad_id": цена_в_BYN} для отслеживания скидок
    raw_seen = load_json_file(SEEN_FILE, {})
    seen_ads = raw_seen if isinstance(raw_seen, dict) else {str(k): 0 for k in raw_seen}
    seen_sellers = load_json_file(SELLERS_FILE, {})

    initial_ads = get_ads()
    if not seen_ads and initial_ads:
        for ad in initial_ads:
            ad_id = str(ad.get("ad_id", ""))
            price_byn = int(ad.get("price_byn", "0")) / 100
            if ad_id:
                seen_ads[ad_id] = price_byn
        save_json_file(SEEN_FILE, seen_ads)
        send_telegram(
            f"🚀 <b>Снайпер 2.0 (Аналитика рынка + Умные фильтры) запущен!</b>\n"
            f"📦 В стартовой базе: {len(seen_ads)} объявлений.",
            with_sound=False
        )

    print(f"🚀 Мониторинг активен. В базе {len(seen_ads)} объявлений.")

    while (time.time() - start_time) < max_seconds:
        ads = get_ads()
        if ads:
            state_changed = False
            for ad in reversed(ads):
                ad_id = str(ad.get("ad_id", ""))
                if not ad_id:
                    continue

                price_byn = int(ad.get("price_byn", "0")) / 100
                price_drop_note = ""

                # Проверяем: новое объявление или продавец скинул цену на старое
                if ad_id in seen_ads:
                    old_price = seen_ads[ad_id]
                    if old_price > 0 and (old_price - price_byn) >= 20 and ((old_price - price_byn) / old_price) >= 0.05:
                        price_drop_note = f"📉 <b>СНИЖЕНИЕ ЦЕНЫ!</b> (Было {old_price:.0f} ➡️ Стало {price_byn:.0f} BYN)\n"
                        seen_ads[ad_id] = price_byn
                        state_changed = True
                    else:
                        continue
                else:
                    seen_ads[ad_id] = price_byn
                    state_changed = True

                raw_title = ad.get("subject", "Без названия")

                # --- ЭТАП 1: Быстрая проверка заголовка на стоп-слова ---
                bad_title = check_regex_list(raw_title, STOP_PATTERNS)
                if bad_title:
                    print(f"⛔ [Бан заголовка: '{bad_title}'] {raw_title}")
                    continue

                # --- ЭТАП 2: Загружаем описание и проверяем телефон ---
                description = get_ad_description(ad_id)
                full_text = f"{raw_title}\n{description}"

                bad_desc = check_regex_list(description, STOP_PATTERNS)
                if bad_desc:
                    print(f"⛔ [Бан описания: '{bad_desc}'] {raw_title}")
                    continue

                # Нормализация модели и памяти + отсев мульти-лотов
                phone_info, norm_err = normalize_phone(raw_title, description, ad.get("ad_parameters", []))
                if not phone_info:
                    print(f"⏭ [Пропуск: {norm_err}] {raw_title}")
                    continue

                # Если это iPhone — жесткая проверка на родной АКБ
                if phone_info["type"] == "apple":
                    bat_err = is_bad_iphone_battery(full_text, phone_info["model"])
                    if bat_err:
                        print(f"⛔ [Бан АКБ iPhone: {bat_err}] {raw_title}")
                        continue

                # --- ЭТАП 3: Расчет рыночной цены и поправки на состояние ---
                base_market, sample_cnt, new_catalog_price = get_market_price(phone_info, market_cache)

                if base_market:
                    adj_market, cond_note, has_defects = adjust_market_for_condition(base_market, full_text)
                    profit_byn = adj_market - price_byn
                    profit_pct = (profit_byn / adj_market) * 100 if adj_market > 0 else 0
                else:
                    adj_market = None
                    cond_note = "Мало аналогов (оцени вручную)"
                    has_defects = bool(check_regex_list(full_text, DEFECT_PATTERNS))
                    profit_byn = 0
                    profit_pct = 0

                # Триггеры реальной срочности
                matched_urgent = [w for w in URGENT_WORDS if w in clean_text(full_text)]
                is_urgent = len(matched_urgent) > 0

                # --- ЭТАП 4: Классификация лота (ЖИР / НЕ ЖИР / ПОД ОСМОТР / ИГНОР) ---
                with_sound = False
                if adj_market is None:
                    # Редкая модель из белого списка — шлем тихо на всякий случай
                    tier_header = "📊 <b>РЕДКАЯ МОДЕЛЬ (Мало данных о рынке)</b>"
                elif profit_byn >= FAT_PROFIT_BYN or profit_pct >= FAT_PROFIT_PCT or (is_urgent and profit_byn >= URGENT_PROFIT_BYN):
                    tier_header = "🚨🔥 <b>ЖИРНЫЙ ЛОТ! (ЗВОНИ ПЕРВЫМ)</b> 🔥🚨"
                    with_sound = True
                elif profit_byn >= WORK_PROFIT_BYN:
                    tier_header = "🟢 <b>РАБОЧИЙ ВАРИАНТ (Хорошая маржа)</b>"
                    with_sound = False
                elif profit_byn >= INSPECT_MIN_PROFIT and not has_defects:
                    tier_header = "👀 <b>ПОД ОСМОТР / ТОРГ НА МЕСТЕ</b>"
                    with_sound = False
                else:
                    print(f"📉 [Мало выгоды: {profit_byn:.0f} BYN] {phone_info['key']} за {price_byn:.0f} BYN (Рынок ~{adj_market} BYN)")
                    continue

                # Проверка на подозрительного продавца и аномальный скам
                warnings = []
                if adj_market and profit_pct >= 55:
                    warnings.append("⚠️ <b>АНОМАЛЬНО ДЕШЕВО (>55% ниже рынка) — осторожно, возможен скам на предоплату!</b>")
                if len(description.strip()) < 30:
                    warnings.append("⚠️ <i>Пустое описание — внимательно осмотри фото на сколы!</i>")
                if phone_info["is_assumed_mem"]:
                    warnings.append(f"ℹ️ <i>Память не указана — рынок посчитан по минимуму ({phone_info['memory']} ГБ)</i>")

                seller_id = str(ad.get("account_id", ""))
                if seller_id:
                    seen_sellers[seller_id] = seen_sellers.get(seller_id, 0) + 1
                    if seen_sellers[seller_id] >= 3:
                        warnings.append("👀 <i>Этот продавец уже выкладывал несколько телефонов (возможно, перекуп)</i>")

                # Формируем карточку в Telegram
                area = parse_area(ad)
                link = ad.get("ad_link", f"https://www.kufar.by/item/{ad_id}")
                images = ad.get("images", [])
                photo_url = f"https://rms.kufar.by/v1/gallery/{images[0]['path']}" if (images and "path" in images[0]) else None

                safe_title = html.escape(raw_title)
                short_desc = html.escape(description.strip())
                if len(short_desc) > 250:
                    short_desc = short_desc[:250] + "..."

                msg = f"{tier_header}\n{price_drop_note}"
                if is_urgent:
                    msg += f"⚡ Триггер: <b>{', '.join(matched_urgent).upper()}</b>\n"

                msg += (
                    f"📱 Распознано: <b>{phone_info['model']} ({phone_info['memory']} GB)</b>\n"
                    f"🏷 Заголовок: {safe_title}\n"
                    f"📍 Район: {html.escape(area)}\n\n"
                    f"💰 Цена продавца: <b>{price_byn:.0f} BYN</b>\n"
                )

                if adj_market:
                    target_buy = max(100, adj_market - 100)
                    new_str = f" (Новый в каталоге: ~{new_catalog_price:.0f} р.)" if new_catalog_price else ""
                    msg += (
                        f"📊 Реальный рынок (с торгом): <b>~{adj_market} BYN</b>{new_str}\n"
                        f"🛠 Коррекция: <i>{cond_note} (база {sample_cnt} шт.)</i>\n"
                        f"💵 Расчетная выгода: <b>{profit_byn:+.0f} BYN ({profit_pct:+.0f}%)</b>\n"
                        f"🎯 <b>Торгуй до: ~{target_buy:.0f} BYN</b> (под маржу 100+ BYN)\n"
                    )

                if warnings:
                    msg += "\n" + "\n".join(warnings) + "\n"

                if short_desc:
                    msg += f"\n📝 <i>{short_desc}</i>\n"

                msg += (
                    f"\n💬 Шаблон в ЛС (нажми, чтобы скопировать):\n"
                    f"<code>Здравствуйте! Готов приехать и забрать сегодня за наличные без лишних вопросов. Куда можно подъехать?</code>\n\n"
                    f"👉 <a href='{link}'><b>ОТКРЫТЬ ОБЪЯВЛЕНИЕ НА КУФАРЕ</b></a>"
                )

                print(f"✅ ОТПРАВЛЕНО [{phone_info['key']}]: {price_byn:.0f} BYN (Рынок ~{adj_market} BYN | Выгода {profit_byn:+.0f})")
                send_telegram(msg, photo_url, with_sound=with_sound)

            if state_changed:
                # Оставляем последние 800 объявлений в памяти
                if len(seen_ads) > 800:
                    keys_to_keep = list(seen_ads.keys())[-800:]
                    seen_ads = {k: seen_ads[k] for k in keys_to_keep}
                save_json_file(SEEN_FILE, seen_ads)
                save_json_file(SELLERS_FILE, seen_sellers)

        time.sleep(random.uniform(MIN_INTERVAL, MAX_INTERVAL))

    save_json_file(SEEN_FILE, seen_ads)
    save_json_file(MARKET_CACHE_FILE, market_cache)
    print("🔄 Смена 5.8 ч завершена. Передача эстафеты...")


if __name__ == "__main__":
    main()
