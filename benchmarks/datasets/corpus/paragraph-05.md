# Field Notes from a Migration

## Week One

The first week of any storage migration is a study in humility. You have read the old system's documentation, you have a map of its tables, and both turn out to be wrong in small, load-bearing ways: a column that the docs call nullable but the writers never leave null, an index that exists only in production, a nightly job that quietly repairs rows nobody remembers creating. The temptation in week one is to fix what you find. Resist it. Write it down instead, because the fixes will interfere with the shadow comparisons you will run later, and the value of the migration depends on those comparisons being clean.

## Week Four

By the fourth week the dual-write path exists and the shadow reads begin. The first results are always humbling: a drift of a few hundred rows out of billions, concentrated in exactly the corners the map got wrong. Each drift gets a story, each story ends in one of three ways: the old system was wrong, the new system is wrong, or both are wrong in different directions on alternating Tuesdays. The temptation in week four is to declare the long tail acceptable. Quantify it instead: put a number on the residual drift, put an owner on it, and let the number shrink on a schedule that the business can see.

## Cutover

Cutover itself is an anticlimax if the previous weeks were honest. You flip the reads, you watch the dashboards that you built when you still did not trust the new store, and nothing happens, which is the goal. The last task is decommissioning, and it deserves the same discipline: remove the old writes, then the old reads, then the old store, in that order, with a week of quiet between each step. Migrations end not with a switch but with an audit that finds nothing left to turn off.
