# GFX Projects List

The following projects must include `Test:` section in commit message.

## Project Check

From git_config.sh `dic_gfx_msg_check`

Check path pattern in:
https://scgit.amlogic.com/plugins/gitiles/amlogic/tools/buildbot/+/jenkins/checkpatch/config/git_config.sh

## Special Requirement

Must add `Test:` section after `Verify:`:

```
module: subject [n/m]

PD#XXXXXX

Problem:
Detail info

Solution:
Detail info

Verify:
Detail info

Test:
Detail info

Change-Id: XXXX
Signed-off-by: XXXX
```

## Test Field Instructions

See: https://confluence.amlogic.com/pages/viewpage.action?pageId=273325646
