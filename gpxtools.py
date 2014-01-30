#   Copyright 2014 Martijn Grendelman <m@rtijn.net>
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import os
import copy
from iso8601 import parse_date
from pprint import pprint,pformat
from lxml import etree
from math import radians, sin, cos, atan2, sqrt

ns = '{http://www.topografix.com/GPX/1/1}'

do_merge = False
base_file = ''

# Get unique dates from all tracks
def get_dates(tree):
    dates = set()
    for trk in tree.iterchildren(ns + 'trk'):
        dates.add(get_date(trk))
    return dates

def get_name(trk):
    return trk.findtext(ns + 'name')

def get_date(trk):
    gpxtime = trk.findtext(ns + 'trkseg/' + ns + 'trkpt/' + ns + 'time')
    return parse_date(gpxtime).date()

def get_numpts(trk):
    return len(trk.findall(ns + 'trkseg/' + ns + 'trkpt'))

def get_numtrk(root):
    return len(root.findall(ns + 'trk'))

def get_numwpt(root):
    return len(root.findall(ns + 'wpt'))

def get_numrte(root):
    return len(root.findall(ns + 'rte'))

def get_numrtept(rte):
    return len(rte.findall(ns + 'rtept'))

def distance(lat1, lon1, lat2, lon2):
    radius = 6371000 # meter
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2) * sin(dlat/2) + cos(lat1) \
        * cos(lat2) * sin(dlon/2) * sin(dlon/2)
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    d = radius * c
    return d

def make_filename(d, dir='.'):
    global do_merge, base_file
    do_merge = False
    n = 0
    fn = "%s-%03d.gpx" % (d.isoformat(), n)
    fname =  os.path.join (dir, fn)
    base_file = fname
    while os.path.exists(fname):
        n += 1
        fn = "%s-%03d.gpx" % (d.isoformat(), n)
        fname =  os.path.join (dir, fn)
        do_merge = True
    return fname

def split(filename):
    try:
        tree0 = etree.parse(filename)
    except Exception as e:
        print "Could not parse GPX: %s" % e
        return False

    root = tree0.getroot()
    dates = get_dates(root)

    # Iterate over the dates and remove non-matching tracks
    for d in dates:
        fname = make_filename(d)
        tree = copy.deepcopy(tree0)
        root = tree.getroot()
        tracks = {}
        for trk in root.iterchildren():

            # Remove all non-track elements
            if trk.tag != ns + 'trk':
                root.remove(trk)
                continue

            name      = get_name(trk)
            trackdate = get_date(trk)

            if trackdate != d:
                print "%-25s: date mismatch, removing %s" % (fname, name)
                root.remove(trk)
            elif name in tracks:
                oldnum = tracks[name]['numpts']
                newnum = get_numpts(trk)
                if oldnum >= newnum:
                    print "%-25s: DUPLICATE %s (track points: old=%d, new=%d) -> removing" % (fname, name, oldnum, newnum)
                    root.remove(trk)
                else:
                    # newnum > oldnum. Old track should be removed and this one kept.
                    print "%-25s: duplicate %s (track points differ, old=%d new=%d) -> keeping and removing the old one" % \
                        (fname, name, oldnum, newnum)
                    root.remove(tracks[name]['track'])
                    tracks[name] = { 'numpts': newnum, 'track': trk }
            else:
                numpts = get_numpts(trk)
                tracks[name] = { 'numpts': numpts, 'track': trk }
                print "%-25s: keeping %s" % (fname, name)

        tree.write(fname, xml_declaration = True, encoding='utf-8')

        # Merge if necessary
        if do_merge:
            print "%-25s: starting merge into %s" % (fname, base_file)
            merge(base_file, fname, False)

# Merge tracks from file2 into file1.
# On duplicate names, keep the track with the most track points.

