import os
import json
import time
import random
import html
import requests

# В облаке данные берутся из зашифрованных Secrets (а на ПК — из запасных значений справа)
TG_TOKEN = os.getenv("TG_TOKEN", "8874085987:AAFA6bn_mxYb41eZyRRSRwtQLEOgyb7975c")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "1091251853")
PROXY_URL = os.getenv("PROXY_URL", "")  # Если понадобится прокси: http://log:pass@ip:port

# Сколько часов длится одна смена на сервере GitHub (5.8 часа = 5 ч 48 мин)
MAX_RUN_HOURS = float(os.getenv("MAX_RUN_HOURS", "5.8"))

KUFAR_SEARCH_URL = (
    "https://api.kufar.by/search-api/v2/search/rendered-paginated"
    "?cat=17010&cmp=0&cnd=1&lang=ru&prc=r%3A12000%2C70000&rgn=7&size=20&sort=lst.d"
)

MIN_INTERVAL = 5
MAX_INTERVAL = 12
SILENT_FOR_NORMAL_ADS = True
SEEN_FILE = "seen_ads.json"

STOP_WORDS = [
    "рассрочка", "рассрочку", "кредит", "гарантия", "доставка по рб",
    "трейд-ин", "трейдин", "trade-in", "trade in", "обмен", "скупка",
    "выкуп", "магазин", "наличии", "в наличии", "халва", "черепаха",
    "на запчасти", "запчасти", "не включается", "разбит", "разбита", "разбито",
    "трещина", "трещины", "поплыл", "пятно на экране", "пятно", "пятна",
    "выгорание", "выгорел", "плата", "icloud", "айклауд", "заблокирован",
    "заблокирована", "mdm", "мдм", "лизинг", "не оплачен", "неоплачен", "донор"
]

URGENT_WORDS = [
    "срочно", "торг", "сегодня", "быстрым", "уезжаю", "подарили"
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.kufar.by/"
})

if PROXY_URL:
    session.proxies.update({"http": PROXY_URL, "https": PROXY_URL})


def load_seen_ads():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_seen_ads(seen_set):
    try:
        # Храним последние 500 ID, чтобы файл не разрастался
        recent_list = list(seen_set)[-500:]
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(recent_list, f)
    except Exception as e:
        print(f"Ошибка сохранения кэша: {e}")


def find_matched_word(text, word_list):
    if not text:
        return None
    text_lower = text.lower()
    for word in word_list:
        if word in text_lower:
            return word
    return None


def get_ads():
    try:
        response = session.get(KUFAR_SEARCH_URL, timeout=8)
        if response.status_code == 200:
            return response.json().get("ads", [])
        elif response.status_code == 429:
            print("⚠️ Ошибка 429 (слишком часто). Пауза 30 сек...")
            time.sleep(30)
        else:
            print(f"⚠️ Куфар вернул код {response.status_code}")
    except Exception as e:
        print(f"⚠️ Ошибка сети: {e}")
    return []


def get_ad_description(ad_id):
    url = f"https://api.kufar.by/search-api/v2/item/{ad_id}/rendered?lang=ru"
    try:
        response = session.get(url, timeout=6)
        if response.status_code == 200:
            return response.json().get("result", {}).get("body", "")
    except Exception as e:
        print(f"⚠️ Ошибка загрузки описания {ad_id}: {e}")
    return ""


def parse_ad_parameters(ad):
    area = "Минск"
    details = []
    for param in ad.get("ad_parameters", []):
        p_code = param.get("p")
        val = param.get("vl") or param.get("v")
        if not val:
            continue
        if p_code == "area":
            area = f"Минск ({val})"
        elif p_code in ("phablet_phones_memory", "mobile_phones_memory", "memory"):
            details.append(f"Память: {val}")
        elif p_code == "condition":
            details.append(f"Сост: {val}")
    return area, ", ".join(details)


def send_telegram(text, photo_url=None, is_urgent=False):
    disable_sound = False if is_urgent else SILENT_FOR_NORMAL_ADS
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
        else:
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


def main():
    start_time = time.time()
    max_seconds = MAX_RUN_HOURS * 3600

    seen_ads = load_seen_ads()
    initial_ads = get_ads()
    
    # Если кэш пустой (первый запуск), просто запоминаем текущие объявления
    if not seen_ads:
        for ad in initial_ads:
            seen_ads.add(ad.get("ad_id"))
        save_seen_ads(seen_ads)
        send_telegram(
            f"☁️ <b>Облачный снайпер запущен!</b>\n"
            f"📦 В стартовой базе: {len(seen_ads)} шт.",
            is_urgent=False
        )

    print(f"🚀 Мониторинг активен. В базе {len(seen_ads)} объявлений.")

    while (time.time() - start_time) < max_seconds:
        ads = get_ads()
        if ads:
            new_found = False
            for ad in reversed(ads):
                ad_id = ad.get("ad_id")
                if not ad_id or ad_id in seen_ads:
                    continue

                seen_ads.add(ad_id)
                new_found = True

                raw_title = ad.get("subject", "Без названия")
                price_byn = int(ad.get("price_byn", "0")) / 100

                if find_matched_word(raw_title, STOP_WORDS):
                    continue

                description = get_ad_description(ad_id)
                if find_matched_word(description, STOP_WORDS):
                    continue

                full_text = f"{raw_title}\n{description}"
                matched_urgent = [w for w in URGENT_WORDS if w in full_text.lower()]
                is_urgent = len(matched_urgent) > 0

                area, params_str = parse_ad_parameters(ad)
                link = ad.get("ad_link", f"https://www.kufar.by/item/{ad_id}")

                images = ad.get("images", [])
                photo_url = None
                if images and "path" in images[0]:
                    photo_url = f"https://rms.kufar.by/v1/gallery/{images[0]['path']}"

                safe_title = html.escape(raw_title)
                short_desc = html.escape(description.strip())
                if len(short_desc) > 280:
                    short_desc = short_desc[:280] + "..."

                if is_urgent:
                    triggers_str = ", ".join(matched_urgent).upper()
                    header = f"🚨🔥 <b>СРОЧНЫЙ ЛОТ! ({triggers_str})</b> 🔥🚨\n"
                else:
                    header = "📱 "

                message = (
                    f"{header}<b>{safe_title}</b>\n"
                    f"💰 Цена: <b>{price_byn:.0f} BYN</b> | 📍 {html.escape(area)}\n"
                )
                if params_str:
                    message += f"⚙️ {html.escape(params_str)}\n"
                if short_desc:
                    message += f"\n📝 <i>{short_desc}</i>\n"

                message += f"\n⚡ <a href='{link}'><b>ОТКРЫТЬ НА КУФАРЕ</b></a>"

                print(f"✅ ОТПРАВЛЕНО: {raw_title} — {price_byn:.0f} BYN")
                send_telegram(message, photo_url, is_urgent=is_urgent)

            if new_found:
                save_seen_ads(seen_ads)

        time.sleep(random.uniform(MIN_INTERVAL, MAX_INTERVAL))

    save_seen_ads(seen_ads)
    print("🔄 Смена 5.8 ч завершена. Передача эстафеты следующему запуску...")


if __name__ == "__main__":
    main()