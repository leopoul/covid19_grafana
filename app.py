import requests
import pytz
import time
import json
import yaml
import os

from datetime import datetime, tzinfo, timedelta
from influxdb import InfluxDBClient
from flask_cors import CORS
from flask import Flask, jsonify, request


LOCAL_CACHE = int(os.getenv('DATASOURCE_LOCAL_CACHE_TIME', 3600))
URL = os.getenv('DATASOURCE_URL',
                'https://coronavirus-tracker-api.herokuapp.com/all')
INFLUX_DB = os.getenv('INFLUX_DB', 'covid19')
INFLUX_USER = os.getenv('INFLUX_USER')
INFLUX_PASS = os.getenv('INFLUX_PASS')
INFLUX_DBPORT = os.getenv('INFLUX_DBPORT', 8086)

app = Flask(__name__)
CORS(app)

keys = ['confirmed', 'deaths', 'recovered']


def get_locations():
    target_locations = []
    seen_locations = {}
    data = requests.get(URL).json()
    for k in keys:
        category_data = data[k]

        locations = category_data['locations']
        for l in locations:
            location = {}
            location['country'] = l['country']
            location['province'] = l['province']
            location_hash = "{}_{}".format(
                location['country'], location['province'])
            if location_hash in seen_locations:
                continue
            seen_locations[location_hash] = 1
            try:
                coordinates = l['coordinates']
            except Exception as e:
                print('Could not parse {}: {}. Error: {}'.format(k, l, e))
                continue
            location['longitude'] = float(coordinates['long'])
            location['latitude'] = float(coordinates['lat'])
            location['name'] = '{} {}'.format(
                location['country'], location['province'])
            location['key'] = location['name']
            target_locations.append(location)

    return target_locations


@app.route('/locations')
def locations():
    locations = get_locations()
    return jsonify(locations)


class Zone(tzinfo):
    def __init__(self, offset, isdst, name):
        self.offset = offset
        self.isdst = isdst
        self.name = name

    def utcoffset(self, dt):
        return timedelta(hours=self.offset) + self.dst(dt)

    def dst(self, dt):
        return timedelta(hours=1) if self.isdst else timedelta(0)

    def tzname(self, dt):
        return self.name


GMT = Zone(0, False, 'GMT')


def determine_cached():
    now = int(time.time())
    with open(r'/app/last_run.yaml') as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    last_run = data['last_run']
    points_parsed = data['points_parsed']
    print(last_run, points_parsed)
    if now - last_run > LOCAL_CACHE:
        return True, last_run, points_parsed
    return False, last_run, points_parsed


def update_cached(points):
    now = int(time.time())
    data = {"last_run": now, "points_parsed": points}
    with open(r'/app/last_run.yaml', 'w') as f:
        data = yaml.dump(data, f)


def get_points():
    measurements = []
    measurements_hash = {}
    data = requests.get(URL).json()
    for k in keys:
        category_data = data[k]
        time_location_hash = {}
        locations = category_data['locations']
        for l in locations:
            latest_value = l['latest']
            today = datetime.today().replace(hour=0, minute=0, second=0,
                                             microsecond=0).replace(tzinfo=GMT).timestamp()

            country = l['country']
            province = l['province']
            location_hash = "{} {}".format(country, province)
            time_loc_hash = "{}:{}".format(today, location_hash)

            if time_loc_hash not in measurements_hash:
                measurements_hash[time_loc_hash] = {'measurement': 'covid19', 'tags': {
                }, 'fields': {}, 'time': int(today) * 1000 * 1000 * 1000}
                measurements_hash[time_loc_hash]['tags']['location'] = location_hash
                measurements_hash[time_loc_hash]['tags']['country'] = country
                measurements_hash[time_loc_hash]['tags']['province'] = province.strip(
                )
            measurements_hash[time_loc_hash]['fields'][k] = latest_value

            location_history = l['history']
            for h in location_history:
                datemdy = datetime.strptime(h, '%m/%d/%y').replace(
                    hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=GMT).timestamp()
                time_loc_hash = "{}:{}".format(datemdy, location_hash)
                value = int(location_history[h])
                if time_loc_hash not in measurements_hash:
                    measurements_hash[time_loc_hash] = {'measurement': 'covid19', 'tags': {
                    }, 'fields': {}, 'time': int(datemdy) * 1000 * 1000 * 1000}
                    measurements_hash[time_loc_hash]['tags']['location'] = location_hash
                    measurements_hash[time_loc_hash]['tags']['country'] = country
                    measurements_hash[time_loc_hash]['tags']['province'] = province.strip(
                    )
                measurements_hash[time_loc_hash]['fields'][k] = value

    for m in measurements_hash:
        measurements.append(measurements_hash[m])

    return measurements


def fetch_retry(count, force=False):
    if force is False:
        should_run, lastrun, points = determine_cached()
        if should_run is False:
            return "URL: {} - {}: Cached: {}".format(URL, lastrun, points)
    if count > 0:
        try:
            print('attempt {}'.format(count))
            points = get_points()
            client = InfluxDBClient('influxdb', INFLUX_DBPORT, INFLUX_USER, INFLUX_PASS, INFLUX_DB)
            print("Parsed {}".format(len(points)))
            client.write_points(points)
            update_cached(len(points))
            return "{} - parsed {}".format(URL, len(points))
        except Exception as e:
            print('Could not get points, retrying attempt {}'.format(count))
            time.sleep(10)
            count = count - 1
            fetch_retry(count)
    else:
        raise Exception('Failed to get points')


@app.route('/refresh')
def refresh():
    count = 5
    try:
        result = fetch_retry(5)
    except Exception as e:
        result = e
    return jsonify({'status': result})


if __name__ == '__main__':
    fetch_retry(5, force=True)
    app.run(host="0.0.0.0", debug=True)
