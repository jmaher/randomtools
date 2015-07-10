assuming you do:
wget --user-agent=Firefox -p -k  -e robots=off http://www.facebook.com/barackobama


this generates a single file:
barackobama

If we load this file in a browser, you will see a lot of network activity.  Most of this comes from:
* javascript
* css
* css referencing images
* css referencing javascript
* javascript loading images
* and a few other random tweaks


In firefox if you open the devtools console, there is the main console and you can toggle the messages.  For example there is (css, javascript, errors, net).  In this case we only want to select net (for network), and do a full page reload.

After the page is done fully loading, copy paste the content to a text file (hardcoded to f.txt) in the same directory as this file.

This script will attempt to download the file references and if it fails, it will search for the full reference (usually something like http:\/obfuscated\/file.jpg?params&12314&blah).

Once it finds the url, it will download the file properly into a files/ subdir.  Assuming it was successful at downloading the file, it will replace the reference in the code and continue on.

There are 2 error cases:
1) we fail on some files in our f.txt - here we might have to do something manually
2) assuming all files in f.txt are completed and replaced, there might be calls to apis which don't work well with this script- either comment them out or figure out how to manually download the data and then edit the raw file.

this currently works on facebook profile pages (circa July 2015).
