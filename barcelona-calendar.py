import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, timedelta
import pytz
import re
import os
import sys

# --- Configuración de Paths ---

# Definición del archivo de salida
OUTPUT_FILE = 'barcelona.ics'


# --- Funciones de Web Scraping y ICS ---

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

                # Filtrar solo LALIGA y Champions
                if "LALIGA" not in competition and "Champions League" not in competition:
                    continue

                team_elements = container.find_all('span', class_='nombre-equipo')
                teams = "FC Barcelona vs Rival"
                is_home_match = True

                if len(team_elements) >= 2:
                    team1 = team_elements[0].get_text(strip=True)
                    team2 = team_elements[1].get_text(strip=True)
                    teams = f"{team1} vs {team2}"
                    is_home_match = "Barcelona" in team1 or "Barça" in team1

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

    # Metadata importante para suscripción
    cal.add('prodid', '-//Calendari FC Barcelona//github.com//')
    cal.add('version', '2.0')
    cal.add('name', 'FC Barcelona - Partidos')
    cal.add('X-WR-CALNAME', 'FC Barcelona - Partidos')
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

            # Determinar el año correcto (para partidos entre temporadas)
            if match_month < current_datetime.month and current_datetime.month >= 10:
                year = next_year
            else:
                year = current_year

            match_datetime_str = f"{year}-{month}-{day} {match['time_str']}"
            match_dt_naive = datetime.strptime(match_datetime_str, '%Y-%m-%d %H:%M')
            match_dt = spain_tz.localize(match_dt_naive)

            is_home_match = match.get('is_home_match', True)

            # Colores según localía
            if is_home_match:
                color = "#004D98"  # Azul Barça
                location = "Spotify Camp Nou / Estadi Olímpic"
                emoji = "🏟️"
            else:
                color = "#A50044"  # Granate visitante
                location = "Fuera de casa"
                emoji = "⚔️"

            resultado = match.get('resultado', '')
            competicion = match['competition']

            # Simplificar nombre de competición
            if "LALIGA" in competicion:
                competicion_simple = "LALIGA"
            elif "Champions League" in competicion:
                competicion_simple = "Champions"
            else:
                competicion_simple = competicion

            # Formato del evento según si ya se jugó
            if resultado and re.search(r'\d+\s*-\s*\d+', resultado):
                resultado_limpio = re.sub(r'\s+', ' ', resultado).strip()
                summary = f"{emoji} ⚽ {match['teams']} ({resultado_limpio})"
                description = f"Resultado: {resultado_limpio}\nCompetición: {competicion}"
                end_time = match_dt + timedelta(hours=2, minutes=15)
            else:
                summary = f"{emoji} {match['teams']}"
                description = f"Partido: {match['teams']}\nCompetición: {competicion}"
                end_time = match_dt + timedelta(hours=2)

            event.add('summary', summary)
            event.add('description', description)
            event.add('dtstart', match_dt)
            event.add('dtend', end_time)
            event.add('dtstamp', datetime.now(pytz.UTC))
            event.add('location', location)

            # Añadir color para calendarios que lo soportan
            event.add('X-APPLE-CALENDAR-COLOR', color)
            event.add('COLOR', color)

            # UID único para cada evento
            uid = f"barca_{match_dt.strftime('%Y%m%d%H%M')}_{hash(match['teams']) % 10000}@github.com"
            event.add('uid', uid)

            cal.add_component(event)

        except Exception as e:
            print(f"❌ Error procesando partido {match}: {e}")
            continue

    return cal


# --- Función de Ejecución Principal (SIMPLIFICADA para GitHub Actions) ---

if __name__ == '__main__':
    print("🔄 Iniciando generación de calendario FC Barcelona...")

    # En GitHub Actions, SIEMPRE generamos el archivo
    matches = scrape_barcelona_calendar()

    if matches:
        print(f"📊 Partidos encontrados: {len(matches)}")

        calendar = create_ics_calendar(matches)
        ics_content = calendar.to_ical()

        # Guardar el archivo ICS
        try:
            with open(OUTPUT_FILE, 'wb') as f:
                f.write(ics_content)
            print(f"✅ Calendario ICS guardado exitosamente en {OUTPUT_FILE}")

            # Mostrar información del archivo generado
            file_size = os.path.getsize(OUTPUT_FILE)
            print(f"📏 Tamaño del archivo: {file_size} bytes")
            print(f"🗓️  Partidos en calendario: {len(matches)}")

        except Exception as e:
            print(f"❌ Error guardando {OUTPUT_FILE}: {e}")
            sys.exit(1)
    else:
        print("⚠️ No se pudieron obtener partidos. Manteniendo archivo existente si hay.")
        # No salimos con error para no romper el workflow si falla temporalmente