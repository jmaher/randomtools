import datetime
import requests
import yaml

known_suites = ["marionette", "browser-chrome", "mochitest-browser-media", "mochitest-devtools-chrome", "web-platform-tests", "mochitest-plain", "mochitest-media", "mochitest-chrome", "xpcshell", "crashtest", "jsreftest", "reftest"]
build_types = ["asan", "ccov", "tsan", "debug"]
variant_data = {}


def getAllFailures(start, end, branch="trunk"):
    start = datetime.datetime.strptime(start, "%Y-%m-%d")
    end = datetime.datetime.strptime(end, "%Y-%m-%d")
    # https://treeherder.mozilla.org/api/failures/?startday=2024-07-09&endday=2024-07-16&tree=all&failurehash=all
    url = "https://treeherder.mozilla.org/api/failures/?startday=%s&endday=%s&tree=%s&failurehash=all" % (start.date(), end.date(), branch)
    if verbose:
        print(url)
    try:
        response = requests.get(url, headers={"User-agent": "mach-test-info/1.0"})
        cdata = response.json()
        return cdata
    except Exception as e:
        print(e)
        pass


def getResults(bug, start, end, branch="trunk", verbose=False):
    start = datetime.datetime.strptime(start, "%Y-%m-%d")
    end = datetime.datetime.strptime(end, "%Y-%m-%d")
    url = "https://treeherder.mozilla.org/api/failuresbybug/?startday=%s&endday=%s&tree=%s&bug=%s" % (start.date(), end.date(), branch, bug)
    if verbose:
        print(url)
    try:
        response = requests.get(url, headers={"User-agent": "mach-test-info/1.0"})
        cdata = response.json()
        return cdata
    except Exception as e:
        print(e)
        pass


def getBZInfo(bugid):
    url = "https://bugzilla.mozilla.org/rest/bug?include_fields=summary&id=%s" % bugid    
    if verbose:
        print(url)
    try:
        response = requests.get(url, headers={"User-agent": "mach-test-info/1.0"})
        cdata = response.json()
        return cdata["bugs"][0]["summary"]
    except Exception as e:
        print(e)
        pass


def findVariant(testSuite):
    variant = ""
    parts = testSuite.split('-')
    try:
        if str(int(parts[-1])) == parts[-1]:
            parts = parts[:-1]
    except:
        pass

    ts = "-".join(parts)
    found = False
    for suite in known_suites:
        if suite in ts:
            variant = ts.split(suite)[-1].strip("-")
            found = True
            break

    if not found:
        variant = testSuite

    return variant


def getPlatformCondition(platform):
    # TODO: this is hardcoded and will get out of date
    condition = ""
    if 'linux1804' in platform:
        condition += "os == 'linux' && os_version == '18.04'"
    elif 'linux2204' in platform:
        condition += "os == 'linux' && os_version == '22.04'"
    elif 'macosx1015' in platform:
        condition += "os == 'mac' && os_version == '10.15' && processor == 'x86_64'"
    elif 'macosx1470' in platform:
        condition += "os == 'mac' && os_version == '14.70' && processor == 'x86_64'"
    elif 'macosx1100' in platform:
        condition += "os == 'mac' && os_version == '11.20' && arch == 'aarch64'"
    elif 'macosx1500' in platform:
        condition += "os == 'mac' && os_version == '15.30' && arch == 'aarch64'"
    elif 'windows11-64-24h2' in platform:
        condition += "os == 'win' && os_version == '11.26100' && processor == 'x86_64'"
    elif 'windows10-64-24h2' in platform:
        condition += "os == 'win' && os_version == '10.26100' && processor == 'x86_64'"
    elif 'windows11-32-24h2' in platform:
        condition += "os == 'win' && os_version == '11.2009' && processor == 'x86'"
    elif 'android-em-7-0-x86_64' in platform:
        condition += "os == 'android' && android_version == 24"
    else:
        print("UNKNOWN PLATFORM: %s" % platform)

    # build type
    type = "opt"
    if [t for t in build_types if t in platform]:
        type = [t for t in build_types if t in platform][0]
    
    condition = "%s && %s" % (condition, type)
    return condition


