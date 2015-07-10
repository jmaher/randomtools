import subprocess
import re
import os

filename = ''

def findAndGet(url, lines):
    retVal = None
    fname, root, query = getFilename(url)

    resrc = re.compile('.*src="%s(.*)".*' % url)
    rebg = re.compile('.*\(%s(.*)\).*' % url)
    for line in lines:
        match = resrc.match(line)
        if match:
            retVal = url + match.group(1).split('"')[0]
            break
        match = rebg.match(line)
        if match:
            retVal = url + match.group(1).split('"')[0]
            break

    if retVal:
        retVal = retVal.replace("&amp;", "&")
    return retVal

def findEscapedUrl(url, lines):
    #look for the \/ version of the url
    retVal = None
    fname, root, query = getFilename(url)

    refname = re.compile('.*[=:]"https:(.*)%s(.*)".*' % fname)
    refname2 = re.compile('.*src=https:(.*)%s(.*)".*' % fname)
    for line in lines:
        match = refname.match(line)
        if match:
            first = match.group(1).split('"')[-1]
            if first.startswith('files/'):
                break
            retVal = 'https:' + first + fname + match.group(2).split('"')[0]
            print "matched on refname: %s" % retVal
            break
        match = refname2.match(line)
        if match:
            first = match.group(1).split('"')[-1]
            if first.startswith('files/'):
                break
            retVal = 'https:' + first + fname + match.group(2).split('"')[0]
            print "matched on refname2: %s" % retVal
            break

    if retVal:
        retVal = retVal.replace("&amp;", "&")
    return retVal



def getFilename(url):
    parts = url.split('?')
    query = ""
    if len(parts) > 1:
        query = '?'.join(parts[1:])
    dirparts = parts[0].split('/')
    root = '/'.join(dirparts[:-1])
    fname = dirparts[-1]
    return fname, root, query


def wgetFile(filename, url):
    try:
        url.index('&')
        url = '"%s"' % url
    except:
        pass

    if os.path.exists('files/%s' % filename):
        stats = os.stat('files/%s' % filename)
        if stats.st_size > 0:
            return ""

    url = url.replace('\/', '/')

    cmd = 'wget --user-agent=Firefox -O files/%s %s' % (filename, url)
    print cmd
    # NOTE: using subprocess fails for wget as it has a scheme error
    os.system('%s > wget.out' % cmd)
    with open('wget.out', 'r') as fHandle:
        stderr = fHandle.read()

    if os.path.exists('files/%s' % filename):
        stats = os.stat('files/%s' % filename)
        if stats.st_size <= 0:
            stderr = "%s\nERROR: file %s is size 0" % (stderr, filename)
            os.system('rm files/%s' % filename)
    return stderr


def replaceLines(query, root, lines):
    newlines = []
    newline = ""
    for line in lines:
        if query:
            newline = line.replace('%s' % query, '')
        else:
            newline = line
        newline = newline.replace('%s' % root, 'files')
        newlines.append(newline)
    return newlines


with open('f.txt', 'r') as fHandle:
    urls = fHandle.readlines()

with open(filename, 'r') as fHandle:
    lines = fHandle.readlines()

redo = []
for url in urls:
    url = url.split(' ')[0]
    url = url.strip('\n')
    if url.strip(' ') == "":
        continue

    if url.startswith('file://'):
        continue

    fname, root, query = getFilename(url)
    stderr = wgetFile(fname, url)

    replace = True
    rewget = re.compile('.*ERROR.*', re.MULTILINE|re.DOTALL)
    if rewget.match(stderr):
        found = findAndGet(url, lines)
        if not found:
            redo.append(url)
            replace = False
        else:
            url = found
            fname, root, query = getFilename(url)
            stderr = wgetFile(fname, url)
            if rewget.match(stderr):
                redo.append(url)
                replace = False

    if replace:
        lines = replaceLines(query, root, lines)

    # Handle second pass for escaped urls
    found = findEscapedUrl(url, lines)
    if found:
        fname, root, query = getFilename(found)
        stderr = wgetFile(fname, found)
        if rewget.match(stderr):
            if url not in redo:
                redo.remove(url)
        else:
            lines = replaceLines(query, root, lines)

with open(filename, 'w') as fHandle:
    for line in lines:
        fHandle.write(line)


print "\n\n:Files that didn't work out so well:"
for r in redo:
    print r
