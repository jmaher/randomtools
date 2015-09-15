import csv
import time
from talosmaps import TBPL_TESTS, PLATFORMS
import datetime
import requests
import os
import json
import copy

revision_cache = {}
pushlog_cache = {}

def loadRevisionCache():
    global revision_cache
    if os.path.exists('revisions.cache'):
        try:
            with open('revisions.cache', 'rb') as fHandle:
                revision_cache = json.load(fHandle)
        except:
            print "FAILED TO LOAD REVISION CACHE"
            revision_cache = {}

def saveRevisionCache():
    global revision_cache
    with open('revisions.cache', 'wb') as fHandle:
        json.dump(revision_cache, fHandle)


def loadPushLogCache():
    global pushlog_cache
    if os.path.exists('pushlog.cache'):
        try:
            with open('pushlog.cache', 'rb') as fHandle:
                pushlog_cache = json.load(fHandle)
        except:
            pushlog_cache = {}

    if not pushlog_cache:
        for branch in ['integration/mozilla-inbound',
                       'integration/fx-team',
                       'integration/b2g-inbound',
                       'mozilla-central']:
            pushlog_cache[branch] = []

            dateArgs = "startdate=2015-09-01&enddate=2015-09-15"
            url = "https://hg.mozilla.org/%s/json-pushes?version=2&tipsonly=1&%s" % (branch, dateArgs)
            print url
            try:
                response = requests.get(url, headers={'accept-encoding':'json'}, verify=True)
                data = response.json()
            except:
                print "   --------- failure getting json for url: %s" % url
                return

            # oldest to newest - I assume
            pushes = data['pushes'].keys()
            pushes.sort()
            for push in pushes:
                rev = data['pushes'][push]['changesets'][0][:12]
                pushlog_cache[branch].append(rev)
        savePushLogCache()


def savePushLogCache():
    global pushlog_cache
    with open('pushlog.cache', 'wb') as fHandle:
        json.dump(pushlog_cache, fHandle)




# Given a revision get the push date from hg, in PDT+8
def getRevisionDate(branch, rev):
    global revision_cache
    key = "%s-%s" % (branch, rev)
    if key in revision_cache.keys():
        return revision_cache[key]

    if branch.startswith('firefox'):
        branch = branch.replace('firefox', 'mozilla-central')

    if branch.startswith('mozilla-aurora') or branch.startswith('mozilla-beta'):
        br = "releases/%s" % branch.split('-non-pgo')[0]
    elif not branch.startswith('mozilla-central'):
        br = "integration/%s" % branch.split('-non-pgo')[0]
    else:
        br = "%s" % branch.split('-non-pgo')[0]

    # https://hg.mozilla.org/integration/mozilla-inbound/json-pushes?changeset=b9150539d787&version=2&tipsonly=1
    url = "https://hg.mozilla.org/%s/json-pushes?changeset=%s&version=2&tipsonly=1" % (br, rev) 
    try:
        response = requests.get(url, headers={'accept-encoding':'json'}, verify=True)
        data = response.json()
    except:
        print "   --------- failure getting json for url: %s" % url
        return ""

    #TODO: how to deal with the timezones?
    pushes = data['pushes'].keys()
    date = time.strftime("%Y-%m-%d %H-%M-%S", time.localtime(data['pushes'][pushes[0]]['date']))
    revision_cache[key] = date
    return date


def isReverseTest(name):
    try:
        if name.lower().index('canvas') >= 0:
            return True
    except ValueError:
        pass

    try:
        if name.lower().index('dromaeo') >= 0:
            return True
    except ValueError:
        pass

    try:
        if name.lower().index('v8') >= 0:
            return True
    except ValueError:
        pass

    return False


# ensure we have:
#   branch, platform, test, percentage, date, revision

def importPHData(filename):
    phdata = {}
    branch = 0
    plat = 1
    test = 3
    date = 5
    change = 6
    pct = 7
    rev = 9

    with open(filename, 'rb') as fHandle:
        alerts = csv.reader(fHandle)
        firstrow = True
        for row in alerts:
            if firstrow:
                firstrow = False
                continue

            row[pct] = float(row[pct])
            if float(row[change]) < 0.0:
                row[pct] = row[pct] * -1.0

            if isReverseTest(row[test]):
                row[pct] = row[pct] * -1.0

            if float(row[pct]) > -2.0 and float(row[pct]) < 2.0:
