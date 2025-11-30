import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, timedelta
import pytz
import re
import os
import json
import platform

# Cache en el filesystem (compatible con Windows y Linux)
if platform.system() == "Windows":
    CACHE_DIR = "C:/temp/"
else:
    CACHE_DIR = "/tmp/"

# Crear directorio si no existe
os.makedirs(CACHE_DIR, exist_ok=True)

CACHE_FILE = os.path.join(CACHE_DIR, 'barcelona_calendar_cache.ics')
CACHE_TIMESTAMP = os.path.join(CACHE_DIR, 'barcelona_cache_timestamp.txt')

def should_update():
    """Determina si debe actualizar el calendario (después de las 9 AM hora española)"""
    try:
        # Verificar si existe archivo de timestamp
        if not os.path.exists(CACHE_TIMESTAMP):
            return True

        with open(CACHE_TIMESTAMP, 'r') as f:
            last_update_str = f.read().strip()
            last_update = datetime.fromisoformat(last_update_str)

        now_spain = datetime.now(pytz.timezone('Europe/Madrid'))
        last_update_spain = last_update.astimezone(pytz.timezone('Europe/Madrid'))

        # Actualizar si:
        # 1. La última actualización fue antes de hoy a las 9 AM
        # 2. O no hay cache
        if (last_update_spain.date() < now_spain.date() or
                (last_update_spain.date() == now_spain.date() and last_update_spain.hour < 9) or
                not os.path.exists(CACHE_FILE)):
            print(f"🚀 Actualizando calendario - Última actualización: {last_update_spain}")
            return True

        print(f"✅ Usando cache - Última actualización: {last_update_spain}")
        return False

    except Exception as e:
        print(f"⚠️ Error verificando cache: {e}")
        return True


def update_cache_timestamp():
    """Actualiza el timestamp de la última actualización"""
    try:
        now_utc = datetime.now(pytz.UTC)
        with open(CACHE_TIMESTAMP, 'w') as f:
            f.write(now_utc.isoformat())
        print(f"📅 Cache actualizado: {now_utc}")
    except Exception as e:
        print(f"Error actualizando timestamp: {e}")


def scrape_barcelona_calendar():
    """Extrae los partidos del Barcelona del sitio web - SOLO LALIGA y Champions"""
    url = "https://as.com/resultados/ficha/equipo/barcelona/3/calendario/"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        print("🔍 Iniciando scraping del calendario...")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        matches = []

        # Buscar todos los elementos que contienen partidos
        match_containers = soup.find_all('div', class_=re.compile(r'cont-modulo|modulo'))

        print(f"📦 Encontrados {len(match_containers)} contenedores de partidos")

        for container in match_containers:
            # Buscar el elemento con la fecha
            date_element = container.find('h2', class_='tit-modulo')
            if not date_element:
                continue

            text_content = date_element.get_text()

            # Extraer fecha y hora usando regex
            date_match = re.search(r'([SDMJLX]-)?(\d{2}/\d{2})\s+(\d{2}:\d{2})', text_content)

            if date_match:
                date_str = date_match.group(2)  # "16/08"
                time_str = date_match.group(3)  # "19:30"

                # Extraer competición
                competition_span = date_element.find('span', class_='fecha-evento')
                competition = competition_span.get_text(strip=True) if competition_span else "Partido"

                # FILTRAR: SOLO LALIGA y Champions League
                if "LALIGA" not in competition and "Champions League" not in competition:
                    continue  # Saltar este partido

                # Buscar equipos
                team_elements = container.find_all('span', class_='nombre-equipo')
                if len(team_elements) >= 2:
                    team1 = team_elements[0].get_text(strip=True)
                    team2 = team_elements[1].get_text(strip=True)
                    teams = f"{team1} vs {team2}"

                    # Determinar si es en casa o fuera
                    is_home_match = "Barcelona" in team1
                else:
                    teams = "FC Barcelona vs Rival"
                    is_home_match = True

                # BUSCAR RESULTADO
                resultado = ""

                # 1. Buscar en enlaces con clase 'resultado'
                result_link = container.find('a', class_='resultado')
                if result_link:
                    result_text = result_link.get_text(strip=True)
                    # Limpiar el texto del resultado
                    result_text = re.sub(r'\s+', ' ', result_text)
                    if re.search(r'\d+\s*-\s*\d+', result_text):
                        resultado = result_text
                        print(f"   📊 Resultado encontrado en enlace: {resultado}")

                # 2. Si no hay resultado en enlace, buscar en spans
                if not resultado:
                    score_spans = container.find_all('span', class_=re.compile(r'marcador|resultado|score'))
                    for span in score_spans:
                        span_text = span.get_text(strip=True)
                        if re.search(r'\d+\s*-\s*\d+', span_text):
                            resultado = span_text
                            print(f"   📊 Resultado encontrado en span: {resultado}")
                            break

                # 3. Si no hay resultado, buscar cualquier texto con formato de resultado
                if not resultado:
                    # Buscar patrones como "0 - 3", "2-1", etc.
                    text_elements = container.find_all(string=re.compile(r'\d+\s*[-–]\s*\d+'))
                    for text in text_elements:
                        match = re.search(r'(\d+\s*[-–]\s*\d+)', text.strip())
                        if match:
                            resultado = match.group(1)
                            print(f"   📊 Resultado encontrado en texto: {resultado}")
                            break

                # 4. Si sigue sin haber resultado, verificar si es partido por jugar
                if not resultado:
                    # Buscar guiones que indican "por jugar"
                    if container.find(string=re.compile(r'^\s*-\s*$')):
                        resultado = ""  # Vacío para partidos por jugar
                    else:
                        resultado = ""  # Vacío para partidos sin resultado

                # Construir objeto de partido
                match = {
                    'date_str': date_str,
                    'time_str': time_str,
                    'competition': competition,
                    'teams': teams,
                    'resultado': resultado,
                    'is_home_match': is_home_match
                }

                matches.append(match)
                print(f"✅ Partido añadido: {match}")

        print(f"🎯 Total de partidos encontrados (LALIGA + Champions): {len(matches)}")
        return matches

    except Exception as e:
        print(f"❌ Error en scraping: {str(e)}")
        return []


