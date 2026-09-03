# Running Groma on AutoDL — a guide for someone who has never used a server

This guide assumes nothing. If you have never opened a terminal, typed a command,
or heard the word "SSH", start at the top and go in order. If you have, skip to
[the cheat-sheet](#cheat-sheet) at the end.

## 1. What you actually have

You have rented a computer from AutoDL. It lives in a data centre, it runs Linux,
and it has no screen. The only way to use it is to connect to it from your own
computer and type instructions to it. Those instructions are called **commands**,
the window you type them into is called a **terminal**, and the connection between
your computer and theirs is called **SSH**.

Groma is a program running on that rented computer. It is a web service: once it is
running, you can open a web page that shows the coverage map for the site. Your job,
as its manager, is to be able to answer four questions:

1. Is it running?
2. If not, how do I start it?
3. What is it complaining about?
4. How do I put the latest version on?

Every one of those is one command, and the whole of this guide is about those
commands and what their answers mean.

### The few words you will keep seeing

| Word | What it means here |
| --- | --- |
| **instance** | AutoDL's name for the computer you rented. |
| **terminal** | The window on *your* computer where you type commands. |
| **SSH** | The way your terminal connects to the instance. |
| **root** | The user account on the instance. It can do anything, which is convenient and slightly dangerous. |
| **command** | A line of text you type and then press Enter. |
| **prompt** | The bit of text the terminal shows when it is waiting for you to type. |
| **port** | A numbered door on the instance. Groma listens on door 6006. |
| **log** | A text file the service writes to as it runs. When something is wrong, the reason is in there. |
| **service** | A program that keeps running in the background, waiting for requests. Groma is one. |

## 2. Opening a terminal on your own computer

- **Mac:** press `Cmd + Space`, type `Terminal`, press Enter.
- **Windows 10 or 11:** press the Windows key, type `PowerShell`, press Enter.
- **Linux:** you already know.

Both Mac and Windows come with SSH built in; there is nothing to install.

A terminal shows a prompt and a blinking cursor. You type a command, press Enter, and
it prints an answer (or nothing, which usually means "done, no complaints").

Two things that surprise everyone the first time:

- **When you type a password, nothing appears.** Not dots, not stars, nothing. The
  characters are going in. Type it and press Enter.
- **Copying and pasting** works, but the shortcut differs. In PowerShell,
  right-click pastes. In the Mac Terminal, `Cmd + V` pastes. Once you are connected
  to the instance, `Ctrl + C` does *not* copy — it means "stop what you're doing".

## 3. Connecting to the instance

In the AutoDL console, each instance shows a login line that looks like this:

```
ssh -p 54959 root@connect.bjb2.seetacloud.com
```

The number after `-p` and the address after `root@` are specific to your instance
and can change if the instance is moved. Always copy the current one from the
console rather than from memory.

Paste it into your terminal and press Enter.

- The very first time, it will ask `Are you sure you want to continue connecting?`
  Type `yes` and press Enter. That is it confirming you trust this computer.
- Then it asks for the password. Type it (nothing will appear) and press Enter.

When it works, the prompt changes to something like:

```
root@autodl-container-abc123:~#
```

The `root@autodl-container` part tells you that **you are now typing on the instance,
not on your own computer**. Everything you type from here runs there.

To leave, type `exit` and press Enter. The prompt goes back to your own computer's.
The service keeps running after you leave; disconnecting does not stop it.

> **Change the password now.** The password for this instance was shared in a chat.
> Anything shared in a chat should be treated as public. In the AutoDL console, on
> the instance's row, open the **更多 / More** menu and choose **重置密码 / Reset
> password**. Do this once, today. (This is item 19.5 in the build specification:
> "rotate any credential that has been pasted into a chat.")

## 4. Installing Groma for the first time

### 4a. First decide: is the code public or private?

The Groma code lives on GitHub at `samw212/aerial-data-compute-platform`, and
**right now that repository is private.** A private repository refuses anonymous
downloads, so the instance cannot fetch the code unless you give it a way in. You
have two choices; pick one before going on.

**Option 1 — make the repository public.** Simplest. On GitHub, open the
repository, click **Settings**, scroll to the **Danger Zone** at the bottom, click
**Change visibility**, choose **Public**, and confirm. Nothing about the code needs
a private repository — the design documents are not secret and there are no
credentials in it. If you go this way, use the commands in 4b as written.

**Option 2 — keep it private and create a read-only token.** A token is a long
password that grants exactly one permission: reading this one repository. Create it
like this, in your browser:

1. On GitHub, click your picture (top right) → **Settings**.
2. Left column, at the bottom: **Developer settings**.
3. **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
4. Give it a name (`groma-autodl`), an expiry (a year is fine), and under
   **Repository access** choose **Only select repositories** and pick
   `aerial-data-compute-platform`.
5. Under **Permissions → Repository permissions**, set **Contents** to
   **Read-only**. Leave everything else alone.
6. Click **Generate token** and copy it. It starts with `github_pat_` and you will
   not be shown it again — paste it somewhere safe for the next ten minutes.

If you go this way, use the commands in 4c instead. The token is stored once on the
instance in a file only `root` can read, and you will not need it again there.

### 4b. Install (public repository)

Connect to the instance (section 3). Then paste this one line and press Enter:

```
curl -fsSL https://raw.githubusercontent.com/samw212/aerial-data-compute-platform/main/deploy/autodl/bootstrap.sh | GROMA_BRANCH=main bash
```

### 4c. Install (private repository, with a token)

Connect to the instance (section 3). Put your token in place of `github_pat_XXXX`
in **both** places, then paste the whole line and press Enter:

```
curl -fsSL -H "Authorization: token github_pat_XXXX" https://raw.githubusercontent.com/samw212/aerial-data-compute-platform/main/deploy/autodl/bootstrap.sh | GROMA_GITHUB_TOKEN=github_pat_XXXX GROMA_BRANCH=main bash
```

(The first copy lets the installer itself be downloaded; the second lets the
installer download the code.)

### What the installer does

Either way, it does the same things, in order, printing a blue `==>` heading for
each step:

1. Checks the machine has what it needs.
2. Installs `uv`, the tool that manages Python for this project.
3. Downloads the Groma code from GitHub into `/root/autodl-tmp/groma/app`.
4. Installs Python 3.12 and all the project's dependencies.
5. **Runs the test suite.** If any test fails, it stops and starts nothing. That is
   deliberate: a coverage service whose tests fail is not one you want to publish.
6. Installs `supervisord`, which keeps the service running and restarts it if it
   crashes.
7. Installs the `groma-ctl` command you will use from now on.
8. Starts the service and checks it answers.

It takes two to five minutes the first time, mostly downloading. It ends with a
green `Done` and a short summary. **It is safe to run again** — if something goes
wrong halfway (the network drops, say), just paste the same line again.

If the download is slow or fails, AutoDL has a network accelerator for GitHub. The
script turns it on automatically if it is available. If the script itself will not
download (the `curl` line fails), run this first and try again:

```
source /etc/network_turbo
```

### Installing a branch other than `main`

If you have been told the code is on a branch — for instance while a change is under
review — put its name in place of `main` in both places. The branch this guide was
first written on is `claude/repo-setup-devy66`, so until that is merged into `main`:

```
curl -fsSL https://raw.githubusercontent.com/samw212/aerial-data-compute-platform/claude/repo-setup-devy66/deploy/autodl/bootstrap.sh | GROMA_BRANCH=claude/repo-setup-devy66 bash
```

(add the two token pieces from 4c if the repository is private.)

### If it says "code download failed"

That is the private-repository problem from 4a: either the repository is still
private and no token was given, or the token was pasted wrongly. Re-read 4a and try
again — the installer is safe to rerun.

## 5. Seeing it in your browser

The service listens on port 6006. AutoDL exposes exactly that port to the outside.

**The easy way.** In the AutoDL console, on your instance's row, click
**自定义服务 / Custom service**. A new browser tab opens straight onto the Groma
page. Anyone with that link can open it; there is nothing secret on the page, but
bear it in mind.

**The other way**, if the console button is not available. On *your own* computer's
terminal (not on the instance — type `exit` first if you are connected), run the
login command with one extra piece added:

```
ssh -L 6006:127.0.0.1:6006 -p 54959 root@connect.bjb2.seetacloud.com
```

Leave that terminal open, and open <http://localhost:6006> in your browser. The extra
`-L ...` part makes port 6006 on your computer lead to port 6006 on the instance
for as long as the terminal stays connected.

### What the page shows

A map of the site, north at the top, coloured by how well the cameras can see each
square metre:

| Colour | Meaning |
| --- | --- |
| red | Identify — 250 or more pixels per metre; you could recognise a stranger |
| amber | Recognise — 125 or more; you could recognise someone you know |
| green | Observe — 62 or more; you can follow what a person is doing |
| blue | Detect — 25 or more; you can tell a person is there |
| grey | seen by a camera, but too far away to be useful |
| dark | blind — no camera has a line of sight at all |

Below the map are the percentages, and a table of how much area each camera is the
*only* camera covering. That last number is the one that justifies each camera: it is
what would go dark if that camera failed.

The links at the top let you erect the event tents, switch between winter and
summer (the trees are in leaf in summer), and change the grid resolution. Nothing
you click on this page changes anything on the instance; it only changes what you
are looking at.

Two other addresses on the same service:

- `/api/health` — one line of text saying whether it is well, and which version.
- `/docs` — the technical description of the service's endpoints.

## 6. Everyday management: the `groma-ctl` command

Connect to the instance (section 3). All of these are typed there.

### Is it running?

```
groma-ctl status
```

Healthy looks like:

```
groma-api                        RUNNING   pid 4172, uptime 2 days, 3:14:05
```

`RUNNING` is the word you want. `uptime` is how long since it last started. Anything
else — `STOPPED`, `FATAL`, `BACKOFF`, or a red message saying supervisord is not up
— means it is not serving, and section 8 tells you what to do.

### Is it well?

```
groma-ctl health
```

This does not ask supervisord; it asks the service itself, the way a browser would.
Healthy looks like:

```
healthy: {"status":"ok","kernel_version":"1.0.0","contracts_version":"0.1.0","site":"site_alpha","cameras":4,"structures":14}
```

If `status` says RUNNING but `health` fails, the program is alive but not answering.
Restart it.

### What is it complaining about?

```
groma-ctl logs
```

Shows the last sixty lines the service wrote. Each web request appears as a line
ending in a number: `200` is fine, `422` means somebody asked for something the
service refused (a grid too fine, for instance), `500` means it hit a bug — and the
lines just above will say which.

To see more, give it a number: `groma-ctl logs 300`.

To watch the log live while you click around the web page:

```
groma-ctl follow
```

Press `Ctrl + C` to stop watching. (This is the one place `Ctrl + C` is what you
want. It stops the *watching*, not the service.)

### Turn it off and on again

```
groma-ctl restart
```

Stops the service and starts it. Takes about three seconds. This is the first thing
to try for almost any problem, and it is completely safe: nothing is stored on the
instance that a restart could lose.

### Stop it, start it

```
groma-ctl stop
groma-ctl start
```

You would stop it to save resources while you are not using it for a long period,
or before shutting the instance down. `start` is safe to run when it is already
running; it just tells you so.

### Put the latest version on

```
groma-ctl update
```

This fetches the newest code from GitHub, installs anything new it needs, **runs the
whole test suite**, and only if every test passes does it restart the service on the
new code. If a test fails, it tells you so, and the *old* version keeps running
untouched. It prints the exact command to type if you want to roll back manually.

It also prints the list of changes it is bringing in, so you can see what you are
about to run.

### Where is everything?

```
groma-ctl where
```

Prints the folders in use, which branch of the code is installed, and the address
the service is on. Useful to paste into a message when asking for help.

### The other commands

| Command | What it does |
| --- | --- |
| `groma-ctl test` | Runs the test suite without touching the service. |
| `groma-ctl coverage` | Prints the coverage figures for the site in the terminal — the same numbers as the web page. Try `groma-ctl coverage --tents`. |
| `groma-ctl bench` | Runs the speed benchmark. Should say under 800 ms. |
| `groma-ctl help` | Lists all of the above. |

## 7. What happens when the instance is shut down

AutoDL charges for every hour the instance is switched on, whether or not you are
using it. Shut it down when you do not need it, from the console (**关机 / Shut
down**).

When you shut it down:

- Everything on disk is kept. The code, the environment, the logs — all of it is on
  the data disk (`/root/autodl-tmp`), which survives.
- **The running service is not kept.** Programs do not survive a shutdown, on any
  computer.

So after you switch the instance back on (**开机 / Power on**), connect to it and run:

```
groma-ctl start
```

That is all. Nothing needs reinstalling.

There is a second, more drastic thing the console lets you do: **释放 / Release**.
That gives the computer back to AutoDL and **deletes everything on it, including the
data disk.** The Groma code is safe because it lives on GitHub, and reinstalling from
scratch is section 4 again — but anything else you put on that instance is gone.
Release only when you mean it.

## 8. When something is wrong

Work down this list; stop at the first thing that fixes it.

**I cannot connect at all** (`Connection refused`, `Connection timed out`, or it
just hangs).
The instance is probably switched off. Check the console. If it says it is on, copy
the login line from the console again — the port number changes if AutoDL moves the
instance.

**`Permission denied` when I type the password.**
Wrong password, or the password was reset. Reset it from the console (section 3) and
use the new one. Remember nothing appears while you type it.

**`groma-ctl: command not found`.**
The first-time install (section 4) has not been run on this instance, or did not
finish. Run it. It is safe to run on top of a half-finished attempt.

**`status` says it is not running.**
Run `groma-ctl start`. If that comes back with an error, run `groma-ctl logs 100` and
read the last few lines; they say why it could not start. The commonest reason is
something else already using port 6006 — a leftover from a previous attempt. Run
`groma-ctl stop`, then `groma-ctl start`.

**`status` says `RUNNING` but `health` fails, or the web page does not load.**
`groma-ctl restart`. If it still fails, `groma-ctl logs 100`.

**The web page loads but the numbers look wrong.**
Run `groma-ctl coverage` on the instance and compare. They come from the same code;
if they agree, the page is right and the question is about the site model, not the
service. If they disagree, that is a bug — copy both outputs into a message.

**`update` says tests failed.**
The service is still running on the old code and is fine. Someone has pushed
something that does not pass; tell them, and include the last twenty lines it
printed. Do not force it.

**The install or update is very slow or fails downloading.**
GitHub and Python's package index are slow from some networks. Run
`source /etc/network_turbo` and try again. The install script does this on its own,
but it cannot help with downloading the install script itself.

**`No space left on device`.**
The disk is full. `df -h` shows every disk and how full it is; look at the
`/root/autodl-tmp` line. Logs are capped and rotate automatically, so a full disk is
almost always something else that was put there. AutoDL's console can also enlarge
the data disk.

**Something else.**
Run `groma-ctl where`, `groma-ctl status`, `groma-ctl health` and `groma-ctl logs 100`,
copy all four outputs into a message, and send it to whoever maintains the code.
Those four answers are what they will ask for first.

## 9. What the service can and cannot do today

Groma is a fifteen-milestone build and this instance runs the first two: the
repository skeleton and the coverage kernel. The service computes camera coverage
over a hand-authored site model (`site_alpha`) with four fixed cameras, and shows
the result. It does not yet ingest drone imagery, reconstruct a 3D model, extract
structures, or let you place cameras through the web page. Each of those is a
later milestone, and each one, when it lands, arrives through `groma-ctl update`.

Nothing on this instance holds data you could lose. There is no database yet. The
site model is a file in the code, and the coverage is recomputed on every request.

## Cheat-sheet

```
# On your own computer
ssh -p 54959 root@connect.bjb2.seetacloud.com          connect (copy the real one from the console)
ssh -L 6006:127.0.0.1:6006 -p 54959 root@...            connect AND make http://localhost:6006 work
exit                                                    disconnect

# On the instance, first time only (public repository — see section 4 if private)
curl -fsSL https://raw.githubusercontent.com/samw212/aerial-data-compute-platform/main/deploy/autodl/bootstrap.sh | GROMA_BRANCH=main bash

# On the instance, every day
groma-ctl status        running?
groma-ctl health        answering?
groma-ctl logs          what happened?  (groma-ctl logs 300 for more)
groma-ctl restart       off and on again
groma-ctl update        latest code, tested, then restarted
groma-ctl start         after the instance was powered on
groma-ctl stop          before powering it off
groma-ctl where         paths, branch, address — for asking for help
```
