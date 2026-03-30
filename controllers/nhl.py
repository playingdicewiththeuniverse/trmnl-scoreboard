import os
import json
from datetime import datetime
from dateutil import tz
from dateutil.parser import parse
from .common import *


# Constants
TZ_SCHEDULE = [tz.gettz("America/New_York")]
TZ_UTC      = tz.gettz("Etc/UTC")

GAME_FILE_PATH      = 'nhl/data/games_{}.json'
TEAMS_FILE_PATH     = 'nhl/data/all_teams.json'
LIVESCORE_FILE_PATH = 'nhl/data/livescores.json'
STANDINGS_FILE_PATH = 'nhl/data/standings_{}.json'
TEAM_OUTPUT_PATH    = 'nhl/api/{}_summary.json'
NEXT_GAME_PATH      = 'nhl/api/{}_next_game.json'

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
    with open( STANDINGS_FILE_PATH.format(group_id), 'w+') as f:
      json.dump(group_standings[group_id], f, indent=2)

  with open( TEAMS_FILE_PATH, 'w+') as f:
    json.dump(teams_data, f, indent=2)
    return True


def update_games():
  year = datetime.today().year + 1 if datetime.today().month > 9 else datetime.today().year
  url  = f'https://www.hockey-reference.com/leagues/NHL_{year}_games.html'
  soup = http_request(url)
  rows = soup.select('table#games tbody tr:not(.thead)')
  full_schedule = []

  all_team_ids = {}

  if len(rows) == 0:
    return False

  for row in rows:
    game_date    = get_data_stat(row, 'date_game')
    game_time    = parse_datetime_to_utc( get_data_stat(row, 'date_game'), get_data_stat(row, 'time_game'), "America/New_York")
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
      'game_date': game_date,
      'game_time_utc': f"{game_time}",
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

  # with open( os.path.join(OUTPUT_PATH, 'json', 'games', '_all.json'), 'w+') as f:
  #   json.dump(full_schedule, f, indent=2)
  
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
      'location': 'home',
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
      'location': 'away',
    })

  for team_id in team_schedules:
    with open( GAME_FILE_PATH.format(team_id.lower()), 'w+') as f:
      json.dump(team_schedules[team_id], f, indent=2)


def update_livescores():
  url = 'https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard'
  response = json_request(url)
  live_data = {}

  if response['events'] == []:
    return False

  for event in response['events']:
    if event['status']['type']['name'] != 'STATUS_SCHEDULED':
      game_date = f"{parse(event['date'], tzinfos=TZ_SCHEDULE).astimezone().strftime('%Y%m%d')}"
      h = 1 if event['competitions'][0]['competitors'][0]['homeAway'] == 'away' else 0
      a = 1 - h
      home_id  = event['competitions'][0]['competitors'][h]['team']['abbreviation']
      away_id  = event['competitions'][0]['competitors'][a]['team']['abbreviation']
      home_scr = event['competitions'][0]['competitors'][h]['score']
      away_scr = event['competitions'][0]['competitors'][a]['score']
      game_id  = build_game_id( game_date, home_id, away_id )
      clock    = event['status']['displayClock']
      period   = event['status']['period']
      status   = event['status']['type']['name']
      detail   = event['status']['type']['shortDetail']
      live_data[game_id] = {
        'clock': clock,
        'period': period,
        'status': status,
        'detail': detail,
        'home_score': int(home_scr),
        'away_score': int(away_scr),
      }

  with open( LIVESCORE_FILE_PATH, 'w+') as f:
    json.dump(live_data, f, indent=2)
    return True


def generate_team_json():
  teams = json_from_file( TEAMS_FILE_PATH )
  for team_id in teams:
    team = teams[team_id]

    all_games    = json_from_file( GAME_FILE_PATH.format(team_id.lower()) )
    past_games   = []
    future_games = []
    for game in all_games:
      if game['outcome'] == 'upcoming':
        future_games.append(game)
      else:
        past_games.append(game)

    num_past_games   = len(past_games)
    num_future_games = len(future_games)

    games_back  = 3
    games_ahead = 4
    total_games = games_ahead + games_back

    if num_past_games >= games_back and num_future_games >= games_ahead:
      team['games'] = [*past_games[-games_back:]] + [*future_games[0:games_ahead]]
    elif num_past_games < games_back and num_future_games >= games_ahead:
      team['games'] = [*past_games] + [*future_games[0:(total_games-num_pas_games)]]
    elif num_past_games >= games_back and num_future_games < games_ahead:
      team['games'] = [*past_games[-(total_games-num_future_games):]] + [*future_games]
    else:
      team['games'] = [*past_games] + [*future_games]

    team['standings'] = {
      'division':   json_from_file( STANDINGS_FILE_PATH.format(team['team']['div']['id']) ),
      'conference': json_from_file( STANDINGS_FILE_PATH.format(team['team']['conf']['id']) ),
    }

    with open( TEAM_OUTPUT_PATH.format(team_id), 'w+') as f:
      json.dump(team, f, indent=2)

    next_game = {}
    for g in future_games:
      if g['location'] == 'home':
        home_team = team
        away_team = teams[g['opponent_id']]
      else:
        away_team = team
        home_team = teams[g['opponent_id']]

      next_game = {
        'game_time_utc': g['game_time_utc'],
        'home_team': {
          'id':   home_team['team']['id'],
          'city': home_team['team']['city'],
          'nick': home_team['team']['nick'],
          'full': home_team['team']['full'],
          'record': {
            'gp':  home_team['stats']['gp'],
            'w':   home_team['stats']['w'],
            'l':   home_team['stats']['l'],
            'otl': home_team['stats']['otl'],
            'pts': home_team['stats']['pts'],
            'pct': home_team['stats']['pct'],
          }
        },
        'away_team': {
          'id':   away_team['team']['id'],
          'city': away_team['team']['city'],
          'nick': away_team['team']['nick'],
          'full': away_team['team']['full'],
          'record': {
            'gp':  away_team['stats']['gp'],
            'w':   away_team['stats']['w'],
            'l':   away_team['stats']['l'],
            'otl': away_team['stats']['otl'],
            'pts': away_team['stats']['pts'],
            'pct': away_team['stats']['pct'],
          }
        }
      }

    with open( NEXT_GAME_PATH.format(team_id), 'w+') as f:
      json.dump(next_game, f, indent=2)      
