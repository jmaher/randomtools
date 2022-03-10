
import json
import os
import requests

import mozinfo
from manifestparser import TestManifest

def getTestManifest(manifest):
    if isinstance(manifest, TestManifest):
        return manifest
    elif manifest is not None:
        manifest = os.path.normpath(os.path.abspath(manifest))
        if os.path.isfile(manifest):
            return TestManifest([manifest], strict=True)
        else:
            return None


def getIntermittentData():
    retVal = {}
    cachename = '_intermittentbugs.json'
    if os.path.exists(cachename):
        with open(cachename, 'r') as f:
            retVal = json.load(f)
    else:
        url = 'https://treeherder.mozilla.org/api/failures/?startday=2022-01-01&endday=2022-03-08&tree=trunk'
        response = requests.get(url, headers={'User-agent': 'Mozilla/90.0'})
        data = response.json()

        for bug in data:
            retVal[bug['bug_id']] = bug['bug_count']

        with open(cachename, 'w') as f:
            json.dump(retVal, f)

    return retVal


def _getBugzilaData():
    cachename = '_simplebug.json'
    if os.path.exists(cachename):
        with open(cachename, 'r') as f:
            retVal = json.load(f)
    else:
        retVal = {'bugs': []}
        done = False
        limit = 10000
        offset = 0
        while (not done):
            # 5 years of history!
            url = "https://bugzilla.mozilla.org/rest/bug?keywords=intermittent-failure&creation_time=2017-03-01&status=---&include_fields=id,summary,status,resolution,product,component&limit=%s&offset=%s" % (limit, offset) 
            response = requests.get(url, headers={'User-agent': 'Mozilla/90.0'})
            data = response.json()
            num_retrieved = len(data['bugs'])
            offset += num_retrieved
            if num_retrieved < limit:
                done = True
            # merge the results
            for item in data['bugs']:
                retVal['bugs'].append(item)

        with open(cachename, 'w') as f:
            json.dump(retVal, f)

    return retVal


def getBugDetails(bugid):
    url = "https://bugzilla.mozilla.org/rest/bug?id=%s&include_fields=id,summary,product,component" % (bugid) 
    response = requests.get(url, headers={'User-agent': 'Mozilla/90.0'})
    data = response.json()
    if 'bugs' in data and bugid == data['bugs'][0]['id']:
        print(data['bugs'][0]['summary'])
        return data['bugs'][0]['product'], data['bugs'][0]['component']
    return "", ""


def createBug(path, buglist, api_key):
    cachename = '_simplebug.json'

    url = "https://bugzilla.mozilla.org/rest/bug"

    # get the product/component for the first bug in the list
    product, component = getBugDetails(buglist[0])

    postdata = {
        "product" : product,
        "component" : component,
        "version" : "Trunk", # would prefer Default, maybe "Other Branch"
        "summary" : "Intermittent %s | single tracking bug" % path,
        "keywords" : ["intermittent-failure, intermittent-testcase"],
        "op_sys" : "All",
        "priority" : "P3",
        "platform" : "All",
        "type" : "defect",
        "dependson": buglist
    }

    response = requests.post(url, postdata, headers={'User-agent': 'Mozilla/90.0', 'X-BUGZILLA-API-KEY': api_key})
    data = response.json()
    print(data)
    id = data['id']

    newBug = {"component": component,
              "product": product,
              "id": id,
              "summary": "Intermittent %s | single tracking bug" % path,
              "status": "NEW",
              "resolution": ""
             }

    with open(cachename, 'r') as f:
        data = json.load(f)

    data['bugs'].append(newBug)

    # update cache with new bug
    with open(cachename, 'w') as f:
        json.dump(data, f)

    return id


def splitNameFromSummary(summary, includes, excludes):
    # find test_*.js pattern in title and collect just the paths
    parts = summary.split(' ')
    names = [x.strip() for x in parts]
    for i in includes:
        names = [x for x in names if len(x.split(i)) > 1]

    for e in excludes:
        names = [x for x in names if len(x.split(e)) == 1]

    if names == []:
        return ''

    # filter out chrome:// urls
    names = [x.split('/content/browser/')[-1] for x in names]
    names = [x.strip('/') for x in names]

    # very few instances have >1 testcase in the summary
    if len(names) > 1:
        if len(set(names)) > 1:
            # find shortest item, if it is part of longer item and has '/', then keep longer
            shortest = [x for x in names if len(x) == min([len(x) for x in names])][0]
            matches = [x for x in names if len(x.split(shortest)) > 1]
            if len(matches) == len(names) - 1:
                names.remove(shortest)
                if len(names) > 1:
                    return ''
    return names[0]