def merge(file1, file2, interactive=True):
    try:
        tree1 = etree.parse(file1)
        tree2 = etree.parse(file2)
    except Exception as e:
        print "Could not parse GPX: %s" % e
        return False
    root1 = tree1.getroot()
    root2 = tree2.getroot()

    modified = False

    # Analyze the first file
    tracks1 = {}
    for trk in root1.iterchildren(ns + 'trk'):
        name   = get_name(trk)
        numpts = get_numpts(trk)
        if not name in tracks1:
            tracks1[name] = { 'numpts': numpts, 'track': trk }
        else:
            print "Track '%s' already seen in '%s'. File contains dupes?" % (name, file1)
            oldnum = tracks[name]['numpts']
            if numpts > oldnum:
                print "Duplicate '%s' replacing old track (old=%d, new=%d points)" % (name, oldnum, numpts)
                tracks1[name] = { 'numpts': numpts, 'track': trk }
     
    for trk in root2.iterchildren(ns + 'trk'):
        name   = get_name(trk)
        numpts = get_numpts(trk)
        if not name in tracks1:
            print "%-25s: appending track '%s'" % (file1, name)
            root1.append(copy.deepcopy(trk))
            tracks1[name] = { 'numpts': numpts, 'track': trk }
            modified = True
        else:
            oldpts = tracks1[name]['numpts']
            if numpts > oldpts:
                print "%-25s: replacing track '%s'. oldpts=%d. newpts=%d" % (file2, name, oldpts, numpts)
                root1.remove(tracks1[name]['track'])
                root1.append(copy.deepcopy(trk))
                tracks1[name] = { 'numpts': numpts, 'track': trk }
                modified = True
            else:
                print "%-25s: skipping track '%s'. oldpts=%d. newpts=%d" % (file2, name, oldpts, numpts)

    if modified:
        yn=False
        if interactive:
            while yn not in ['y','n']:
                yn = raw_input("Overwrite '%s' and remove '%s' ? (y/n)" % (file1, file2))

        if not interactive or yn == 'y':
            print "%-25s: Overwriting file" % file1
            tree1.write(file1, xml_declaration = True, encoding='utf-8')
            print "%-25s: Removing file" % file2
            os.remove(file2)

    else:
        print "%-25s: No changes to write to file" % file1
        yn=False
        if interactive:
            while yn not in ['y','n']:
                yn = raw_input("Remove '%s' ? (y/n)" % file2)
        if not interactive or yn == 'y':
            print "%-25s: Removing file" % file2
            os.remove(file2)

def info(filename):
    try:
        tree0 = etree.parse(filename)
    except Exception as e:
        print "Could not parse GPX: %s" % e
        return False

    root = tree0.getroot()

    print "Number of tracks   : %d" % get_numtrk(root)
    print "Number of routes   : %d" % get_numrte(root)
    print "Number of waypoints: %d" % get_numwpt(root)
    print ''

    for trk in root.iterchildren(ns + 'trk'):
        name = get_name(trk)
        print "Track name  : %s " % name
        n = 0
        trkd = 0
        for trkseg in trk.iterchildren(ns + 'trkseg'):
            numpts = len(list(trkseg))
            oldlat = None
            d = 0
            for trkpt in trkseg.iterchildren(ns + 'trkpt'):
                lat = float(trkpt.get('lat'))
                lon = float(trkpt.get('lon'))
                if oldlat != None:
                    d += distance(oldlat, oldlon, lat, lon)
                oldlat = lat
                oldlon = lon
            print "Segment %3d : %4d track points, distance: %d meter" % (n, numpts, d)
            n += 1
            trkd += d

        pts = get_numpts(trk)
        print "Total points  : %4d" % pts
        print "Total distance: %d meter" % trkd
        print ''

    for rte in root.iterchildren(ns + 'rte'):
        print "Route name  : %s " % get_name(rte).encode('utf-8')
        print "Numer of route points: %d" % get_numrtept(rte)

    print ''

    for wpt in root.iterchildren(ns + 'wpt'):
        name = get_name(wpt)
        if name:
            print "Waypoint name  : %s " % get_name(wpt).encode('utf-8')
        #print "Waypoint name  : %s " % get_name(wpt)

# vim: ts=4 sw=4 et :
