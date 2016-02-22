import re
import datetime
import sys
import time
from sets import Set

import requests


DEFAULT_REQUEST_HEADERS = {
    'Accept': 'application/json',
    'User-Agent': 'elvis314',
}

def getResults(branch, offset, rsid):
    #https://treeherder.mozilla.org/api/project/try/jobs/?count=2000&exclusion_profile=false&offset=6000&result_set_id=87951&return_type=list
    url = "https://treeherder.mozilla.org/api/project/%s/jobs/?count=2000&exclusion_profile=false&offset=%s&result_set_id=%s&return_type=list" % (branch, offset, rsid)
    try:
        response = requests.get(url, headers={'accept-encoding':'gzip'}, verify=True)
        cdata = response.json()
        return cdata
    except SSLError:
        pass


def analyzeResults(branch, resultSetID):
    offset = 0
    done = False
    exclusions = ['Dbg', '[tc]-Initial-decision-task-for-try', 'build']

    bbjobs = {}
    tcjobs = {}
    while not done:
        data = getResults(branch, offset, resultSetID)
        offset += 2000

        if len(data['results']) < 2000:
            done = True

        #for each job, parse and put into hash
        job_property_names = data["job_property_names"]
        i = lambda x: job_property_names.index(x)
        results = data["results"]
        for r in results:
            _result = r[i("result")]
            if _result == u'unknown':
                continue

            if _result == u'usercancel':
                continue

            #TODO: this is sort of a hack
            if _result == u'retry':
                continue

            duration = (int(r[i("end_timestamp")]) - int(r[i("start_timestamp")]))

            if r[i("build_system_type")] == "taskcluster":
                testtype = r[i("job_type_name")].split("Linux64")[-1]

                # HACK to match up taskcluster names to buildbot names
                testtype = testtype.replace('-plain', '').replace('M(gl', '').replace('M(p', '').strip()
                testtype = testtype.replace(' ', '-').replace('M(dt', '').replace('M(bc', '').replace(')', '')
                testtype = testtype.replace('--', '-').replace('browser-chrome-e10s', 'e10s-browser-chrome')
                testtype = testtype.replace('jittests', 'jittest').strip('-').replace('jsreftest-1', 'jsreftest')

                if testtype in exclusions:
                    continue

                if testtype not in tcjobs:
                    tcjobs[testtype] = {'totaljobs': 0, 'avg_runtime': 0, 'total_runtime': 0,
                                        'testfailed': [], 'success': [], 'retry': [], 'busted': [],
                                        'exception': []}
                tcjobs[testtype]['totaljobs'] += 1
                tcjobs[testtype]['total_runtime'] += duration
                tcjobs[testtype]['avg_runtime'] = tcjobs[testtype]['total_runtime'] / tcjobs[testtype]['totaljobs']
                tcjobs[testtype][_result].append(duration)
            else:
                testtype = r[i("ref_data_name")].split()[-1]

                # bb = mochitest-jetpack
                testtype = testtype.replace('mochitest-jetpack', 'jetpack')

                if testtype in exclusions:
                    continue

                if testtype not in bbjobs:
                    bbjobs[testtype] = {'totaljobs': 0, 'avg_runtime': 0, 'total_runtime': 0,
                                        'testfailed': [], 'success': [], 'retry': [], 'busted': [],
                                        'exception': []}
                bbjobs[testtype]['totaljobs'] += 1
                bbjobs[testtype]['total_runtime'] += duration
                bbjobs[testtype]['avg_runtime'] = bbjobs[testtype]['total_runtime'] / bbjobs[testtype]['totaljobs']
                bbjobs[testtype][_result].append(duration)
    return bbjobs, tcjobs

def getResultSetID(branch, revision):
    url = "https://treeherder.mozilla.org/api/project/%s/resultset/?format=json&full=true&revision=%s" % (branch, revision)
    response = requests.get(url, headers=DEFAULT_REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    rs_data = response.json()
    results_set_id = rs_data['results'][0]['id']
    return results_set_id

def mergeDict(old, new):
    retVal = old.copy()
    for item in new:
        if item in retVal:
            print "ERROR: %s in both dicts" % (item)
            if old[item] != new[item]:
                print "    NOT EQUAL"
    retVal.update(new)
    return retVal


branch = 'try'
#rsid = 87951 # old experiment
revisions = ['2d21b4595e8c', '2625f93db046', '2ee943fae4e0', '285b7ebbd3a5', '5b05313e7af1', '6b6f29b4170b', '96c9eef950b1', '4ef8580c9355', '7e4d00972383', '5a421ae2c2bd']
bbjobs = {}
tcjobs = {}
for rev in revisions:
    bjobs, tjobs = analyzeResults(branch, getResultSetID(branch, rev))
    bbjobs = mergeDict(bbjobs, bjobs)
    tcjobs = mergeDict(tcjobs, tjobs)

keys = set(tcjobs.keys()) & set(bbjobs.keys())
for data in [tcjobs, bbjobs]:
    print "testtype,totaljobs,total_runtime,avg_runtime,avg_greentime,%% green"
    for type in keys:
        root = type.strip().split(' ')[0].split('-')[0]
        if root not in ['mochitest', 'reftest', 'jsreftest', 'crashtest', 'jittest', 'jetpack',
                        'web', 'xpcshell', 'jittest', 'gtest', 'cppunit', 'jittests', 'marionette']:
            print "skipping: %s" % type
            continue

        tt = data[type]
        gtime = sum(tt['success']) / len(tt['success']) if len(tt['success']) > 0 else -1
        pct_green = ((len(tt['success'])*1.0) / tt['totaljobs'])
        print "%s,%s,%s,%s,%s,%s" % (type, tt['totaljobs'], tt['total_runtime'], tt['avg_runtime'], gtime, pct_green)
    print "\n"



#testtype	avg_greentime (TC)	avg_greentime (BB)	TC % slower
keys = set(tcjobs.keys()) & set(bbjobs.keys())
print "testtype,avg_greentime (TC),avg_greentime (BB),TC % slower"
for type in keys:
    root = type.strip().split(' ')[0].split('-')[0]
    if root not in ['mochitest', 'reftest', 'jsreftest', 'crashtest', 'jittest', 'jetpack',
                    'web', 'xpcshell', 'jittest', 'gtest', 'cppunit', 'jittests', 'marionette']:
        print "skipping: %s" % type
        continue

    print "%s,%s,%s,%s" % (type, tcjobs[type]['avg_runtime'], bbjobs[type]['avg_runtime'], ((tcjobs[type]['avg_runtime']*1.0 / bbjobs[type]['avg_runtime']*1.0) - 1.0))
print "\n"


keys = Set(tcjobs.keys())
keys ^= Set(bbjobs.keys())
print "\n"
print "jobtypes we are ignoring:"
for k in keys:
    print k

