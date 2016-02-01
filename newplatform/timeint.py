import re
import datetime
import sys
import time
from sets import Set

import requests


def getResults(branch, offset, rsid):
    #https://treeherder.mozilla.org/api/project/try/jobs/?count=2000&exclusion_profile=false&offset=6000&result_set_id=87951&return_type=list
    url = "https://treeherder.mozilla.org/api/project/%s/jobs/?count=2000&exclusion_profile=false&offset=%s&result_set_id=%s&return_type=list" % (branch, offset, rsid)
    try:
        response = requests.get(url, headers={'accept-encoding':'gzip'}, verify=True)
        cdata = response.json()
        return cdata
    except SSLError:
        pass


branch = 'try'
offset = 0
rsid = 87951
done = False
bbjobs = {}
tcjobs = {}

while not done:
    data = getResults(branch, offset, rsid)
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

        duration = (int(r[i("end_timestamp")]) - int(r[i("start_timestamp")]))

        if r[i("build_system_type")] == "taskcluster":
            testtype = r[i("job_type_name")].split("Linux64")[-1]

            # HACK to match up taskcluster names to buildbot names
            testtype = testtype.replace('-plain', '').replace('M(gl', '').replace('M(p', '').strip()
            testtype = testtype.replace(' ', '-').replace('M(dt', '').replace('M(bc', '').replace(')', '')
            testtype = testtype.replace('--', '-').replace('browser-chrome-e10s', 'e10s-browser-chrome')
            testtype = testtype.replace('jittests', 'jittest').strip('-').replace('jsreftest-1', 'jsreftest')

            if testtype not in tcjobs:
                tcjobs[testtype] = {'totaljobs': 0, 'avg_runtime': 0, 'total_runtime': 0, 
                                    'testfailed': [], 'success': [], 'retry': [], 'busted': [], 'exception': []}
            tcjobs[testtype]['totaljobs'] += 1
            tcjobs[testtype]['total_runtime'] += duration
            tcjobs[testtype]['avg_runtime'] = tcjobs[testtype]['total_runtime'] / tcjobs[testtype]['totaljobs']
            tcjobs[testtype][_result].append(duration)
        else:
            testtype = r[i("ref_data_name")].split()[-1]
            if testtype not in bbjobs:
                bbjobs[testtype] = {'totaljobs': 0, 'avg_runtime': 0, 'total_runtime': 0, 
                                    'testfailed': [], 'success': [], 'retry': [], 'busted': [], 'exception': []}
            bbjobs[testtype]['totaljobs'] += 1
            bbjobs[testtype]['total_runtime'] += duration
            bbjobs[testtype]['avg_runtime'] = bbjobs[testtype]['total_runtime'] / bbjobs[testtype]['totaljobs']
            bbjobs[testtype][_result].append(duration)


keys = set(tcjobs.keys()) & set(bbjobs.keys())
for data in [tcjobs, bbjobs]:
    print "testtype,totaljobs,total_runtime,avg_runtime,avg_greentime,%% green"
    for type in keys:
        root = type.strip().split(' ')[0].split('-')[0]
        if root not in ['mochitest', 'reftest', 'jsreftest', 'crashtest', 'jittest',
                        'web', 'xpcshell', 'jittest', 'gtest', 'cppunit', 'jittests', 'marionette']:
            continue

        tt = data[type]
        gtime = sum(tt['success']) / len(tt['success']) if len(tt['success']) > 0 else -1
        pct_green = ((len(tt['success'])*1.0) / tt['totaljobs'])
        print "%s,%s,%s,%s,%s,%s" % (type, tt['totaljobs'], tt['total_runtime'], tt['avg_runtime'], gtime, pct_green)
    print "\n"


keys = Set(tcjobs.keys())
keys ^= Set(bbjobs.keys())
print "\n"
print "jobtypes we are ignoring:"
for k in keys:
    print k

