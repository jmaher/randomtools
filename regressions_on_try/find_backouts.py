import datetime
import json
import os
import requests
import sys
import time

from collections import defaultdict


# copied from: https://github.com/getredash/redash-toolbelt/blob/master/redash_toolbelt/examples/refresh_query.py
def poll_job(s, redash_url, job):
    # TODO: add timeout
    while job['status'] not in (3,4):
        response = s.get('{}/api/jobs/{}'.format(redash_url, job['id']))
        job = response.json()['job']
        time.sleep(1)

    if job['status'] == 3:
        return job['query_result_id']
    
    return None


# copied from: https://github.com/getredash/redash-toolbelt/blob/master/redash_toolbelt/examples/refresh_query.py
def get_fresh_query_result(redash_url, query_id, api_key, params):
    s = requests.Session()
    s.headers.update({'Authorization': 'Key {}'.format(api_key)})

    payload = dict(max_age=0, parameters=params)

    response = s.post('{}/api/queries/{}/results'.format(redash_url, query_id), data=json.dumps(payload))

    if response.status_code != 200:
        raise Exception('Refresh failed.')

    result_id = poll_job(s, redash_url, response.json()['job'])

    if result_id:
        response = s.get('{}/api/queries/{}/results/{}.json'.format(redash_url, query_id, result_id))
        if response.status_code != 200:
            raise Exception('Failed getting results.')
    else:
        raise Exception('Query execution failed.')

    return response.json()['query_result']['data']['rows']


def getHGData():
    url = 'https://hg.mozilla.org/integration/autoland/json-pushes?startdate=2+week+ago&enddate=now&full=true'
    response = requests.get(url, headers={'User-agent': 'Mozilla/5.0'})
    data = response.json()

    revs = defaultdict()
    for push in data:
        cset = data[push]['changesets'][-1]
        revs[cset['node'][:12]] = {'user': data[push]['user'], 'date': datetime.datetime.fromtimestamp(int(data[push]['date'])), 'summary': cset['desc']}
    return revs    

def getTryPushes(user):
    # get_try_pushes
    # 
    url = 'https://treeherder.mozilla.org/api/project/try/push/?full=true&count=100&author=%s' % user
    response = requests.get(url, headers={'User-agent': 'Mozilla/5.0'})
    data = response.json()
    return data

def getUser(user):
    map = {'edgul@mozilla.com': 'eguloien@mozilla.com',
           'dholbert@cs.stanford.edu': 'dholbert@mozilla.com',
           'dao@mozilla.com': 'dgottwald@mozilla.com',
           'eitan@monotonous.org': 'eisaacson@mozilla.com',
           'hsivonen@hsivonen.fi': 'hsivonen@mozilla.com',
           'kelsey.gilbert@mozilla.com': 'jgilbert@mozilla.com',
           'botond@mozilla.com': 'bballo@mozilla.com',
           'pbz@mozilla.com': 'pzuhlcke@mozilla.com',
           'sguelton@mozilla.com': 'serge.guelton@telecom-bretagne.eu',
           'mh+mozilla@glandium.org': 'mh@glandium.org',
           'will+git@drnd.me': 'wdurand@mozilla.com',
           'git@intuitionlibrary.com:': 'gwatson@mozilla.com',
           'ealvarez@mozilla.com': 'emilio@crisal.io',
           'rvandermeulen@mozilla.com': 'ryanvm@gmail.com',
           'tnikkel@mozilla.com': 'tnikkel@gmail.com',
           'tjovanovic@mozilla.com': 'tomica@gmail.com'
          }
    
    if user in map.keys():
        return map[user]
    return user


def hasGroupSummary(jtname):
    parts = jtname.split('/')
    if len(parts) != 2:
        return False
    
    if 'mochitest' in parts[1]:
        return True
    if 'web-platform' in parts[1]:
        return True
    if 'xpcshell' in parts[1]:
        return True
    if 'verify' in parts[1]:
        return True
    return False


def getVariants():
    url = 'https://hg.mozilla.org/mozilla-central/raw-file/tip/taskcluster/ci/test/variants.yml'
    response = requests.get(url, headers={'User-agent': 'Mozilla/5.0'})
    data = response.text
    variants = []
    for line in data.split('\n'):
        if 'suffix' in line:
            variants.append(line.split(':')[-1].strip())
    return variants


def removeVariant(jtname, variants):
    retVal = jtname

    for v in variants:
        if v in retVal:
            retVal = retVal.split(v)[1]

    return retVal


def strip_chunk(jobname):
    try:
        parts = jobname.split('-')
        if int(parts[-1]):
            return '-'.join(parts[:-1])
    except:
        pass
    return jobname


def getFBCData(brev):
    # assume all failures and fbc, just need list of tasks and then add groups in
    fbc_tasks = get_fresh_query_result(url, fbc_id, api_key, {'revision': brev})
    fbc = defaultdict()
    for x in fbc_tasks:
        fbc[strip_chunk(x['name'])] = []

    fbc_group_tasks = get_fresh_query_result(url, fbc_groups_id, api_key, {'revision': brev})
    for x in fbc_group_tasks:
        # list of task -> [group1, group2, ...]
        fbc[strip_chunk(x['name'])].append(x['name1'])
    return fbc

