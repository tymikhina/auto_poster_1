"""
Auto Poster Generator v2
Вводишь модель -> находит на сайте -> парсит данные -> делает постер
Капчу проходишь вручную в открытом браузере
"""

import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from rembg import remove as remove_bg
import requests
import os
import time
import re
import json

BASE_URL = "https://www.automobile-catalog.com"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posters")
COOKIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

captcha_passed = False  # Флаг что капча уже пройдена в этой сессии

BRAND_COUNTRIES = {
    "audi": "germany", "bmw": "germany", "mercedes": "germany", "mercedes-benz": "germany",
    "mercedes-amg": "germany", "amg": "germany", "volkswagen": "germany", "porsche": "germany",
    "opel": "germany",
    "toyota": "japan", "honda": "japan", "nissan": "japan", "mazda": "japan",
    "subaru": "japan", "mitsubishi": "japan", "lexus": "japan", "infiniti": "japan",
    "ford": "usa", "chevrolet": "usa", "dodge": "usa", "jeep": "usa",
    "cadillac": "usa", "tesla": "usa", "lincoln": "usa",
    "ferrari": "italy", "lamborghini": "italy", "maserati": "italy", "alfa romeo": "italy",
    "fiat": "italy", "alfa": "italy",
    "renault": "france", "peugeot": "france", "citroen": "france", "bugatti": "france",
    "jaguar": "uk", "bentley": "uk", "mclaren": "uk", "lotus": "uk", "aston martin": "uk",
    "rolls-royce": "uk", "land rover": "uk", "mini": "uk",
    "volvo": "sweden", "koenigsegg": "sweden",
    "hyundai": "south_korea", "kia": "south_korea", "genesis": "south_korea",
}

driver = None


def save_cookies():
    """Сохраняем cookies в файл"""
    try:
        cookies = driver.get_cookies()
        with open(COOKIES_FILE, 'w') as f:
            json.dump(cookies, f)
        print("  Cookies сохранены")
    except Exception as e:
        print(f"  Ошибка сохранения cookies: {e}")


def load_cookies():
    """Загружаем cookies из файла"""
    try:
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, 'r') as f:
                cookies = json.load(f)
            for cookie in cookies:
                try:
                    driver.add_cookie(cookie)
                except:
                    pass
            print("  Cookies загружены")
            return True
    except Exception as e:
        print(f"  Ошибка загрузки cookies: {e}")
    return False


def create_driver():
    """Создаём браузер"""
    global driver
    print("\n  Запускаю браузер...")
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1400,900")
    options.add_argument("--disable-gpu")
    driver = uc.Chrome(options=options, version_main=144)

    # Загружаем cookies если есть
    driver.get(BASE_URL)
    time.sleep(1)
    if load_cookies():
        driver.refresh()
        time.sleep(2)

    return driver


