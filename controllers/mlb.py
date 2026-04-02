import os
import json
from datetime import datetime
from dateutil import tz
from dateutil.parser import parse
from .common import *


# Constants
TZ_SCHEDULE = [tz.gettz("America/New_York")]
TZ_UTC      = tz.gettz("Etc/UTC")

GAME_FILE_PATH      = 'mlb/data/games_{}.json'
LKUP_FILE_PATH      = 'mlb/data/lookup.json'
TEAMS_FILE_PATH     = 'mlb/data/all_teams.json'
LIVESCORE_FILE_PATH = 'mlb/data/livescores.json'
STANDINGS_FILE_PATH = 'mlb/data/standings_{}.json'
TEAM_OUTPUT_PATH    = 'mlb/api/{}.json'


# Functions
def build_game_id( game_date, home_id, away_id, seq=1 ):
  game_date = game_date.replace('-','')
  home_id = normalize_id(home_id)
  away_id = normalize_id(away_id)
  return f"{game_date}-{home_id}-{away_id}-{seq}"


def normalize_id( team_id ):
  # Normalizes Team IDs coming from ESPN or Baseball Reference to those used by the MLB
  lkup = {}
  if team_id in lkup:
    return lkup[team_id]
  return team_id


def get_team_names():
  team_names     = {}
  league_names   = {}
  division_names = {}

  al_response = json_request('https://statsapi.mlb.com/api/v1/standings?leagueId=103')
  nl_response = json_request('https://statsapi.mlb.com/api/v1/standings?leagueId=104')
  divisions   = [ *al_response['records'] ] + [ *nl_response['records'] ]
  for division in divisions:
    league_id   = division['league']['id']
    division_id = division['division']['id']
    for team in division['teamRecords']:
      team_response = json_request(f"https://statsapi.mlb.com{team['team']['link']}")
      team_id = team['team']['id']
      division_names[division_id] = team_response['teams'][0]['division']['name']
      league_names[league_id]     = team_response['teams'][0]['league']['name']
      team_names[team_id] = {
        'id': team_response['teams'][0]['abbreviation'],
        'city': team_response['teams'][0]['franchiseName'],
        'nick': team_response['teams'][0]['clubName'],
        'full': team_response['teams'][0]['name'],
      }
  data = {
    'teams': team_names,
    'divisions': division_names,
    'leagues': league_names,
  }
  with open( LKUP_FILE_PATH, 'w+') as f:
    json.dump(data, f, indent=2)
    return True


def get_lookup_file():
  try:
    return json_from_file(LKUP_FILE_PATH)
  except:
    get_team_names()
    return json_from_file(LKUP_FILE_PATH)


