import json
import requests
import os
import re
import datetime

import click

from generate_alerts import RevisionDatum, detect_changes

# constants in perfherder
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
    "windows10-64-shippable",
    "windows10-64-qr",
    "linux64",
    "linux64-shippable",
    "linux64-qr",
    "osx-10-10",
    "windows7-32",
    "windows7-32-shippable",
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
            key = f"{timestamp}:{pushid}"
            if key not in datum.keys():
                datum[key] = []
            datum[key].append(value)

    data = []
    for key in datum:
        timestamp, pushid = key.split(":")
        values = datum[key]
        data.append([timestamp, pushid, values])
    return data


def getFrameworkId(name):
    retVal = [f["id"] for f in frameworks if f["name"] == name]
    return retVal[0]


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
        f_list = list()
        for f in second:
            if (
                s < f + datetime.timedelta(hours=hours)
                and s > f - datetime.timedelta(hours=hours)
                and s not in list(f_matched)
            ):
                f_list.append(s)
        f_matched.update(f_list)
    for s in second:
        s_list = list()
        for f in first:
            if (
                s < f + datetime.timedelta(hours=hours)
                and s > f - datetime.timedelta(hours=hours)
                and s not in list(s_matched)
            ):
                s_list.append(s)
        s_matched.update(s_list)
    sets = [list(set(first) - f_matched), list(set(second) - s_matched)]

    for iter in [0, 1]:
        for item in results[iter]:
            remaining = list()
            for x in results[iter]["result"]:
                if (
                    datetime.datetime.fromtimestamp(float(x.push_timestamp))
                    in sets[iter]
                ):
                    remaining.append(x)
            if len(remaining) == 0:
                continue

            filtered[iter]["sig"] = results[iter]["sig"]
            filtered[iter]["result"] = remaining
        if filtered[iter] == {"sig": {}, "result": []}:
            filtered[iter] = None
    results = [x for x in filtered if x is not None]
    return results


class Alerts(object):
    def __init__(
        self, framework, branch, platforms, subtests, days, test, metrics, verbose
    ):
        self.framework = getFrameworkId(framework)
        self.branch = branch
        self.platforms = platforms
        self.subtests = subtests
        self.interval = 86400 * int(days)
        self.test = re.compile(test)
        self.metrics = metrics
        self.verbose = verbose
        self.alerts = 0
        self.push_ids = set()

    def getSignatures(self, platform):
        url = f"{thurl}/api/project/{self.branch}/performance/signatures/?framework={self.framework}&interval={self.interval}&platform={platform}&subtests=1"
        key = f"{self.branch}-{self.framework}-{platform}-{self.interval}"
        return self.getUrl(url, key)

    def getTestNames(self, platform):
        signatures = self.getSignatures(platform)
        names = []
        for sig in signatures:
            if signatures[sig]["suite"] not in names:
                names.append(signatures[sig]["suite"])
        return names

    # useful for getting a given url from treeherder
    def getUrl(self, url, key):
        if not os.path.exists("cache"):
            os.makedirs("cache")

        keypath = os.path.join("cache", f"{key}.json")
        if os.path.exists(keypath):
            if self.verbose:
                print(f"Restoring cached response for {url} from {keypath}")
            with open(keypath, "r") as f:
                return json.load(f)

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5)",
            "accept-encoding": "json",
        }
        if self.verbose:
            print(f"Downloading response for {url}")
        response = requests.get(url, headers=headers)
        data = response.json()

        with open(keypath, "w") as f:
            if self.verbose:
                print(f"Caching response for {url} in {keypath}")
            json.dump(data, f)
        return data

    def filterSignatureIds(self, signatures, testname):
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
                    if not self.subtests:
                        continue

                if not self.metrics or metric in self.metrics:
                    sig_ids.append(
                        {
                            "id": signatures[sig]["id"],
                            "metric": metric,
                            "option": option,
                        }
                    )
        return sig_ids

    def analyzeData(self, sig):
        url = f"{thurl}/api/project/{self.branch}/performance/data/?framework={self.framework}&interval={self.interval}&signature_id={sig['id']}"
        key = f"{self.branch}-{self.framework}-{sig['id']}-{self.interval}"
        payload = self.getUrl(url, key)

        runs = parseSignatureData(payload)
        data = [RevisionDatum(r[0], r[1], r[2]) for r in runs]

        results = detect_changes(data)
        regressions = [d for d in results if d.change_detected]
        return regressions

    def analyzeTest(self, platform, testname):
        signatures = self.getSignatures(platform)
        sig_ids = self.filterSignatureIds(signatures, testname)

        results = []
        for sig in sig_ids:
            result = self.analyzeData(sig)
            if result:
                results.append({"sig": sig, "result": result})

        if results == []:
            return

        if not self.subtests and len(results) == 2:
            results = filterUniqueAlerts(results)

        for i in results:
            print(
                f"{testname}: {i['sig']['option']}:{i['sig']['metric']} ({len(i['result'])})"
            )
            for d in i["result"]:
                self.alerts += 1
                self.push_ids.add(d.push_id)
                date = datetime.datetime.fromtimestamp(
                    float(d.push_timestamp)
                ).isoformat()
                print(f"{date} ({d.push_id})")
            print("")

    def do(self):
        for platform in self.platforms:
            print(f"-------- {platform} --------")
            testnames = self.getTestNames(platform)

            filtered_testnames = filter(lambda x: self.test.search(x), testnames)
            for testname in filtered_testnames:
                self.analyzeTest(platform, testname)

        print(f"-------- summary --------")
        print(f"{self.alerts} alerts found in {len(self.push_ids)} pushes")


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
@click.option(
    "--days", "-d", default="90", type=click.Choice(["1", "2", "7", "14", "30", "60", "90", "365"])
)
@click.option("--test", "-t")
@click.option("--metric", "-m", "metrics", multiple=True)
@click.option("--verbose", "-v", is_flag=True)
def cli(framework, branch, platforms, subtests, days, test, metrics, verbose):
    alerts = Alerts(
        framework, branch, platforms, subtests, days, test, metrics, verbose
    )
    alerts.do()


if __name__ == "__main__":
    cli()