def wait_for_page(timeout=60):
    """Ждём пока страница загрузится (капча пройдена) - 1 минута"""
    global captcha_passed

    print("  Жду загрузки страницы...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            html = driver.page_source

            # Если есть таблицы или много ссылок - страница загружена
            if "<table" in html and html.count('href="') > 10:
                print("  Страница загружена!")

                # Сохраняем cookies после первого успешного прохождения
                if not captcha_passed:
                    save_cookies()
                    captcha_passed = True

                time.sleep(1)
                return True

        except:
            pass
        time.sleep(1)

    # Даже если таймаут - пробуем парсить
    print("  Таймаут, пробую парсить...")
    return True


def get_page(url, wait=3, scroll=False):
    """Загружаем страницу"""
    global captcha_passed

    print(f"  -> {url}")
    driver.get(url)
    time.sleep(wait)

    # Проверяем на капчу
    html = driver.page_source.lower()
    if "challenge" in html or "подтвердите" in html or "checking" in html:
        if captcha_passed:
            # Капча уже была пройдена - ждём автоматически
            print("  Ожидание (капча уже пройдена)...")
            wait_for_page(30)
        else:
            # Первый раз - просим пройти капчу
            print("\n  !!! КАПЧА - пройди в браузере (1 минута) !!!\n")
            wait_for_page(60)

    # Прокручиваем страницу вниз для загрузки всех фото
    if scroll:
        print("  Прокручиваю страницу...")
        for _ in range(5):
            driver.execute_script('window.scrollBy(0, 800);')
            time.sleep(0.5)
        time.sleep(1)

    return BeautifulSoup(driver.page_source, "lxml")


def find_car_on_site(query):
    """
    Ищем машину на сайте
    Формат URL: https://www.automobile-catalog.com/list-{brand}.html
    Затем переходим на страницу /car/ с характеристиками
    """
    query = query.strip().lower()
    parts = query.split()

    # Определяем бренд
    brand = parts[0]
    model_keywords = parts[1:] if len(parts) > 1 else []

    # Формируем URL списка
    brand_slug = brand.replace(" ", "-").replace("_", "-")
    list_url = f"{BASE_URL}/list-{brand_slug}.html"

    print(f"\n  Ищу: {query}")
    print(f"  Бренд: {brand}")
    print(f"  Ключевые слова: {model_keywords}")

    # Открываем список моделей бренда
    soup = get_page(list_url)
    if not soup:
        print(f"  Не удалось загрузить {list_url}")
        return None, brand, None, None

    # Ищем ссылки на модели
    all_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()

        # Ищем ссылки на конкретные машины
        if href.endswith(".html") and brand in href.lower():
            all_links.append({
                "href": href,
                "text": text,
                "score": 0
            })

    # Считаем релевантность - ИЩЕМ ТОЧНУЮ МОДЕЛЬ по всем ключевым словам
    for link in all_links:
        text_lower = link["text"].lower()
        href_lower = link["href"].lower()
        combined = text_lower + " " + href_lower

        # ШТРАФ ЗА КОНЦЕПТ-КАРЫ (если пользователь не ищет концепт специально)
        if "concept" in combined and "concept" not in query.lower():
            link["score"] -= 200  # Огромный штраф

        # Проверяем ВСЕ ключевые слова из запроса
        for keyword in model_keywords:
            kw_clean = keyword.strip("().,").lower()
            if len(kw_clean) < 2:
                continue

            # ВЫСОКИЙ ПРИОРИТЕТ для номеров моделей (970, 971, 992, etc.)
            if kw_clean.isdigit() and len(kw_clean) == 3:
                if kw_clean in combined:
                    link["score"] += 100  # Номер модели - очень важно!
                else:
                    link["score"] -= 50  # Штраф если номер модели не совпал

            # ВЫСОКИЙ ПРИОРИТЕТ для поколений (1st, 2nd, 3rd, phase-i, phase-ii)
            elif kw_clean in ["1st", "2nd", "3rd", "phase-i", "phase-ii", "1st-gen", "2nd-gen"]:
                if kw_clean in combined or kw_clean.replace("-", " ") in combined:
                    link["score"] += 80
                # Проверяем также "1st generation", "2nd generation"
                elif kw_clean == "2nd-gen" or kw_clean == "2nd":
                    if "2nd" in combined or "second" in combined:
                        link["score"] += 80
                elif kw_clean == "1st-gen" or kw_clean == "1st":
                    if "1st" in combined or "first" in combined:
                        link["score"] += 80

            # Обычные ключевые слова
            elif kw_clean in combined:
                link["score"] += 15

        # Бонус за первое ключевое слово (название модели) в URL
        if model_keywords and model_keywords[0] in href_lower:
            link["score"] += 20

    # Сортируем по релевантности
    all_links.sort(key=lambda x: x["score"], reverse=True)

    if not all_links:
        print("  Не нашёл ссылок на модели")
        return None, brand, None, None

    # Показываем топ-10 найденных
    print(f"\n  Найдено {len(all_links)} ссылок. Топ совпадений:")
    for i, link in enumerate(all_links[:10]):
        print(f"    {i+1}. [{link['score']}] {link['text'][:80]}")

    # Если несколько вариантов с похожим score - даём выбрать
    top_5 = all_links[:5]
    if len(top_5) > 1 and top_5[0]["score"] == top_5[1]["score"]:
        print(f"\n  Найдено несколько подходящих вариантов.")
        print(f"  Выберите номер (1-5) или нажмите Enter для автовыбора:")
        try:
            choice = input("  > ").strip()
            if choice and choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(top_5):
                    best = top_5[idx]
                    print(f"  Выбрано: {best['text'][:60]}")
                else:
                    best = all_links[0]
            else:
                best = all_links[0]
        except:
            best = all_links[0]
    else:
        best = all_links[0]

    model_url = best["href"]
    if not model_url.startswith("http"):
        model_url = BASE_URL + "/" + model_url.lstrip("/")

    print(f"\n  Страница модели: {model_url}")

    # Ищем год в тексте выбранной модели (в названии ссылки)
    year_range = None
    selected_text = best["text"]
    year_match = re.search(r'(\d{4})[-–](\d{4})', selected_text)
    if year_match:
        year_range = f"{year_match.group(1)}-{year_match.group(2)}"
        print(f"  Год из названия модели: {year_range}")
    else:
        # Если не нашли диапазон, ищем одиночный год
        year_match = re.search(r'(\d{4})', selected_text)
        if year_match:
            year_range = year_match.group(1)
            print(f"  Год из названия модели: {year_range}")

    # Теперь переходим на страницу модели
    soup2 = get_page(model_url)
    if not soup2:
        return model_url, brand, model_url, year_range

    # Ищем ТОЧНУЮ модель на странице - парсим текст и ищем совпадения с годами
    print("\n  Ищу точную модель на странице...")
    page_text = soup2.get_text()

    # Ищем строки вида "Jaguar F-Type phase-I Convertible AWD (2015-2017)"
    # Парсим все упоминания бренда с годами в скобках
    lines = page_text.split('\n')
    best_match = None
    best_match_score = 0

    for line in lines:
        line_lower = line.lower().strip()

        # Ищем строки с годами в скобках
        year_match = re.search(r'\((\d{4}[-–]\d{4}|\d{4})\)', line)
        if not year_match:
            continue

        # Подсчитываем сколько ключевых слов совпало
        matched = 0
        for keyword in model_keywords:
            if keyword in line_lower:
                matched += 1

        if matched > best_match_score:
            best_match_score = matched
            best_match = {"text": line.strip(), "year": year_match.group(1), "matched": matched}

        # Если совпали ВСЕ ключевые слова - это точное совпадение!
        if matched == len(model_keywords):
            year_range = year_match.group(1)
            print(f"  -> Найдено ТОЧНОЕ совпадение:")
            print(f"     {line.strip()[:100]}")
            print(f"     Год: {year_range}")
            break

    # Если нашли хорошее совпадение (хотя бы 70% слов)
    if best_match and best_match["matched"] >= len(model_keywords) * 0.7:
        year_range = best_match["year"]
        print(f"  Используем год из найденной модели: {year_range}")
        print(f"    Совпало {best_match['matched']}/{len(model_keywords)} слов")

    # НЕ ПЕРЕХОДИМ на /car/ страницы - все данные берем со страницы модели
    print(f"\n  Используем страницу модели для парсинга данных и фото")
    return model_url, brand, model_url, year_range


def parse_car_page(url, brand, model_page_url=None, year_from_model=None, query_keywords=None):
    """Парсим страницу модели с характеристиками"""
    # Загружаем страницу модели БЕЗ прокрутки - фото уже рядом с моделью
    soup = get_page(url, scroll=False)
    if not soup:
        return None, {}, None

    # Заголовок
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else "Unknown"
    print(f"  Название: {title}")

    specs = {}

    # === ИЩЕМ ССЫЛКУ НА /car/ СТРАНИЦУ ДЛЯ ДЕТАЛЬНЫХ SPECS ===
    print(f"\n  Ищу ссылку на детальную страницу /car/...")
    car_page_url = None
    best_car_score = 0

    # Ключевые слова для поиска нужной версии
    search_keywords = query_keywords or []

    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/car/' not in href:
            continue

        text = a.get_text(strip=True).lower()
        href_lower = href.lower()
        combined = text + ' ' + href_lower

        # Считаем совпадения с ключевыми словами
        score = 0
        for kw in search_keywords:
            if kw in combined:
                score += 1

        # Бонус если год совпадает
        if year_from_model:
            year_start = year_from_model.split('-')[0] if '-' in str(year_from_model) else str(year_from_model)
            if year_start in href:
                score += 2

        if score > best_car_score:
            best_car_score = score
            car_page_url = href

    # Если нашли хорошую /car/ страницу, парсим specs оттуда
    if car_page_url and best_car_score >= 2:
        if not car_page_url.startswith('http'):
            car_page_url = BASE_URL + '/' + car_page_url.lstrip('/')
        print(f"  Найдена /car/ страница (score={best_car_score}): {car_page_url[-60:]}")

        car_soup = get_page(car_page_url, scroll=False)
        if car_soup:
            car_text = car_soup.get_text()

            # Парсим Torque: "700 Nm" или "Torque net:700 Nm"
            torque_match = re.search(r'Torque\s*(?:net)?[:\s]*(\d+)\s*Nm', car_text, re.IGNORECASE)
            if torque_match:
                specs["torque"] = f"{torque_match.group(1)} Nm"
                print(f"    Torque: {specs['torque']}")

            # Парсим Weight: "1705 kg" или "Curb weight:1705 kg"
            weight_match = re.search(r'(?:Curb\s*weight|Weight)[^:]*:\s*(\d+)\s*kg', car_text, re.IGNORECASE)
            if weight_match:
                specs["weight"] = f"{weight_match.group(1)} kg"
                print(f"    Weight: {specs['weight']}")

            # Парсим Top speed: "322 km/h"
            speed_match = re.search(r'Top\s*speed[:\s]*(\d+)\s*km/h', car_text, re.IGNORECASE)
            if speed_match:
                specs["top_speed"] = f"{speed_match.group(1)} km/h"
                print(f"    Top speed: {specs['top_speed']}")

            # Парсим 0-100 km/h: "3.7" или "3.5"
            accel_match = re.search(r'0-100\s*km/h\s*\(?sec\)?[:\s]*(\d+\.?\d*)', car_text, re.IGNORECASE)
            if accel_match:
                specs["acceleration"] = f"{accel_match.group(1)} s"
                print(f"    0-100 km/h: {specs['acceleration']}")

            # Парсим Engine displacement: "5000 cm3"
            disp_match = re.search(r'Displacement[:\s]*(\d+)\s*cm3', car_text, re.IGNORECASE)
            if disp_match:
                cc = int(disp_match.group(1))
                liters = round(cc / 1000, 1)
                specs["engine"] = f"{liters}L ({cc} cc)"
                print(f"    Engine: {specs['engine']}")

            # Парсим Power: "575 PS" или "567 hp"
            power_match = re.search(r'Horsepower\s*net[:\s]*\d+\s*kW\s*/\s*(\d+)\s*PS\s*/\s*(\d+)\s*hp', car_text, re.IGNORECASE)
            if power_match:
                specs["power"] = f"{power_match.group(1)} PS / {power_match.group(2)} hp"
                print(f"    Power: {specs['power']}")
    else:
        print(f"  Не найдена подходящая /car/ страница, парсим со страницы модели...")

    # === FALLBACK: парсим со страницы модели если /car/ не дала результатов ===
    page_text = soup.get_text()

    # Ищем диапазон объема двигателя в формате "2995 - 5000 cc"
    if "engine" not in specs:
        engine_match = re.search(r'engines?\s+of\s+(\d+)\s*[-–]\s*(\d+)\s*cc', page_text, re.IGNORECASE)
        if not engine_match:
            engine_match = re.search(r'engines?\s+of\s+(\d+)\s*cc', page_text, re.IGNORECASE)

        if engine_match:
            if len(engine_match.groups()) > 1:
                # Диапазон - берем максимальное значение
                cc_max = int(engine_match.group(2))
                liters = round(cc_max / 1000, 1)
                specs["engine"] = f"{liters}L ({cc_max} cc)"
            else:
                # Одно значение
                cc = int(engine_match.group(1))
                liters = round(cc / 1000, 1)
                specs["engine"] = f"{liters}L ({cc} cc)"

    # Ищем мощность в формате "delivering 280 - 423 kW (381 - 575 PS, 375 - 567 hp)"
    if "power" not in specs:
        power_match = re.search(r'delivering\s+(\d+)\s*[-–]\s*(\d+)\s*kW\s*\((\d+)\s*[-–]\s*(\d+)\s*PS,\s*(\d+)\s*[-–]\s*(\d+)\s*hp\)', page_text, re.IGNORECASE)
        if not power_match:
            # Может быть одно значение
            power_match = re.search(r'delivering\s+(\d+)\s*kW\s*\((\d+)\s*PS,\s*(\d+)\s*hp\)', page_text, re.IGNORECASE)

        if power_match:
            if len(power_match.groups()) > 3:
                # Диапазон - берем максимальное значение
                specs["power"] = f"{power_match.group(4)} PS / {power_match.group(6)} hp"
            else:
                specs["power"] = f"{power_match.group(2)} PS / {power_match.group(3)} hp"

    # Если не нашли в описании, пробуем парсить таблицы (запасной вариант)
    if not specs.get("engine") or not specs.get("power"):
        for table in soup.find_all("table"):
            for tr in table.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True).lower()
                    val = cells[1].get_text(strip=True)

                    if not val or val == "-" or len(val) > 60:
                        continue

                    # Двигатель
                    if "engine" not in specs and any(x in key for x in ["displacement", "capacity", "engine size"]):
                        if "cc" in val.lower():
                            specs["engine"] = val

                    # Мощность
                    if "power" not in specs and "power" in key and "steering" not in key:
                        if any(x in val.lower() for x in ["hp", "ps", "kw"]):
                            specs["power"] = val

                    # Крутящий момент
                    if "torque" not in specs and "torque" in key:
                        if "nm" in val.lower():
                            specs["torque"] = val

                    # Вес
                    if "weight" not in specs and any(x in key for x in ["kerb weight", "curb weight"]):
                        if "kg" in val.lower():
                            specs["weight"] = val

                    # Разгон
                    if "acceleration" not in specs and ("0-100" in key or "0 to 100" in key):
                        if "s" in val.lower() or "." in val:
                            specs["acceleration"] = val

                    # Максимальная скорость
                    if "top_speed" not in specs and any(x in key for x in ["top speed", "max speed"]):
                        if "km/h" in val.lower():
                            specs["top_speed"] = val

    # Год - используем переданный из названия модели (самый точный источник)
    if year_from_model:
        specs["year"] = year_from_model
        print(f"  Год из названия модели: {specs.get('year', '—')}")
    else:
        # Если не передан, ищем в заголовке страницы модификации
        year_match = re.search(r'(\d{4})(?:\s*[-–]\s*(\d{4}))?', title)
        if year_match:
            if year_match.group(2):
                specs["year"] = f"{year_match.group(1)}-{year_match.group(2)}"
            else:
                specs["year"] = year_match.group(1)
            print(f"  Год из заголовка: {specs.get('year', '—')}")

    print(f"  Specs: {specs}")

    # Ищем фото НАПРОТИВ названия модели (в той же таблице)
    # Логика: находим самую маленькую таблицу, содержащую все ключевые слова модели
    img_url = None
    brand_lower_clean = brand.lower().replace("-", "").replace(" ", "")

    # Извлекаем ключевые слова из заголовка для поиска нужной таблицы
    title_lower = title.lower()
    # Убираем общие слова и бренд
    keywords = []
    for word in title_lower.split():
        word_clean = re.sub(r'[^a-z0-9-]', '', word)
        if word_clean and len(word_clean) > 2 and word_clean not in ['the', 'and', 'specifications', 'versions', 'types', 'model', brand.lower()]:
            keywords.append(word_clean)

    print(f"\n  Ищу фото напротив модели...")
    print(f"  Ключевые слова: {keywords[:5]}")

    # Ищем таблицы, содержащие ключевые слова модели
    best_table = None
    best_img_src = None
    min_brand_images = 999

    for table in soup.find_all('table'):
        table_text = table.get_text().lower()

        # Проверяем что таблица содержит хотя бы 2-3 ключевых слова
        matched_keywords = sum(1 for kw in keywords[:5] if kw in table_text)
        if matched_keywords < 2:
            continue

        # Ищем picto изображения бренда в этой таблице
        imgs = table.find_all('img')
        brand_picto_imgs = []
        for img in imgs:
            src = img.get('src', '').lower()
            if 'picto' in src and brand_lower_clean in src.replace('-', '').replace('_', ''):
                # Пропускаем фото сзади
                if 'rear' not in src and 'back' not in src and 'tail' not in src:
                    brand_picto_imgs.append(img.get('src', ''))

        # Выбираем таблицу с наименьшим числом фото бренда (самая специфичная)
        if brand_picto_imgs and len(brand_picto_imgs) < min_brand_images:
            min_brand_images = len(brand_picto_imgs)
            best_table = table
            best_img_src = brand_picto_imgs[0]
            print(f"  Найдена таблица с {len(brand_picto_imgs)} фото бренда, matched={matched_keywords}")

    if best_img_src:
        img_url = best_img_src
        if not img_url.startswith('http'):
            img_url = BASE_URL + '/' + img_url.lstrip('/')
        print(f"  Фото напротив модели: {img_url}")
    else:
        print(f"  Не найдено фото напротив модели, ищу любое фото бренда...")
        # Fallback: ищем любое picto фото бренда на странице
        for img in soup.find_all('img'):
            src = img.get('src', '').lower()
            if 'picto' in src and brand_lower_clean in src.replace('-', '').replace('_', ''):
                if 'rear' not in src and 'back' not in src:
                    img_url = img.get('src', '')
                    if not img_url.startswith('http'):
                        img_url = BASE_URL + '/' + img_url.lstrip('/')
                    print(f"  Fallback фото: {img_url}")
                    break

    return title, specs, img_url