def update_teams():
  teams_data      = {}
  group_standings = {}

  al_response = json_request('https://statsapi.mlb.com/api/v1/standings?leagueId=103')
  nl_response = json_request('https://statsapi.mlb.com/api/v1/standings?leagueId=104')
  divisions   = [ *al_response['records'] ] + [ *nl_response['records'] ]
  
  lookup = get_lookup_file()
  team_ids = list(( str(team['team']['id']) for division in divisions for team in division['teamRecords'] ))

  for team_id in team_ids:
    if team_id not in lookup['teams']:
      get_team_names()
      lookup = get_lookup_file()

  for division in divisions:
    league_id   = str(division['league']['id'])
    division_id = str(division['division']['id'])
    for team in division['teamRecords']:
      team_lkup = lookup['teams'][str(team['team']['id'])]
      
      conf_name = lookup['leagues'][league_id]
      divs_name = lookup['divisions'][division_id]

      divs_id = divs_name.lower().replace(' ','-')
      conf_id = conf_name.lower().replace(' ','-')
      team_id = team_lkup['id']

      teams_data[team_id] = {
        'team': {
          'id':   team_lkup['id'],
          'city': team_lkup['city'],
          'nick': team_lkup['nick'],
          'full': team_lkup['full'],
          'div':  {'id': divs_id, 'name': divs_name},
          'conf': {'id': conf_id, 'name': conf_name},
        },
        'stats':{
          'gp':  team['gamesPlayed'],
          'w':   int(team['wins']),
          'l':   int(team['losses']),
          'gb_div': team['divisionGamesBack'],
          'gb_wc':  team['wildCardGamesBack'],
          'pct': team['winningPercentage'],
          'stk': team['streak']['streakCode'],
          'rf':  int(team['runsScored']),
          'ra':  int(team['runsAllowed']),
          'rd':  int(team['runsScored']) - int(team['runsAllowed']),
        },
        'rnk':{
          'lg': team['sportRank'],
          'cf': team['leagueRank'],
          'dv': team['divisionRank'],
          'clinch': team['clinched'],
        },
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
  full_schedule = []
  lookup     = get_lookup_file()
  teams_data = json_from_file(TEAMS_FILE_PATH)

  year  = datetime.today().year
  url   = f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={year}-01-01&endDate={year}-12-31&gameType[]=R&gameType[]=F&gameType[]=D&gameType[]=L&gameType[]=W&gameType[]=C&gameType[]=P'
  games = json_request(url)
  for day in games['dates']:
    for game in day['games']:
      game_date    = game['officialDate']
      game_time    = parse(game['gameDate'])
      
      if game['status']['statusCode'] == 'S':
        game_final = ''
      elif game['status']['abstractGameState'] == 'Final':
        if game['status']['statusCode'] == 'F':
          game_final = 'final'
        else:
          game_final = game['status']['detailedState']  
      elif game['status']['abstractGameState'] == 'Live':
        game_final = 'live'
      else:
        game_final = '???'
      
      home_team  = teams_data[lookup['teams'][str(game['teams']['home']['team']['id'])]['id']]
      home_id    = home_team['team']['id']
      home_name  = home_team['team']['full']

      away_team  = teams_data[lookup['teams'][str(game['teams']['away']['team']['id'])]['id']]
      away_id    = away_team['team']['id']
      away_name  = away_team['team']['full']

      try:
        home_score = game['teams']['home']['score']
        away_score = game['teams']['away']['score']
        home_outcome = "win" if home_score > away_score else ("loss" if home_score < away_score else "tie")
        away_outcome = "win" if away_score > home_score else ("loss" if away_score < home_score else "tie")
      except:
        home_score = None
        away_score = None
        home_outcome = "upcoming"
        away_outcome = "upcoming"

      game_id = build_game_id( game_date.replace('-',''), home_id, away_id, game['gameNumber'] )

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
  
  team_schedules = {team['id']: [] for team in lookup['teams'].values()}
  
  for game in full_schedule:
    team_schedules[game['home_id']].append({
      'game_id': game['game_id'],
      'game_time_utc': game['game_time_utc'],
      'game_date': game['game_date'],
      'final': game['final'],
      'outcome': game['home_outcome'],
      'location': 'Home',
      'score': [game['home_score'], game['away_score']],
      'opponent': {
        'id': game['away_id'],
        'name': game['away_name'],
        'stats': teams_data[game['away_id']]['stats']
      },
    })
    team_schedules[game['away_id']].append({
      'game_id': game['game_id'],
      'game_time_utc': game['game_time_utc'],
      'game_date': game['game_date'],
      'final': game['final'],
      'location': 'Away',
      'outcome': game['away_outcome'],
      'score': [game['away_score'], game['home_score']],
      'opponent': {
        'id': game['home_id'],
        'name': game['home_name'],
        'stats': teams_data[game['home_id']]['stats']
      },
    })

  for team_id in team_schedules:
    with open( GAME_FILE_PATH.format(team_id.lower()), 'w+') as f:
      json.dump(team_schedules[team_id], f, indent=2)


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

    team['games'] = {'past':[], 'upcoming': []}

    if num_past_games >= games_back and num_future_games >= games_ahead:
      team['games']['past']     = past_games[-games_back:]
      team['games']['upcoming'] = future_games[0:games_ahead]
    elif num_past_games < games_back and num_future_games >= games_ahead:
      team['games']['past']     = past_games
      team['games']['upcoming'] = future_games[0:(total_games-num_pas_games)]
    elif num_past_games >= games_back and num_future_games < games_ahead:
      team['games']['past']     = past_games[-(total_games-num_future_games):]
      team['games']['upcoming'] = future_games
    else:
      team['games']['past']     = past_games
      team['games']['upcoming'] = future_games

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
        away_team = teams[g['opponent']['id']]
      else:
        away_team = team
        home_team = teams[g['opponent']['id']]
    
