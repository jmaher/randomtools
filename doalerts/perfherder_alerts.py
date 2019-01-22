import json
import requests
import os
import datetime

import click

from generate_alerts import RevisionDatum, detect_changes

# constants in perfherder
interval = 7776000  # 90 days
interval = 31536000  # 1 year
pgohash = "f69e1b00908837bf0550250abb1645014317e8ec"
thurl = "https://treeherder.mozilla.org"

# data we can iterate through
frameworks = [
    {"id": 1, "name": "talos"},
    {"id": 10, "name": "raptor"},
    {"id": 4, "name": "awsy"},
    {"id": 11, "name": "js-bench"},
]
branches = ["mozilla-inbound", "autoland", "mozilla-central"]
platforms = [
    "windows10-64",
    "windows10-64-qr",
    "linux64",
    "linux64-qr",
    "osx-10-10",
    "windows7-32",
    "android-hw-p2-8-0-arm7-api-16",
    "android-hw-p2-8-0-android-aarch64",
    "android-hw-g5-7-0-arm7-api-16",
]


# given raw data from a given perfherder signature,
# put it into format for analysis
def parseSignatureData(payload):
    datum = {}
    for rev in payload:
        for item in payload[rev]:
            timestamp = item["push_timestamp"]
            pushid = item["push_id"]
            value = item["value"]
            key = "%s:%s" % (timestamp, pushid)
            if key not in datum.keys():
                datum[key] = []
            datum[key].append(value)

    data = []
    for key in datum:
        timestamp, pushid = key.split(":")
        values = datum[key]
        data.append([timestamp, pushid, values])
    return data


# useful for getting a given url from treeherder
def getUrl(url, key):
    if not os.path.exists("cache"):
        os.makedirs("cache")

    keypath = os.path.join("cache", "%s.json" % key)
    if os.path.exists(keypath):
        with open(keypath, "r") as f:
            return json.load(f)

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5)",
        "accept-encoding": "json",
    }
    response = requests.get(url, headers=headers)
    data = response.json()

    with open(keypath, "wb") as f:
        json.dump(data, f)
    return data


def getFrameworkId(name):
    retVal = [f["id"] for f in frameworks if f["name"] == name]
    return retVal[0]


def getSignatures(branch, framework, platform):
    url = "%s/api/project/%s/performance/signatures/" % (thurl, branch)
    url = "%s?framework=%s&interval=%s&platform=%s&subtests=1" % (
        url,
        framework,
        interval,
        platform,
    )
    key = "%s-%s-%s" % (branch, framework, platform)
    return getUrl(url, key)


def filterSignatureIds(signatures, testname, subtests):
    sig_ids = []
    for sig in signatures:
        if signatures[sig]["suite"] == testname:
            metric = "geomean"
            option = "opt"
            if signatures[sig]["option_collection_hash"] == pgohash:
                option = "pgo"

            # we have a subtest
            if "test" in signatures[sig]:
                metric = signatures[sig]["test"].split(testname)[-1].strip("-")
                if not subtests:
                    continue

            sig_ids.append(
                {"id": signatures[sig]["id"], "metric": metric, "option": option}
            )
    return sig_ids


def getTestNames(branch, framework, platform):
    signatures = getSignatures(branch, framework, platform)
    names = []
    for sig in signatures:
        if signatures[sig]["suite"] not in names:
            names.append(signatures[sig]["suite"])
    return names


def analyzeData(sig, branch, framework):
    url = (
        "https://treeherder.mozilla.org/api/project/%s/performance/data/?framework=%s&interval=%s&signature_id=%s"
        % (branch, framework, interval, sig["id"])
    )
    key = "%s-%s-%s" % (branch, framework, sig["id"])
    payload = getUrl(url, key)

    runs = parseSignatureData(payload)
    data = [RevisionDatum(r[0], r[1], r[2]) for r in runs]

    results = detect_changes(data)
    regressions = [d for d in results if d.change_detected]
    return regressions


def filterUniqueAlerts(results):
    filtered = [{"sig": {}, "result": []}, {"sig": {}, "result": []}]
    # TODO: consider weekends or slow times for a longer window - 24 hours
    # TODO: sanity check no alerts are on the same 12 hour window (maybe within 100 pushids?)
    hours = 6
    first = [
        datetime.datetime.fromtimestamp(float(x.push_timestamp))
        for x in results[0]["result"]
    ]
    second = [
        datetime.datetime.fromtimestamp(float(x.push_timestamp))
        for x in results[1]["result"]
    ]
    f_matched = set()
    s_matched = set()
    for s in first:
        f_matched.update(
            [
                s
                for f in second
                if s < f + datetime.timedelta(hours=hours)
                and s > f - datetime.timedelta(hours=hours)
                and s not in list(f_matched)
            ]
        )
    for s in second:
        s_matched.update(
            [
                s
                for f in first
                if s < f + datetime.timedelta(hours=hours)
                and s > f - datetime.timedelta(hours=hours)
                and s not in list(s_matched)
            ]
        )
    sets = [list(set(first) - f_matched), list(set(second) - s_matched)]

    for iter in [0, 1]:
        for item in results[iter]:
            remaining = [
                x
                for x in results[iter]["result"]
                if datetime.datetime.fromtimestamp(float(x.push_timestamp))
                in sets[iter]
            ]
            if len(remaining) == 0:
                continue

            filtered[iter]["sig"] = results[iter]["sig"]
            filtered[iter]["result"] = remaining
        if filtered[iter] == {"sig": {}, "result": []}:
            filtered[iter] = None
    results = [x for x in filtered if x is not None]
    return results


def analyzeTest(framework, branch, platform, testname, subtests):
    signatures = getSignatures(branch, framework, platform)
    sig_ids = filterSignatureIds(signatures, testname, subtests)

    results = []
    for sig in sig_ids:
        result = analyzeData(sig, branch, framework)
        if result:
            results.append({"sig": sig, "result": result})

    if results == []:
        return

    if not subtests and len(results) == 2:
        results = filterUniqueAlerts(results)

    for i in results:
        print(
            "%s: %s:%s (%s)"
            % (testname, i["sig"]["option"], i["sig"]["metric"], len(i["result"]))
        )
        for d in i["result"]:
            date = datetime.datetime.fromtimestamp(float(d.push_timestamp)).isoformat()
            print("%s (%s)" % (date, d.push_id))
        print("")


@click.command()
@click.option(
    "--framework",
    "-f",
    required=True,
    type=click.Choice([f["name"] for f in frameworks]),
)
@click.option("--branch", "-b", required=True, type=click.Choice(branches))
@click.option(
    "--platform",
    "-p",
    "platforms",
    multiple=True,
    required=True,
    type=click.Choice(platforms),
)
@click.option("--subtests/--no-subtests", default=False)
def cli(framework, branch, platforms, subtests):
    framework = getFrameworkId(framework)

    for platform in platforms:
        print("-------- %s -------------" % platform)
        testnames = getTestNames(branch, framework, platform)

        for testname in testnames:
            analyzeTest(framework, branch, platform, testname, subtests)


if __name__ == "__main__":
    cli()