def remove_watermark(img):
    """Убираем водяной знак (обычно внизу фото)"""
    # Водяной знак "found in automobile-catalog.com" обычно в нижней части
    # Закрашиваем нижнюю полосу белым цветом
    width, height = img.size

    # Создаём копию
    img_clean = img.copy()
    draw = ImageDraw.Draw(img_clean)

    # Закрашиваем нижние 25 пикселей белым (где обычно водяной знак)
    watermark_height = 25
    draw.rectangle([0, height - watermark_height, width, height], fill=(255, 255, 255, 255))

    return img_clean


def download_image(url, check_only=False):
    """Скачиваем фото через Selenium (обход 403 ошибки)."""
    try:
        # Пробуем сначала через Selenium - получаем base64 изображения
        print(f"  Загружаю через браузер: {url}")

        # Загружаем URL в браузере
        driver.get(url)
        time.sleep(1)

        # Находим тег img на странице
        try:
            img_element = driver.find_element("tag name", "img")

            # Получаем размеры для проверки
            width = img_element.size['width']
            height = img_element.size['height']

            if check_only:
                return (width, height)

            # Получаем изображение через скриншот элемента
            img_png = img_element.screenshot_as_png
            img = Image.open(BytesIO(img_png)).convert("RGBA")
            return img

        except:
            # Если не нашли img, пробуем через requests (старый метод)
            cookies = {c['name']: c['value'] for c in driver.get_cookies()}
            headers = {
                "User-Agent": driver.execute_script("return navigator.userAgent"),
                "Referer": BASE_URL
            }
            r = requests.get(url, headers=headers, cookies=cookies, timeout=15)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert("RGBA")

            if check_only:
                return img.size

            return img

    except Exception as e:
        print(f"  ! Ошибка загрузки фото: {e}")
        return None