def getRepoPath(path, basedir):
    filename = "%s/%s" % (basedir, path)

    # if windows, fix: paths
    if os.path.sep == '\\':
        filename = filename.replace('/c/', 'c:/')
        filename = filename.replace('/', '\\\\')
    return filename


def checkTestcaseInRepo(path, basedir):
    # test each 'name' with file path relative to m-c
    filename = getRepoPath(path, basedir)

    if not os.path.exists(filename):
        # print("%s :: path doesn't exist: %s" % (bug['id'], name))
        return False
    return True

def timeoutLeakCrash(summary):
    if 'TED-TIMEOUT' in summary or \
        'test_timeout ' in summary:
       return True
    
    if 'leakcheck' in summary or \
       'leaked' in summary:
       return True
    
    if 'MOZ_CRASH' in summary or \
        'PROCESS-CRASH' in summary or \
        'crashed' in summary:
        return True
    return False


def getMozInfo(filename):
    mozInfo = json.load(open(filename))
    fixedInfo = {}
    for k, v in mozInfo.items():
        if isinstance(k, bytes):
            k = k.decode("utf-8")
        fixedInfo[k] = v
    mozInfo = fixedInfo
    mozinfo.update(mozInfo)


def getTestFilesByPath(path, fileroot):
    files = []
    getMozInfo('mozinfo.json')
    mpath = getRepoPath(path, basedir)
    files = os.listdir(mpath)
    manifests = []
    for file in files:
        if file.endswith('.ini') and file.startswith(fileroot):
            manifests.append(file)
        # TODO: serious hack here for _webconsole.ini
        elif fileroot=='browser' and file == '_webconsole.ini':
            manifests.append(file)

    if len(manifests) < 1:
        print("%s :: %s" % (mpath, manifests))
        return []

    for m in manifests:
        filename = os.path.join(mpath, m)
        manifest = getTestManifest(filename)
    #    tests = manifest.active_tests(exists=False,
    #                                  filters=None,
    #                                  noDefaultFilters=True,
    #                                  **mozinfo.info)
        for item in manifest.tests:
            fullname = "%s/%s" % (path, item['name'])
            if fullname not in files:
                files.append(fullname)

    return files


def getHarnessTests(bugzillaData, intermittentData, harness):
    counter = 0
    paths = {}
    intermittent_bugs_to_ignore = []
    for bug in bugzillaData['bugs']:
        if bug['status'] in ['RESOLVED', 'VERIFIED']:
            continue
        try:
            name = splitNameFromSummary(bug['summary'], harness['includes'], harness['excludes'])
        except:
            # TODO: catch exception and handle it, all codec issues
            pass

        # filter out thunderbird
        if name == '' or name.startswith('comm'):
            continue

        for p in harness['pathfilter']:
            name = name.split(p)[-1]

        # intermittent hasn't been seen in 2 months, skip
