from __future__ import division
import json

# from the treeherder SETA implementation
def is_matched(failure, removals):
    found = False
    if failure in removals:
        found = True

    return found

# from the treeherder SETA implementation
def check_removal(failures, removals):
    results = {}
    for failure in failures:
        results[failure] = []
        for failure_job in failures[failure]:
            found = is_matched(failure_job, removals)

            # we will add the test to the resulting structure unless we find a match
            # in the jobtype we are trying to ignore.
            if not found:
                results[failure].append(failure_job)

        if not results[failure]:
            del results[failure]

    return results

# from the treeherder SETA implementation
def build_removals(active_jobs, failures, target):
    """
    active_jobs - all possible desktop & android jobs on Treeherder (no PGO)
    failures - list of all failures
    target - percentage of failures we're going to process

    Return list of jobs to remove and list of revisions that are regressed
    """
    # Determine the number of failures we're going to process
    # A failure is a revision + all of the jobs that were fixed by it
    number_of_failures = int((target / 100) * len(failures))
    low_value_jobs = []

    for jobtype in active_jobs:
        # Determine if removing an active job will reduce the number of failures we would catch
        # or stay the same
        remaining_failures = check_removal(failures, [jobtype])

        if len(remaining_failures) >= number_of_failures:
            low_value_jobs.append(jobtype)
            failures = remaining_failures
        else:
            failed_revisions = []
            for revision in failures:
                if revision not in remaining_failures:
                    failed_revisions.append(revision)

    return low_value_jobs

# this replaces the proper SETA version where we query all possible jobs to run
# here we query all possible tests to run based on what we identified as problematic
def get_all_tests(fixed_by_commit_jobs):
    retVal = []
    tests = []
    for rev in fixed_by_commit_jobs:
        for item in fixed_by_commit_jobs[rev]:
            if item not in retVal:
                retVal.append(item)
            if item[0] not in tests:
                tests.append(item[0])
    return retVal

# from the treeherder SETA implementation, with small mods
def get_high_value_jobs(fixed_by_commit_jobs, target=100):
    """
    fixed_by_commit_jobs:
        Revisions and jobs that have been starred that are fixed with a push or a bug
    target:
        Percentage of failures to analyze
    """
    total = len(fixed_by_commit_jobs)
    active_jobs = get_all_tests(fixed_by_commit_jobs)

    low_value_jobs = build_removals(
        active_jobs=active_jobs,
        failures=fixed_by_commit_jobs,
        target=target)

    # Only return high value jobs
    for low_value_job in low_value_jobs:
        try:
            active_jobs.remove(low_value_job)
        except ValueError:
            print("%s is missing from the job list", low_value_job)

    total = len(fixed_by_commit_jobs)
    total_detected = check_removal(fixed_by_commit_jobs, low_value_jobs)
    percent_detected = 100 * len(total_detected) / total
    return active_jobs

def getData(filename):
    data = ''
    results = []
    with open(filename, 'r') as f:
        data = f.readlines()

    firstline = True
    for line in data:
        if firstline:
            firstline = False
            continue
        results.append(line.split(','))
    return results