def getVariantData():
    global variant_data
    if variant_data:
        return variant_data

    url = "https://hg.mozilla.org/mozilla-central/raw-file/tip/taskcluster/kinds/test/variants.yml"
    try:
        response = requests.get(url, headers={"User-agent": "mach-test-info/1.0"})
        variant_data = yaml.safe_load(response.text)
    except:
        raise
        pass

    return variant_data


def getVariantCondition(variant):
    condition = ""

    if not variant:
        return ""

    vdata = getVariantData()
    matches = [v for v in vdata if variant in vdata[v]["suffix"]]
    if not matches:
        # composite - need to find all combination of matches
        suffixes = sorted([vdata[v]["suffix"] for v in vdata], key=len, reverse=True)
        found = []
        done = False
        v = variant
        while not done:
            matches = [s for s in suffixes if s in v]
            if matches:
                # first match is the longest string
                found.append(matches[0])
                found = list(set(found))
                v = v.replace(matches[0], "").strip("-")
                if not v:
                    done = True
            else:
                print("UNKNOWN VARIANT: %s, found: %s, remaining: %s" % (variant, found, v))
                done = True

        found_variants = []
        for f in found:
            found_variants.extend([v for v in vdata if vdata[v]["suffix"] == f])
        condition = " && ".join([vdata[f].get("mozinfo", "") for f in found_variants])
    elif len(matches) > 1:
        # NOT SURE
        print("TOO MANY MATCHES for %s: %s" % (variant, matches))
    else:
        condition = vdata[matches[0]].get("mozinfo", "")

    return condition



def generateConditions(bugid, start, end, verbose=False):
    retVal = {"ignored": 0}
    total_failures = 0
    data = getResults(bugid, start, end, verbose=verbose)
    results = {}
    for failure in data:
        key = "%s/%s" % (failure["platform"].replace('-shippable', ''), failure["build_type"])
        if key not in results:
            results[key] = {}
        
        variant = findVariant(failure["test_suite"])
        if variant not in results[key]:
            results[key][variant] = 0

        if verbose:
            print("%s :: %s" % (key, variant))
        results[key][variant] += 1
        total_failures += 1

    # if total failures > 30/week - skip anything with >5
    # if < 30; skip anything with >10
    threshold = 3
    if total_failures < 30:
        threshold = 20
    
    if verbose:
        print("total_failures found: %s, threshold is now: %s" % (total_failures, threshold))

    for key in results:
        failures = [v for v in results[key] if results[key][v] > threshold]
        if not failures:
            retVal["ignored"] += sum([int(results[key][v]) for v in results[key]])
            continue

        retVal["ignored"] += sum([int(results[key][v]) for v in results[key] if results[key][v] <= threshold])

        for v in failures:
            condition = getPlatformCondition(key)
            if getVariantCondition(v):
                condition = "%s && %s" % (condition, getVariantCondition(v))
            retVal[condition] = results[key][v]
    return retVal


verbose = False
start = "2025-02-10"
end = "2025-03-10"
bugs = getAllFailures(start, end)
bad_summaries = ['leakcheck', 'leaksanitizer', 'org.mozilla', 'moz_assert', 'assertion', 'moz_crash', 'taskcluster:error', 'application crashed']
total_failures = 0
skipped_failures = 0
ignored_failures = 0
skipped_tests = []
for b in bugs:
    total_failures += b["bug_count"]
    if b["bug_count"] < 30:
        continue

    summary = getBZInfo(int(b["bug_id"]))
    if "single tracking bug" not in summary:
        continue
    if any([bs for bs in bad_summaries if bs in summary.lower()]):
        continue

    print("%s - %s" % (b["bug_id"], summary))
    conditions = generateConditions(str(b["bug_id"]), start, end, verbose=verbose)
    for c in conditions:
        print("%s :: %s" % (c, conditions[c]))
        if c != "ignored":
            skipped_failures += conditions[c]
        else:
            ignored_failures += conditions[c]
            if b["bug_id"] not in skipped_tests:
                skipped_tests.append(b["bug_id"])

print("total failures: %s" % total_failures)
print("skipped failures: %s" % skipped_failures)
print("ignored failures: %s" % ignored_failures)
print("skipped tests: %s" % len(skipped_tests))