def find_best_exterior_photo(candidates):
    """
    Из списка кандидатов выбираем лучшее экстерьерное фото.
    Экстерьер обычно имеет широкий формат (width > height * 1.2)
    ФИЛЬТРУЕМ баннеры и слишком маленькие изображения
    """
    print(f"  Проверяю пропорции топ-{min(10, len(candidates))} фото...")

    for i, img_data in enumerate(candidates[:10]):
        src = img_data["src"]
        if not src.startswith("http"):
            src = BASE_URL + "/" + src.lstrip("/")

        size = download_image(src, check_only=True)
        if size:
            width, height = size
            ratio = width / height if height > 0 else 0
            print(f"    {i+1}. ratio={ratio:.2f} ({width}x{height})")

            # ФИЛЬТР: Пропускаем баннеры и слишком маленькие изображения
            if width < 200 or height < 100:
                print(f"       -> Пропускаю (слишком маленькое)")
                continue

            # ФИЛЬТР: Пропускаем слишком узкие баннеры
            if ratio > 10 or ratio < 0.5:
                print(f"       -> Пропускаю (странные пропорции)")
                continue

            # Экстерьерное фото - широкое (landscape)
            if ratio >= 1.3:  # Ширина больше высоты на 30%+
                print(f"  -> Выбрано экстерьерное фото #{i+1}")
                return src

    # Если не нашли широкое среди валидных, берём первое валидное
    for i, img_data in enumerate(candidates[:10]):
        src = img_data["src"]
        if not src.startswith("http"):
            src = BASE_URL + "/" + src.lstrip("/")

        size = download_image(src, check_only=True)
        if size:
            width, height = size
            # Проверяем минимальные размеры
            if width >= 200 and height >= 100:
                ratio = width / height if height > 0 else 0
                if 0.5 <= ratio <= 10:
                    print(f"  -> Берём фото #{i+1} (первое валидное)")
                    return src

    # Крайний случай - берём первое
    print(f"  -> Берём первое фото (валидные не найдены)")
    src = candidates[0]["src"]
    if not src.startswith("http"):
        src = BASE_URL + "/" + src.lstrip("/")
    return src


