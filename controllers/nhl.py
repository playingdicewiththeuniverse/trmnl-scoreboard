import os
import json
from datetime import datetime
from dateutil import tz
from dateutil.parser import parse
from common import http_request, json_request, get_data_stat


# Constants
TZ_SCHEDULE = [tz.gettz("America/New_York")]
TZ_UTC      = tz.gettz("Etc/UTC")
OUTPUT_PATH = '../nhl'


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


def update_teams():
  url = 'https://api-web.nhle.com/v1/standings/now'
  response = json_request(url)
  
  if 'standings' not in response or response['standings'] == []:
    return False

  teams_data      = {}
  group_standings = {}

  for team in response['standings']:
    team_id   = team['teamAbbrev']['default']
    divs_id   = f"div-{team['divisionName'].lower()}"
    conf_id   = f"conf-{team['conferenceName'].lower()}"
    divs_name = f"{team['divisionName']} Division"
    conf_name = f"{team['conferenceName']} Conference"

    teams_data[team_id] = {
      'team': {
        'id':   team['teamAbbrev']['default'],
        'city': team['placeName']['default'],
        'nick': team['teamCommonName']['default'],
        'full': team['teamName']['default'],
        'div':  {'id': divs_id, 'name': divs_name},
        'conf': {'id': conf_id, 'name': conf_name},
      },
      'stats': {
        'gp':  team['gamesPlayed'],
        'w':   team['wins'],
        'l':   team['losses'],
        't':   team['ties'],
        'otl': team['otLosses'],
        'pts': team['points'],
        'pct': None if team['gamesPlayed'] == 0 else  round( (team['wins']+team['wins']+team['ties']+team['otLosses']) / (2.0*team['gamesPlayed']), 5 ),
        'stk': f"{team['streakCode']}{team['streakCount']}",
        'gf':  team['goalFor'],
        'ga':  team['goalAgainst'],
        'gd':  team['goalDifferential'],
      },
      'rnk': {
        'lg': team['leagueSequence'],
        'cf': team['conferenceSequence'],
        'dv': team['divisionSequence'],
        'wc': None if team['wildcardSequence'] == 0 else team['wildcardSequence'],
      }
    }

    group_standings[divs_id] = group_standings.get(divs_id, [])
    group_standings[conf_id] = group_standings.get(conf_id, [])

    group_standings[divs_id].append( json.loads(json.dumps(teams_data[team_id]) ) )
    group_standings[conf_id].append( json.loads(json.dumps(teams_data[team_id]) ) )

  for group_id in group_standings:
    with open( os.path.join(OUTPUT_PATH, 'data', f'standings_{group_id}.json'), 'w+') as f:
      json.dump(group_standings[group_id], f, indent=2)


  with open( os.path.join(OUTPUT_PATH, 'data', f'all_teams.json'), 'w+') as f:
    json.dump(teams_data, f, indent=2)

  # for team_id in teams_data:
  #   del teams_data[team_id]['stats']
  #   teams_data[team_id]['standings'] = {
  #     'division':   group_standings[teams_data[team_id]['team']['div']['id']],
  #     'conference': group_standings[teams_data[team_id]['team']['conf']['id']],
  #   }
  #   with open( os.path.join(OUTPUT_PATH, 'json', 'teams', f'{team_id}.json'), 'w+') as f:
  #     json.dump(teams_data[team_id]['standings'], f, indent=2)

  return True


def update_games():
  year = datetime.today().year + 1 if datetime.today().month > 9 else datetime.today().year
  url  = f'https://www.hockey-reference.com/leagues/NHL_{year}_games.html'
  soup = http_request(url)
  rows = soup.select('table#games tbody tr:not(.thead)')
  full_schedule = []

  all_team_ids = {}

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
    all_team_ids[home_id] = home_id

    full_schedule.append({
      'game_id': game_id,
      'game_time_utc': f"{parse(game_time, tzinfos=TZ_SCHEDULE).astimezone(TZ_UTC)}",
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

  with open( os.path.join(OUTPUT_PATH, 'json', 'games', '_all.json'), 'w+') as f:
    json.dump(full_schedule, f, indent=2)
  
  team_schedules = {team_id: [] for team_id in all_team_ids}
  
  for game in full_schedule:
    team_schedules[game['home_id']].append({
      'game_id': game['game_id'],
      'game_time_utc': game['game_time_utc'],
      'game_date': game['game_date'],
      'final': game['final'],
      'outcome': game['home_outcome'],
      'score': [game['home_score'], game['away_score']],
      'opponent_id': game['away_id'],
      'opponent_name': game['away_name'],
    })
    team_schedules[game['away_id']].append({
      'game_id': game['game_id'],
      'game_time_utc': game['game_time_utc'],
      'game_date': game['game_date'],
      'final': game['final'],
      'outcome': game['away_outcome'],
      'score': [game['away_score'], game['home_score']],
      'opponent_id': game['home_id'],
      'opponent_name': game['home_name'],
    })

  for team_id in team_schedules:
    with open( os.path.join(OUTPUT_PATH, 'data', f'games_{team_id.lower()}.json'), 'w+') as f:
      json.dump(team_schedules[team_id], f, indent=2)


# update_games()
update_teams()