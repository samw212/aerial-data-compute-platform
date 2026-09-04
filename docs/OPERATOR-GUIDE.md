# Running ADCP on AutoDL — the operator's guide

For the person who keeps the system running. It assumes you have never used a
server or a terminal. Read sections 1–4 once; after that the cheat-sheet at the end
is all you will normally need.

## 1. What you have

You rent a computer from AutoDL. It lives in a data centre, runs Linux, and has no
screen. You use it by connecting from your own computer and typing **commands**
into a **terminal**; the connection is called **SSH**.

ADCP runs on that computer as five programs that a supervisor keeps alive:

| Program | What it does | Port |
|---|---|---|
| `nginx` | the front door: serves the web app and passes `/api` to the API | **6006** (the one AutoDL exposes) |
| `api` | the ADCP service itself (FastAPI) | 8000, local only |
| `worker` | background jobs: fine coverage grids, processing, tiling | — |
| `postgres` | the database (PostgreSQL + PostGIS) | 5432, local only |
| `redis` | the job queue and heartbeat | 6379, local only |

Your job as operator is to answer five questions, each one command:

1. Is it running? `groma-ctl status`
2. Is it well? `groma-ctl health`
3. What is it complaining about? `groma-ctl logs`
4. How do I put the latest version on? `groma-ctl update`
5. Is my data safe? `groma-ctl backup`

### Words you will keep seeing

| Word | Meaning here |
|---|---|
| **instance** | AutoDL's name for the computer you rented |
| **terminal** | the window on *your* computer where you type commands |
| **SSH** | the way your terminal connects to the instance |
| **root** | the user account on the instance; it can do anything |
| **prompt** | the text the terminal shows while waiting for you to type |
| **log** | a text file a program writes as it runs; when something is wrong, the reason is in there |
| **data disk** | `/root/autodl-tmp` — fast, survives shutdown, **not** saved into an image |
| **system disk** | `/` — small, saved with the image |

## 2. The AutoDL console

Everything about the *machine* (as opposed to the *software*) happens in the AutoDL
web console, in your browser.

- **Start / shut down.** Shutting down stops the bill for the GPU. Everything on the
  data disk stays. When you start again, ADCP starts by itself.
- **No-GPU mode (无卡模式).** Cheap. Everything except photogrammetry works. Use it
  for planning, reviewing and reports. Switch to a GPU mode only for the days you
  process a new survey.
- **The login line.** On the instance's row the console shows something like
  `ssh -p 25423 root@connect.bjb2.seetacloud.com` and a password. **The host, port
  and password can change when the instance is moved or re-created** — always copy
  the current one from the console, never from memory or old notes.
- **Reset password (重置密码).** Under the instance's "More" menu. Do this once
  now: the password has been pasted into chats and files, and anything pasted is
  public. (Your SSH key, section 3, keeps working after a reset.)
- **Enlarge the data disk (扩容).** Before the first real survey. A 10 GB set of
  images needs about 80 GB free while it processes; `groma-ctl disk 10` tells you.
- **Custom service (自定义服务).** Opens port 6006 in a new tab: that is the app.
- **Save image.** Only saves the system disk. Your database and surveys are on the
  data disk, so a saved image does *not* back them up — `groma-ctl backup` does.

## 3. Connecting

**Mac:** press `Cmd + Space`, type `Terminal`, press Enter.
**Windows 10/11:** press the Windows key, type `PowerShell`, press Enter.

Paste the login line from the console and press Enter. The first time it asks
`Are you sure you want to continue connecting?` — type `yes`. Then it asks for the
password; **nothing appears while you type it**; type it and press Enter.

When it works the prompt changes to `root@autodl-container-…:~#`. You are now
typing on the instance. Type `exit` to leave; the system keeps running.

**Save yourself the password.** Once, on your own computer:

```
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_adcp -N ""
ssh-copy-id -i ~/.ssh/id_ed25519_adcp -p <PORT> root@<HOST>
```

and add to `~/.ssh/config` (create it if missing):

```
Host adcp
  HostName <HOST>
  Port <PORT>
  User root
  IdentityFile ~/.ssh/id_ed25519_adcp
```

From then on `ssh adcp` connects without a password. When the console shows a new
host or port, edit those two lines.

## 4. Installing, and updating

First time, connected to the instance, one line:

```
curl -fsSL https://raw.githubusercontent.com/samw212/aerial-data-compute-platform/main/deploy/autodl/bootstrap.sh | bash
```

