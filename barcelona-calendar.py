import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, timedelta
import pytz
import re
import os
import platform

# --- Configuración de Paths ---

# Definición del archivo de salida que será subido por Git
OUTPUT_FILE = 'barcelona.ics'

# La cache se usa para evitar hacer scraping si ya se ha hecho hoy.
# En GitHub Actions, /tmp/ es el lugar seguro para almacenar archivos temporales.
if platform.system() == "Windows":
    CACHE_DIR = "C:/temp/"
else:
    CACHE_DIR = "/tmp/"

os.makedirs(CACHE_DIR, exist_ok=True)

CACHE_TIMESTAMP = os.path.join(CACHE_DIR, 'barcelona_cache_timestamp.txt')


# --- Lógica de Control de Cache ---

def should_update():
    """Determina si debe actualizar el calendario (solo una vez al día después de las 9 AM hora española)"""
    try:
        # Si el archivo de cache final no existe o el timestamp no existe, SIEMPRE actualizar
        if not os.path.exists(CACHE_TIMESTAMP) or not os.path.exists(OUTPUT_FILE):
            print("🚀 Actualizando calendario - Cache o Output no encontrado.")
            return True

        with open(CACHE_TIMESTAMP, 'r') as f:
            last_update_str = f.read().strip()
            last_update = datetime.fromisoformat(last_update_str)

        spain_tz = pytz.timezone('Europe/Madrid')
        now_spain = datetime.now(spain_tz)
        last_update_spain = last_update.astimezone(spain_tz)

        # Regla de actualización: Una vez al día, después de las 9 AM hora española

        # Caso 1: La última actualización es de un día anterior
        if last_update_spain.date() < now_spain.date():
            print(f"🚀 Actualizando calendario - Última actualización es de ayer: {last_update_spain.date()}")
            return True

        # Caso 2: La actualización es de hoy, pero fue antes de las 9 AM
        if last_update_spain.date() == now_spain.date() and now_spain.hour >= 9 and last_update_spain.hour < 9:
            print(f"🚀 Actualizando calendario - Hoy son más de las 9:00 AM, la última fue antes.")
            return True

        print(f"✅ Usando cache - Última actualización: {last_update_spain.strftime('%Y-%m-%d %H:%M:%S')}")
        return False

    except Exception as e:
        print(f"⚠️ Error verificando cache ({e}). Forzando actualización.")
        return True


def update_cache_timestamp():
    """Actualiza el timestamp de la última actualización"""
    try:
        now_utc = datetime.now(pytz.UTC)
        with open(CACHE_TIMESTAMP, 'w') as f:
            f.write(now_utc.isoformat())
        print(f"📅 Timestamp de Cache actualizado a: {now_utc.strftime('%Y-%m-%d %H:%M:%S')} (UTC)")
    except Exception as e:
        print(f"Error actualizando timestamp: {e}")


# --- Funciones de Web Scraping y ICS (Mantenidas) ---

def scrape_barcelona_calendar():
    """Extrae los partidos del Barcelona del sitio web - SOLO LALIGA y Champions"""
    url = "https://as.com/resultados/ficha/equipo/barcelona/3/calendario/"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        print("🔍 Iniciando scraping del calendario...")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        matches = []

        match_containers = soup.find_all('div', class_=re.compile(r'cont-modulo|modulo'))

        print(f"📦 Encontrados {len(match_containers)} contenedores de partidos")

        current_datetime = datetime.now(pytz.timezone('Europe/Madrid'))
        current_year = current_datetime.year
        next_year = current_year + 1

        for container in match_containers:
            date_element = container.find('h2', class_='tit-modulo')
            if not date_element:
                continue

            text_content = date_element.get_text()
            date_match = re.search(r'([SDMJLX]-)?(\d{2}/\d{2})\s+(\d{2}:\d{2})', text_content)

            if date_match:
                date_str = date_match.group(2)
                time_str = date_match.group(3)

                competition_span = date_element.find('span', class_='fecha-evento')
                competition = competition_span.get_text(strip=True) if competition_span else "Partido"

                if "LALIGA" not in competition and "Champions League" not in competition:
                    continue

                team_elements = container.find_all('span', class_='nombre-equipo')
                teams = "FC Barcelona vs Rival"
                is_home_match = True

                if len(team_elements) >= 2:
                    team1 = team_elements[0].get_text(strip=True)
                    team2 = team_elements[1].get_text(strip=True)
                    teams = f"{team1} vs {team2}"
                    is_home_match = "Barcelona" in team1

                resultado = ""
                for class_name in ['resultado', 'marcador', 'score']:
                    score_spans = container.find_all(class_=re.compile(class_name))
                    for span in score_spans:
                        span_text = span.get_text(strip=True)
                        if re.search(r'\d+\s*[-–]\s*\d+', span_text):
                            resultado = re.sub(r'\s+', ' ', span_text).strip()
                            break
                    if resultado:
                        break

                match = {
                    'date_str': date_str,
                    'time_str': time_str,
                    'competition': competition,
                    'teams': teams,
                    'resultado': resultado,
                    'is_home_match': is_home_match
                }

                matches.append(match)
                print(f"✅ Partido añadido: {teams} ({resultado if resultado else 'Pendiente'})")

        return matches

    except Exception as e:
        print(f"❌ Error grave en scraping: {str(e)}")
        return []


