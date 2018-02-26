# kivabot

This is a script to pull data on loans from kiva.org's api, write them to disk, and compute a metric expressing average number of days to loan payment.

Please do not abuse it, kiva is a charity. It is useful for diversifying your loan portfolio while maintaining certain return length conditions.

It was enough for my purposes but there are data like charity name/id that are also pulled that I don't even print, so it is quite extensible.

Be careful with the multhithreading, the API has a rate limit.