It prints a blue `==>` heading for each step: system packages, Python, the code,
the web build, the database, migrations, **the test suite** (if any test fails it
stops and starts nothing), the services, the sample site and the first admin
account (email and a generated password are printed at the end — change the
password after your first sign-in). It takes 10–20 minutes the first time and is
safe to run again if it is interrupted.

**Updating** to the latest version, from then on:

```
groma-ctl update
```

It fetches the code, installs, migrates the database, rebuilds the web app, runs
the tests, restarts, and finally signs in through the front door and runs a
coverage to prove the whole path works. If anything fails it tells you the
rollback command and leaves the old version running where it can.

## 5. Everyday commands

All typed on the instance.

```
groma-ctl status              RUNNING is the word you want, for all five programs
groma-ctl health              the service's own view: database, redis, worker, disk, versions
groma-ctl logs                last 60 lines of the api log
groma-ctl logs worker 200     last 200 lines of the worker log (also: postgres redis nginx nginx-error)
groma-ctl follow api          watch a log live; Ctrl-C stops watching (not the service)
groma-ctl restart             turn everything off and on again — safe, ~10 s
groma-ctl restart api         just one program
groma-ctl stop / start        before shutting the instance down / not needed on start
groma-ctl smoke               the end-to-end check: sign in, run a coverage, report the numbers
groma-ctl disk 10             free space, and what a 10 GB survey needs to process
groma-ctl gpu                 which GPU, and whether processing will use it
groma-ctl where               every path and port this install uses
```

### Users

```
groma-ctl users list
groma-ctl users add someone@emsd.gov.hk "Their Name" --role surveyor
groma-ctl users passwd someone@emsd.gov.hk
groma-ctl users role someone@emsd.gov.hk admin
```

Roles: **viewer** looks; **surveyor** also reviews structures, marks ground control,
places cameras and runs coverage; **admin** also manages users. Reviews and
ground-control marks are recorded against the user who made them, so give each
person their own account.

### Backups

```
groma-ctl backup                       now, into /root/autodl-tmp/groma/backups
groma-ctl restore backups/groma-20260904-0330.dump
```

A backup runs by itself every night at 03:30 and the last 14 are kept. The
database backup is small (megabytes); the survey imagery and point clouds in
`artefacts/` are large and are listed in a manifest next to each backup rather than
copied. **Copy the backups somewhere else** now and then — the data disk is not
part of a saved image, and if the instance is deleted it goes with it. From your
own computer:

```
scp -r adcp:/root/autodl-tmp/groma/backups ~/adcp-backups
```

## 6. Reading the health check

`groma-ctl health` prints something like:

```
status ok · version v0.1.3 · kernel 1.1.0
database  ok   jobs_queued 0  jobs_running 0
redis     ok
worker    ok   last_heartbeat 2026-09-04T…
disk      ok   free_gb 41.2  total_gb 50
```

- **status degraded** — one line below says which part; restart that program.
- **worker ok false** — jobs will queue and never run. `groma-ctl restart worker`.
- **disk ok false** — under 5 GB free. Processing will fail. Delete old surveys'
  artefacts or enlarge the disk.
- **kernel** — the coverage kernel version printed on every report. If a report and
  the screen disagree, this is the first thing to compare.

## 7. When something is wrong

The pattern is always the same: `groma-ctl status` to see *what* is down,
`groma-ctl logs <that program>` to see *why*, then fix or restart. The specific
failures we have caused on purpose and know how to recognise are in
`docs/runbook-autodl.md`, each as symptom → diagnosis → fix.

Things that look like faults but are not:

- **The page says "not signed in" after an update.** Sessions are signed with a
  secret in `/etc/groma.env`; an update keeps it. If someone regenerated the file,
  everyone signs in again once.
- **Processing refuses to start with a red "blocking" list.** That is the capture
  quality gate doing its job. A surveyor must read the items and acknowledge them.
- **Measurements are refused on a survey.** The survey has no georeferencing
  (`georef = none`): the model is the right shape and an unknown size. Re-fly with
  RTK or add ground control; do not look for a setting to switch this off.

## 8. Cheat-sheet

```
ssh adcp                          connect
groma-ctl status                  running?
groma-ctl health                  well?
groma-ctl logs [program] [N]      why not?
groma-ctl restart [program]       fix most things
groma-ctl update                  latest version, tested, restarted
groma-ctl backup                  now; nightly at 03:30 anyway
groma-ctl users add EMAIL NAME --role surveyor
groma-ctl disk 10 / gpu / where   capacity, GPU, paths
exit                              leave (the service keeps running)
```
