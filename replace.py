import os

files = [f for f in os.listdir('.') if os.path.isfile(f)]

for filename in files:
    if not filename.endswith('.ini'):
        continue

    if os.path.exists(filename):
        with open(filename, 'r') as f:
            data = f.read()
    else:
        print "unable to find: %s" % filename
        continue

    lines = []
    found = False
    for line in data.split('\n'):
        if '15063' in line:
            found = True
        lines.append(line.replace("15063", "17134"))
    with open(filename, 'w+') as f:
        f.write('\n'.join(lines))
    if found:
        print filename
