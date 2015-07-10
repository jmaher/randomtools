compare alerts is a way to compare a new alert system with an old one to see if we have parity.

Ideally we will take a large sample of alerts and compare them.

This is designed to go revision by revision.

NOTE: there is hacking in here to convert data and row fields- that is subject to change.

When we get a revision, we will build a list of branches where each branch will have a list of:
[platform, test, percent]

We do this for both alert files, then compare.  A loose compare is platform and test, a strict compare is percent.

Ideally we can deal with a loose compare and then focus on the details of a strict one because a calculation might be off.

This is really sloppy, but it has produced good data so far to date.

Future work would be to make it more configurable.

NOTE: from alert manager database, we generate the csv file with:
select branch,platform,test,push_date,percent,keyrevision from alerts where  push_date > '2015-04-01'  into outfile '/tmp/alerts.csv' fields terminated by ',' enclosed by '"' lines terminated by '\n';


that should be massaged to be more precise and smoother for less converting in the input.


