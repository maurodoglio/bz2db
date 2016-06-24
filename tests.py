# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
from datetime import date, timedelta
from update_bugs import get_release_cycle, get_release_channel, release_trains


def test_get_release_cycle():
    release_48_date = date(2016, 8, 2)
    delta_1d = timedelta(days=1)
    day_before = (release_48_date - delta_1d)
    day_after= (release_48_date + delta_1d)

    assert get_release_cycle(day_before) == (date(2016, 6, 7), 47)

    assert get_release_cycle(release_48_date) == (date(2016, 8, 2), 48)

    assert get_release_cycle(day_after) == (date(2016, 8, 2), 48)


def test_get_release_channel():
    release_48_date = date(2016, 8, 2)

    assert get_release_channel(release_48_date, 47) == 'old release'
    assert get_release_channel(release_48_date, 48) == 'release'
    assert get_release_channel(release_48_date, 49) == 'beta'
    assert get_release_channel(release_48_date, 50) == 'aurora'
    assert get_release_channel(release_48_date, 51) == 'nightly'

    release_47_date = date(2016, 6, 7)

    assert get_release_channel(release_47_date, 47) == 'release'
    assert get_release_channel(release_47_date, 48) == 'beta'
    assert get_release_channel(release_47_date, 49) == 'aurora'
    assert get_release_channel(release_47_date, 50) == 'nightly'
    assert get_release_channel(release_47_date, 51) == 'nightly'