def create_ics_calendar(matches):
    """Crea un calendario ICS para suscripción con colores según localía y resultados"""
    cal = Calendar()

    # Configuración para suscripciones
    cal.add('prodid', '-//Calendari FC Barcelona//barcelona-calendar.netlify.app//')
    cal.add('version', '2.0')
    cal.add('name', 'FC Barcelona - Partits')
    cal.add('X-WR-CALNAME', 'FC Barcelona - Partits')
    cal.add('X-WR-TIMEZONE', 'Europe/Madrid')
    cal.add('REFRESH-INTERVAL;VALUE=DURATION', 'PT6H')
    cal.add('X-PUBLISHED-TTL', 'PT6H')
    cal.add('CALSCALE', 'GREGORIAN')
    cal.add('METHOD', 'PUBLISH')

    spain_tz = pytz.timezone('Europe/Madrid')
    current_year = datetime.now().year

    for i, match in enumerate(matches):
        event = Event()

        try:
            day, month = match['date_str'].split('/')

            match_month = int(month)
            current_month = datetime.now().month

            if match_month < current_month:
                year = current_year + 1
            else:
                year = current_year

            match_datetime_str = f"{year}-{month}-{day} {match['time_str']}"
            match_dt_naive = datetime.strptime(match_datetime_str, '%Y-%m-%d %H:%M')
            match_dt = spain_tz.localize(match_dt_naive)

            # Determinar si es partido en casa o fuera
            is_home_match = match.get('is_home_match', True)

            # Asignar colores según localía
            if is_home_match:
                color = "#4A6FA5"  # Azul marino suave para partidos en casa
                location = "Camp Nou"
                emoji = "🏠"
                category = "Partit Casa"
            else:
                color = "#D4A5A5"  # Rojo suave para partidos fuera
                location = "Fora"
                emoji = "✈️"
                category = "Partit Fora"

            # Formatear el título y descripción
            resultado = match.get('resultado', '')
            teams_display = match['teams']

            # Si hay resultado real, añadirlo al título
            if resultado and re.search(r'\d+\s*-\s*\d+', resultado):
                # Limpiar y formatear el resultado
                resultado_limpio = re.sub(r'\s+', ' ', resultado).strip()
                teams_display = f"{emoji} {match['teams']} ⚽ {resultado_limpio}"
            else:
                teams_display = f"{emoji} {match['teams']}"

            # Simplificar nombre de competición
            competicion = match['competition']
            if "LALIGA" in competicion:
                competicion_simple = "LALIGA"
            elif "Champions League" in competicion:
                competicion_simple = "Champions"
            else:
                competicion_simple = competicion

            # Configurar el evento
            event.add('summary', teams_display)
            event.add('description', f"{competicion_simple}")
            event.add('dtstart', match_dt)
            event.add('dtend', match_dt + timedelta(hours=2))
            event.add('dtstamp', datetime.now(pytz.UTC))
            event.add('location', location)

            # Propiedades de color compatibles con diferentes calendarios
            event.add('X-APPLE-CALENDAR-COLOR', color)
            event.add('COLOR', color)
            event.add('CATEGORIES', f"{category}, {competicion_simple}")

            # UID estable para suscripciones
            uid = f"barca_{year}{month}{day}{match['time_str'].replace(':', '')}@barcelona-calendar.netlify.app"
            event.add('uid', uid)

            cal.add_component(event)

        except Exception as e:
            print(f"❌ Error procesando partido {match}: {e}")
            continue

    return cal


def get_or_create_calendar():
    """Obtiene el calendario actual o crea uno nuevo si es necesario"""

    # Verificar si necesitamos actualizar
    if should_update():
        print("🔄 Actualizando calendario desde la web...")
        matches = scrape_barcelona_calendar()

        if matches:
            calendar = create_ics_calendar(matches)
            ics_content = calendar.to_ical()

            # Guardar en cache
            try:
                with open(CACHE_FILE, 'wb') as f:
                    f.write(ics_content)
                update_cache_timestamp()
                print(f"✅ Calendario actualizado con {len(matches)} partidos")
                return ics_content
            except Exception as e:
                print(f"⚠️ Error guardando cache: {e}")
                return ics_content
        else:
            print("❌ No se pudieron obtener partidos, intentando usar cache...")

    # Intentar usar cache existente
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'rb') as f:
                print("📂 Sirviendo calendario desde cache")
                return f.read()
    except Exception as e:
        print(f"❌ Error leyendo cache: {e}")

    # Fallback: calendario vacío
    print("⚠️ Creando calendario vacío de emergencia")
    cal = Calendar()
    cal.add('prodid', '-//Calendario FC Barcelona//mxm.dk//')
    cal.add('version', '2.0')
    cal.add('name', 'FC Barcelona - Partidos (Error)')
    return cal.to_ical()


def handler(event, context):
    """Función principal que maneja las peticiones"""
    try:
        ics_content = get_or_create_calendar()

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'text/calendar',
                'Content-Disposition': 'attachment; filename="barcelona.ics"',
                'Cache-Control': 'public, max-age=3600',
                'Last-Modified': datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
            },
            'body': ics_content.decode('utf-8')
        }

    except Exception as e:
        print(f"❌ Error en handler: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Error interno: {str(e)}'})
        }
