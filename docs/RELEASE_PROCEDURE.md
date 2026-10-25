# Release procedure: from a code change to the live server

Follow these steps in order for every change. The live site changes only when someone runs step 6
by hand; there are no automatic updates (they were removed after one took the site down on 25 October 2026).

| Branch | Purpose |
|---|---|
| `floodpulse-v2` | Day-to-day work. Pushing here changes nothing on the server. |
| `main` | What the server runs. Merge into it only after steps 1–4 pass. |

Do not update the server during a demo or presentation: the site is unavailable for a few seconds while
the app restarts, and longer if something goes wrong.

---

## 1. Start from the latest code (laptop)

```
cd ~/Projects/FloodPulse-v2
git switch floodpulse-v2
git pull
```

## 2. Make the change and try it (laptop)

```
./floodpulse.sh            # starts (or restarts) the app with your change
```

Open <http://127.0.0.1:14180> and try what you changed, on a laptop-sized window and at phone width
(browser developer tools → device toolbar, about 390 × 700). Every page must still fit one screen.
`Ctrl+C` in that terminal stops the app.

## 3. Run the checks (laptop)

All must pass before you commit. Run them from the project folder:

```
(cd backend && .venv/bin/python -m pytest -q)        # backend tests
(cd frontend && npm test)                            # frontend unit tests
(cd frontend && npm run build)                       # production build of the website
(cd frontend && npm run test:map)                    # browser tests (about 4 minutes)
```

Browser tests: one admin-form test fails until the Admin page fits one screen; any other failure must
be fixed (or re-run once if it is a timing failure that then passes on its own, and say so in `update.md`).

**Also build the server image** when you changed `Dockerfile`, `deploy/`, `backend/requirements.txt`,
`frontend/package.json`, or anything the server starts with. This is the same build the server does and
catches a broken image before it reaches the site:

```
docker build -t floodpulse-check .
docker run --rm --entrypoint python floodpulse-check -c "import app.main; print('app loads')"
docker image rm floodpulse-check
```

## 4. Record, commit and push (laptop)

1. Add a short entry at the end of `update.md`: what changed, how you tested it, what is still missing.
2. Check what will be committed. Never commit `.env` files, passwords, keys, uploads or personal data:
   ```
   git status --short
   git diff --stat
   ```
3. Commit only the files of this change, then push:
   ```
   git add <the files you changed> update.md
   git commit -m "Short description of the change"
   git push origin floodpulse-v2
   ```
4. Confirm GitHub has it: both lines must show the same commit.
   ```
   git rev-parse HEAD
   git ls-remote origin refs/heads/floodpulse-v2
   ```

## 5. Merge into `main` (GitHub)

1. Open <https://github.com/Codovia/FloodThings/compare/main...floodpulse-v2>.
2. **Create pull request**, write what changed and how it was tested.
3. **Merge pull request** with **Create a merge commit** (not Squash, not Rebase).
4. Do **not** delete the `floodpulse-v2` branch.

## 6. Update the server (by hand)

Log in (Lightsail; see `AWS_HOSTING.md` for the key file):

```
ssh -i ~/Downloads/LightsailDefaultKey-ap-south-1.pem ubuntu@YOUR_STATIC_IP
```

Then, on the server:

```
cd ~/floodpulse
git status --short            # must show no "M" lines: nobody may edit code on the server
git branch --show-current     # must say: main
git log -1 --oneline          # WRITE THIS DOWN: the version to go back to if needed

cd deploy
./backup.sh                   # database backup first; note the file name it prints
git pull --ff-only            # fetch the merged code
./setup.sh                    # rebuild and restart (data is kept); takes a few minutes
```

If `git status` shows `M` lines, stop: someone changed code on the server. Do not pull over it; find out
what changed first (`git diff`).

## 7. Check the live site

On the server:

```
docker compose ps                                             # app: "Up", not "Restarting"
docker compose logs --tail 40 app                             # no "Error" or "Traceback"
curl -s https://YOUR-DOMAIN/api/health/ready                  # {"status":"ok","database":"ok"}
```

Then on your phone: open the site, allow location, open Home, Flood Map, Shelters and Report, and
check the thing you changed.

## 8. If the site is broken after an update: go back

1. Read why: `docker compose logs --tail 40 app`. A small fix on the laptop (steps 1–6) may be quicker.
2. Check whether the update changed the database (use the commit you wrote down in step 6):
   ```
   cd ~/floodpulse
   git diff --stat <previous-commit> HEAD -- backend/alembic/versions
   ```
3. **Nothing printed** (no database change): run the previous version.
   ```
   git checkout --detach <previous-commit>
   cd deploy && ./setup.sh
   docker compose ps
   ```
   **Files printed** (the database was changed): the old version cannot start on the new database, so
   restore the backup from step 6 first. This **replaces all data** with the backup, so reports or
   subscriptions made since the update are lost. The script asks you to type `RESTORE`.
   ```
   git checkout --detach <previous-commit>
   cd deploy
   ./restore.sh backups/floodpulse-YYYYMMDD-HHMMSS.dump
   ./setup.sh
   docker compose ps
   ```
4. Fix the problem on the laptop (steps 1–5). When the fix is merged, put the server back on `main`:
   ```
   cd ~/floodpulse && git checkout main
   cd deploy && ./backup.sh && git pull --ff-only && ./setup.sh
   ```

## Settings only (no code change)

To change a setting in `deploy/.env` on the server (for example a limit or a key), edit it with
`nano deploy/.env`, then run `docker compose up -d app` in `~/floodpulse/deploy`. No pull or rebuild is
needed. Never copy `deploy/.env` to GitHub, chat or screenshots.