#        if str(bug['id']) not in intermittentData.keys():
#            print("%s not in %s" % (bug['id'], intermittentData.keys()))
#            continue

        # sometimes we have <name>.js:X (i.e. .js:1) for the summary
        if len(name.split('.js:')) > 1:
            name = "%s.js" % name.split('.js:')[0]

        # test each 'name' with file path relative to m-c
        if checkTestcaseInRepo(name, basedir):
            if timeoutLeakCrash(bug['summary']):
                continue

            if name not in paths.keys():
                paths[name] = {'bugs': [], 'summary': [], 'intermittents': 0}
            paths[name]['bugs'].append(bug['id'])
            paths[name]['summary'].append(bug['summary'])
            # add data from last 2 months
            if str(bug['id']) in intermittentData.keys():
                if intermittentData[str(bug['id'])] >= 100:
                    intermittent_bugs_to_ignore.append(name)
                paths[name]['intermittents'] += intermittentData[str(bug['id'])]

    dirs = {}
    for test in paths.keys():
        path = '/'.join(test.split('/')[:-1])
        if path not in dirs.keys():
            dirs[path] = {'bugs': [], 'tests': [], 'count': 0, 'sametestbugs': 0, 'intermittents': 0, 'disabled': 0}

        dirs[path]['bugs'].extend(paths[test]['bugs'])
        dirs[path]['tests'].append(test)

        # want to know how many bugs will be redundant
        dirs[path]['sametestbugs'] += (len(paths[test]['bugs']) - 1)

        # sum up intermittents for given manifest
        dirs[path]['intermittents'] += paths[test]['intermittents']

        # intermittents >100/month (when combined), increment disabled
        if paths[test]['intermittents'] >= 100 and test not in intermittent_bugs_to_ignore:
            dirs[path]['disabled'] += 1

    toRemove = []
    for path in dirs.keys():
        count = len(getTestFilesByPath(path, harness['name']))
        if count <= 0:
            toRemove.append(path)
        else:
            dirs[path]['count'] = count

    for p in toRemove:
        del dirs[p]

    for path in dirs.keys():
        counter += len(dirs[path]['bugs'])
    
    return paths, dirs, counter


def getConfig(filename='.config'):
    with open(filename, 'r') as f:
        data = json.load(f)
    return data


basedir = '/c/Users/elvis/mozilla-central'
bugzillaData = _getBugzilaData()
intermittentData = getIntermittentData()
config = getConfig()
api_key = config['bzapi_key']


# xpcshell summary rough filter
xpcshell = {'name': 'xpcshell',
            'includes': ['test_', '.js'],
            'excludes': ['browser_', 'helper_', 'packages.json'],
            'pathfilter': ['/build/tests/xpcshell/tests/']
            }

browser = {'name': 'browser',
            'includes': ['browser_', '.js'],
            'excludes': ['test_', 'packages.json'],
            'pathfilter': ['/build/tests/xpcshell/tests/']
            }

a11y = {'name': 'a11y',
            'includes': ['test_', 'html'],
            'excludes': ['browser__', 'packages.json'],
            'pathfilter': ['/build/tests/xpcshell/tests/']
            }

mochitest = {'name': 'mochitest',
            'includes': ['test_', 'html'],
            'excludes': ['browser__', 'packages.json'],
            'pathfilter': ['/build/tests/xpcshell/tests/']
            }

chrome = {'name': 'chrome',
            'includes': ['test_', 'html'],
            'excludes': ['browser__', 'packages.json'],
            'pathfilter': ['/build/tests/xpcshell/tests/']
            }

paths, testdirs, totalbugs = getHarnessTests(bugzillaData, intermittentData, xpcshell )

print("path, # bugs, # tests w/bugs, # test files, # bugs reduced, # intermittents seen, # tests to disable")
total_saved = 0
total_intermittents = 0
total_disabled = 0
for dir in testdirs:
    print("%s, %s, %s, %s, %s, %s, %s" % (dir, 
                                          len(testdirs[dir]['bugs']),
                                          len(testdirs[dir]['tests']),
                                          testdirs[dir]['count'],
                                          testdirs[dir]['sametestbugs'],
                                          testdirs[dir]['intermittents'],
                                          testdirs[dir]['disabled']))
    total_saved += testdirs[dir]['sametestbugs']
    total_intermittents += testdirs[dir]['intermittents']
    total_disabled += testdirs[dir]['disabled']

print("Total bugs: %s" % totalbugs)
print("total saved bugs: % s" % total_saved)
print("total intermittents: %s" % total_intermittents)
print("total testcases to disable: %s" % total_disabled)


for path in paths:
    tracking = [x for x in paths[path]['summary'] if 'single tracking bug' in x]
    if tracking:
        print("tracking bug for: %s" % path)

for path in paths:
    # skip existing tracking bugs, so we can incrementally do this.
    tracking = [x for x in paths[path]['summary'] if 'single tracking bug' in x]
    if not tracking:
#        if api_key:
#        id = createBug(path, paths[path]['bugs'], api_key)
#        print("created bug: %s" % id)
        break