def parseTestname(item):
    error_line = item
    parts = error_line.split('|')
    if len(parts) == 5:
        if len(parts[1].split('jit-test')) > 1:
            testname = 'jittest'
        elif len(parts[2].split('junit')) > 1:
            testname = parts[1].strip()
        else:
            return ''
    elif len(parts) == 4:
        if len(parts[1].split('test_')) > 1:
            testname = parts[1].strip()
        else:
            return ''
    elif len(parts) == 2:
        if len(parts[1].split('tests/reftest')) > 1:
            testname = parts[1].split('tests/reftest')[-1]
        elif len(parts[1].split('GTest')) > 1:
            testname = "GTest"
        else:
            testname = parts[1].strip()
    elif len(parts) != 3:
        return ''
    else:
        testname = parts[1].strip()
        testname = testname.split('==')[0]
        testname = testname.split('!=')[0]
        testname = testname.split('tests/reftest/tests/')[-1]

    # filter out non tests;
    nonTests = ['ShutdownLeaks', 'automation.py', 'LeakSanitizer',
                'gtest', 'GTest', 'FilePreferencesWin.AccessUNC', 'jittest',
                'None', 'none', 'tps', 'dromaeo_css', 'tp5o', 'ts_paint', 'ts_paint_heavy',
                'ts_paint_webext', 'tp6_google', 'a11yr', 'tp5o_scroll', 'about_preferences_basic',
                'basic_compositor_video', 'perf_reftest', 'perf_reftest_singletons',
                'speedometer', 'damp', 'testAccessibleCarets', 'remoteautomation.py',
                'ry_on_working_if_the_frame_is_deleted_from_under_us', 'tsvgx', 'Pipes.Main']
    if testname in nonTests:
        return ''

    if testname.startswith('http://'):
        parts = testname.split('/')
        testname = '/'.join(parts[3:])

    if len(testname.split('test=')) > 1:
        testname = testname.split('test=')[-1]

    if '/' not in testname:
        return ''

    if testname.startswith('/'):
        testname = "testing/web-platform/tests%s" % testname

    nonTestPatterns = ['org.mozilla', 'tests/jit-test', 'testing/marionette/harness', 'awsy']
    found = False
    tname = testname.replace('\\', '/')
    for nonTestPattern in nonTestPatterns:
        if tname.startswith(nonTestPattern):
            found = True
            break
    if found:
        return ''

    if len(testname.split('.ini:')) > 1:
        testname = testname.split('.ini:')[-1]
    return testname

def testfilesPerRevision(data):
    # per test format: fixed_by_revision,failed_revision,config,jobid,error_line,platform - would like platform_options
    perRevision = {}
    testnames = []
    jobids = []
    for item in data:
        if len(item) < 6:
            print("Invalid length: %s" % len(item))
            continue

        platform = item[-1].strip('\n')
        config = item[2]

        # we only need one failure/job
        # reduces about 85% of the unique testnames
        if item[3] in jobids:
            continue

        jobids.append(item[3])

        lineindex = 4
        rev = item[0]
        if rev.startswith('http'):
            rev = rev.split('/')[-1]
        if rev.startswith('"'):
            rev = rev[1:]
            jobindex = 4
        if len(rev) > 12:
            rev = rev[0:12]


        testname = parseTestname(item[lineindex])
        if not testname:
            continue

        found = False
        for p in ['linux', 'android', 'win', 'osx', 'mac']:
            if platform.startswith(p):
                found = True
                break
        if not found:
            print "skipping %s" % item
            continue

        if rev not in perRevision:
            perRevision[rev] = []

        testname = testname.strip()
        if testname not in testnames:
            testnames.append(testname)
        if [testname, config, platform] not in perRevision[rev]:
            perRevision[rev].append([testname, config, platform])

    return perRevision


def prioritizeKeys(perRevsion):
    # in order of removal: mac, osx, android, windows, linux
    # in secondary order of removal: cov, asan, pgo, debug, opt
    retVal = {}
    for rev in perRevision:
        items = perRevision[rev]
        newItems = []
        for os in ['mac', 'osx', 'android', 'win', 'linux']:
            for item in items:
                if item[2].startswith(os):
                    newItems.append(item)

        items = newItems
        newItems = []
        for config in ['asan', 'pgo', 'debug', 'opt']:
            for item in items:
                if item[1].startswith(config):
                    newItems.append(item)
 
        retVal[rev] = newItems
    return retVal


results = getData('SETA_testnames.csv')
perRevision = testfilesPerRevision(results)
perRevision = prioritizeKeys(perRevision)

# accept up to 5% of the failures missed
retVal = get_high_value_jobs(perRevision, 95)
print "Tests that need to be run..."
for job in retVal:
    print job[0]