#                print "skipping too small: %s (reverse: %s)" % (row[pct], isReverseTest(row[test]))
#                print "  %s" % row
                continue

            if float(row[pct]) > -10.0 and row[test].startswith('dromaeo'):
                print "skipping dromaeo: %s" % row
                continue

            row[pct] = str(row[pct])

            data = []
            for item in [branch, plat, test, pct, date, rev]:
                data.append(row[item].lower())

            for item in [branch, plat, test, pct, date, rev]:
                if item == test:
                    if row[test].endswith('opt'):
                        data[0] = "%s-non-pgo" % row[branch]
                    data[2] = row[test].split('summary')[0].strip()
                    if row[test].split('summary')[1].strip().startswith('e10s'):
                        data[1] = "%s-e10s" % row[plat]

                if item == pct:
                    # make percent x.xx%
                    #TODO: I assume this is regressions only
                    data[3] = float("%.2f" % (abs(float(row[pct]))))

                if item == date:
                    # date to human date
                    data[4] = time.strftime('%Y-%m-%d %H-%M-%S', time.localtime(float(row[date])))

            # TODO: this is hacky and depends on the data we are working with
            if datetime.datetime.strptime(data[4], "%Y-%m-%d %H-%M-%S") < datetime.datetime.strptime('2015-08-30', "%Y-%m-%d"):
                continue

            # TODO: this is hacky and depends on the data we are working with
            if datetime.datetime.strptime(data[4], "%Y-%m-%d %H-%M-%S") > datetime.datetime.strptime('2015-10-02', "%Y-%m-%d"):
                continue

            #TODO: we don't use the v8 formula in perfherder
            if data[2] == 'v8_7':
                continue

            if data[4].split(' ')[0] not in phdata.keys():
                phdata[data[4].split(' ')[0]] = []
            phdata[data[4].split(' ')[0]].append(data)
            sorted(phdata[data[4].split(' ')[0]], key=lambda d: d[4])

    return phdata

def importGSData(filename):
    loadRevisionCache()

    gsdata = {}
    with open(filename, 'rb') as fHandle:
        alerts = csv.reader(fHandle, delimiter=',')
        for row in alerts:
            data = []
            for item in row:
                data.append(item.lower())

            data[2] = TBPL_TESTS[row[2]]['testname']
            data[1] = PLATFORMS[row[1].lower()]

            if data[1] == 'android-4-0-armv7-api11':
                data[0] = "%s-non-pgo" % data[0]

            if data[1] == 'osx-10-10':
                data[0] = "%s-non-pgo" % data[0]

            if data[1] == 'osx-10-10-e10s':
                data[0] = "%s-non-pgo" % data[0]

            # make percent x.xx
            data[4] = "%.2f" % (float(row[4].strip('%')))

            # TODO: this is hacky and depends on the data we are working with
            if datetime.datetime.strptime(data[3], "%Y-%m-%d %H:%M:%S") > datetime.datetime.strptime('2015-10-04', "%Y-%m-%d"):
                continue

            #TODO: we should support this!!!!
            # we don't do anything for tp5n xperf bits
#            if data[2] == 'tp5n' or data[2] == 'xperf':
#                continue

            # flip flop data 4 and 3
            data[3] = abs(float(data[4]))
            # get the actual push date
            data[4] = getRevisionDate(data[0], data[5])

            if data[0] == 'firefox':
                data[0] = 'mozilla-central'
            elif data[0] == 'firefox-non-pgo':
                data[0] = 'mozilla-central-non-pgo'
            elif data[0] not in ['fx-team', 'fx-team-non-pgo',
                               'mozilla-inbound', 'mozilla-inbound-non-pgo',
                               'b2g-inbound', 'b2g-inbound-non-pgo']:
                continue

            data[5] = data[5][:12]

            if data[4].split(' ')[0] not in gsdata.keys():
                gsdata[data[4].split(' ')[0]] = []
            gsdata[data[4].split(' ')[0]].append(data)
            sorted(gsdata[data[4].split(' ')[0]], key=lambda d: d[4])

    saveRevisionCache()
    return gsdata


def compareRevision(revision):
    ph = {}
    gs = {}
    for row in phdata:
        if row[5].strip() == revision:
            if row[0] not in ph:
                ph[row[0]] = []
            ph[row[0]].append([row[1], row[2], row[3], row[4]])

    for row in gsdata:
        if len(row) < 6:
           continue

        if row[5].strip() == revision:
            if row[0] not in gs:
                gs[row[0]] = []
            gs[row[0]].append([row[1], row[2], row[3], row[4]])


    errors = []
    if len(ph) == len(gs) and ph.keys() == gs.keys():
        keys = ph.keys()
        keys.sort()
        for r in keys:
            for phitem in ph[r]:
                found = False
                for gsitem in gs[r]:
                    if phitem[0] == gsitem[0] and \
                       phitem[1] == gsitem[1]:
                       found = True
                       break
                if not found:
                    errors.append(phitem)
    else:
        for r in ph.keys():
            errors.extend(ph[r])

    if not errors:
        pass