def create_ics_calendar(matches):
    """Crea un calendario ICS para suscripción con colores según localía y resultados"""
    cal = Calendar()

    cal.add('prodid', '-//Calendari FC Barcelona//barcelona-calendar.netlify.app//')
    cal.add('version', '2.0')
    cal.add('name', 'FC Barcelona - Partits (Actualització Diària)')
    cal.add('X-WR-CALNAME', 'FC Barcelona - Partits')
    cal.add('X-WR-TIMEZONE', 'Europe/Madrid')
    cal.add('REFRESH-INTERVAL;VALUE=DURATION', 'PT6H')
    cal.add('X-PUBLISHED-TTL', 'PT6H')
    cal.add('CALSCALE', 'GREGORIAN')
    cal.add('METHOD', 'PUBLISH')

    spain_tz = pytz.timezone('Europe/Madrid')
    current_datetime = datetime.now(spain_tz)
    current_year = current_datetime.year
    next_year = current_year + 1

    for match in matches:
        event = Event()

        try:
            day, month = match['date_str'].split('/')
            match_month = int(month)

            if match_month < current_datetime.month and current_datetime.month >= 10:
                year = next_year
            else:
                year = current_year

            match_datetime_str = f"{year}-{month}-{day} {match['time_str']}"
            match_dt_naive = datetime.strptime(match_datetime_str, '%Y-%m-%d %H:%M')
            match_dt = spain_tz.localize(match_dt_naive)

            is_home_match = match.get('is_home_match', True)

            if is_home_match:
                color = "#004D98"
                location = "Estadi Olímpic Lluís Companys / Spotify Camp Nou"
                emoji = "🏟️"
            else:
                color = "#A50044"
                location = "Camp Visitant"
                emoji = "⚔️"

            resultado = match.get('resultado', '')
            competicion = match['competition']
            competicion_simple = "LALIGA" if "LALIGA" in competicion else "Champions League" if "Champions League" in competicion else competicion

            if resultado and re.search(r'\d+\s*-\s*\d+', resultado):
                resultado_limpio = re.sub(r'\s+', ' ', resultado).strip()
                summary = f"{emoji} ⚽ FINAL: {match['teams']} ({resultado_limpio}) ({competicion_simple})"
                description = f"Resultat Final: {resultado_limpio}. Competició: {competicion}"
                end_time = match_dt + timedelta(hours=2, minutes=15)
            else:
                summary = f"{emoji} {match['teams']} ({competicion_simple})"
                description = f"Partit: {match['teams']}. Competició: {competicion}"
                end_time = match_dt + timedelta(hours=2)

            event.add('summary', summary)
            event.add('description', description)
            event.add('dtstart', match_dt)
            event.add('dtend', end_time)
            event.add('dtstamp', datetime.now(pytz.UTC))
            event.add('location', location)

            event.add('X-APPLE-CALENDAR-COLOR', color)
            event.add('COLOR', color)
            uid = f"barca_{match_dt.strftime('%Y%m%d%H%M')}_{match['teams'].replace(' ', '')}@barcelona-calendar.netlify.app"
            event.add('uid', uid)

            cal.add_component(event)

        except Exception as e:
            print(f"❌ Error procesando partido {match}: {e}")
            continue

    return cal


# --- Función de Ejecución Principal (para GitHub Actions) ---

if __name__ == '__main__':

    # El script SOLO se ejecuta si la lógica de cache lo permite
    if should_update():
        print("🔄 Iniciando proceso de actualización...")

        matches = scrape_barcelona_calendar()

        if matches:
            calendar = create_ics_calendar(matches)
            ics_content = calendar.to_ical()

            # 1. Guardar el archivo ICS en la raíz del proyecto (usando OUTPUT_FILE)
            try:
                with open(OUTPUT_FILE, 'wb') as f:
                    f.write(ics_content)
                print(f"✅ Calendario ICS guardado exitosamente en {OUTPUT_FILE}.")
            except Exception as e:
                print(f"⚠️ Error guardando el archivo de salida {OUTPUT_FILE}: {e}")
                exit(1)  # Finalizar con error

            # 2. Guardar el timestamp (para la próxima ejecución)
            update_cache_timestamp()

        else:
            print("❌ No se pudieron obtener partidos. El archivo ICS existente no será modificado.")

    else:
        print("El calendario no necesita actualización en este momento según la política de cache.")