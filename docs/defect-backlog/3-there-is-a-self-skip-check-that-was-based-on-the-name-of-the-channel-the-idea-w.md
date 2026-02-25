# there is a self-skip check that was based on the name of the channel. The idea w

## Status: Open

## Priority: Medium

## Summary

there is a self-skip check that was based on the name of the channel. The idea was to avoid going into an infinite loop however now it’s just ignoring a lot messages it shouldn’t. when I reported this issue, you just replaced the name check with an id check. This doesn’t address the real issue. Come up with a smarter rule or get rid of this rule altogether. Remember we just want to avoid looping so you can use a different check altogether that doesn’t regularly drop messages

## Source

Created from Slack message by U0AEWQYSLF9 at 1771992074.534839.