def process_car_image(url):
    """Скачиваем фото, убираем фон (силуэт машины)"""
    print(f"  Скачиваю фото: {url}")
    img = download_image(url)
    if not img:
        return None

    # Проверяем пропорции
    width, height = img.size
    ratio = width / height if height > 0 else 0
    print(f"  Размер: {width}x{height}, ratio={ratio:.2f}")

    # Убираем фон с помощью rembg
    print(f"  Удаляю фон (rembg)...")
    try:
        img_no_bg = remove_bg(img)
        print(f"  Фон удалён!")
        return img_no_bg
    except Exception as e:
        print(f"  ! Ошибка удаления фона: {e}")
        # Возвращаем оригинал без водяного знака
        return remove_watermark(img)


def draw_flag(country, w=60, h=40):
    """Рисуем флаг страны"""
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)

    if country == "germany":
        d.rectangle([0, 0, w, h//3], fill="#000")
        d.rectangle([0, h//3, w, 2*h//3], fill="#DD0000")
        d.rectangle([0, 2*h//3, w, h], fill="#FFCC00")
    elif country == "japan":
        # Чёрный контур для белого флага
        d.rectangle([0, 0, w-1, h-1], outline="#000000", width=1)
        cx, cy = w // 2, h // 2
        r = min(w, h) // 3
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill="#BC002D")
    elif country == "italy":
        d.rectangle([0, 0, w//3, h], fill="#009246")
        d.rectangle([2*w//3, 0, w, h], fill="#CE2B37")
    elif country == "france":
        d.rectangle([0, 0, w//3, h], fill="#002395")
        d.rectangle([2*w//3, 0, w, h], fill="#ED2939")
    elif country == "usa":
        for i in range(13):
            color = "#B22234" if i % 2 == 0 else "#FFFFFF"
            d.rectangle([0, i*h//13, w, (i+1)*h//13], fill=color)
        d.rectangle([0, 0, w//2, h//2], fill="#3C3B6E")
    elif country == "uk":
        d.rectangle([0, 0, w, h], fill="#012169")
        d.rectangle([w//2-2, 0, w//2+2, h], fill="#FFFFFF")
        d.rectangle([0, h//2-2, w, h//2+2], fill="#FFFFFF")
        d.rectangle([w//2-1, 0, w//2+1, h], fill="#C8102E")
        d.rectangle([0, h//2-1, w, h//2+1], fill="#C8102E")
    elif country == "sweden":
        d.rectangle([0, 0, w, h], fill="#006AA7")
        d.rectangle([w//3, 0, w//3+6, h], fill="#FECC00")
        d.rectangle([0, h//2-3, w, h//2+3], fill="#FECC00")
    elif country == "south_korea":
        cx, cy = w // 2, h // 2
        r = min(w, h) // 3
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill="#C60C30")
    else:
        d.rectangle([0, 0, w, h], fill="#CCCCCC")

    return img


def make_poster(title, specs, car_img, brand):
    """Создаём постер в стиле референса AUDI TT RS"""
    # Размеры с рамкой
    FRAME = 12  # Толщина рамки
    W_INNER, H_INNER = 500, 680  # Внутренний размер постера
    W, H = W_INNER + FRAME * 2, H_INNER + FRAME * 2  # Полный размер с рамкой

    # Создаём с чёрной рамкой
    poster = Image.new("RGB", (W, H), "#1A1A1A")  # Почти чёрная рамка
    # Белый внутренний прямоугольник
    draw = ImageDraw.Draw(poster)
    draw.rectangle([FRAME, FRAME, W - FRAME - 1, H - FRAME - 1], fill="white")

    # Шрифты - точно по размерам референса
    try:
        f_brand = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 28)  # AUDI - крупный, жирный
        f_model = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 34)  # TT RS - еще крупнее
        f_year_label = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 10)  # YEAR - жирный
        f_year_value = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 9)  # Год - обычный
        f_label = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 8)  # Лейблы - ЖИРНЫЙ (Engine, Power...)
        f_value = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 8)  # Значения - обычный
    except:
        f_brand = f_model = f_year_label = f_year_value = f_label = f_value = ImageFont.load_default()

    # Парсим название
    title_clean = re.sub(r'\d{4}[-–]?\d{0,4}', '', title).strip()
    title_clean = re.sub(r'\(.*?\)', '', title_clean).strip()
    title_clean = re.sub(r'model since.*', '', title_clean, flags=re.IGNORECASE).strip()
    title_clean = re.sub(r'specifications.*', '', title_clean, flags=re.IGNORECASE).strip()
    title_clean = re.sub(r'car\s*$', '', title_clean, flags=re.IGNORECASE).strip()

    parts = title_clean.split()
    brand_name = parts[0] if parts else brand

    # Модель - берём 2-4 слова после бренда
    model_parts = parts[1:5] if len(parts) > 1 else []
    model_name = " ".join(model_parts)

    # Рассчитываем позицию серой области заранее (текст будет выровнен по ней)
    gray_margin_x = 65  # Отступы слева и справа (уменьшили на 3 см = ~30px с каждой стороны)
    gray_left = FRAME + gray_margin_x
    gray_right = W - FRAME - gray_margin_x

    # === ВЕРХНЯЯ ЧАСТЬ: Название ===
    y = FRAME + 15
    # BRAND - СЕРЫЙ, жирный (как на референсе)
    draw.text((gray_left, y), brand_name.upper(), fill="#6B6B6B", font=f_brand)
    y += 32

    # MODEL - чёрный, жирный, крупный (с автоподбором размера шрифта)
    if model_name:
        # Автоматически уменьшаем шрифт если текст не помещается
        max_width = gray_right - gray_left - 10  # Ширина серого поля минус отступы
        model_text = model_name.upper()

        # Начинаем с базового размера 34
        font_size = 34
        f_model_adjusted = f_model

        while font_size > 14:  # Минимум 14px
            try:
                f_model_adjusted = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", font_size)
            except:
                f_model_adjusted = ImageFont.load_default()
                break

            # Проверяем ширину текста
            bbox = draw.textbbox((0, 0), model_text, font=f_model_adjusted)
            text_width = bbox[2] - bbox[0]

            if text_width <= max_width:
                break  # Текст помещается

            font_size -= 2  # Уменьшаем на 2px

        draw.text((gray_left, y), model_text, fill="#000000", font=f_model_adjusted)
        y += 40
    else:
        y += 10

    # === СРЕДНЯЯ ЧАСТЬ: Серый фон + машина (начинается сразу под текстом) ===
    gray_rect_y = y + 5  # Сразу под текстом модели
    gray_margin_bottom = 15  # Меньший отступ снизу
    gray_rect_h = H - FRAME - gray_rect_y - 85 - gray_margin_bottom  # Большая высота серой области
    draw.rectangle([gray_left, gray_rect_y, gray_right, gray_rect_y + gray_rect_h], fill="#CCCCCC")  # Как на референсе

    # Фото машины (центрируем, не выходит за границы листа)
    if car_img:
        # Масштабируем машину - большая, но в пределах листа
        target_w = W_INNER - 20  # Почти вся ширина внутренней области
        target_h = int(gray_rect_h * 1.3)

        img_ratio = car_img.width / car_img.height
        target_ratio = target_w / target_h

        if img_ratio > target_ratio:
            new_w = target_w
            new_h = int(target_w / img_ratio)
        else:
            new_h = target_h
            new_w = int(target_h * img_ratio)

        car_img = car_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Центрируем по горизонтали, по вертикали - чуть ниже центра (колёса выходят за край)
        x = (W - car_img.width) // 2
        img_y = gray_rect_y + (gray_rect_h - car_img.height) // 2 + 15  # +15 чтобы колёса чуть вышли

        try:
            poster.paste(car_img, (x, img_y), car_img)
        except:
            poster.paste(car_img, (x, img_y))

    # === НИЖНЯЯ ЧАСТЬ: Характеристики (вплотную к серой области) ===
    specs_y = gray_rect_y + gray_rect_h + 10

    # YEAR - слева (выровнено по серой области)
    draw.text((gray_left, specs_y), "YEAR", fill="#000000", font=f_year_label)
    year_val = specs.get("year", "—")
    draw.text((gray_left, specs_y + 14), year_val, fill="#666666", font=f_year_value)

    # Вертикальная линия-разделитель после YEAR
    line_x = gray_left + 60
    draw.line([(line_x, specs_y), (line_x, specs_y + 55)], fill="#CCCCCC", width=1)

    # Колонка 1: Engine, Power, Torque, Weight
    col1_label_x = line_x + 12
    col1_val_x = col1_label_x + 42
    specs_data = [
        ("Engine", specs.get("engine", "—")),
        ("Power", specs.get("power", "—")),
        ("Torque", specs.get("torque", "—")),
        ("Weight", specs.get("weight", "—")),
    ]

    for i, (label, value) in enumerate(specs_data):
        row_y = specs_y + i * 14  # Уменьшенный интервал (было 16)
        draw.text((col1_label_x, row_y), label, fill="#000000", font=f_label)  # ЧЕРНЫЙ цвет
        # Укорачиваем значение если слишком длинное
        if len(value) > 16:
            value = value[:16]
        draw.text((col1_val_x, row_y), value, fill="#000000", font=f_value)

    # Колонка 2: 0-100, Top speed
    col2_label_x = col1_val_x + 120
    col2_val_x = col2_label_x + 60
    specs_data2 = [
        ("0-100 km/h", specs.get("acceleration", "—")),
        ("Top speed", specs.get("top_speed", "—")),
    ]

    for i, (label, value) in enumerate(specs_data2):
        row_y = specs_y + i * 14  # Уменьшенный интервал (было 16)
        draw.text((col2_label_x, row_y), label, fill="#000000", font=f_label)  # ЧЕРНЫЙ цвет
        if len(value) > 12:
            value = value[:12]
        draw.text((col2_val_x, row_y), value, fill="#000000", font=f_value)

    # Флаг - под Top speed
    country = BRAND_COUNTRIES.get(brand.lower(), "germany")
    flag = draw_flag(country, 35, 22)
    poster.paste(flag, (col2_val_x, specs_y + 45))

    return poster


def run(query=None):
    """Главная функция"""
    print("\n" + "="*55)
    print("  AUTO POSTER GENERATOR v2")
    print("  Формат: brand model (например: mercedes-amg c63)")
    print("="*55)

    if not query:
        query = input("\n  Введи модель: ").strip()

    if not query:
        print("  Пустой ввод, выхожу")
        return

    print(f"\n  Запрос: {query}")

    create_driver()

    try:
        # 1. Ищем машину на сайте
        result = find_car_on_site(query)
        if not result or not result[0]:
            print("  Не удалось найти машину")
            return

        car_url, brand, model_url, year_range = result

        # Извлекаем ключевые слова из запроса для поиска /car/ страницы
        query_keywords = [kw.lower() for kw in query.split() if len(kw) > 2]

        # 2. Парсим страницу (передаём также URL модели для поиска фото и год)
        title, specs, img_url = parse_car_page(car_url, brand, model_url, year_range, query_keywords)
        if not title:
            print("  Не удалось распарсить страницу")
            return

        # 3. Скачиваем фото и удаляем фон (силуэт машины)
        car_img = None
        if img_url:
            car_img = process_car_image(img_url)

        if not car_img:
            print("  ! Фото не найдено, делаю постер без фото")

        # 4. Создаём постер
        print("\n  Создаю постер...")
        poster = make_poster(title, specs, car_img, brand)

        # 5. Сохраняем
        fname = re.sub(r"[^a-zA-Z0-9]+", "_", title)[:50]
        filepath = os.path.join(OUTPUT_DIR, f"{fname}.png")
        poster.save(filepath, "PNG")

        print(f"\n  {'='*50}")
        print(f"  ГОТОВО!")
        print(f"  Файл: {filepath}")
        print(f"  {'='*50}\n")

    except Exception as e:
        print(f"\n  ! Ошибка: {e}")
        import traceback
        traceback.print_exc()

    finally:
        try:
            input("\n  Нажми Enter чтобы закрыть браузер...")
        except:
            pass
        try:
            driver.quit()
        except:
            pass


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        # Модель передана через аргументы
        query = " ".join(sys.argv[1:])
        run(query)
    else:
        # Интерактивный режим
        run()
