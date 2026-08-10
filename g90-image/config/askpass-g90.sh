#!/bin/bash
# g90 askpass wrapper for ssh from the dev Pi (nomadpi).
# Used by ~/.local/bin/ssh-g90 via SSH_ASKPASS.
#
# This is a TEMPLATE — fill in the box's ssh password before
# using it. The pattern on the dev Pi is:
#   cp askpass-g90.sh ~/.local/bin/askpass-<boxname>.sh
#   chmod 700 ~/.local/bin/askpass-<boxname>.sh
#   echo "<the box's password>" > ~/.ssh/.<boxname>-pass
#   chmod 600 ~/.ssh/.<boxname>-pass
#   sed -i 's/PASSWORD_FROM_SECRET_STORE/PASSWORD/' ~/.local/bin/askpass-<boxname>.sh
#
# ⚠️  NEVER commit this file with a real password inside.
# Group-specific values go in the g90-fleet-config repo, not here.
echo "PASSWORD_FROM_SECRET_STORE"