def getTryData(found):
    # {'taskname': {'group1': results, 'group2': results}, 'task2': {'groupx': reuslts,...}}
    try_tasks = get_fresh_query_result(url, try_id, api_key, {'revision': found})
    trydata = defaultdict(dict)
    for tj in try_tasks:
        trydata[strip_chunk(tj['name'])]['task'] = tj['result']

    try_task_groups = get_fresh_query_result(url, try_groups_id, api_key, {'revision': found, 'job_type_name': 'test-'})
    try_groups = {}
    for x in try_task_groups:
        trydata[strip_chunk(x['name'])][x['name1']] = int(x['status'])
    return trydata


# for query
api_key = os.environ.get("REDASH_API_KEY", "")
if not api_key:
    print("please set environment variable REDASH_API_KEY.  This can be found at: https://sql.telemetry.mozilla.org/users/me")
    sys.exit(1)
url = "https://sql.telemetry.mozilla.org"
fbc_id = 91058
try_id = 91059

# NOTE: when getting groups, it only works for certain harnesses, i.e. build, gtest, etc. returns nothing.
try_groups_id = 91068
fbc_groups_id = 91072


variants = getVariants()
revs = getHGData()
# iterate through the summaries, here we look for "Backed out changeset <hgrev> (Bug XYZ)"
# we will miss many "Backed out X changesets (Bug ABC, Bug XYZ, ...)"
for rev in revs:
    if 'Backed out changeset' in revs[rev]['summary']:
        parts = revs[rev]['summary'].split('Backed out changeset')

        # if there are >1 cases of this, we need to find the first in the list, also assure same bug or ignore
        if len(parts) > 2:
            bugs = []
            for part in parts[1:]:
                bugs.append(part.split('bug ')[1].split(')')[0])
            # TODO: figure out solution for this
            # skipping for multiple bugs
            if len(list(set(bugs))) < len(bugs):
                continue
        # use #0 as it will be the push rev
        brev = parts[1].strip()
        brev = brev.split(' ')[0]
        if brev not in revs.keys():
            print("%s (%s) :: didn't find backout rev %s in hglog" % (rev, revs[rev]['date'], brev))
            continue
        user = revs[brev]['user'].split('<')[-1]
        user = user.split('>')[0]
        user = getUser(user)

        bug = revs[brev]['summary'].strip()
        if bug.startswith('Bug '):
            bug = bug.split(' ')[1]
            bug = bug.strip('.')
            bug = bug.strip(',')
            bug = bug.strip(':')
        else:
            continue

        trypushes = getTryPushes(user)

        # results['push_timestamp'] < revs[brev]['date']
        # look for bug in revisions comment
        found = False
        for results in trypushes['results']:
            # TODO: push_timestamp is in local tz- not accurate (I hacked to add 7 hours)
            pt = datetime.datetime.fromtimestamp(int(results['push_timestamp']) + 25200)
            if pt >= revs[brev]['date']:
                continue
            for revision in results['revisions']:
                if bug in revision['comments']:
                    found = True
                    break
            if found:
                found = results['revision']
                break
        
        if not found:
            pushes_last_month = 0
            for results in trypushes['results']:
                pt = datetime.datetime.fromtimestamp(int(results['push_timestamp']))
                now = datetime.datetime.now()
                if (now-pt).days > 30:
                    continue
                pushes_last_month += 1
            
            print("%s, %s, %s, %s try pushes last month" % (brev, user, bug, pushes_last_month))
            found = len(trypushes['results'])
        else:
            # {'taskname': [groups], 'taskname': [groups]}
            fbc = getFBCData(brev)

            # {'taskname': {'group1': results, 'group2': results}, 'task2': {'groupx': reuslts,...}}
            trydata = getTryData(found)

            # only keep try jobs that match the FBC jobs
            # if there are groups, then groups need to match and only keep matching groups
            try_matches = defaultdict(dict)
            for td in trydata:
                if td in fbc:
                    # get the 'task' results
                    try_matches[td]['task'] = trydata[td]['task']

                    # no groups
                    if list(fbc[td]) == ['task']:
                        continue

                    try_matches[td]['has_groups'] = True
                    # only copy over matching groups
                    for g in trydata[td]:
                        if g in fbc[td]:
                            try_matches[td][g] = trydata[td][g]

            # get flattened/summarized views
            matching_tasks = len(list(try_matches))
            failing_tasks = len([x for x in try_matches if try_matches[x]['task'] in ('busted', 'testfailed')])

            # flatten matching groups - if 1 group is failed, then we would have caught the regression
            matching_tasks_groups = [x for x in try_matches if try_matches[x]['has_groups']]
            failing_groups = 0
            for t in matching_tasks_groups:
                for g in try_matches[t]:
                    if g == 'task':
                        continue
                    if try_matches[t][g] > 1:
                        failing_groups += 1

            print("%s, %s, %s, %s, %s, %s, %s, %s" % (brev, user, bug, found, matching_tasks, failing_tasks, len(matching_tasks_groups), failing_groups))
