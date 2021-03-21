import os

# set up environment variable overrides, can use for different versions
# as well as native (TALOS-II POWER9) builds.
cmds = {}
for cmd in ['objcopy', 'as', 'ld', 'gcc', 'ar', 'gdb']:
    cmds[cmd] = os.environ.get(cmd.upper(), "powerpc64-linux-gnu-%s" % cmd)


