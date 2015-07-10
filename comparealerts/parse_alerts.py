import csv
import time
from talosmaps import TBPL_TESTS, PLATFORMS
import datetime

# ensure we have:
#   branch, platform, test, percentage, date, revision

def importPHData(filename):
    phdata = []
    branch = 0
    plat = 1
    test = 3
    date = 5
    pct = 7
    rev = 9

    with open(filename, 'rb') as fHandle:
        alerts = csv.reader(fHandle)
        firstrow = True
        for row in alerts:
            if firstrow:
                firstrow = False
                continue

            if float(row[pct]) < 2.0:
                continue

            if float(row[pct]) < 10.0 and row[test].startswith('dromaeo'):
                continue

            data = []
            for item in [branch, plat, test, pct, date, rev]:
                data.append(row[item].lower())

            for item in [branch, plat, test, pct, date, rev]:
                if item == test:
                    if row[test].endswith('opt'):
                        data[0] = "%s-non-pgo" % row[branch]
                    data[2] = row[test].split('summary')[0].strip()
                    if row[test].split('summary')[0].strip().startswith('e10s'):
                        data[1] = "%s-e10s" % row[plat]

                if item == branch:
                    if data[0].startswith('mozilla-central'):
                        data[0] = data[0].replace('mozilla-central', 'firefox')

                if item == pct:
                    # make percent x.xx%
                    #TODO: I assume this is regressions only
                    data[3] = "-%.2f" % (float(row[pct]))

                if item == date:
                    # date to human date
                    data[4] = time.strftime('%Y-%m-%d %H-%M-%S', time.localtime(float(row[date])))


            # TODO: this is hacky and depends on the data we are working with
            if datetime.datetime.strptime(data[4], "%Y-%m-%d %H-%M-%S") < datetime.datetime.strptime('2015-03-30', "%Y-%m-%d"):
                continue

            #TODO: platform to e10s
            phdata.append(data)
    return phdata


def importGSData(filename):
    gsdata = []
    with open(filename, 'rb') as fHandle:
        alerts = csv.reader(fHandle, delimiter='\t')
        for row in alerts:
            data = []
            for item in row:
                data.append(item.lower())

            data[2] = TBPL_TESTS[row[2]]['testname']
            data[1] = PLATFORMS[row[1].lower()]

            # make percent x.xx
            data[4] = "%.2f" % (float(row[4].strip('%')))

            # TODO: this is hacky and depends on the data we are working with
            if datetime.datetime.strptime(data[3], "%Y-%m-%d %H:%M:%S") > datetime.datetime.strptime('2015-07-02', "%Y-%m-%d"):
                continue

            gsdata.append(data)
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



phdata = importPHData('perfalerts.csv')
gsdata = importGSData('alerts.csv')


phrevisions = []
for row in phdata:
    if row[5] not in phrevisions:
        phrevisions.append(row[5])

gsrevisions = []
for row in gsdata:
    if row[5] not in gsrevisions:
        gsrevisions.append(row[5])

#TODO: derive revisions from phdata
print "number of ph revisions: %s" % len(phrevisions)
print "number of gs revisions: %s" % len(gsrevisions)

revisions = list(set(phrevisions) & set(gsrevisions))
print "number of common revisions: %s" % len(revisions)
extraph = list(set(gsrevisions) - set(revisions))
print "number of unique ph revisions: %s" % len(extraph)

revisions = []
for r in extraph:
    date = ''
    for row in gsdata:
        if row[5] == r:
            date = row[3]
            break
    if not date:
        print row
    revisions.append(r)
#    print "%s : %s" % (r, date)

    print "select branch, platform, test, percent, bug, status from alerts where keyrevision='%s';" % r
#print revisions

#revisions = ['b6623a27fa64']


# store in: branch, platform, test, date, percent
#for revision in revisions:
#    compareRevision(revision)


