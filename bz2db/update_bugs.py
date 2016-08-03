import re
import time
from datetime import date, datetime

import requests
from decouple import config
from sqlalchemy import (
    create_engine,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table
)


branch_re = re.compile('(\d{2}) branch')

release_dates = {
    date(2015, 3, 31): 37,
    date(2015, 5, 12): 38,
    date(2015, 6, 30): 39,
    date(2015, 8, 11): 40,
    date(2015, 9, 22): 41,
    date(2015, 11, 3): 42,
    date(2015, 12, 15): 43,
    date(2016, 1, 26): 44,
    date(2016, 3, 8): 45,
    date(2016, 4, 26): 46,
    date(2016, 6, 7): 47,
    date(2016, 8, 2): 48,
    date(2016, 9, 13): 49,
    date(2016, 11, 8): 50,
    date(2017, 1, 24): 51
}

release_trains = {}
for r_date, r_version in release_dates.items():
    release_trains[r_date] = {
        'release': r_version,
        'beta': r_version + 1,
        'aurora': r_version + 2,
        'nightly': r_version + 3
    }


def fetch_bug_fields():
    fields_endpoint = 'https://bugzilla.mozilla.org/rest/field/bug'
    response = requests.get(fields_endpoint)
    fields = response.json()['fields']

    status_fields = filter(lambda x: 'cf_status_firefox' in x['name'], fields)
    tracking_fields = filter(lambda x: 'cf_tracking_firefox' in x['name'],
                             fields)
    return (map(lambda x: x['name'], status_fields) +
            map(lambda x: x['name'], tracking_fields))


def fetch_bugs(**kwargs):
    endpoint = 'https://bugzilla.mozilla.org/rest/bug'
    response = requests.get(endpoint, params=kwargs)
    return response.json()['bugs']


def fetch_paginated_endpoint(fetch_func, page_size=2000,
                             max_pages=50, **kwargs):
    offset = 0
    data = []

    while offset < (max_pages * page_size):
        print "fetching page %s" % (offset / page_size)
        page = fetch_func(limit=page_size, offset=offset, **kwargs)

        if page:
            data += page
            offset += page_size
            # Let's be gentle with the api service
            time.sleep(1)
        else:
            break

    return data


def get_discovery_release_cycle(release_date):

    assert isinstance(release_date, date)

    for d in sorted(release_trains.keys(), reverse=True):
        if d <= release_date:
            return d, release_dates[d]

    return None


def get_release_channel(release_date, release_cycle):
    if release_cycle < min(release_trains[release_date].values()):
        return 'old release'
    elif release_cycle > max(release_trains[release_date].values()):
        return 'nightly'
    for channel, cycle in release_trains[release_date].items():
        if release_cycle == cycle:
            return channel
    print 'error retrieving channel for %s in %s' % (
        release_cycle, release_trains[release_date])
    return 'error'


def join_keywords(bug):
    bug['keywords'] = ",".join(bug['keywords'])


def add_release_cycle_and_channel(bug):
    creation_time = datetime.strptime(bug['creation_time'][0:10],
                                      '%Y-%m-%d').date()
    release_date, release_cycle = get_discovery_release_cycle(
        creation_time
    )

    branch = bug['version'].lower()
    release_channel = 'unknown'

    if branch == 'trunk':
        release_channel = 'nightly'
    elif branch == 'unspecified':
        release_channel = branch
    else:
        match = branch_re.match(branch)
        if match:
            release_channel = get_release_channel(release_date,
                                                  int(match.group(1)))
    try:
        bug['release_cycle'] = release_trains[release_date][release_channel]
    except KeyError:
        # If we don't know which version it refers to assign it to the
        # current release
        bug['release_cycle'] = release_cycle

    bug['release_channel'] = release_channel


def update_bug_db(bugs, cf_fields):
    metadata = MetaData()
    db = {
        'USER': config('DATABASE_USER'),
        'PASSWORD': config('DATABASE_PASSWORD', default=''),
        'HOST': config('DATABASE_HOST'),
        'PORT': config('DATABASE_PORT', default='5432'),
        'NAME': config('DATABASE_NAME', default='bugzilla')
    }

    bug_table = Table('bug', metadata,
                      Column('id', Integer, primary_key=True),
                      Column('version', String),
                      Column('target_milestone', String),
                      Column('status', String),
                      Column('severity', String),
                      Column('resolution', String),
                      Column('dupe_of', Integer, nullable=True),
                      Column('product', String),
                      Column('platform', String),
                      Column('op_sys', String),
                      Column('keywords', String),
                      Column('is_confirmed', Boolean),
                      Column('creator', String),
                      Column('creation_time', DateTime),
                      Column('whiteboard', String),
                      Column('release_channel', String),
                      Column('release_cycle', String)
                      )

    for f in cf_fields:
        bug_table.append_column(Column(f, String))

    engine = create_engine(
        'postgresql://%(USER)s:%(PASSWORD)s@%(HOST)s:%(PORT)s/%(NAME)s' % db)

    if bug_table.exists(engine):
        bug_table.drop(engine)
    bug_table.create(engine)

    conn = engine.connect()
    conn.execute(bug_table.insert(), bugs)


def main():
    cf_fields = fetch_bug_fields()
    include_fields = [
         'id',
         'version',
         'target_milestone',
         'status',
         'severity',
         'resolution',
         'product',
         'platform',
         'op_sys',
         'keywords',
         'is_confirmed',
         'creator',
         'creation_time',
         'whiteboard',
         'dupe_of',
     ] + cf_fields

    bug_params = {
        'product': [
            "Core",
            "Firefox",
            "Firefox%20for%20Android",
            "Firefox%20for%20iOS",
            "Toolkit"
        ],
        'creation_time': '2015-06-01',
        'exclude_fields': ['cc', 'cc_detail', 'creator_detail'],
        'include_fields': include_fields,
        'bug_severity': [
            "blocker",
            "critical",
            "major",
            "normal",
            "minor",
            "trivial"
        ],
        'resolution': [
            "---",
            "FIXED",
            "WONTFIX",
            "DUPLICATE",
            "WORKSFORME",
            "SUPPORT",
            "EXPIRED",
            "MOVED"
        ]
    }

    data = fetch_paginated_endpoint(fetch_bugs, **bug_params)

    # clear unwanted fields
    for bug in data:
        for key in bug.keys():
            if key not in include_fields:
                del bug[key]
        join_keywords(bug)
        add_release_cycle_and_channel(bug)

    update_bug_db(data, cf_fields)


if __name__ == '__main__':
    main()
