import os
import json
from datetime import datetime
from dateutil import tz
from dateutil.parser import parse
from common import http_request, get_data_stat


# Constants
tz_schedule = [tz.gettz("America/New_York")]
tz_utc      = tz.gettz("Etc/UTC")


# Functions
def build_game_id( game_date, home_id, away_id ):
  game_date = game_date.replace('-','')
  home_id = normalize_id(home_id)
  away_id = normalize_id(away_id)
  return f"{game_date}-{home_id}-{away_id}"


def normalize_id( team_id ):
  # Normalizes Team IDs coming from ESPN or Hockey Reference to those used by the NHL
  lkup = {'LA': 'LAK', 'NJ': 'NJD', 'SJ': 'SJS', 'TB': 'TBL', 'UTAH': 'UTA', 'VEG': 'VGK'}
  if team_id in lkup:
    return lkup[team_id]
  return team_id


def update_master_schedule():
  year = datetime.today().year + 1 if datetime.today().month > 9 else datetime.today().year
  url  = f'https://www.hockey-reference.com/leagues/NHL_{year}_games.html'
  soup = http_request(url)
  rows = soup.select('table#games tbody tr:not(.thead)')
  full_schedule = []

  if len(rows) == 0:
    # print(f"Attempting to scrape '{url}', no rows found for 'table#games'")
    return False

  for row in rows:
    game_date    = get_data_stat(row, 'date_game')
    game_time    = f"{game_date} {get_data_stat(row, 'time_game')}"
    game_final   = f"Final/{get_data_stat(row, 'overtimes')}" if get_data_stat(row, 'overtimes') else ("Final" if get_data_stat(row, 'date_game', href='True') else "")
    home_id      = normalize_id(get_data_stat(row, 'home_team_name', href=True)[7:10])
    away_id      = normalize_id(get_data_stat(row, 'visitor_team_name', href=True)[7:10])
    home_name    = get_data_stat(row, 'home_team_name')
    away_name    = get_data_stat(row, 'visitor_team_name')
    home_score,  = get_data_stat(row, 'home_goals'),
    away_score,  = get_data_stat(row, 'visitor_goals'),
    home_outcome = "upcoming" if game_final == "" else ("win" if home_score > away_score else ("loss" if home_score < away_score else "tie"))
    away_outcome = "upcoming" if game_final == "" else ("win" if away_score > home_score else ("loss" if away_score < home_score else "tie"))
    game_id      = build_game_id( game_date, home_id, away_id )
        
    full_schedule.append({
      'game_id': game_id,
      'game_time_utc': f"{parse(game_time, tzinfos=tz_schedule).astimezone(tz_utc)}",
      'game_date': f"{parse(game_time).strftime('%Y-%m-%d')}",
      'final': game_final,
      'home_id': home_id,
      'home_name': home_name,
      'home_score': home_score,
      'home_outcome': home_outcome,
      'away_id': away_id,
      'away_name': away_name,
      'away_score': away_score,
      'away_outcome': away_outcome,
    })

  with open( os.path.join('..', 'schedules', 'nhl', '_master.json'), 'w+') as f:
    json.dump(full_schedule, f, indent=2)
    return True

update_master_schedule()