#        print "alerts for revision %s is OK" % revision
    else:
        pass
        print "%s : https://groups.google.com/forum/#!searchin/mozilla.dev.tree-alerts/%s" % (revision, revision)
        for e in errors:
            print "  %s" % e


# match branch (0), platform (1), test (2), and fuzzy match revision (5)
def findMatch(target, haystack, rev):
#    print "target: %s" % target
    for item in haystack:
#        print " - item: %s" % item
        if item[0] == target[0] and \
           item[1] == target[1] and \
           fuzzyRevisionMatch(target[0], target[5], item[5]) <= 10 and \
           item[2] == target[2]:
#            print "match!"
            return item
    return None

def fuzzyMatch(val1, val2):
    diff = abs(float(val2) - float(val1))
    # allow for a 10% difference
    if float(val2) - float(val1) >= 0:
        maxval = float(val2)
    else:
        maxval = float(val1)

    if abs(maxval*.20) >= diff:
        return True

    return False

def fuzzyRevisionMatch(branch, rev1, rev2):
    global pushlog_cache

    if rev1 == rev2:
        return 0

    branch = branch.split('-non-pgo')[0]

    if branch != 'mozilla-central':
        branch = 'integration/%s' % branch

    try:
       index1 = pushlog_cache[branch].index(rev1)
       index2 = pushlog_cache[branch].index(rev2)
       # TODO: made this +- 3, the problem is we could coelesce,
       # ideally this would be for revisions with data
       return abs(index1 - index2)
    except ValueError:
       pass
    return 100

loadPushLogCache()
phdata = importPHData('perfalerts.csv')
gsdata = importGSData('alerts.csv')

dates = set(phdata.keys()) | set(gsdata.keys())
dates = sorted(dates)

for date in dates:
    if date < '2015-09-05':
        continue

    print "%s:" % date
    if date in phdata and date in gsdata:
        # minimum match: branch, platform, test, date
        gsdata_extra = copy.deepcopy(gsdata[date])
        for pitem in phdata[date]:
            gitem = findMatch(pitem, gsdata[date], pitem[5])
            if gitem:
                try:
                    gsdata_extra.remove(gitem)
                except:
                    print "failed to remove: %s" % gitem

                # match percent?
                if gitem[3] == pitem[3] or fuzzyMatch(gitem[3], pitem[3]):
                    # match revision?
                    if gitem[5] == pitem[5] or fuzzyRevisionMatch(gitem[0], gitem[5], pitem[5]) <= 10:
                        #perfect match: percent and revision
                        print "!! %s" % gitem
                        pass
                    else:
                        print "## %s. g.%s != p.%s (%s pushes diff)" % (gitem, gitem[5], pitem[5], fuzzyRevisionMatch(gitem[0], gitem[5], pitem[5]))
                        pass
                elif gitem[5] == pitem[5] or fuzzyRevisionMatch(gitem[0], gitem[5], pitem[5]) <= 10:
                    #fuzzy match - percent is off, but all other data is close
                    print "$$ %s. g.%s != p.%s" % (gitem, gitem[3], pitem[3])
                    pass
                else:
                    #minimum match
                    print "@@ %s. g.%s != p.%s / g.%s != p.%s (%s rev diff)" % (gitem, gitem[3], pitem[3], gitem[5], pitem[5], fuzzyRevisionMatch(gitem[0], gitem[5], pitem[5]))
            else:
                #no match
                try:
                    br = pitem[0].split('-non-pgo')[0]
                    if br != 'mozilla-central':
                        br = 'integration/%s' % br
                    rindex = pushlog_cache[br].index(pitem[5])
                except:
                    rindex = -1
                print "p. %s. (index: %s)" % (pitem, rindex)
        for gitem in gsdata_extra:
            try:
                br = gitem[0].split('-non-pgo')[0]
                if br != 'mozilla-central':
                    br = 'integration/%s' % br
                rindex = pushlog_cache[br].index(gitem[5])
            except:
                rindex = -1
            print "g.%s. (index: %s)" % (gitem, rindex)

    #TODO: deal with gdata only alerts

    """
    if date in phdata
        for item in phdata[date]:
            print "-ph- %s" % item
    if date in gsdata:
        for item in gsdata[date]:
            print "-gs- %s" % item
    """

# store in: branch, platform, test, date, percent
#for revision in revisions:
#    compareRevision(revision)

"""
for key in pushlog_cache.keys():
    print "%s: %s" % (key, len(pushlog_cache[key]))
    for r in pushlog_cache[key]:
        if r == "d71995d0ccd2":
            print "key: %s, index: %s" % (key, pushlog_cache[key].index(r))
"""



